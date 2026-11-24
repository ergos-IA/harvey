"""LinkedIn outreach: the server queue (linkedin_queue), its API and the PC
worker's logic with a fake browser. Nothing here opens LinkedIn.

Fictional people and companies on example domains only.
"""

from datetime import datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from harvey import linkedin_queue as lq
from harvey import linkedin_worker as lw
from harvey import products as prod
from harvey.collectors.spain.accounts import import_accounts, tracked_accounts
from harvey.config import HarveyConfig
from harvey.state import StateManager

CSV = (
    "nombre;web;segmento;empleados\n"
    "Distribuciones Ejemplo SL;distribuciones-ejemplo.example;distribucion;60\n"
    "Talleres Demo SA;talleres-demo.example;distribucion;90\n"
    "Muestra Baja SL;muestra-baja.example;distribucion;40\n"
)


def make_config() -> HarveyConfig:
    return HarveyConfig.model_validate({
        "persona": {"name": "Ana Ejemplo", "company": "Ejemplo SL", "role": "Ventas",
                    "email": "ana@ejemplo.example", "linkedin": "", "tone": "cercano"},
        "product": {"name": "Pedidos Demo", "description": "Pedidos al ERP", "pricing": "",
                    "key_benefits": [], "objection_responses": {}},
        "icp": {"industries": ["distribución"], "company_size": "10-150", "titles": ["Gerente"],
                "geography": ["España"]},
        "channels": {"email": {"link_domains": ["ejemplo.example"]}},
    })


@pytest_asyncio.fixture
async def state(tmp_path):
    state = StateManager(str(tmp_path / "l.db"))
    await state.init_db()
    await lq.ensure_tables(state)
    return state


async def _setup(state, tmp_path, scores=(80, 75, 40)):
    (tmp_path / "a.csv").write_text(CSV, encoding="utf-8")
    await import_accounts(state, tmp_path / "a.csv")
    ids = {a["domain"]: a["id"] for a in await tracked_accounts(state)}
    product = await prod.save_product(state, prod.Product(
        name="Pedidos Demo", icp={"titles": ["Gerente", "Director de Operaciones"]}))
    await prod.assign_accounts(state, product.id, list(ids.values()))
    async with state._connect() as db:
        for domain, score in zip(["distribuciones-ejemplo.example", "talleres-demo.example",
                                  "muestra-baja.example"], scores):
            await db.execute("UPDATE product_accounts SET score = ? WHERE company_id = ?",
                             (score, ids[domain]))
        await db.commit()
    return ids, product


