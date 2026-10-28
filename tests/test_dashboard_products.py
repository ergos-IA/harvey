"""The Productos tab and the product parts of the Cuentas tab.

Fictional companies on example domains only.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import harvey.dashboard as dash
from harvey import dashboard_accounts, dashboard_products

CSV = (
    "nombre;web;segmento;empleados\n"
    "Ejemplo Industrial;ejemplo-industrial.example;industrial;120\n"
    "Muestra Retail;muestra-retail.example;retail;300\n"
)

PRODUCT = {
    "name": "Agentes personales",
    "description": "Un asistente para cada directivo",
    "pricing": "licencia por usuario",
    "key_benefits": ["menos correo", "agenda al día"],
    "objection_responses": {"es caro": "Se paga con dos horas ahorradas a la semana"},
    "offer": {"entry": "Prueba de 14 días", "goal": "book_call"},
    "icp": {"segments": ["retail"], "titles": ["Director General"], "geography": ["España"]},
    "scoring": {"threshold": 20, "rules": [], "segments": {
        "retail": {"rules": [{"signal": "EMPLOYEE_COUNT", "when": {"min": 200}, "points": 25}]}}},
}


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "data" / "harvey.db"
        db.parent.mkdir()
        monkeypatch.setattr(dash, "DB_PATH", db)
        # No configured product: these tests create their own.
        monkeypatch.setattr(dashboard_products, "_config", lambda: None)
        monkeypatch.setattr(dashboard_accounts, "_config", lambda: None)
        dash.token_store.configure(Path(tmp) / "data" / "dashboard-token")
        token = dash.token_store.get()
        with TestClient(dash.app, base_url="http://127.0.0.1:5555",
                        headers={"Authorization": f"Bearer {token}"}) as c:
            yield c


def _create(client, **over):
    r = client.post("/api/products", json={**PRODUCT, **over})
    assert r.status_code == 200, r.text
    return r.json()["product"]


def test_create_list_and_update_a_product(client):
    p = _create(client)
    listed = client.get("/api/products").json()
    assert [x["name"] for x in listed["products"]] == ["Agentes personales"]
    assert listed["products"][0]["accounts"]["total"] == 0
    assert "retail" in listed["segments"] and "min" in listed["conditions"]
    r = client.put(f"/api/products/{p['id']}", json={**PRODUCT, "status": "paused"})
    assert r.json()["success"]
    assert client.get("/api/products").json()["products"][0]["status"] == "paused"


@pytest.mark.parametrize("body, message", [
    ({**PRODUCT, "name": ""}, "nombre"),
    ({**PRODUCT, "status": "borrado"}, "estado"),
    ({**PRODUCT, "scoring": {"rules": [{"signal": "EMPLOYEE_COUNT", "when": {"cuando": 1}}]}}, "condition"),
])
def test_bad_products_are_refused(client, body, message):
    r = client.post("/api/products", json=body)
    assert r.status_code == 400 and message in r.json()["message"]


def test_import_into_a_product_and_see_its_scores(client):
    p = _create(client)
    r = client.post("/api/accounts/import", json={"filename": "lote-01.csv", "csv": CSV,
                                                 "product_id": p["id"]}).json()
    assert r["success"] and r["product"] == "Agentes personales"
    accounts = {a["domain"]: a for a in client.get("/api/accounts").json()["accounts"]}
    retail = accounts["muestra-retail.example"]["products"]
    assert retail[0]["name"] == "Agentes personales" and retail[0]["score"] == 25 and retail[0]["above"]
    assert accounts["ejemplo-industrial.example"]["products"][0]["score"] == 0
    summary = client.get("/api/products").json()["products"][0]["accounts"]
    assert (summary["total"], summary["pending"], summary["above_threshold"]) == (2, 2, 1)


def test_an_unknown_product_on_import_is_refused(client):
    r = client.post("/api/accounts/import", json={"csv": CSV, "product_id": "nope"})
    assert r.status_code == 400 and "producto" in r.json()["message"]


def test_assign_a_lote_to_a_second_product(client):
    client.post("/api/accounts/import", json={"filename": "lote-01.csv", "csv": CSV})
    p = _create(client)
    r = client.post(f"/api/products/{p['id']}/accounts", json={"batch": "lote-01"}).json()
    assert (r["added"], r["already"]) == (2, 0)
    again = client.post(f"/api/products/{p['id']}/accounts", json={"all": True}).json()
    assert (again["added"], again["already"]) == (0, 2)
    assert client.post(f"/api/products/{p['id']}/accounts", json={"batch": "otro"}).status_code == 400
    cid = client.get("/api/accounts").json()["accounts"][0]["id"]
    assert client.delete(f"/api/products/{p['id']}/accounts/{cid}").json()["success"]


def test_deleting_a_product_with_campaigns_pauses_it(client):
    import asyncio
    from harvey.models.campaign import Campaign

    p = _create(client)
    asyncio.run(dash._state().add_campaign(Campaign(id="", name="c", product_id=p["id"])))
    r = client.delete(f"/api/products/{p['id']}").json()
    assert r["success"] and not r["deleted"]
    assert client.get("/api/products").json()["products"][0]["status"] == "paused"
    q = _create(client, name="Otro")
    assert client.delete(f"/api/products/{q['id']}").json()["deleted"]
    assert client.delete("/api/products/nope").status_code == 404
