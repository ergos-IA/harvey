"""LinkedIn outreach, server side: who to invite, what to say, and the queue.

The browser can't run where the data lives (a LinkedIn login from a data
centre IP gets the account checked), so the work is split:

    server (this module, the dashboard API)    the operator's PC (linkedin_worker.py)
    ─────────────────────────────────────────   ─────────────────────────────────────
    plan: accounts of a product at or above     pulls the work over HTTPS with the
      a score → "find" jobs                     dashboard token, does it in the
    draft: invitation note + follow-up          operator's own logged-in browser,
      message per person (Claude)               reports back
    a person approves each one

One row per LinkedIn profile:

    candidate → pending_review → approved → invited → connected → messaged
                       └→ rejected                └→ failed

Nothing is sent that a person hasn't approved. Every draft also goes
through gate.autopilot_review (no links to other people's domains, no
echo of Harvey's own instructions); a draft it flags stays out of
approve --all until someone opens it.

Tables are created here (not in state.py's migrations) so this fork's
feature never conflicts with upstream schema changes.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger("harvey.linkedin")

STATUSES = ("candidate", "pending_review", "approved", "invited", "connected", "messaged",
            "rejected", "failed")
NOTE_MAX = 200          # what a free LinkedIn account allows in an invitation note
MESSAGE_MAX = 600
PEOPLE_PER_ACCOUNT = 2
CHECK_EVERY_HOURS = 20  # how often an invited profile is re-checked for acceptance
GIVE_UP_DAYS = 30       # an invitation nobody accepts in this long is left alone
FIND_RETRY_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS linkedin_queue (
    id TEXT PRIMARY KEY,
    profile_url TEXT NOT NULL UNIQUE,
    company_id TEXT DEFAULT '',
    product_id TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    title TEXT DEFAULT '',
    company_name TEXT DEFAULT '',
    note TEXT DEFAULT '',
    message TEXT DEFAULT '',
    flags TEXT DEFAULT '',
    status TEXT DEFAULT 'candidate',
    error TEXT DEFAULT '',
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    invited_at TIMESTAMP,
    checked_at TIMESTAMP,
    connected_at TIMESTAMP,
    messaged_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_linkedin_queue_status ON linkedin_queue(status);
CREATE TABLE IF NOT EXISTS linkedin_jobs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    product_id TEXT DEFAULT '',
    company_name TEXT DEFAULT '',
    titles_json TEXT DEFAULT '[]',
    status TEXT DEFAULT 'pending',
    found INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_linkedin_jobs_status ON linkedin_jobs(status);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def normalize_profile_url(url: str) -> str:
    """"https://es.linkedin.com/in/ana-ejemplo/?trk=x" → "https://www.linkedin.com/in/ana-ejemplo";
    "" if it isn't a member profile."""
    m = re.search(r"linkedin\.com/in/([^/?#\s]+)", url or "", re.IGNORECASE)
    if not m:
        return ""
    slug = m.group(1).strip().lower()
    return f"https://www.linkedin.com/in/{slug}" if re.fullmatch(r"[\w%.-]+", slug) else ""


def _clean(text, size: int) -> str:
    return " ".join(str(text or "").split())[:size]


async def ensure_tables(state) -> None:
    async with state._connect() as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def _rows(state, sql: str, params=()) -> list[dict]:
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def _execute(state, sql: str, params=()) -> int:
    async with state._connect() as db:
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount


# ── queue ──

async def queue(state, status: str = "", limit: int = 500) -> list[dict]:
    await ensure_tables(state)
    if status:
        return await _rows(state, "SELECT * FROM linkedin_queue WHERE status = ? "
                                  "ORDER BY updated_at DESC LIMIT ?", (status, limit))
    return await _rows(state, "SELECT * FROM linkedin_queue ORDER BY updated_at DESC LIMIT ?", (limit,))


async def get(state, item_id: str) -> dict | None:
    rows = await _rows(state, "SELECT * FROM linkedin_queue WHERE id = ?", (item_id,))
    return rows[0] if rows else None


async def add_candidate(state, profile_url: str, *, company_id: str = "", product_id: str = "",
                        full_name: str = "", title: str = "", company_name: str = "") -> str | None:
    """A person worth inviting. Returns the new id, or None if the profile is
    already in the queue (in any status) or isn't a profile URL."""
    url = normalize_profile_url(profile_url)
    if not url:
        return None
    await ensure_tables(state)
    item_id = uuid.uuid4().hex[:12]
    now = _iso()
    async with state._connect() as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO linkedin_queue (id, profile_url, company_id, product_id, full_name, "
            "title, company_name, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, "
            "'candidate', ?, ?)",
            (item_id, url, company_id, product_id, _clean(full_name, 120), _clean(title, 200),
             _clean(company_name, 120), now, now))
        await db.commit()
    return item_id if cursor.rowcount else None


