"""Dashboard routes for the Productos tab: what you sell, each with its ICP,
its scoring rules and the accounts it targets (see harvey.products)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from harvey import products as prod

logger = logging.getLogger("harvey.dashboard")

router = APIRouter()

_state_factory = None


def configure(state_factory) -> None:
    global _state_factory
    _state_factory = state_factory


def _config():
    try:
        from harvey.config import load_config
        return load_config()
    except Exception:
        return None


async def ready_state():
    """The state, migrated, with the configured product turned into the
    first one (once). Shared with the Cuentas routes."""
    state = _state_factory()
    await state.init_db()
    try:
        await prod.ensure_default_product(state, _config())
    except Exception as e:
        logger.warning(f"products: could not create the first product: {e}")
    return state


def _fail(message: str, status: int = 400):
    return JSONResponse({"success": False, "message": message}, status_code=status)


def _validation_message(e: ValidationError) -> str:
    first = e.errors()[0] if e.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", ()))
    msg = str(first.get("msg", "dato no válido")).replace("Value error, ", "")
    return f"{where}: {msg}" if where else msg


def _product_from(body: dict, product_id: str = "") -> prod.Product:
    data = {k: v for k, v in (body or {}).items() if k in prod.Product.model_fields and k != "id"}
    return prod.Product(id=product_id, **data)


async def _counts(state) -> dict[str, dict]:
    out: dict[str, dict] = {}
    async with state._connect() as db:
        async with db.execute(
            "SELECT product_id, status, COUNT(*) FROM product_accounts GROUP BY product_id, status"
        ) as cursor:
            for pid, status, n in await cursor.fetchall():
                out.setdefault(pid, {"pending": 0, "active": 0, "done": 0})[status] = n
        async with db.execute(
            "SELECT product_id, COUNT(*) FROM campaigns WHERE product_id != '' GROUP BY product_id"
        ) as cursor:
            for pid, n in await cursor.fetchall():
                out.setdefault(pid, {"pending": 0, "active": 0, "done": 0})["campaigns"] = n
    return out


@router.get("/api/products")
async def list_products():
    try:
        state = await ready_state()
        counts = await _counts(state)
        rows = []
        for p in await prod.list_products(state):
            c = counts.get(p.id, {})
            above = 0
            if p.scoring.configured():
                for a in await prod.assignments(state, product_id=p.id):
                    if a["score"] is not None and a["score"] >= p.scoring.threshold:
                        above += 1
            rows.append({**p.model_dump(), "accounts": {
                "pending": c.get("pending", 0), "active": c.get("active", 0), "done": c.get("done", 0),
                "total": c.get("pending", 0) + c.get("active", 0) + c.get("done", 0),
                "above_threshold": above}, "campaigns": c.get("campaigns", 0)})
        signals = [{"code": s["code"], "label": s.get("label") or s["code"], "status": s.get("status")}
                   for s in await state.get_signal_codes() if s.get("status") != "rejected"]
        from harvey.accounts_config import CONDITIONS
        from harvey.dashboard_accounts import SEGMENTS
        return {"products": rows, "signals": signals, "segments": list(SEGMENTS),
                "conditions": sorted(CONDITIONS), "cooldown_days": prod.NEXT_PRODUCT_COOLDOWN_DAYS}
    except Exception as e:
        logger.exception("products list failed")
        return _fail(str(e), 500)


async def _body(request: Request) -> dict | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


@router.post("/api/products")
async def create_product(request: Request):
    body = await _body(request)
    if body is None:
        return _fail("cuerpo no válido")
    try:
        product = _product_from(body)
    except ValidationError as e:
        return _fail(_validation_message(e))
    try:
        state = await ready_state()
        product = await prod.save_product(state, product)
        return {"success": True, "product": product.model_dump()}
    except Exception as e:
        logger.exception("product create failed")
        return _fail(str(e), 500)


@router.put("/api/products/{product_id}")
async def update_product(product_id: str, request: Request):
    body = await _body(request)
    if body is None:
        return _fail("cuerpo no válido")
    try:
        product = _product_from(body, product_id)
    except ValidationError as e:
        return _fail(_validation_message(e))
    try:
        state = await ready_state()
        await prod.save_product(state, product)
        scored = 0
        if product.scoring.configured():
            from harvey.collectors.spain.accounts import tracked_accounts
            scored = await prod.score_products(state, await tracked_accounts(state), [product])
        return {"success": True, "product": product.model_dump(), "scored": scored}
    except KeyError:
        return _fail("ese producto no existe", 404)
    except Exception as e:
        logger.exception("product update failed")
        return _fail(str(e), 500)


@router.delete("/api/products/{product_id}")
async def delete_product(product_id: str):
    try:
        state = await ready_state()
        product = await prod.get_product(state, product_id)
        if product is None:
            return _fail("ese producto no existe", 404)
        if await prod.delete_product(state, product_id):
            return {"success": True, "deleted": True}
        product.status = "paused"
        await prod.save_product(state, product)
        return {"success": True, "deleted": False,
                "message": "Ya tiene campañas, así que lo he pausado en lugar de borrarlo."}
    except Exception as e:
        logger.exception("product delete failed")
        return _fail(str(e), 500)


@router.post("/api/products/{product_id}/accounts")
async def assign_accounts(product_id: str, request: Request):
    """Add tracked accounts to a product: {company_ids: [...]} or {batch: "lote-01"}
    (every account of that lote) or {all: true}."""
    body = await _body(request)
    if body is None:
        return _fail("cuerpo no válido")
    try:
        state = await ready_state()
        product = await prod.get_product(state, product_id)
        if product is None:
            return _fail("ese producto no existe", 404)
        from harvey.collectors.spain.accounts import tracked_accounts
        accounts = await tracked_accounts(state)
        batch = str(body.get("batch") or "").strip()
        if body.get("all"):
            chosen = accounts
        elif batch:
            chosen = [a for a in accounts if (a.get("batch") or "").lower() == batch.lower()]
        else:
            wanted = {str(c) for c in body.get("company_ids") or []}
            chosen = [a for a in accounts if a["id"] in wanted]
        if not chosen:
            return _fail("ninguna cuenta coincide")
        added = 0
        for a in chosen:
            added += await prod.assign_accounts(state, product_id, [a["id"]], a.get("batch") or "")
        scored = await prod.score_products(state, accounts, [product])
        return {"success": True, "added": added, "already": len(chosen) - added, "scored": scored}
    except Exception as e:
        logger.exception("product assign failed")
        return _fail(str(e), 500)


@router.delete("/api/products/{product_id}/accounts/{company_id}")
async def unassign_account(product_id: str, company_id: str):
    try:
        state = await ready_state()
        if await prod.unassign_account(state, product_id, company_id):
            return {"success": True}
        return _fail("solo se puede quitar una cuenta a la que aún no se ha escrito por este producto")
    except Exception as e:
        logger.exception("product unassign failed")
        return _fail(str(e), 500)
