"""Enrich tracked accounts: web, jobs, BORME and press, confirmed signals only.

``harvey accounts enrich [--only web|jobs|borme|news]`` runs these by hand;
the heartbeat runs them on a cadence (``accounts.enrich_every_days``) through
pipeline.run_account_signals_stage, a few accounts per cycle so one cycle
never runs long. Like every collector here:

- nothing is collected unless its signal is CONFIRMED;
- observations are flushed per account, so a run that dies keeps what it read;
- a reading already on record (same signal, text and evidence) isn't written
  again, so re-running is safe and the history stays meaningful.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import aiosqlite

from harvey.collectors.spain.accounts import tracked_accounts

logger = logging.getLogger("harvey.collectors.spain.enrich")

KINDS = ("web", "jobs", "borme", "news")
BORME_CODES = {"BORME_APPOINTMENT", "BORME_CAPITAL", "BORME_MERGER"}
NEWS_CODES = {"NEWS_EXPANSION", "NEWS_ACQUISITION", "NEWS_INVESTOR", "NEWS_LEADERSHIP"}
JOBS_CODES = {"HIRING_FUNCTION"}
USER_AGENT = "Mozilla/5.0 (compatible; Harvey account research)"


@dataclass
class EnrichReport:
    accounts: int = 0
    written: dict = field(default_factory=dict)      # kind -> observations
    skipped: dict = field(default_factory=dict)      # kind -> why
    notes: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [f"{kind}: {n} dato(s) nuevo(s)" for kind, n in self.written.items()]
        lines += [f"{kind}: omitido ({why})" for kind, why in self.skipped.items()]
        return lines + self.notes


async def _existing(state, company_id: str, codes) -> set[tuple]:
    codes = list(codes)
    if not codes:
        return set()
    ph = ",".join("?" for _ in codes)
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT signal_code, value_text, evidence_url FROM observations "
            f"WHERE company_id = ? AND signal_code IN ({ph})", (company_id, *codes)) as cursor:
            return {(r["signal_code"], r["value_text"] or "", r["evidence_url"] or "")
                    for r in await cursor.fetchall()}


async def _write_new(state, rows: list[dict], run_id: str, codes, by_link: bool = False) -> int:
    """Insert the rows not already on record. ``by_link`` dedups on the
    evidence URL alone (one headline, one row, however it's worded)."""
    written = 0
    by_company: dict[str, list[dict]] = {}
    for r in rows:
        by_company.setdefault(r["company_id"], []).append(r)
    for company_id, batch in by_company.items():
        seen = await _existing(state, company_id, codes)
        links = {(c, u) for c, _, u in seen}
        fresh = []
        for r in batch:
            key = (r["signal_code"], r.get("value_text") or "", r.get("evidence_url") or "")
            if key in seen or (by_link and r.get("evidence_url") and (key[0], key[2]) in links):
                continue
            seen.add(key)
            links.add((key[0], key[2]))
            fresh.append(r)
        written += await state.add_observations(fresh, run_id=run_id)
    return written


async def _stamp(state, kind: str, company_id: str = "") -> None:
    key = f"accounts_enriched:{kind}" + (f":{company_id}" if company_id else "")
    await state.set_setting(key, datetime.now(timezone.utc).isoformat())


async def _stamped_at(state, kind: str, company_id: str = "") -> datetime | None:
    key = f"accounts_enriched:{kind}" + (f":{company_id}" if company_id else "")
    raw = await state.get_setting(key, "")
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


async def _due(state, kind: str, accounts: list[dict], stale_days: float | None,
               limit: int | None) -> list[dict]:
    if stale_days is None:
        return accounts[:limit] if limit else accounts
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stamped = [(await _stamped_at(state, kind, a["id"]), a) for a in accounts]
    due = [(t, a) for t, a in stamped if t is None or t < cutoff]
    due.sort(key=lambda ta: (ta[0] is not None, ta[0] or cutoff))
    out = [a for _, a in due]
    return out[:limit] if limit else out


def _accounts_cfg(config):
    from harvey.accounts_config import AccountsConfig
    return getattr(config, "accounts", None) or AccountsConfig()


def _open_profile_collector(state, confirmed, config):
    from harvey.collectors.ats import role_keywords
    from harvey.collectors.profile import ProfileCollector
    return ProfileCollector(state, confirmed,
                            role_keywords=role_keywords(getattr(config, "icp", None)))


def _http_client():
    from harvey.public_http import public_http_client
    return public_http_client(timeout=20.0, headers={"User-Agent": USER_AGENT})


async def enrich_accounts(state, config=None, only: str | list[str] | None = None,
                          segment: str = "", batch: str = "", stale_days: float | None = None,
                          limit: int | None = None, borme_days: int | None = None,
                          all_provinces: bool = False, http_client=None, infojobs_client=None,
                          profile_collector=None) -> EnrichReport:
    """Run the enrichment collectors for tracked accounts.

    ``only`` picks collectors (default: all four). ``stale_days``/``limit``
    pick the accounts least recently enriched, for the heartbeat. The HTTP
    clients are injectable for tests; by default each run opens its own.
    """
    from harvey.collectors.spain import borme, infojobs, jobs, news
    from harvey.signals import seed_signal_catalog

    await seed_signal_catalog(state)
    confirmed = await state.confirmed_signal_codes()
    kinds = [only] if isinstance(only, str) else list(only or KINDS)
    cfg = _accounts_cfg(config)
    report = EnrichReport()
    accounts = await tracked_accounts(state, segment=segment, batch=batch)
    report.accounts = len(accounts)
    if not accounts:
        report.notes.append("no hay cuentas: impórtalas en la pestaña Cuentas o con `harvey accounts import <file.csv>`")
        return report

    own_http = http_client is None
    http = http_client or _http_client()
    try:
        # ── web: the profile stage, forced for these accounts ──
        if "web" in kinds:
            due = await _due(state, "web", accounts, stale_days, limit)
            if not confirmed:
                report.skipped["web"] = "no hay señales confirmadas"
            elif due:
                run_id = await state.start_run("profile", provider="http", params={"accounts": len(due)})
                collector = profile_collector or _open_profile_collector(state, confirmed, config)
                if profile_collector is None:
                    async with collector:
                        n = await collector.run([{"id": a["id"], "name": a["name"], "domain": a["domain"]}
                                                 for a in due], run_id=run_id)
                else:
                    n = await collector.run([{"id": a["id"], "name": a["name"], "domain": a["domain"]}
                                             for a in due], run_id=run_id)
                await state.finish_run(run_id, records=n, cost_usd=0.0)
                for a in due:
                    await _stamp(state, "web", a["id"])
                report.written["web"] = n

        # ── jobs: watched functions on their board and on InfoJobs ──
        if "jobs" in kinds:
            if not (JOBS_CODES & confirmed):
                report.skipped["jobs"] = "HIRING_FUNCTION sin confirmar"
            else:
                creds = infojobs.credentials()
                if not creds:
                    report.notes.append("empleo: InfoJobs omitido (añade INFOJOBS_CLIENT_ID e "
                                        "INFOJOBS_CLIENT_SECRET para usarlo)")
                functions = jobs.compile_functions(cfg.watched_functions or None)
                due = await _due(state, "jobs", accounts, stale_days, limit)
                run_id = await state.start_run("jobs", provider="ats+infojobs" if creds else "ats")
                total = 0
                collector = profile_collector or _open_profile_collector(state, confirmed, config)
                try:
                    if profile_collector is None:
                        await collector.__aenter__()
                    for a in due:
                        rows = await jobs.collect_jobs(a, functions, collector, creds, infojobs_client)
                        # Open roles are a state, not events: the whole current
                        # list is written each time (as PROFILE does for
                        # HIRING_ROLE), so roles that closed stop counting.
                        total += await state.add_observations(rows, run_id=run_id)
                        await _stamp(state, "jobs", a["id"])
                finally:
                    if profile_collector is None:
                        await collector.__aexit__(None, None, None)
                await state.finish_run(run_id, records=total, cost_usd=0.0)
                report.written["jobs"] = total

        # ── BORME: recent acts in the provinces of tracked accounts ──
        if "borme" in kinds:
            wanted = BORME_CODES & confirmed
            if not wanted:
                report.skipped["borme"] = "ninguna señal BORME_* confirmada"
            elif stale_days is not None and (stamp := await _stamped_at(state, "borme")) and \
                    stamp > datetime.now(timezone.utc) - timedelta(days=stale_days):
                report.skipped["borme"] = "leído hace poco"
            else:
                run_id = await state.start_run("borme", provider="boe")
                days = borme_days or max(cfg.borme_days, int(stale_days or 0))
                result = await borme.collect_borme(accounts, http, days=days,
                                                   all_provinces=all_provinces, wanted=wanted)
                n = await _write_new(state, result.observations, run_id, BORME_CODES)
                await state.finish_run(run_id, records=n, cost_usd=0.0,
                                       **({"status": "failed", "error": "; ".join(result.errors)}
                                          if result.errors and not result.days else {}))
                await _stamp(state, "borme")
                report.written["borme"] = n
                report.notes.append(f"borme: {result.days} día(s), {result.documents} boletín(es) "
                                    f"provinciales, {result.entries} anuncios, {result.matched} de tus cuentas")
                if result.no_province:
                    report.notes.append(f"borme: {result.no_province} cuenta(s) sin provincia, "
                                        "así que su provincia no se lee (añádela en el CSV)")

        # ── press: Google News headlines ──
        if "news" in kinds:
            wanted = NEWS_CODES & confirmed
            if not wanted:
                report.skipped["news"] = "ninguna señal NEWS_* confirmada"
            else:
                due = await _due(state, "news", accounts, stale_days, limit)
                run_id = await state.start_run("news", provider="google_news_rss")
                total = 0
                for a in due:
                    rows = await news.collect_news(a, http, months=cfg.news_months,
                                                   use_brand=cfg.news_use_domain_brand, wanted=wanted)
                    if rows is None:
                        continue
                    total += await _write_new(state, rows, run_id, NEWS_CODES, by_link=True)
                    await _stamp(state, "news", a["id"])
                await state.finish_run(run_id, records=total, cost_usd=0.0)
                report.written["news"] = total
    finally:
        if own_http:
            await http.aclose()
    return report
