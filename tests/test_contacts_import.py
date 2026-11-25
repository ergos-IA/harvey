"""harvey contacts import: named people for accounts on file (harvey/contacts_import.py).

Every company, person and address here is invented (.test / example.test).
The email finder is a fake: no network, no verifier.
"""

import json

import pytest
import pytest_asyncio

from harvey import contacts_import as ci
from harvey.integrations.email_finder import EmailResult
from harvey.models.company import Company
from harvey.models.prospect import COMPANY_INBOX_SOURCE, Prospect
from harvey.state import StateManager


@pytest_asyncio.fixture
async def state(tmp_path):
    s = StateManager(str(tmp_path / "c.db"))
    await s.init_db()
    return s


def fake_finder(statuses: dict):
    """first.last@domain with the status given per first name (default verified)."""
    calls = []

    async def finder(first, last, domain, **kw):
        calls.append((first, last, domain, kw.get("other_people")))
        email = f"{first}.{last}@{domain}".lower()
        return EmailResult(email=email, status=statuses.get(first, "verified"))
    finder.calls = calls
    return finder


async def _company(state, domain="rodillos.test", description=""):
    cid = await state.add_company(Company(name="Rodillos Demo", domain=domain, description=description))
    return cid


@pytest.mark.parametrize("full, expected", [
    ("Ana Ruiz", ("Ana", "Ruiz", "Ana", "Ruiz")),
    ("Emilio Ortega Pardo", ("Emilio", "Ortega Pardo", "Emilio", "Ortega")),
    ("Francisco José Tarín", ("Francisco José", "Tarín", "Francisco", "Tarín")),
    ("MARIA JOSE GIL GARRIDO", ("Maria Jose", "Gil Garrido", "Maria", "Gil")),
    ("esteve vidal soler", ("Esteve", "Vidal Soler", "Esteve", "Vidal")),
    ("Luis de la Fuente", ("Luis", "de la Fuente", "Luis", "Fuente")),
    ("Miguel Pardo de Haro", ("Miguel", "Pardo de Haro", "Miguel", "Pardo")),
    ("Juan Antonio Mora Puig De Oca", ("Juan Antonio", "Mora Puig De Oca", "Juan", "Mora")),
])
def test_split_name(full, expected):
    assert ci.split_name(full) == expected


def test_load_rows_reads_semicolon_csv_and_json(tmp_path):
    csv_file = tmp_path / "p.csv"
    csv_file.write_text("domain;name;title\nhttps://www.Rodillos.test/;Ana Ruiz;Directora Comercial\n;Sin Dominio;X\n",
                        encoding="utf-8")
    rows = ci.load_rows(csv_file)
    assert [(r.domain, r.name, r.title) for r in rows] == [("rodillos.test", "Ana Ruiz", "Directora Comercial")]
    js = tmp_path / "p.json"
    js.write_text(json.dumps([{"domain": "a.test", "full_name": "Jo Li", "since": "2011-11"}]), encoding="utf-8")
    assert ci.load_rows(js)[0].since == "2011-11"


@pytest.mark.asyncio
async def test_adds_the_first_reachable_person_with_notes(state):
    cid = await _company(state)
    rows = [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="Directora Comercial", since="2011-11",
                   notes="Lleva la red de distribuidores.", linkedin_url="https://linkedin.example.test/in/ana"),
            ci.Row(domain="rodillos.test", name="Jo Li", title="Gerente")]
    finder = fake_finder({"Ana": "guess"})
    report = await ci.import_contacts(state, rows, finder=finder)
    assert [e["name"] for e in report.unreachable] == ["Ana Ruiz"]
    assert [e["email"] for e in report.added] == ["jo.li@rodillos.test"]
    # the other person named there is passed on, so the verifier never confirms their mailbox for this one
    assert finder.calls[0][3] == [("Jo", "Li")]
    people = await state.get_contacts_for_company(cid)
    assert len(people) == 1 and people[0].source == ci.SOURCE and people[0].seniority == "c_suite"
    assert people[0].status == "new" and people[0].email_status == "verified"


@pytest.mark.asyncio
async def test_research_notes_carry_role_and_tenure(state):
    await _company(state)
    rows = [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="Directora Comercial", since="2011-11",
                   notes="Lleva la red de distribuidores.")]
    await ci.import_contacts(state, rows, finder=fake_finder({}))
    p = (await state.get_prospects_by_status("new"))[0]
    assert p.personalization_notes == ("Directora Comercial en Rodillos Demo desde 2011. "
                                       "Lleva la red de distribuidores.")


@pytest.mark.asyncio
async def test_per_company_limit_and_unknown_companies(state):
    await _company(state)
    rows = [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO"),
            ci.Row(domain="rodillos.test", name="Jo Li", title="Gerente"),
            ci.Row(domain="nadie.test", name="Eva Sol", title="CEO")]
    report = await ci.import_contacts(state, rows, finder=fake_finder({}))
    assert len(report.added) == 1
    reasons = sorted(s["reason"] for s in report.skipped)
    assert reasons == ["empresa no importada", "ya hay persona en esta empresa"]
    # a second run adds nobody: the company already has its person
    again = await ci.import_contacts(state, rows[:1], finder=fake_finder({}))
    assert not again.added