class FakeBrain:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    async def think_json(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.result


def test_profile_urls_are_normalised():
    assert lq.normalize_profile_url("https://es.linkedin.com/in/Ana-Ejemplo/?trk=x") == \
        "https://www.linkedin.com/in/ana-ejemplo"
    assert lq.normalize_profile_url("https://www.linkedin.com/company/ejemplo") == ""
    assert lq.normalize_profile_url("") == ""


@pytest.mark.asyncio
async def test_plan_takes_only_accounts_above_the_score_once(state, tmp_path):
    ids, _ = await _setup(state, tmp_path)
    assert await lq.plan(state, make_config(), min_score=70) == 2
    assert await lq.plan(state, make_config(), min_score=70) == 0        # not twice
    batch = await lq.work(state)
    assert {j["company_id"] for j in batch["find"]} == {
        ids["distribuciones-ejemplo.example"], ids["talleres-demo.example"]}
    assert batch["find"][0]["titles"] == ["Gerente", "Director de Operaciones"]
    assert (await lq.work(state))["find"] == []                          # claimed


@pytest.mark.asyncio
async def test_plan_skips_companies_that_replied_or_opted_out(state, tmp_path):
    ids, _ = await _setup(state, tmp_path)
    async with state._connect() as db:
        await db.execute("INSERT INTO prospects (id, company_id, first_name, status) VALUES "
                         "('p1', ?, 'Luis', 'replied')", (ids["distribuciones-ejemplo.example"],))
        await db.commit()
    assert await lq.plan(state, make_config(), min_score=70) == 1


@pytest.mark.asyncio
async def test_a_found_person_becomes_a_candidate(state, tmp_path):
    ids, _ = await _setup(state, tmp_path)
    await lq.plan(state, make_config(), min_score=70)
    job = (await lq.work(state))["find"][0]
    people = [{"profile_url": "https://www.linkedin.com/in/ana-ejemplo/", "full_name": "Ana Ejemplo",
               "title": "Gerente en Distribuciones Ejemplo"},
              {"profile_url": "not a profile", "full_name": "X"}]
    assert (await lq.report(state, "find", job["id"], people=people))["added"] == 1
    assert (await lq.report(state, "find", job["id"], people=people))["updated"] == 0   # once
    items = await lq.queue(state, "candidate")
    assert len(items) == 1 and items[0]["profile_url"] == "https://www.linkedin.com/in/ana-ejemplo"


@pytest.mark.asyncio
async def test_draft_then_approve_then_the_full_cycle(state, tmp_path):
    ids, product = await _setup(state, tmp_path)
    item_id = await lq.add_candidate(state, "https://www.linkedin.com/in/ana-ejemplo",
                                     company_id=ids["distribuciones-ejemplo.example"],
                                     product_id=product.id, full_name="Ana Ejemplo",
                                     company_name="Distribuciones Ejemplo SL")
    brain = FakeBrain({"note": "Hola Ana, he visto que buscáis administrativo de pedidos.",
                       "message": "Gracias por aceptar. ¿Cuántos pedidos os llegan al día?"})
    assert await lq.draft(state, make_config(), brain) == 1
    assert "<untrusted" in brain.prompts[0]                   # the profile is fenced
    assert await lq.approve(state, None) == 1

    batch = await lq.work(state)
    assert [i["id"] for i in batch["invite"]] == [item_id]
    await lq.report(state, "invite", item_id, ok=True)
    assert (await lq.get(state, item_id))["status"] == "invited"
    assert (await lq.work(state))["check"] == []              # checked just now

    await lq.report(state, "check", item_id, connected=True)
    batch = await lq.work(state)
    assert [i["id"] for i in batch["message"]] == [item_id]
    await lq.report(state, "message", item_id, ok=True)
    assert (await lq.get(state, item_id))["status"] == "messaged"
    await lq.report(state, "invite", item_id, ok=False, error="late")   # stale: ignored
    assert (await lq.get(state, item_id))["status"] == "messaged"


@pytest.mark.asyncio
async def test_a_flagged_draft_is_left_out_of_approve_all(state, tmp_path):
    item_id = await lq.add_candidate(state, "https://www.linkedin.com/in/luis-demo")
    brain = FakeBrain({"note": "Mira esto: https://otro-sitio.example/x", "message": "Hola"})
    await lq.draft(state, make_config(), brain)
    item = await lq.get(state, item_id)
    assert item["status"] == "pending_review" and item["flags"]
    assert await lq.approve(state, None) == 0
    assert await lq.approve(state, [item_id]) == 1            # named: someone looked


@pytest.mark.asyncio
async def test_an_empty_or_bad_draft_leaves_the_candidate(state):
    await lq.add_candidate(state, "https://www.linkedin.com/in/luis-demo")
    assert await lq.draft(state, make_config(), FakeBrain({"note": ""})) == 0
    assert await lq.draft(state, make_config(), FakeBrain(None)) == 0
    assert len(await lq.queue(state, "candidate")) == 1


# ── the API ──

def test_the_worker_api_needs_the_token(tmp_path, monkeypatch):
    import harvey.dashboard as dash
    monkeypatch.setattr(dash, "DB_PATH", tmp_path / "data" / "harvey.db")
    dash.token_store.configure(tmp_path / "data" / "dashboard-token")
    with TestClient(dash.app, base_url="http://127.0.0.1:5555") as c:
        assert c.get("/api/linkedin/work").status_code == 401
        h = {"Authorization": f"Bearer {dash.token_store.get()}"}
        r = c.get("/api/linkedin/work", headers=h)
        assert r.status_code == 200 and r.json()["invite"] == []
        r = c.post("/api/linkedin/report", headers=h, json={"kind": "nope", "id": "x"})
        assert r.status_code == 400
        r = c.post("/api/linkedin/report", headers=h, json={"kind": "invite", "id": "x", "ok": True})
        assert r.json()["updated"] == 0
        assert c.get("/api/linkedin", headers=h).json()["queue"]["approved"] == 0


# ── the worker ──

def test_pick_people_keeps_only_who_works_there():
    cards = [
        {"profile_url": "https://www.linkedin.com/in/a", "name": "Ana",
         "headline": "Responsable de compras en Distribuciones Ejemplo"},
        {"profile_url": "https://www.linkedin.com/in/b", "name": "Bea",
         "headline": "Gerente · Distribuciones Ejemplo SL"},
        {"profile_url": "https://www.linkedin.com/in/c", "name": "Carla",
         "headline": "Gerente en Otra Empresa"},
    ]
    people = lw.pick_people(cards, "Distribuciones Ejemplo SL", ["Gerente"])
    assert [p["full_name"] for p in people] == ["Bea", "Ana"]
    assert lw.pick_people(cards, "SL", ["Gerente"]) == []


def test_office_hours():
    assert lw.in_office_hours(datetime(2026, 11, 24, 10, 0))      # Tuesday
    assert not lw.in_office_hours(datetime(2026, 11, 24, 20, 0))
    assert not lw.in_office_hours(datetime(2026, 11, 29, 10, 0))  # Sunday


class FakeServer:
    def __init__(self, batch):
        self.batch, self.reports, self.limits = batch, [], None

    async def work(self, **limits):
        self.limits = limits
        return self.batch

    async def report(self, **body):
        self.reports.append(body)


class FakeBrowser:
    def __init__(self):
        self.invited = []

    async def search(self, company, titles):
        return [{"profile_url": "https://www.linkedin.com/in/a", "name": "Ana",
                 "headline": f"Gerente en {company}"}]

    async def invite(self, url, note, dry_run):
        self.invited.append((url, dry_run))
        return True, ""

    async def profile_state(self, url):
        return "connected"

    async def send_message(self, url, text, dry_run):
        return True, ""


def _batch():
    return {"find": [{"id": "j1", "company_name": "Distribuciones Ejemplo", "titles": ["Gerente"]}],
            "invite": [{"id": f"i{n}", "profile_url": f"https://www.linkedin.com/in/p{n}", "note": "Hola"}
                       for n in range(5)],
            "check": [{"id": "c1", "profile_url": "https://www.linkedin.com/in/c"}],
            "message": [{"id": "m1", "profile_url": "https://www.linkedin.com/in/m", "message": "Hola"}]}


@pytest.mark.asyncio
async def test_run_once_reports_and_respects_the_daily_caps(tmp_path):
    activity = lw.Activity(tmp_path / "act.json", caps={"invite": 2})
    server, browser = FakeServer(_batch()), FakeBrowser()
    done = await lw.run_once(server, browser, activity, gap=(0, 0), log=lambda *_: None)
    assert done["invite"] == 2 and len(browser.invited) == 2
    assert server.limits["invite"] == 2
    kinds = [(r["kind"], r.get("connected")) for r in server.reports]
    assert ("find", None) in kinds and ("check", True) in kinds and ("message", None) in kinds
    assert server.reports[0]["people"][0]["profile_url"] == "https://www.linkedin.com/in/a"
    assert lw.Activity(tmp_path / "act.json", caps={"invite": 2}).left("invite") == 0   # persisted


@pytest.mark.asyncio
async def test_a_dry_run_reports_nothing_and_spends_no_invites(tmp_path):
    activity = lw.Activity(tmp_path / "act.json")
    server, browser = FakeServer(_batch()), FakeBrowser()
    await lw.run_once(server, browser, activity, dry_run=True, gap=(0, 0), log=lambda *_: None)
    assert server.reports == []
    assert all(dry for _, dry in browser.invited)
    assert activity.left("invite") == lw.CAPS["invite"]


def test_the_worker_refuses_a_plain_http_server(monkeypatch):
    monkeypatch.setenv("HARVEY_REMOTE_TOKEN", "x")
    with pytest.raises(SystemExit, match="https"):
        lw.server_settings("http://harvey.example.test")
    monkeypatch.delenv("HARVEY_REMOTE_TOKEN")
    with pytest.raises(SystemExit, match="HARVEY_REMOTE_TOKEN"):
        lw.server_settings("https://harvey.example.test")
