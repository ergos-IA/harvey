"""Dashboard routes for the Proceso tab: every product's process, phase by
phase, and the gates you open or close (see harvey.process)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from harvey import process
from harvey import products as prod

logger = logging.getLogger("harvey.dashboard")

router = APIRouter()


def _fail(message: str, status: int = 400):
    return JSONResponse({"success": False, "message": message}, status_code=status)


async def _ready_state():
    from harvey.dashboard_products import ready_state
    return await ready_state()


async def _system(state) -> dict:
    """What the phases need from outside the product: signals, mailbox,
    verifier, the sending switch."""
    from harvey import dashboard, dashboard_accounts

    out = {"confirmed_signals": 0, "verifier_ok": False, "provider_ok": False,
           "provider": "", "sending_paused": False, "approval": True,
           "enrich_running": bool(dashboard_accounts._enrich_task
                                  and not dashboard_accounts._enrich_task.done())}
    try:
        out["confirmed_signals"] = sum(1 for s in await state.get_signal_codes()
                                       if s.get("status") == "confirmed")
        out["sending_paused"] = bool(await state.get_setting("sending_paused"))
    except Exception as e:
        logger.debug(f"process: signals/sending: {e}")
    try:
        checks = {c["id"]: c for c in (await dashboard.get_setup_status())["checks"]}
        out["verifier_ok"] = bool(checks.get("verifier", {}).get("done"))
        out["provider_ok"] = bool(checks.get("email_provider", {}).get("done"))
        out["provider"] = dashboard._current_provider()
    except Exception as e:
        logger.debug(f"process: setup status: {e}")
    try:
        from harvey.config import load_config
        out["approval"] = bool(load_config().channels.email.require_approval)
    except Exception:
        pass
    return out


@router.get("/api/process")
async def get_process(product: str = ""):
    from harvey.collectors.spain.accounts import tracked_accounts
    try:
        state = await _ready_state()
        products = await prod.list_products(state)
        accounts = {a["id"]: a for a in await tracked_accounts(state)}
        system = await _system(state)
        facts = await process._facts(state)
        overview, chosen = [], None
        for p in products:
            view = await process.product_process(state, p, accounts, system, facts)
            overview.append({
                "id": p.id, "name": p.name, "status": p.status,
                "reached": [c["reached"] for c in view["phases"]],
                "you": sum(c["here"]["you"] for c in view["phases"]),
                "blocked": sum(c["here"]["blocked"] for c in view["phases"]),
                "accounts": len(view["accounts"]),
            })
            if p.id == product or (chosen is None and not product):
                chosen = (p, view)
        if chosen is None and products:
            chosen = (products[0], await process.product_process(
                state, products[0], accounts, system, facts))
        body = {"products": overview, "system": system,
                "phases": [{"key": k, "label": label} for k, label in process.PHASES]}
        if chosen:
            p, view = chosen
            body.update(product={"id": p.id, "name": p.name, "status": p.status,
                                 "gates": p.gates.model_dump(),
                                 "threshold": p.scoring.threshold,
                                 "scoring_configured": p.scoring.configured()},
                        cards=view["phases"], accounts=view["accounts"])
        return body
    except Exception as e:
        logger.exception("process view failed")
        return _fail(str(e), 500)


async def _body(request: Request) -> dict | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


@router.post("/api/process/{product_id}/decision")
async def decide(product_id: str, request: Request):
    """{company_ids: [...], phase: contacts|write, decision: go|stop|""}."""
    body = await _body(request)
    if body is None:
        return _fail("cuerpo no válido")
    ids = [str(c) for c in body.get("company_ids") or [] if c]
    if not ids:
        return _fail("elige al menos una cuenta")
    try:
        state = await _ready_state()
        if await prod.get_product(state, product_id) is None:
            return _fail("ese producto no existe", 404)
        n = await prod.set_decision(state, product_id, ids, str(body.get("phase") or ""),
                                    str(body.get("decision") or ""))
        return {"success": True, "updated": n}
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        logger.exception("process decision failed")
        return _fail(str(e), 500)


@router.post("/api/process/{product_id}/gates")
async def set_gates(product_id: str, request: Request):
    """{contacts: auto|manual|all, write: auto|manual}: how accounts move on."""
    body = await _body(request)
    if body is None:
        return _fail("cuerpo no válido")
    try:
        state = await _ready_state()
        product = await prod.get_product(state, product_id)
        if product is None:
            return _fail("ese producto no existe", 404)
        try:
            product.gates = prod.ProductGates(**{**product.gates.model_dump(),
                                                 **{k: v for k, v in body.items()
                                                    if k in ("contacts", "write")}})
        except ValidationError as e:
            msg = e.errors()[0].get("msg", "modo no válido") if e.errors() else "modo no válido"
            return _fail(str(msg).replace("Value error, ", ""))
        await prod.save_product(state, product)
        return {"success": True, "gates": product.gates.model_dump()}
    except Exception as e:
        logger.exception("process gates failed")
        return _fail(str(e), 500)
