"""The process phase by phase: the gates between phases, what the Scout and
the Writer may do behind them, and the Proceso tab.

Fictional companies on example domains only.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import harvey.dashboard as dash
from harvey import dashboard_accounts, dashboard_products
from harvey import process
from harvey import products as prod
from harvey.collectors.spain.accounts import import_accounts, tracked_accounts
from harvey.models.company import Company
from harvey.models.prospect import Prospect
from harvey.state import StateManager

CSV = (
    "nombre;web;segmento;empleados\n"
    "Ejemplo Industrial;ejemplo-industrial.example;industrial;120\n"
    "Demo Distribución;demo-distribucion.example;distribucion;60\n"
    "Muestra Retail;muestra-retail.example;retail;300\n"
)
# 100+ employees scores 10: the industrial and the retail pass, the distributor doesn't.
SCORING = {"threshold": 10, "rules": [{"signal": "EMPLOYEE_COUNT", "when": {"min": 100}, "points": 10}]}


@pytest_asyncio.fixture
async def state(tmp_path):
    state = StateManager(str(tmp_path / "p.db"))
    await state.init_db()
    return state


async def enriched(state, *cids):
    for cid in cids:
        await state.set_setting(f"accounts_enriched:web:{cid}", "2026-10-01T00:00:00+00:00")


async def setup(state, tmp_path, **gates):
    path = tmp_path / "lote-01.csv"
    path.write_text(CSV, encoding="utf-8")
    await import_accounts(state, path)
    accounts = await tracked_accounts(state)
    ids = {a["domain"].split(".")[0]: a["id"] for a in accounts}
    p = await prod.save_product(state, prod.Product(name="Plataforma", scoring=SCORING, gates=gates))
    await prod.assign_accounts(state, p.id, list(ids.values()), "lote-01")
    await prod.score_products(state, accounts, [p])
    return p, ids


async def person(state, cid, name="Eva", email_status="verified"):
    await state.add_prospect(Prospect(
        first_name=name, last_name="Demo", title="Gerente", company=name, company_id=cid,
        email=f"{name.lower()}@{cid}.example" if email_status else "", email_status=email_status))


async def searchable(state) -> set[str]:
    return {c["id"] for c in await state.companies_needing_prospects(limit=50)}


# ── the gates ──

@pytest.mark.parametrize("gates, row, expected", [
    ({}, {"score": 10}, (True, True)),
    ({}, {"score": 0}, (False, False)),
    ({}, {"score": None}, (False, False)),
    ({}, {"score": 0, "contacts_decision": "go"}, (True, True)),
    ({}, {"score": 10, "contacts_decision": "stop"}, (False, False)),
    ({"contacts": "manual"}, {"score": 50}, (False, False)),
    ({"contacts": "manual"}, {"score": 0, "contacts_decision": "go"}, (True, True)),
    ({"contacts": "all"}, {"score": 0}, (True, True)),
    ({"write": "manual"}, {"score": 10}, (True, False)),
    ({"write": "manual"}, {"score": 10, "write_decision": "go"}, (True, True)),
    ({}, {"score": 10, "write_decision": "stop"}, (True, False)),
    ({}, {"score": 10, "status": "done"}, (False, False)),
])
def test_the_gates_follow_the_mode_and_your_decisions(gates, row, expected):
    p = prod.Product(name="P", scoring=SCORING, gates=gates)
    assert prod.gates_for(p, {"status": "pending", **row}) == expected


def test_a_product_without_rules_lets_every_account_through_and_a_paused_one_none():
    assert prod.gates_for(prod.Product(name="P"), {"score": None}) == (True, True)
    assert prod.gates_for(prod.Product(name="P", status="paused", scoring=SCORING),
                          {"score": 99}) == (False, False)


def test_an_unknown_gate_mode_is_refused():
    with pytest.raises(ValueError):
        prod.ProductGates(contacts="siempre")
    with pytest.raises(ValueError):
        prod.ProductGates(write="all")


# ── what the agents may do behind them ──

@pytest.mark.asyncio
async def test_the_scout_only_looks_where_the_contacts_gate_is_open(state, tmp_path):
    p, ids = await setup(state, tmp_path)
    outside = await state.add_company(Company(name="Fuera", domain="fuera.example"))
    assert await searchable(state) == {ids["ejemplo-industrial"], ids["muestra-retail"], outside}
    await prod.set_decision(state, p.id, [ids["demo-distribucion"]], "contacts", "go")
    await prod.set_decision(state, p.id, [ids["muestra-retail"]], "contacts", "stop")
    assert await searchable(state) == {ids["ejemplo-industrial"], ids["demo-distribucion"], outside}
    p.status = "paused"
    await prod.save_product(state, p)
    assert await searchable(state) == {outside}


@pytest.mark.asyncio
async def test_the_titles_come_only_from_products_open_to_contacts(state, tmp_path):
    p, ids = await setup(state, tmp_path)
    p.icp.titles = ["Director de Operaciones"]
    await prod.save_product(state, p)
    assert await prod.titles_for_company(state, ids["ejemplo-industrial"]) == ["Director de Operaciones"]
    assert await prod.titles_for_company(state, ids["demo-distribucion"]) == []


@pytest.mark.asyncio
async def test_the_writer_waits_at_a_manual_write_gate(state, tmp_path):
    p, ids = await setup(state, tmp_path, write="manual")
    cid = ids["muestra-retail"]
    await person(state, cid)
    assert await prod.choose_product(state, cid) == (None, True)
    assert await state.count_writable_prospects() == 0
    await prod.set_decision(state, p.id, [cid], "write", "go")
    chosen, skip = await prod.choose_product(state, cid)
    assert chosen.id == p.id and not skip
    assert await state.count_writable_prospects() == 1


@pytest.mark.asyncio
async def test_below_the_threshold_nothing_is_written(state, tmp_path):
    p, ids = await setup(state, tmp_path)
    await person(state, ids["demo-distribucion"])
    assert await prod.choose_product(state, ids["demo-distribucion"]) == (None, True)
    assert await state.count_writable_prospects() == 0


@pytest.mark.asyncio
async def test_a_bad_decision_is_refused(state, tmp_path):
    p, ids = await setup(state, tmp_path)
    with pytest.raises(ValueError):
        await prod.set_decision(state, p.id, [ids["muestra-retail"]], "envio", "go")
    with pytest.raises(ValueError):
        await prod.set_decision(state, p.id, [ids["muestra-retail"]], "contacts", "quizá")


# ── where each account is ──

async def view(state, p, system=None):
    accounts = {a["id"]: a for a in await tracked_accounts(state)}
    out = await process.product_process(state, p, accounts, system or {"verifier_ok": True})
    return out, {r["domain"].split(".")[0]: r for r in out["accounts"]}


@pytest.mark.asyncio
async def test_each_account_sits_at_its_phase_with_the_reason(state, tmp_path):
    p, ids = await setup(state, tmp_path, write="manual")
    _, rows = await view(state, p)
    # Not enriched yet: it waits at Señales, the enrichment may lift its score.
    assert (rows["demo-distribucion"]["phase"], rows["demo-distribucion"]["state"]) == (2, "ok")
    await enriched(state, *ids.values())
    await person(state, ids["muestra-retail"])
    await person(state, ids["ejemplo-industrial"], "Luis", email_status="")
    out, rows = await view(state, p)
    assert (rows["demo-distribucion"]["phase"], rows["demo-distribucion"]["state"]) == (3, "blocked")
    assert "corte" in rows["demo-distribucion"]["label"]
    assert (rows["ejemplo-industrial"]["phase"], rows["ejemplo-industrial"]["state"]) == (4, "blocked")
    assert (rows["muestra-retail"]["phase"], rows["muestra-retail"]["state"]) == (5, "you")
    cards = {c["key"]: c for c in out["phases"]}
    assert cards["puntuacion"]["here"]["blocked"] == 1
    assert cards["redaccion"]["here"]["you"] == 1
    assert cards["cuentas"]["reached"] == 3 and cards["redaccion"]["reached"] == 1


@pytest.mark.asyncio
async def test_the_phase_cards_say_what_is_missing(state, tmp_path):
    p, _ = await setup(state, tmp_path)
    out, _ = await view(state, p, {"verifier_ok": False, "provider_ok": False, "provider": "smtp",
                                   "confirmed_signals": 0})
    cards = {c["key"]: c for c in out["phases"]}
    assert cards["senales"]["level"] == "block"
    assert cards["contactos"]["level"] == "block"
    assert cards["envio"]["level"] == "block"
    assert cards["cuentas"]["level"] == "ok"


@pytest.mark.asyncio
async def test_a_discarded_account_is_stopped(state, tmp_path):
    p, ids = await setup(state, tmp_path)
    await prod.set_decision(state, p.id, [ids["muestra-retail"]], "contacts", "stop")
    _, rows = await view(state, p)
    assert (rows["muestra-retail"]["state"], rows["muestra-retail"]["label"]) == ("stopped", "Descartada por ti")


@pytest.mark.asyncio
async def test_a_second_product_waits_in_the_queue(state, tmp_path):
    p, ids = await setup(state, tmp_path)
    cid = ids["muestra-retail"]
    await enriched(state, cid)
    await person(state, cid)
    await prod.mark_started(state, p.id, cid)
    q = await prod.save_product(state, prod.Product(name="Agentes", gates={"contacts": "all"}))
    await prod.assign_accounts(state, q.id, [cid])
    _, rows = await view(state, q)
    assert (rows["muestra-retail"]["state"], rows["muestra-retail"]["label"]) == (
        "wait", "En cola: antes va «Plataforma»")


# ── the Proceso tab ──

@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "data" / "harvey.db"
        db.parent.mkdir()
        monkeypatch.setattr(dash, "DB_PATH", db)
        monkeypatch.setattr(dashboard_products, "_config", lambda: None)
        monkeypatch.setattr(dashboard_accounts, "_config", lambda: None)
        dash.token_store.configure(Path(tmp) / "data" / "dashboard-token")
        token = dash.token_store.get()
        with TestClient(dash.app, base_url="http://127.0.0.1:5555",
                        headers={"Authorization": f"Bearer {token}"}) as c:
            yield c


def test_the_tab_shows_the_phases_and_takes_decisions(client):
    r = client.post("/api/products", json={"name": "Plataforma", "scoring": SCORING})
    pid = r.json()["product"]["id"]
    client.post("/api/accounts/import", json={"filename": "lote-01.csv", "csv": CSV, "product_id": pid})
    data = client.get("/api/process").json()
    assert data["product"]["id"] == pid and len(data["cards"]) == 8
    assert data["products"][0]["accounts"] == 3
    low = next(a for a in data["accounts"] if a["domain"] == "demo-distribucion.example")
    assert (low["phase"], low["label"]) == (2, "Pendiente de enriquecer") and not low["can_contact"]

    r = client.post(f"/api/process/{pid}/decision",
                    json={"company_ids": [low["company_id"]], "phase": "contacts", "decision": "go"})
    assert r.json() == {"success": True, "updated": 1}
    again = client.get(f"/api/process?product={pid}").json()
    assert next(a for a in again["accounts"] if a["company_id"] == low["company_id"])["can_contact"]

    assert client.post(f"/api/process/{pid}/gates", json={"write": "manual"}).json()["success"]
    assert client.post(f"/api/process/{pid}/gates", json={"contacts": "nunca"}).status_code == 400
    assert client.post(f"/api/process/{pid}/decision", json={"company_ids": []}).status_code == 400
    assert client.post("/api/process/nope/gates", json={}).status_code == 404

    # Saving the sheet from the Productos editor keeps the gates.
    client.put(f"/api/products/{pid}", json={"name": "Plataforma", "scoring": SCORING})
    assert client.get("/api/process").json()["product"]["gates"]["write"] == "manual"


def test_with_no_products_the_tab_says_so(client):
    data = client.get("/api/process").json()
    assert data["products"] == [] and "product" not in data
