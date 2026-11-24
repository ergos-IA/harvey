"""``harvey products import|export`` and ``harvey accounts import --product``.

Fictional companies on example domains only.
"""

import json
import types

import pytest
import pytest_asyncio

from harvey import cli_accounts, cli_products
from harvey import products as prod
from harvey.collectors.spain.accounts import import_accounts, tracked_accounts
from harvey.state import StateManager

CSV = (
    "nombre;web;segmento;empleados\n"
    "Ejemplo Industrial;ejemplo-industrial.example;industrial;120\n"
    "Demo Distribución;demo-distribucion.example;distribucion;60\n"
)

KIT = {"products": [
    {"name": "Pedidos Demo", "description": "Entrada de pedidos",
     "icp": {"segments": ["distribucion"], "company_size": "10-150"},
     "gates": {"contacts": "auto", "write": "manual"},
     "scoring": {"threshold": 10, "rules": [
         {"signal": "EMPLOYEE_COUNT", "when": {"between": [10, 150]}, "points": 15}]}},
    {"name": "Ofertas Demo", "icp": {"segments": ["industrial"]}},
]}


@pytest_asyncio.fixture
async def state(tmp_path, monkeypatch):
    state = StateManager(str(tmp_path / "p.db"))
    await state.init_db()

    async def _same():
        return state
    monkeypatch.setattr(cli_products, "_state", _same)
    monkeypatch.setattr(cli_accounts, "_state", _same)
    monkeypatch.setattr(cli_accounts, "_config_or_none", lambda: None)
    return state


def _kit(tmp_path, data=KIT):
    path = tmp_path / "kit.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _args(action, file="", assign=False):
    return types.SimpleNamespace(products_action=action, file=str(file), assign=assign)


@pytest.mark.asyncio
async def test_import_creates_then_updates_by_name(state, tmp_path, capsys):
    path = _kit(tmp_path)
    await cli_products._run(_args("import", path))
    first = {p.name: p for p in await prod.list_products(state)}
    assert set(first) == {"Pedidos Demo", "Ofertas Demo"}
    assert first["Pedidos Demo"].gates.write == "manual"

    changed = json.loads(json.dumps(KIT))
    changed["products"][0]["name"] = "pedidos demo"       # same product, other case
    changed["products"][0]["description"] = "Pedidos con IA"
    await cli_products._run(_args("import", _kit(tmp_path, changed)))
    again = await prod.list_products(state)
    assert len(again) == 2
    updated = next(p for p in again if p.id == first["Pedidos Demo"].id)
    assert updated.description == "Pedidos con IA"
    assert "actualizado" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_assign_takes_the_accounts_of_each_products_segments(state, tmp_path):
    (tmp_path / "a.csv").write_text(CSV, encoding="utf-8")
    await import_accounts(state, tmp_path / "a.csv")
    await cli_products._run(_args("import", _kit(tmp_path), assign=True))
    ids = {a["domain"]: a["id"] for a in await tracked_accounts(state)}
    by_name = {p.name: p for p in await prod.list_products(state)}
    pedidos = await prod.assignments(state, product_id=by_name["Pedidos Demo"].id)
    ofertas = await prod.assignments(state, product_id=by_name["Ofertas Demo"].id)
    assert [r["company_id"] for r in pedidos] == [ids["demo-distribucion.example"]]
    assert pedidos[0]["score"] == 15                         # scored with its own rules
    assert [r["company_id"] for r in ofertas] == [ids["ejemplo-industrial.example"]]


@pytest.mark.asyncio
async def test_a_bad_kit_is_refused_with_the_reason(state, tmp_path):
    with pytest.raises(SystemExit, match="producto 1"):
        await cli_products._run(_args("import", _kit(tmp_path, [{"name": ""}])))
    with pytest.raises(SystemExit, match="lista de productos"):
        await cli_products._run(_args("import", _kit(tmp_path, {"other": 1})))
    assert await prod.list_products(state) == []


@pytest.mark.asyncio
async def test_export_round_trips(state, tmp_path):
    await cli_products._run(_args("import", _kit(tmp_path)))
    out = tmp_path / "out.json"
    await cli_products._run(_args("export", out))
    names = {p.name for p in cli_products.read_products(out)}
    assert names == {"Pedidos Demo", "Ofertas Demo"}


@pytest.mark.asyncio
async def test_accounts_import_can_assign_to_a_product(state, tmp_path, capsys):
    await cli_products._run(_args("import", _kit(tmp_path)))
    (tmp_path / "a.csv").write_text(CSV, encoding="utf-8")
    args = types.SimpleNamespace(file=str(tmp_path / "a.csv"), batch="test-a", segment="",
                                 dry_run=False, product="Pedidos Demo")
    await cli_accounts._import(args)
    product = next(p for p in await prod.list_products(state) if p.name == "Pedidos Demo")
    rows = await prod.assignments(state, product_id=product.id)
    assert len(rows) == 2 and {r["batch"] for r in rows} == {"test-a"}
    assert "assigned to product 'Pedidos Demo'" in capsys.readouterr().out

    args.product = "no existe"
    with pytest.raises(SystemExit, match="No existe el producto"):
        await cli_accounts._import(args)


@pytest.mark.asyncio
async def test_accounts_score_also_scores_products(state, tmp_path, capsys):
    (tmp_path / "a.csv").write_text(CSV, encoding="utf-8")
    await import_accounts(state, tmp_path / "a.csv")
    await cli_products._run(_args("import", _kit(tmp_path), assign=True))
    await cli_accounts._score(types.SimpleNamespace(segment="", batch="", threshold=None,
                                                    no_store=False))
    out = capsys.readouterr().out
    assert "Pedidos Demo" in out and "1 at or above 10" in out
    assert "No scoring rules yet" not in out
