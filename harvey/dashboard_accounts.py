"""Dashboard routes for account-based selling: the Cuentas tab.

The CLI (``harvey accounts import|enrich|score``) needs a terminal on the
machine running Harvey; on a hosted install there is none. These routes do
the same from the browser: upload the CSV, enrich, score, and list the
accounts with their score and contacts.
"""

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("harvey.dashboard")

router = APIRouter()

MAX_CSV_BYTES = 2 * 1024 * 1024
SEGMENTS = ("industrial", "distribucion", "retail")

# Set by dashboard.py: the StateManager factory and the database path.
_state_factory = None
_db_path = None          # callable: the database path (tests patch it)

_enrich_task: asyncio.Task | None = None
_enrich_report: dict | None = None


def configure(state_factory, db_path) -> None:
    global _state_factory, _db_path
    _state_factory, _db_path = state_factory, db_path


def _config():
    try:
        from harvey.config import load_config
        return load_config()
    except Exception:
        return None


def _scoring(config):
    from harvey.accounts_config import ScoringConfig
    return getattr(config, "scoring", None) or ScoringConfig()


async def _ready_state():
    state = _state_factory()
    await state.init_db()
    return state


def _fail(message: str, status: int = 400):
    return JSONResponse({"success": False, "message": message}, status_code=status)


@router.get("/api/accounts")
async def list_accounts():
    from harvey.collectors.spain.accounts import tracked_accounts

    try:
        state = await _ready_state()
        accounts = await tracked_accounts(state)
        config = _config()
        scoring = _scoring(config)
        async with state._connect() as db:
            async with db.execute(
                "SELECT company_id, COUNT(*) FROM prospects GROUP BY company_id"
            ) as cursor:
                contacts = {row[0]: row[1] for row in await cursor.fetchall()}
        rows = []
        for a in accounts:
            latest = await state.get_observations(company_id=a["id"], signal_code="ICP_SCORE",
                                                  latest_only=True, limit=1)
            score = latest[0].get("value_num") if latest else None
            rows.append({
                "id": a["id"], "name": a.get("name") or "", "domain": a.get("domain") or "",
                "segment": a.get("segment") or "", "batch": a.get("batch") or "",
                "province": a.get("province") or "", "employees": a.get("employees"),
                "score": score, "why": (latest[0].get("value_text") or "") if latest else "",
                "contacts": contacts.get(a["id"], 0),
            })
        rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["name"].lower()))
        accounts_cfg = getattr(config, "accounts", None)
        return {
            "accounts": rows,
            "threshold": scoring.threshold,
            "scoring_configured": scoring.configured(),
            "abm_only": bool(getattr(accounts_cfg, "abm_only", False)),
            "segments": list(SEGMENTS),
            "enrich": {"running": bool(_enrich_task and not _enrich_task.done()),
                       "report": _enrich_report},
        }
    except Exception as e:
        logger.exception("accounts list failed")
        return _fail(str(e), 500)


@router.post("/api/accounts/import")
async def import_accounts_csv(request: Request):
    from harvey.collectors.spain.accounts import import_accounts

    try:
        body = await request.json()
    except Exception:
        return _fail("cuerpo no válido")
    text = body.get("csv") or ""
    if not isinstance(text, str) or not text.strip():
        return _fail("el archivo está vacío")
    data = text.encode("utf-8")
    if len(data) > MAX_CSV_BYTES:
        return _fail("el archivo supera 2 MB")
    stem = re.sub(r"[^\w.-]+", "-", Path(str(body.get("filename") or "cuentas")).stem).strip("-.")
    stem = (stem or "cuentas")[:60]
    batch = str(body.get("batch") or "").strip()[:60]
    segment = str(body.get("segment") or "").strip().lower()
    if segment and segment not in SEGMENTS:
        return _fail(f"segmento no válido: {segment}")
    dry_run = bool(body.get("dry_run"))
    try:
        folder = Path(_db_path()).parent / "imports"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stem}.csv"
        path.write_bytes(data)
        state = await _ready_state()
        report = await import_accounts(state, path, batch=batch, segment=segment, dry_run=dry_run)
        scored = 0
        if not dry_run and report.company_ids:
            scored = await _score_all(state)
        return {"success": True, "dry_run": dry_run, "batch": report.batch,
                "created": report.created, "updated": report.updated,
                "observations": report.observations, "skipped": report.skipped[:50],
                "skipped_total": len(report.skipped), "scored": scored}
    except Exception as e:
        logger.exception("accounts import failed")
        return _fail(str(e), 500)


async def _score_all(state) -> int:
    from harvey.collectors.spain.accounts import tracked_accounts
    from harvey.scoring import score_accounts

    scoring = _scoring(_config())
    if not scoring.configured():
        return 0
    accounts = await tracked_accounts(state)
    return len(await score_accounts(state, scoring, accounts))


@router.post("/api/accounts/score")
async def score_accounts_now():
    try:
        state = await _ready_state()
        scoring = _scoring(_config())
        if not scoring.configured():
            return _fail("no hay reglas de puntuación (sección scoring: de la configuración)")
        return {"success": True, "scored": await _score_all(state)}
    except Exception as e:
        logger.exception("accounts score failed")
        return _fail(str(e), 500)


@router.post("/api/accounts/enrich")
async def enrich_accounts_now():
    """Web, empleo, BORME y prensa for every tracked account, then re-score.
    Runs in the background; GET /api/accounts reports when it's done."""
    global _enrich_task, _enrich_report
    if _enrich_task and not _enrich_task.done():
        return _fail("ya hay un enriquecimiento en curso", 409)

    async def _go():
        global _enrich_report
        from harvey.collectors.spain.enrich import enrich_accounts
        try:
            state = await _ready_state()
            report = await enrich_accounts(state, _config())
            scored = await _score_all(state)
            _enrich_report = {"ok": True, "accounts": report.accounts,
                              "lines": report.summary_lines(), "scored": scored}
        except Exception as exc:
            logger.exception("accounts enrich failed")
            _enrich_report = {"ok": False, "lines": [str(exc)]}

    _enrich_report = None
    _enrich_task = asyncio.create_task(_go())
    return {"success": True}
