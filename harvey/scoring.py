"""ICP scoring: rules from harvey.yaml, evaluated over an account's signals.

Explainable by construction. A score is the sum of the rules that fired, and
the stored observation (ICP_SCORE) lists every one of them ("+25
HIRING_FUNCTION older_than_days=60"), so "why is this account a 72?" always
has an answer a person can check against the signals themselves.

What a rule reads is the company's CURRENT reading of its signal: the newest
batch of rows (one run, or one moment when rows carry no run), keeping only
positive ones (a 0 for a boolean means "checked, not present"). Events (BORME
acts, headlines) are the exception: every one on record counts. A rule fires
at most once, if any of those rows satisfies all its conditions.

Ages ("posted > 60 days ago", "in the last 6 months") are measured from the
event's own date when the row carries one (the first YYYY-MM-DD in its text:
a posting date, a BORME publication date, a headline's date), else from when
Harvey observed it.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiosqlite

from harvey.accounts_config import ScoringConfig, ScoringRule

_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def event_date(row: dict) -> datetime | None:
    m = _DATE_RE.search(row.get("value_text") or "")
    if m:
        parsed = _parse_ts(m.group(1))
        if parsed:
            return parsed
    return _parse_ts(row.get("observed_at"))


def _positive(row: dict) -> bool:
    return row.get("value_num") is None or row.get("value_num") != 0


def current_rows(rows: list[dict]) -> list[dict]:
    """The newest batch of one signal's rows for one company, positive only.
    ``rows`` are newest first (as state.get_observations returns them)."""
    if not rows:
        return []
    newest = rows[0]
    if newest.get("run_id"):
        batch = [r for r in rows if r.get("run_id") == newest["run_id"]]
    else:
        batch = [r for r in rows if r.get("observed_at") == newest.get("observed_at")]
    return [r for r in batch if _positive(r)]


def _num_ok(row: dict, when: dict) -> bool:
    lo, hi = when.get("min"), when.get("max")
    if "between" in when:
        lo, hi = when["between"]
    if lo is None and hi is None:
        return True
    num = row.get("value_num")
    if num is None:
        return False
    return (lo is None or num >= float(lo)) and (hi is None or num <= float(hi))


def _age_ok(row: dict, when: dict, now: datetime) -> bool:
    keys = ("older_than_days", "within_days", "within_months")
    if not any(k in when for k in keys):
        return True
    when_dt = event_date(row)
    if when_dt is None:
        return False
    age = (now - when_dt).total_seconds() / 86400
    if "older_than_days" in when and age < float(when["older_than_days"]):
        return False
    if "within_days" in when and age > float(when["within_days"]):
        return False
    if "within_months" in when and age > float(when["within_months"]) * 30:
        return False
    return True


def _text_ok(row: dict, when: dict) -> bool:
    text = _fold(row.get("value_text") or "")
    anyof = [_fold(t) for t in when.get("contains_any") or [] if str(t).strip()]
    noneof = [_fold(t) for t in when.get("contains_none") or [] if str(t).strip()]
    if anyof and not any(t in text for t in anyof):
        return False
    return not any(t in text for t in noneof)


def row_matches(row: dict, when: dict, now: datetime) -> bool:
    if "min_confidence" in when and float(row.get("confidence") or 0) < float(when["min_confidence"]):
        return False
    return _num_ok(row, when) and _age_ok(row, when, now) and _text_ok(row, when)


def describe(rule: ScoringRule) -> str:
    if rule.label:
        return rule.label
    conds = " ".join(f"{k}={v}" for k, v in (rule.when or {}).items())
    return f"{rule.signal} {conds}".strip()


# Events (an act in the BORME, a headline) don't replace each other: every
# one on record counts, and age conditions say which are recent enough.
EVENT_SIGNALS = frozenset({"BORME_APPOINTMENT", "BORME_CAPITAL", "BORME_MERGER", "NEWS_EXPANSION",
                           "NEWS_ACQUISITION", "NEWS_INVESTOR", "NEWS_LEADERSHIP"})


def rule_fires(rule: ScoringRule, rows: list[dict], now: datetime) -> bool:
    when = rule.when or {}
    current = ([r for r in rows if _positive(r)] if rule.signal in EVENT_SIGNALS
               else current_rows(rows))
    if when.get("exists") is False:
        return not current
    return any(row_matches(r, when, now) for r in current)


@dataclass
class Score:
    company_id: str
    segment: str
    score: float
    fired: list[tuple[float, str]] = field(default_factory=list)

    def explanation(self) -> str:
        parts = [f"{'+' if p >= 0 else ''}{p:g} {d}" for p, d in self.fired]
        head = f"[{self.segment}] " if self.segment else ""
        return (head + "; ".join(parts))[:900] if parts else head + "ninguna regla suma"


def rules_for(config: ScoringConfig, segment: str) -> list[ScoringRule]:
    rules = list(config.rules)
    seg = (segment or "").strip().lower()
    for name, block in config.segments.items():
        if name.strip().lower() == seg:
            rules += block.rules
    return rules


async def _signal_rows(state, company_id: str, codes: set[str]) -> dict[str, list[dict]]:
    if not codes:
        return {}
    ph = ",".join("?" for _ in codes)
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT * FROM observations WHERE company_id = ? AND signal_code IN ({ph}) "
            "ORDER BY observed_at DESC, rowid DESC", (company_id, *codes),
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["signal_code"], []).append(r)
    return out


async def score_company(state, config: ScoringConfig, company_id: str, segment: str = "",
                        now: datetime | None = None) -> Score:
    now = now or datetime.now(timezone.utc)
    rules = rules_for(config, segment)
    rows = await _signal_rows(state, company_id, {r.signal for r in rules})
    score = Score(company_id=company_id, segment=segment, score=0.0)
    for rule in rules:
        if rule_fires(rule, rows.get(rule.signal, []), now):
            score.score += rule.points
            score.fired.append((rule.points, describe(rule)))
    return score


async def score_accounts(state, config: ScoringConfig, accounts: list[dict], store: bool = True,
                         now: datetime | None = None) -> list[tuple[dict, Score]]:
    """Score every account; store ICP_SCORE unless the user rejected that
    signal. Returns [(account, score)] best first."""
    from harvey.signals import seed_signal_catalog

    results = []
    for account in accounts:
        results.append((account, await score_company(
            state, config, account["id"], account.get("segment") or "", now=now)))
    results.sort(key=lambda pair: (-pair[1].score, (pair[0].get("name") or "").lower()))
    if store and results:
        await seed_signal_catalog(state)
        rejected = {c["code"] for c in await state.get_signal_codes(status="rejected")}
        if "ICP_SCORE" not in rejected:
            run_id = await state.start_run("scoring", provider="rules")
            rows = [{"signal_code": "ICP_SCORE", "company_id": a["id"], "collector": "scoring",
                     "value_num": s.score, "value_text": s.explanation(), "confidence": 1.0,
                     "evidence_url": ""} for a, s in results]
            n = await state.add_observations(rows, run_id=run_id)
            await state.finish_run(run_id, records=n, cost_usd=0.0)
    return results