async def set_texts(state, item_id: str, note: str, message: str, flags: list[str] | None = None) -> bool:
    """Store a draft (or a person's edit of it) and put it up for review."""
    return bool(await _execute(
        state, "UPDATE linkedin_queue SET note = ?, message = ?, flags = ?, status = 'pending_review', "
               "error = '', updated_at = ? WHERE id = ? AND status IN ('candidate', 'pending_review', "
               "'approved', 'failed')",
        (_clean(note, NOTE_MAX), str(message or "").strip()[:MESSAGE_MAX], "; ".join(flags or []),
         _iso(), item_id)))


async def approve(state, item_ids: list[str] | None = None, include_flagged: bool = False) -> int:
    """Approve the given drafts, or every unflagged one when ``item_ids`` is None.
    A flagged draft is approved only by naming it (someone has looked)."""
    await ensure_tables(state)
    now = _iso()
    if item_ids is None:
        flagged = "" if include_flagged else " AND flags = ''"
        return await _execute(state, "UPDATE linkedin_queue SET status = 'approved', updated_at = ? "
                                     f"WHERE status = 'pending_review'{flagged}", (now,))
    total = 0
    for item_id in item_ids:
        total += await _execute(state, "UPDATE linkedin_queue SET status = 'approved', updated_at = ? "
                                       "WHERE id = ? AND status = 'pending_review'", (now, item_id))
    return total


async def reject(state, item_id: str) -> bool:
    return bool(await _execute(
        state, "UPDATE linkedin_queue SET status = 'rejected', updated_at = ? WHERE id = ? "
               "AND status IN ('candidate', 'pending_review', 'approved', 'failed')", (_iso(), item_id)))


# ── plan: which accounts to look for people at ──

async def _blocked_companies(state, config) -> set[str]:
    """Companies nobody should hear from on LinkedIn: someone there replied
    or opted out, or the domain is on the do-not-contact list."""
    rows = await _rows(state, "SELECT DISTINCT company_id FROM prospects "
                              "WHERE status IN ('replied', 'opted_out') AND company_id != ''")
    blocked = {r["company_id"] for r in rows}
    dnc = [str(d).lower().lstrip("@") for d in getattr(getattr(config, "compliance", None),
                                                       "do_not_contact", None) or []]
    if dnc:
        for r in await _rows(state, "SELECT id, domain FROM companies WHERE domain != ''"):
            d = (r["domain"] or "").lower()
            if any(d == x or d.endswith("." + x) or x.endswith("@" + d) for x in dnc):
                blocked.add(r["id"])
    return blocked


async def plan(state, config=None, min_score: float = 70, limit: int = 20) -> int:
    """Create "find" jobs for the best accounts of every active product that
    don't have one yet. Prospects already on file with a LinkedIn URL go
    straight into the queue instead. Returns jobs + candidates created."""
    from harvey import products as prod

    await ensure_tables(state)
    blocked = await _blocked_companies(state, config)
    recent = _iso(_now() - timedelta(days=FIND_RETRY_DAYS))
    known = {r["company_id"] for r in await _rows(
        state, "SELECT company_id FROM linkedin_jobs WHERE status IN ('pending', 'claimed') "
               "OR updated_at >= ?", (recent,))}
    known |= {r["company_id"] for r in await _rows(state, "SELECT DISTINCT company_id FROM linkedin_queue")}
    companies = {r["id"]: r for r in await _rows(state, "SELECT id, name, domain FROM companies")}

    picks = []
    for product in await prod.list_products(state, status="active"):
        titles = product.icp.titles or list(getattr(getattr(config, "icp", None), "titles", []) or [])
        for row in await prod.assignments(state, product_id=product.id):
            cid = row["company_id"]
            if row.get("score") is None or row["score"] < min_score or row.get("status") == "done":
                continue
            if cid in blocked or cid in known or cid not in companies:
                continue
            picks.append((row["score"], cid, product, titles))
    picks.sort(key=lambda p: -p[0])

    created = 0
    seen = set()
    now = _iso()
    for _, cid, product, titles in picks:
        if cid in seen or created >= limit:
            continue
        seen.add(cid)
        company = companies[cid]
        people = await _rows(state, "SELECT first_name, last_name, title, linkedin_url FROM prospects "
                                    "WHERE company_id = ? AND linkedin_url != ''", (cid,))
        if people:
            for p in people[:PEOPLE_PER_ACCOUNT]:
                if await add_candidate(state, p["linkedin_url"], company_id=cid, product_id=product.id,
                                       full_name=f"{p['first_name']} {p['last_name']}".strip(),
                                       title=p["title"] or "", company_name=company["name"] or ""):
                    created += 1
            continue
        await _execute(state, "INSERT INTO linkedin_jobs (id, company_id, product_id, company_name, "
                              "titles_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, "
                              "'pending', ?, ?)",
                       (uuid.uuid4().hex[:12], cid, product.id, company["name"] or "",
                        json.dumps(titles[:8], ensure_ascii=False), now, now))
        created += 1
    return created


