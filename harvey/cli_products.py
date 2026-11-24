"""``harvey products``: list products, or load them from a JSON file.

    harvey products                         # list
    harvey products import kit.json         # create, or update the one with the same name
    harvey products import kit.json --assign   # ... and assign the tracked accounts
                                               #     whose segment the product targets
    harvey products export [file.json]      # all products as JSON (stdout by default)

The file is a list of products, or {"products": [...]}, in the same shape
the Productos tab saves (see harvey/products.py: Product). Products are
matched by name, case-insensitively, so loading the same file twice
updates instead of duplicating.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


async def _state():
    from harvey.state import StateManager
    state = StateManager()
    await state.init_db()
    return state


def read_products(path: str | Path) -> list:
    """The products in a kit file, validated. Raises SystemExit on a bad file."""
    from pydantic import ValidationError

    from harvey.products import Product

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"No se puede leer {path}: {e}") from None
    items = data.get("products") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise SystemExit(f"{path}: se esperaba una lista de productos o {{\"products\": [...]}}")
    out = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise SystemExit(f"{path}: el producto {i} no es un objeto")
        item = {k: v for k, v in item.items() if k != "id"}
        try:
            out.append(Product(**item))
        except ValidationError as e:
            raise SystemExit(f"{path}: producto {i} ({item.get('name', '?')}): {e}") from None
    return out


async def import_products(state, products: list, assign: bool = False) -> list[tuple[str, str, int]]:
    """Upsert by name. Returns [(name, "creado"|"actualizado", accounts assigned)]."""
    from harvey import products as prod

    existing = {p.name.strip().lower(): p for p in await prod.list_products(state)}
    accounts = []
    if assign:
        from harvey.collectors.spain.accounts import tracked_accounts
        accounts = await tracked_accounts(state)
    report = []
    saved = []
    for product in products:
        old = existing.get(product.name.strip().lower())
        product.id = old.id if old else ""
        product = await prod.save_product(state, product)
        saved.append(product)
        added = 0
        if assign:
            wanted = set(product.icp.segments)
            for account in accounts:
                seg = (account.get("segment") or "").strip().lower()
                if not wanted or seg in wanted:
                    added += await prod.assign_accounts(state, product.id, [account["id"]],
                                                        account.get("batch") or "")
        report.append((product.name, "actualizado" if old else "creado", added))
    if assign and accounts:
        await prod.score_products(state, accounts, saved)
    return report


async def _run(args):
    from harvey import products as prod

    state = await _state()
    action = args.products_action or "list"
    if action == "list":
        items = await prod.list_products(state)
        if not items:
            print("No hay productos. Carga uno con: harvey products import <archivo.json>")
        for p in items:
            rows = await prod.assignments(state, product_id=p.id)
            segs = ", ".join(p.icp.segments) or "cualquiera"
            print(f"  {p.status:<7} {p.name[:40]:<40} segmentos: {segs:<24} cuentas: {len(rows)}")
    elif action == "import":
        if not args.file:
            raise SystemExit("Uso: harvey products import <archivo.json> [--assign]")
        for name, verb, added in await import_products(state, read_products(args.file), args.assign):
            extra = f", {added} cuenta(s) asignada(s)" if args.assign else ""
            print(f"  {name}: {verb}{extra}")
        if not args.assign:
            print("\n  Para asignarle las cuentas de sus segmentos: añade --assign")
    elif action == "export":
        items = [{"name": p.name, "status": p.status, **p.data()}
                 for p in await prod.list_products(state)]
        text = json.dumps({"products": items}, ensure_ascii=False, indent=2)
        if args.file:
            Path(args.file).write_text(text + "\n", encoding="utf-8")
            print(f"  {len(items)} producto(s) escritos en {args.file}")
        else:
            sys.stdout.write(text + "\n")


def cmd_products(args):
    asyncio.run(_run(args))


def register(subparsers) -> None:
    sub = subparsers.add_parser("products", help="Products: list, import or export (JSON)")
    sub.add_argument("products_action", nargs="?", default="list",
                     choices=["list", "import", "export"])
    sub.add_argument("file", nargs="?", default="")
    sub.add_argument("--assign", action="store_true",
                     help="Assign the tracked accounts whose segment each product targets")
    sub.set_defaults(func=cmd_products)
