"""Products: several offers, each with its own ICP, scoring and accounts.

Fictional companies on example domains only.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from pydantic import ValidationError

from harvey import products as prod
from harvey.agents.writer import Writer
from harvey.collectors.spain.accounts import import_accounts, tracked_accounts
from harvey.config import HarveyConfig
from harvey.models.prospect import Prospect
from harvey.state import StateManager

CSV = (
    "nombre;web;segmento;empleados\n"
    "Ejemplo Industrial;ejemplo-industrial.example;industrial;120\n"
    "Demo Distribución;demo-distribucion.example;distribucion;60\n"
    "Muestra Retail;muestra-retail.example;retail;300\n"
)


def make_config(**over) -> HarveyConfig:
    data = {
        "persona": {"name": "Ana Ejemplo", "company": "Ejemplo SL", "role": "Ventas",
                    "email": "ana@ejemplo.example", "linkedin": "", "tone": "cercano"},
        "product": {"name": "Plataforma Demo", "description": "Presupuestos en minutos",
                    "pricing": "10 k/año", "key_benefits": ["rápido"], "objection_responses": {}},
        "icp": {"industries": ["industria"], "company_size": "50-500", "titles": ["Gerente"],
                "geography": ["España"]},
        "scoring": {"threshold": 10, "rules": [
            {"signal": "EMPLOYEE_COUNT", "when": {"min": 100}, "points": 10}]},
    }
    data.update(over)
    return HarveyConfig.model_validate(data)


@pytest_asyncio.fixture
async def state(tmp_path):
    state = StateManager(str(tmp_path / "p.db"))
    await state.init_db()
    return state


async def import_csv(state, tmp_path, text=CSV, name="lote-01.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    report = await import_accounts(state, path)
    return {a["domain"]: a["id"] for a in await tracked_accounts(state)}, report


def rules(points_for_big=10, segment_rule=None):
    data = {"threshold": 15, "rules": [{"signal": "EMPLOYEE_COUNT", "when": {"min": 100},
                                        "points": points_for_big}]}
    if segment_rule:
        data["segments"] = {"retail": {"rules": [segment_rule]}}
    return data


# ── the model ──

def test_a_product_needs_a_name_and_a_known_status():
    with pytest.raises(ValidationError):
        prod.Product(name="  ")
    with pytest.raises(ValidationError):
        prod.Product(name="X", status="borrado")
    p = prod.Product(name="  Agentes   personales ", key_benefits=["a", "A", "", "b"],
                     icp={"segments": ["Retail", "retail"], "titles": ["Gerente", " gerente "]})
    assert p.name == "Agentes personales"
    assert p.key_benefits == ["a", "b"]
    assert p.icp.segments == ["retail"] and p.icp.titles == ["Gerente"]


def test_the_brief_carries_offer_icp_and_knowledge():
    p = prod.Product(name="Agentes", description="Un asistente por persona", pricing="licencia",
                     offer={"entry": "Prueba de 14 días"}, icp={"titles": ["Director General"]},
                     objection_responses={"es caro": "Se paga solo"}, knowledge="No sustituye al ERP.")
    brief = p.brief()
    for text in ("# Agentes", "licencia", "Prueba de 14 días", "Director General", "es caro: Se paga solo",
                 "No sustituye al ERP."):
        assert text in brief
    assert prod.knowledge_for(p) == brief
    assert prod.knowledge_for(prod.Product(name="Sin texto")) is None
    assert prod.knowledge_for(None) is None


def test_config_for_swaps_the_offer_and_keeps_what_the_product_leaves_empty():
    config = make_config()
    p = prod.Product(name="Agentes", description="d", icp={"titles": ["Director General"]})
    cfg = prod.config_for(config, p)
    assert cfg.product.name == "Agentes"
    assert cfg.icp.titles == ["Director General"]
    assert cfg.icp.geography == ["España"]                 # left empty: the configured one
    assert config.product.name == "Plataforma Demo"         # the original is untouched
    assert prod.config_for(config, None) is config


# ── storage ──

@pytest.mark.asyncio
async def test_products_are_saved_listed_updated_and_deleted(state):
    p = await prod.save_product(state, prod.Product(name="Uno", scoring=rules()))
    assert p.id and (await prod.get_product(state, p.id)).scoring.threshold == 15
    p.description = "nueva"
    await prod.save_product(state, p)
    assert [x.description for x in await prod.list_products(state)] == ["nueva"]
    assert await prod.delete_product(state, p.id)
    assert await prod.list_products(state) == []
    with pytest.raises(KeyError):
        await prod.save_product(state, prod.Product(id="nope", name="X"))


@pytest.mark.asyncio
async def test_a_product_with_campaigns_is_not_deleted(state):
    from harvey.models.campaign import Campaign
    p = await prod.save_product(state, prod.Product(name="Uno"))
    await state.add_campaign(Campaign(id="", name="c", product_id=p.id))
    assert not await prod.delete_product(state, p.id)
    assert await prod.get_product(state, p.id)


@pytest.mark.asyncio
async def test_assigning_twice_keeps_the_status(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    p = await prod.save_product(state, prod.Product(name="Uno"))
    cid = ids["ejemplo-industrial.example"]
    assert await prod.assign_accounts(state, p.id, [cid, cid]) == 1
    await prod.mark_started(state, p.id, cid)
    assert await prod.assign_accounts(state, p.id, [cid], "lote-02") == 0
    row = (await prod.assignments(state, product_id=p.id))[0]
    assert (row["status"], row["batch"]) == ("active", "lote-02")
    # Only an account nobody has written to yet can be taken out.
    assert not await prod.unassign_account(state, p.id, cid)


# ── scoring ──

@pytest.mark.asyncio
async def test_each_product_scores_with_its_own_rules(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    big = await prod.save_product(state, prod.Product(name="Grandes", scoring=rules(10)))
    shops = await prod.save_product(state, prod.Product(name="Tiendas", scoring=rules(
        1, {"signal": "EMPLOYEE_COUNT", "when": {"min": 200}, "points": 30})))
    unscored = await prod.save_product(state, prod.Product(name="Sin reglas"))
    for p in (big, shops, unscored):
        await prod.assign_accounts(state, p.id, list(ids.values()))
    accounts = await tracked_accounts(state)
    assert await prod.score_products(state, accounts) == 6
    score = {(r["product_id"], r["company_id"]): r["score"] for r in await prod.assignments(state)}
    retail = ids["muestra-retail.example"]
    assert score[(big.id, retail)] == 10
    assert score[(shops.id, retail)] == 31                   # its retail-only rule fired
    assert score[(shops.id, ids["ejemplo-industrial.example"])] == 1
    assert score[(unscored.id, retail)] is None


# ── which product the next email sells ──

@pytest.mark.asyncio
async def test_choose_product_prefers_the_running_one_then_the_best_score(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    cid = ids["muestra-retail.example"]
    assert await prod.choose_product(state, cid) == (None, False)     # in no product
    a = await prod.save_product(state, prod.Product(name="A", scoring=rules(5)))
    b = await prod.save_product(state, prod.Product(name="B", scoring=rules(40)))
    await prod.assign_accounts(state, a.id, [cid])
    await prod.assign_accounts(state, b.id, [cid])
    await prod.score_products(state, await tracked_accounts(state))
    assert (await prod.choose_product(state, cid))[0].name == "B"
    await prod.mark_started(state, a.id, cid)
    assert (await prod.choose_product(state, cid))[0].name == "A"
    await prod._set_assignment(state, a.id, cid, "done")
    b.status = "paused"
    await prod.save_product(state, b)
    assert await prod.choose_product(state, cid) == (None, True)      # wait


@pytest.mark.asyncio
async def test_the_heartbeat_does_not_count_prospects_that_wait(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    cid = ids["muestra-retail.example"]
    await state.add_prospect(Prospect(first_name="Eva", last_name="Demo", title="Gerente",
                                      company="Muestra Retail", company_id=cid,
                                      email="eva@muestra-retail.example", email_status="verified"))
    assert await state.count_writable_prospects() == 1
    p = await prod.save_product(state, prod.Product(name="A", status="paused"))
    await prod.assign_accounts(state, p.id, [cid])
    assert await state.count_writable_prospects() == 0
    p.status = "active"
    await prod.save_product(state, p)
    assert await state.count_writable_prospects() == 1


# ── the Writer ──

class FakeBrain:
    paused_reason = ""
    last_reply_empty = False

    def __init__(self):
        self.prompts, self.skills_for = [], []

    def load_skills_for_agent(self, name, product_knowledge=None):
        self.skills_for.append(product_knowledge)
        return "SKILLS:" + (product_knowledge or "trained")

    def load_prompt(self, name, **kw):
        return "Producto: " + kw.get("product_name", "")

    async def think_json(self, prompt, **kw):
        self.prompts.append(prompt)
        return [{"step": 1, "subject": "una pregunta", "body": "Hola {{first_name}}, ¿quién decide en {{company}}?",
                 "delay_days": 0}]


@pytest.mark.asyncio
async def test_the_writer_writes_each_company_about_its_product(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    p = await prod.save_product(state, prod.Product(name="Agentes", description="d",
                                                   knowledge="Solo para direcciones generales."))
    shop, plant = ids["muestra-retail.example"], ids["ejemplo-industrial.example"]
    await prod.assign_accounts(state, p.id, [shop])
    for cid, name in ((shop, "Eva"), (plant, "Luis")):
        await state.add_prospect(Prospect(first_name=name, last_name="Demo", title="Gerente", company=name,
                                          company_id=cid, email=f"{name.lower()}@x.example",
                                          email_status="verified"))
    brain = FakeBrain()
    await Writer(brain, state, make_config(), None).run()
    async with state._connect() as db:
        async with db.execute("SELECT name, product_id FROM campaigns") as cursor:
            campaigns = {row[1]: row[0] for row in await cursor.fetchall()}
    assert set(campaigns) == {p.id, ""}
    assert campaigns[p.id].startswith("Agentes · ")
    joined = "\n".join(brain.prompts)
    assert "Producto: Agentes" in joined and "Producto: Plataforma Demo" in joined
    assert "SKILLS:# Agentes" in joined                        # its own knowledge, not the trained file
    assert (await prod.assignments(state, product_id=p.id))[0]["status"] == "active"


@pytest.mark.asyncio
async def test_the_writer_skips_a_company_waiting_for_its_next_product(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    cid = ids["muestra-retail.example"]
    p = await prod.save_product(state, prod.Product(name="A", status="paused"))
    await prod.assign_accounts(state, p.id, [cid])
    await state.add_prospect(Prospect(first_name="Eva", last_name="Demo", title="Gerente", company="M",
                                      company_id=cid, email="eva@x.example", email_status="verified"))
    brain = FakeBrain()
    await Writer(brain, state, make_config(), None).run()
    assert brain.prompts == []


# ── one sequence at a time ──

async def _run_sequence(state, product, cid, sent_days_ago, status="sent", prospect_status="contacted"):
    from harvey.models.campaign import Campaign
    pid = await state.add_prospect(Prospect(first_name="Eva", last_name="Demo", title="Gerente", company="M",
                                            company_id=cid, email="eva@x.example", email_status="verified"))
    camp = await state.add_campaign(Campaign(id="", name="c", product_id=product.id))
    when = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=sent_days_ago)).isoformat()
    item = await state.add_outbox_item(prospect_id=pid, campaign_id=camp, step=1, to_email="eva@x.example",
                                       subject="s", body="b", send_at=when, status=status, provider="smtp")
    if status == "sent":
        await state.update_outbox_item(item, sent_at=when)
    async with state._connect() as db:
        await db.execute("UPDATE outbox SET updated_at = ? WHERE id = ?", (when, item))
        await db.execute("UPDATE prospects SET status = ? WHERE id = ?", (prospect_status, pid))
        await db.commit()
    await prod.mark_started(state, product.id, cid)
    return pid


async def _two_products(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    cid = ids["muestra-retail.example"]
    first = await prod.save_product(state, prod.Product(name="Primero"))
    second = await prod.save_product(state, prod.Product(name="Segundo"))
    await prod.assign_accounts(state, first.id, [cid])
    await prod.assign_accounts(state, second.id, [cid])
    return cid, first, second


@pytest.mark.asyncio
async def test_after_the_cooldown_the_company_moves_to_its_next_product(state, tmp_path):
    cid, first, second = await _two_products(state, tmp_path)
    pid = await _run_sequence(state, first, cid, sent_days_ago=prod.NEXT_PRODUCT_COOLDOWN_DAYS + 1)
    assert await prod.advance_products(state) == 1
    status = {r["product_id"]: r["status"] for r in await prod.assignments(state, company_id=cid)}
    assert status == {first.id: "done", second.id: "pending"}
    assert (await state.get_prospect(pid)).status == "new"
    assert (await prod.choose_product(state, cid))[0].name == "Segundo"


@pytest.mark.asyncio
async def test_a_recent_or_waiting_sequence_keeps_its_product(state, tmp_path):
    cid, first, _ = await _two_products(state, tmp_path)
    pid = await _run_sequence(state, first, cid, sent_days_ago=3)
    assert await prod.advance_products(state) == 0
    assert (await state.get_prospect(pid)).status == "contacted"


@pytest.mark.asyncio
async def test_an_approved_email_still_waiting_keeps_its_product(state, tmp_path):
    cid, first, _ = await _two_products(state, tmp_path)
    await _run_sequence(state, first, cid, sent_days_ago=60, status="approved", prospect_status="queued")
    assert await prod.advance_products(state) == 0
    assert {r["status"] for r in await prod.assignments(state, product_id=first.id)} == {"active"}


@pytest.mark.asyncio
async def test_a_reply_ends_it_without_opening_the_next_product(state, tmp_path):
    cid, first, second = await _two_products(state, tmp_path)
    pid = await _run_sequence(state, first, cid, sent_days_ago=1, prospect_status="replied")
    assert await prod.advance_products(state) == 0
    status = {r["product_id"]: r["status"] for r in await prod.assignments(state, company_id=cid)}
    assert status == {first.id: "done", second.id: "pending"}
    assert (await state.get_prospect(pid)).status == "replied"


# ── the configured product becomes the first one ──

@pytest.mark.asyncio
async def test_the_configured_product_is_created_once_with_every_account(state, tmp_path):
    ids, _ = await import_csv(state, tmp_path)
    created = await prod.ensure_default_product(state, make_config())
    assert created.name == "Plataforma Demo" and created.icp.titles == ["Gerente"]
    rows = await prod.assignments(state, product_id=created.id)
    assert {r["company_id"] for r in rows} == set(ids.values())
    assert {r["batch"] for r in rows} == {"lote-01"}
    assert {r["score"] for r in rows} == {0, 10}
    await prod.delete_product(state, created.id)
    assert await prod.ensure_default_product(state, make_config()) is None   # never again
    assert await prod.list_products(state) == []


@pytest.mark.asyncio
async def test_an_untrained_config_creates_no_product(state):
    config = make_config(product={"name": "Your Product", "description": "", "pricing": "",
                                  "key_benefits": [], "objection_responses": {}})
    assert await prod.ensure_default_product(state, config) is None
    assert await prod.list_products(state) == []


# ── the skills ──

def test_a_products_knowledge_replaces_the_trained_file(tmp_path, monkeypatch):
    from harvey import brain as brain_mod
    (tmp_path / "product_knowledge.md").write_text("TRAINED", encoding="utf-8")
    (tmp_path / "competitive_intel.md").write_text("RIVALS", encoding="utf-8")
    (tmp_path / "email_frameworks.md").write_text("AIDA", encoding="utf-8")
    monkeypatch.setattr(brain_mod, "SKILLS_DIR", tmp_path)
    b = brain_mod.Brain.__new__(brain_mod.Brain)
    default = b.load_skills_for_agent("writer")
    assert "TRAINED" in default and "RIVALS" in default and "AIDA" in default
    own = b.load_skills_for_agent("writer", product_knowledge="OWN")
    assert "OWN" in own and "AIDA" in own
    assert "TRAINED" not in own and "RIVALS" not in own