@pytest.mark.asyncio
async def test_dry_run_stores_nothing(state):
    cid = await _company(state)
    report = await ci.import_contacts(state, [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO")],
                                      finder=fake_finder({}), dry_run=True)
    assert len(report.added) == 1
    assert await state.get_contacts_for_company(cid) == []


@pytest.mark.asyncio
async def test_a_reachable_person_replaces_the_unsent_inbox(state):
    cid = await _company(state)
    inbox_id = await state.add_prospect(Prospect(
        email="info@rodillos.test", email_status="verified", company="Rodillos Demo", company_id=cid,
        title="General inbox", source=COMPANY_INBOX_SOURCE))
    await state.update_prospect_status(inbox_id, "queued")
    item = await state.add_outbox_item(prospect_id=inbox_id, to_email="info@rodillos.test", subject="s",
                                       body="b", send_at="2026-01-01T09:00:00", campaign_id="c1")
    report = await ci.import_contacts(state, [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO")],
                                      finder=fake_finder({}))
    assert report.inboxes_replaced == 1 and report.outbox_rejected == 1
    by_id = {p.id: p for p in await state.get_contacts_for_company(cid)}
    assert by_id[inbox_id].status == ci.REPLACED
    async with state._connect() as db:
        async with db.execute("SELECT status FROM outbox WHERE id = ?", (item,)) as cur:
            assert (await cur.fetchone())[0] == "rejected"


@pytest.mark.asyncio
async def test_an_inbox_already_written_to_is_left_alone(state):
    cid = await _company(state)
    inbox_id = await state.add_prospect(Prospect(
        email="info@rodillos.test", email_status="verified", company="Rodillos Demo", company_id=cid,
        title="General inbox", source=COMPANY_INBOX_SOURCE))
    await state.add_outbox_item(prospect_id=inbox_id, to_email="info@rodillos.test", subject="s",
                                body="b", send_at="2026-01-01T09:00:00", status="sent", campaign_id="c1")
    report = await ci.import_contacts(state, [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO")],
                                      finder=fake_finder({}))
    assert len(report.added) == 1 and report.inboxes_replaced == 0


@pytest.mark.asyncio
async def test_fills_an_empty_company_description_only(state):
    empty = await _company(state)
    full = await _company(state, domain="otra.test", description="Ya descrita.")
    rows = [ci.Row(domain="rodillos.test", name="Ana Ruiz", company_description="Fabrica rodillos."),
            ci.Row(domain="otra.test", name="Jo Li", company_description="Otra cosa.")]
    report = await ci.import_contacts(state, rows, finder=fake_finder({}))
    assert report.descriptions_filled == 1
    assert (await state.get_company(empty)).description == "Fabrica rodillos."
    assert (await state.get_company(full)).description == "Ya descrita."


def fake_verifier(good: set, *, answer=True):
    calls = []

    async def verifier(email, mx_type, env):
        calls.append(email)
        if not answer:
            return None, False
        return ("verified" if email in good else "invalid"), False
    verifier.calls = calls
    return verifier


@pytest.mark.asyncio
async def test_a_rejected_address_tries_other_formats_and_remembers_the_right_one(state):
    await _company(state)
    verifier = fake_verifier({"aruiz@rodillos.test"})
    report = await ci.import_contacts(state, [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO")],
                                      finder=fake_finder({"Ana": "invalid"}), verifier=verifier)
    assert [e["email"] for e in report.added] == ["aruiz@rodillos.test"]
    assert verifier.calls == ["aruiz@rodillos.test"]
    assert (await state.get_email_pattern("rodillos.test"))["pattern"] == "{fi}{l}"


@pytest.mark.asyncio
async def test_no_verifier_answer_stops_the_search(state):
    await _company(state)
    verifier = fake_verifier(set(), answer=False)
    report = await ci.import_contacts(state, [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO")],
                                      finder=fake_finder({"Ana": "invalid"}), verifier=verifier)
    assert not report.added and len(verifier.calls) == 1


@pytest.mark.asyncio
async def test_an_initial_shared_with_a_colleague_is_not_tried(state):
    await _company(state)
    verifier = fake_verifier(set())
    rows = [ci.Row(domain="rodillos.test", name="Ana Ruiz", title="CEO"),
            ci.Row(domain="rodillos.test", name="Alba Ruiz", title="Gerente")]
    await ci.import_contacts(state, rows, finder=fake_finder({"Ana": "invalid", "Alba": "invalid"}),
                             verifier=verifier, per_company=2)
    assert not any(e.startswith(("aruiz@", "a.ruiz@")) for e in verifier.calls)