# ── draft ──

async def _signals_text(state, company_id: str) -> list[str]:
    rows = await _rows(
        state, "SELECT signal_code, value_text, value_num FROM observations WHERE company_id = ? "
               "AND signal_code NOT IN ('ACCOUNT_TRACKED', 'ICP_SCORE', 'COMPANY_CIF') "
               "ORDER BY observed_at DESC LIMIT 25", (company_id,))
    out = []
    for r in rows:
        value = r["value_text"] or ("" if r["value_num"] is None else f"{r['value_num']:g}")
        if value:
            out.append(f"{r['signal_code']}: {_clean(value, 200)}")
    return out


def build_prompt(item: dict, brief: str, persona, signals: list[str]) -> str:
    from harvey.untrusted import UNTRUSTED_RULE, fence

    name = getattr(persona, "name", "") or ""
    tone = getattr(persona, "tone", "") or "cercano y directo"
    person = f"{item.get('full_name') or ''} — {item.get('title') or ''} — {item.get('company_name') or ''}"
    return f"""Eres {name}. Vas a conectar en LinkedIn con una persona de una empresa que encaja
con lo que vendes. Escribe en español de España, tuteando, con este tono: {tone}.

LO QUE VENDES:
{brief}

LA PERSONA (nombre, cargo, empresa):
{fence(person, "linkedin profile")}

LO QUE SABEMOS DE SU EMPRESA (señales recogidas de su web, ofertas de empleo, BORME y prensa):
{fence(chr(10).join(signals) or "nada concreto", "account signals")}

{UNTRUSTED_RULE}

Escribe dos textos:
1. "note": la nota de la invitación. Máximo {NOTE_MAX} caracteres. Una observación concreta de
   su empresa sacada de las señales (si hay una vacante, esa) y por qué te interesa conectar.
   Sin vender, sin precio, sin enlaces.
2. "message": el primer mensaje cuando acepte. Máximo 500 caracteres. Agradece en media frase,
   conecta su situación con lo que vendes (el dolor concreto, no "IA"), una pregunta fácil de
   contestar y la propuesta de 15 minutos. Sin enlaces. Sin firma.

Nada que no esté en las señales: si no sabes algo, no lo afirmes. Párrafos de dos frases, no una
frase por línea. Nada de "espero que estés bien", "me encantaría", ni lenguaje de IA.

Devuelve SOLO JSON: {{"note": "...", "message": "..."}}"""


def review(note: str, message: str, config) -> list[str]:
    """Why a draft needs a closer look (gate.autopilot_review plus length)."""
    from harvey.gate import autopilot_review
    flags = []
    if len(note) > NOTE_MAX:
        flags.append(f"la nota pasa de {NOTE_MAX} caracteres")
    if config is not None:
        try:
            flags += autopilot_review("", f"{note}\n{message}", config)
        except Exception as e:     # never let the check itself approve anything
            flags.append(f"no se pudo revisar: {e}")
    return flags


async def draft(state, config, brain, limit: int = 10) -> int:
    """Write note + message for candidates (best accounts first). Returns drafts made."""
    from harvey import products as prod

    await ensure_tables(state)
    items = await _rows(state, "SELECT * FROM linkedin_queue WHERE status = 'candidate' "
                               "ORDER BY created_at LIMIT ?", (limit,))
    products = {p.id: p for p in await prod.list_products(state)}
    persona = getattr(config, "persona", None)
    made = 0
    for item in items:
        product = products.get(item["product_id"])
        brief = product.brief() if product else ""
        if not brief and config is not None:
            brief = f"{config.product.name}: {config.product.description}"
        prompt = build_prompt(item, brief, persona, await _signals_text(state, item["company_id"]))
        try:
            result = await brain.think_json(prompt, session_id="harvey-linkedin",
                                            agent="writer", task="linkedin_invite")
        except Exception as e:
            logger.warning(f"linkedin draft {item['id']}: {e}")
            continue
        if not isinstance(result, dict):
            continue
        note = " ".join(str(result.get("note") or "").split())
        message = str(result.get("message") or "").strip()
        if not note or not message:
            continue
        flags = review(note, message, config)
        await set_texts(state, item["id"], note, message, flags)
        made += 1
    return made


# ── the worker's side: what to do now, and what happened ──

