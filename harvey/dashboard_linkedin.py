"""Dashboard routes for LinkedIn outreach (see harvey.linkedin_queue).

Two kinds of caller, both through the dashboard guard (token or session):
- the dashboard / CLI: the queue, approve, reject, edit, plan, draft;
- the worker on the operator's PC: GET /api/linkedin/work, POST /api/linkedin/report.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from harvey import linkedin_queue as lq

logger = logging.getLogger("harvey.dashboard")

router = APIRouter()

_state_factory = None


def configure(state_factory) -> None:
    global _state_factory
    _state_factory = state_factory


async def _state():
    state = _state_factory()
    await state.init_db()
    await lq.ensure_tables(state)
    return state


def _config():
    try:
        from harvey.config import load_config
        return load_config()
    except Exception:
        return None


def _fail(message: str, status: int = 400):
    return JSONResponse({"success": False, "error": message}, status_code=status)


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _int(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


@router.get("/api/linkedin")
async def linkedin_overview(status: str = ""):
    state = await _state()
    if status and status not in lq.STATUSES:
        return _fail("estado no válido")
    return {"success": True, "items": await lq.queue(state, status), **(await lq.summary(state))}


@router.post("/api/linkedin/{item_id}/edit")
async def linkedin_edit(item_id: str, request: Request):
    body = await _body(request)
    state = await _state()
    item = await lq.get(state, item_id)
    if item is None:
        return _fail("no existe", 404)
    note = body.get("note", item["note"])
    message = body.get("message", item["message"])
    flags = lq.review(" ".join(str(note or "").split()), str(message or ""), _config())
    if not await lq.set_texts(state, item_id, note, message, flags):
        return _fail("ya no se puede editar")
    return {"success": True, "flags": flags}


@router.post("/api/linkedin/approve")
async def linkedin_approve(request: Request):
    body = await _body(request)
    state = await _state()
    ids = body.get("ids")
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
        return _fail("ids debe ser una lista")
    return {"success": True, "approved": await lq.approve(state, ids)}


@router.post("/api/linkedin/{item_id}/reject")
async def linkedin_reject(item_id: str):
    state = await _state()
    return {"success": await lq.reject(state, item_id)}


@router.post("/api/linkedin/plan")
async def linkedin_plan(request: Request):
    body = await _body(request)
    state = await _state()
    try:
        min_score = float(body.get("min_score", 70))
    except (TypeError, ValueError):
        return _fail("min_score no válido")
    created = await lq.plan(state, _config(), min_score=min_score,
                            limit=_int(body.get("limit"), 20, 1, 200))
    return {"success": True, "created": created}


@router.post("/api/linkedin/draft")
async def linkedin_draft(request: Request):
    body = await _body(request)
    config = _config()
    if config is None:
        return _fail("no hay configuración cargable", 503)
    state = await _state()
    from harvey.brain import Brain
    made = await lq.draft(state, config, Brain(state, config.brain),
                          limit=_int(body.get("limit"), 10, 1, 50))
    return {"success": True, "drafted": made}


# ── the PC worker ──

@router.get("/api/linkedin/work")
async def linkedin_work(find: int = 5, invite: int = 10, check: int = 15, message: int = 10):
    state = await _state()
    return {"success": True, **(await lq.work(
        state, max_find=_int(find, 5, 0, 20), max_invite=_int(invite, 10, 0, 30),
        max_check=_int(check, 15, 0, 50), max_message=_int(message, 10, 0, 30)))}


@router.post("/api/linkedin/report")
async def linkedin_report(request: Request):
    body = await _body(request)
    kind, item_id = str(body.get("kind") or ""), str(body.get("id") or "")
    if kind not in ("find", "invite", "check", "message") or not item_id:
        return _fail("kind e id son obligatorios")
    people = body.get("people") or []
    if not isinstance(people, list) or not all(isinstance(p, dict) for p in people):
        return _fail("people debe ser una lista de objetos")
    state = await _state()
    result = await lq.report(state, kind, item_id, ok=bool(body.get("ok", True)),
                             error=str(body.get("error") or ""), people=people,
                             connected=bool(body.get("connected")))
    return {"success": True, **result}
