"""The Cuentas tab: import a CSV, list the accounts, score them.

Fictional companies on example domains only.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import harvey.dashboard as dash
from harvey import dashboard_accounts, dashboard_products
from harvey.accounts_config import ScoringConfig

CSV = (
    "nombre;web;segmento;empleados;provincia\n"
    "Ejemplo Industrial;https://www.ejemplo-industrial.example/;industrial;120;Barcelona\n"
    "Demo Distribución;demo-distribucion.example;distribucion;60;Valencia\n"
    "Sin Web;;retail;10;Madrid\n"
)


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "data" / "harvey.db"
        db.parent.mkdir()
        monkeypatch.setattr(dash, "DB_PATH", db)
        scoring = ScoringConfig.model_validate({
            "threshold": 10,
            "rules": [{"signal": "EMPLOYEE_COUNT", "when": {"min": 100}, "points": 10}],
        })
        monkeypatch.setattr(dashboard_accounts, "_config",
                            lambda: type("C", (), {"scoring": scoring, "accounts": None})())
        monkeypatch.setattr(dashboard_products, "_config", lambda: None)   # no product seeded
        dash.token_store.configure(Path(tmp) / "data" / "dashboard-token")
        token = dash.token_store.get()
        with TestClient(dash.app, base_url="http://127.0.0.1:5555",
                        headers={"Authorization": f"Bearer {token}"}) as c:
            c.db_path = db
            yield c


def _import(client, **extra):
    return client.post("/api/accounts/import",
                       json={"filename": "lote-01.csv", "csv": CSV, **extra}).json()


def test_a_dry_run_checks_the_file_and_imports_nothing(client):
    data = _import(client, dry_run=True)
    assert data["success"] and data["created"] == 2 and data["batch"] == "lote-01"
    assert any("línea 4" in p for p in data["skipped"])
    assert client.get("/api/accounts").json()["accounts"] == []


def test_import_lists_the_accounts_scored(client):
    data = _import(client)
    assert (data["created"], data["updated"], data["scored"]) == (2, 0, 2)
    listed = client.get("/api/accounts").json()
    rows = {a["domain"]: a for a in listed["accounts"]}
    assert set(rows) == {"ejemplo-industrial.example", "demo-distribucion.example"}
    assert rows["ejemplo-industrial.example"]["score"] == 10
    assert rows["demo-distribucion.example"]["score"] == 0
    assert rows["ejemplo-industrial.example"]["segment"] == "industrial"
    assert listed["accounts"][0]["domain"] == "ejemplo-industrial.example"   # best first
    # The uploaded file is kept next to the database, under a safe name.
    assert (c := client.db_path.parent / "imports" / "lote-01.csv").exists() and c.read_bytes()


def test_reimporting_the_same_file_creates_nothing(client):
    _import(client)
    again = _import(client)
    assert (again["created"], again["updated"]) == (0, 2)


@pytest.mark.parametrize("body, message", [
    ({"csv": ""}, "vacío"),
    ({"csv": CSV, "segment": "otro"}, "segmento"),
    ({"csv": "x" * (2 * 1024 * 1024 + 1)}, "2 MB"),
])
def test_bad_uploads_are_refused(client, body, message):
    r = client.post("/api/accounts/import", json=body)
    assert r.status_code == 400 and message in r.json()["message"]


def test_a_filename_cannot_escape_the_imports_folder(client):
    client.post("/api/accounts/import", json={"filename": "../../evil.csv", "csv": CSV})
    assert (client.db_path.parent / "imports" / "evil.csv").exists()
    assert not (client.db_path.parent.parent / "evil.csv").exists()