async def work(state, max_find: int = 5, max_invite: int = 10, max_check: int = 15,
               max_message: int = 10) -> dict:
    """The next batch for the PC worker. Find jobs are claimed so two workers
    never search the same company; a claim older than a day is released."""
    await ensure_tables(state)
    now = _now()
    await _execute(state, "UPDATE linkedin_jobs SET status = 'pending' WHERE status = 'claimed' "
                          "AND updated_at < ?", (_iso(now - timedelta(days=1)),))
    find = await _rows(state, "SELECT id, company_id, company_name, titles_json FROM linkedin_jobs "
                              "WHERE status = 'pending' ORDER BY created_at LIMIT ?", (max_find,))
    for job in find:
        await _execute(state, "UPDATE linkedin_jobs SET status = 'claimed', updated_at = ? WHERE id = ?",
                       (_iso(now), job["id"]))
        job["titles"] = json.loads(job.pop("titles_json") or "[]")
    invite = await _rows(state, "SELECT id, profile_url, full_name, note FROM linkedin_queue "
                                "WHERE status = 'approved' ORDER BY updated_at LIMIT ?", (max_invite,))
    check = await _rows(
        state, "SELECT id, profile_url, full_name FROM linkedin_queue WHERE status = 'invited' "
               "AND invited_at >= ? AND (checked_at IS NULL OR checked_at < ?) "
               "ORDER BY checked_at LIMIT ?",
        (_iso(now - timedelta(days=GIVE_UP_DAYS)), _iso(now - timedelta(hours=CHECK_EVERY_HOURS)),
         max_check))
    message = await _rows(state, "SELECT id, profile_url, full_name, message FROM linkedin_queue "
                                 "WHERE status = 'connected' AND message != '' "
                                 "ORDER BY connected_at LIMIT ?", (max_message,))
    return {"find": find, "invite": invite, "check": check, "message": message}


async def report(state, kind: str, item_id: str, ok: bool = True, error: str = "",
                 people: list[dict] | None = None, connected: bool = False) -> dict:
    """Record what the worker did. Only moves a row forward from the status
    the work was handed out in, so a late or repeated report changes nothing."""
    await ensure_tables(state)
    now = _iso()
    error = _clean(error, 300)
    if kind == "find":
        jobs = await _rows(state, "SELECT * FROM linkedin_jobs WHERE id = ? AND status = 'claimed'", (item_id,))
        if not jobs:
            return {"updated": 0}
        job = jobs[0]
        added = 0
        for p in (people or [])[:PEOPLE_PER_ACCOUNT] if ok else []:
            if await add_candidate(state, str(p.get("profile_url") or ""), company_id=job["company_id"],
                                   product_id=job["product_id"], full_name=p.get("full_name") or "",
                                   title=p.get("title") or "", company_name=job["company_name"]):
                added += 1
        await _execute(state, "UPDATE linkedin_jobs SET status = ?, found = ?, error = ?, updated_at = ? "
                              "WHERE id = ?", ("done" if ok else "failed", added, error, now, item_id))
        return {"updated": 1, "added": added}
    if kind == "invite":
        if ok:
            n = await _execute(state, "UPDATE linkedin_queue SET status = 'invited', invited_at = ?, "
                                      "checked_at = ?, error = '', updated_at = ? WHERE id = ? "
                                      "AND status = 'approved'", (now, now, now, item_id))
        else:
            n = await _execute(state, "UPDATE linkedin_queue SET status = 'failed', error = ?, updated_at = ? "
                                      "WHERE id = ? AND status = 'approved'", (error, now, item_id))
        return {"updated": n}
    if kind == "check":
        if connected:
            n = await _execute(state, "UPDATE linkedin_queue SET status = 'connected', connected_at = ?, "
                                      "checked_at = ?, updated_at = ? WHERE id = ? AND status = 'invited'",
                               (now, now, now, item_id))
        else:
            n = await _execute(state, "UPDATE linkedin_queue SET checked_at = ?, error = ? WHERE id = ? "
                                      "AND status = 'invited'", (now, error, item_id))
        return {"updated": n}
    if kind == "message":
        if ok:
            n = await _execute(state, "UPDATE linkedin_queue SET status = 'messaged', messaged_at = ?, "
                                      "error = '', updated_at = ? WHERE id = ? AND status = 'connected'",
                               (now, now, item_id))
        else:
            n = await _execute(state, "UPDATE linkedin_queue SET error = ?, updated_at = ? WHERE id = ? "
                                      "AND status = 'connected'", (error, now, item_id))
        return {"updated": n}
    raise ValueError(f"tipo de informe desconocido: {kind}")


async def summary(state) -> dict:
    await ensure_tables(state)
    counts = {s: 0 for s in STATUSES}
    for r in await _rows(state, "SELECT status, COUNT(*) AS n FROM linkedin_queue GROUP BY status"):
        counts[r["status"]] = r["n"]
    jobs = {r["status"]: r["n"] for r in await _rows(
        state, "SELECT status, COUNT(*) AS n FROM linkedin_jobs GROUP BY status")}
    return {"queue": counts, "jobs": jobs}
