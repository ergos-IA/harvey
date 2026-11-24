"""Documentos tab: internal files from data/docs, behind the dashboard guard."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import harvey.dashboard as dash
from harvey import dashboard_docs


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        docs = tmp / "data" / "docs"
        docs.mkdir(parents=True)
        monkeypatch.setattr(dash, "DB_PATH", tmp / "data" / "harvey.db")
        dash.token_store.configure(tmp / "data" / "dashboard-token")
        token = dash.token_store.get()
        with TestClient(dash.app, base_url="http://127.0.0.1:5555",
                        headers={"Authorization": f"Bearer {token}"}) as c:
            c.docs = docs
            c.tmp = tmp
            yield c


def test_lists_and_serves_allowed_files(client):
    (client.docs / "Proceso.pdf").write_bytes(b"%PDF-1.4 test")
    (client.docs / "notas.md").write_text("hola", encoding="utf-8")
    (client.docs / "script.sh").write_text("echo", encoding="utf-8")
    (client.docs / ".oculto.pdf").write_bytes(b"x")
    (client.docs / "carpeta").mkdir()
    names = [d["name"] for d in client.get("/api/docs").json()["items"]]
    assert names == ["notas.md", "Proceso.pdf"]
    r = client.get("/api/docs/Proceso.pdf")
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 test"
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]


@pytest.mark.parametrize("name", ["script.sh", ".oculto.pdf", "..%2Fharvey.db", "%2E%2E%2Fdashboard-token",
                                  "no-existe.pdf"])
def test_anything_not_in_the_listing_is_a_404(client, name):
    (client.docs / "script.sh").write_text("echo", encoding="utf-8")
    (client.docs / ".oculto.pdf").write_bytes(b"x")
    r = client.get("/api/docs/" + name)
    assert r.status_code == 404
    assert b"token" not in r.content.lower() or r.status_code == 404


def test_no_folder_means_an_empty_list(client):
    client.docs.rmdir()
    assert client.get("/api/docs").json() == {"items": []}


def test_documents_need_the_dashboard_token(client):
    (client.docs / "Proceso.pdf").write_bytes(b"%PDF")
    assert client.get("/api/docs", headers={"Authorization": ""}).status_code in (401, 403)
    assert client.get("/api/docs/Proceso.pdf", headers={"Authorization": ""}).status_code in (401, 403)
