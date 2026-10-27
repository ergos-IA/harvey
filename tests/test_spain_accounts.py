"""Hand-picked accounts: CSV import, tracked-account queries, ICP scoring.

Every company and person here is fictional (example.com / .test domains).
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from harvey.accounts_config import ScoringConfig, ScoringRule
from harvey.collectors.spain.accounts import (
    import_accounts, normalize_domain, parse_number, read_rows, tracked_accounts,
)
from harvey.collectors.spain.text import (
    company_key, name_in_text, normalize_cif, same_company, same_province,
)
from harvey.scoring import current_rows, event_date, score_accounts, score_company
from harvey.signals import SIGNAL_CATALOG, seed_signal_catalog
from harvey.state import StateManager


@pytest_asyncio.fixture
async def state():
    with tempfile.TemporaryDirectory() as tmp:
        sm = StateManager(os.path.join(tmp, "t.db"))
        await sm.init_db()
        await seed_signal_catalog(sm)
        yield sm


def _csv(tmp_path, text, name="lote-01.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


CSV = (
    "Nombre;Dominio;CIF;Segmento;Provincia;Empleados;Facturación;Notas\n"
    "Industrias Ejemplo, S.L.;https://www.industrias-ejemplo.example/;B-12.345.678;Industrial;"
    "Zaragoza;1.200;12,5 M€;Contacto vía feria\n"
    "Distribuciones Prueba SA;distribuciones-prueba.test;ES A87654321;distribución;Valencia;"
    "51-200;3.400.000;\n"
    "Sin Dominio SL;;;;;;;\n"
)


# ── text helpers ──

def test_company_key_drops_legal_forms_and_accents():
    for name in ("Industrias Ejemplo, S.L.", "INDUSTRIAS EJEMPLO SL", "Industrias Ejemplo Sociedad Limitada",
                 "Industrias Ejemplo S.L.U.", "industrias ejemplo, s. l."):
        assert company_key(name) == "industrias ejemplo", name
    assert company_key("Construcciones Ñandú S.A.") == "construcciones nandu"
    assert same_company("Talleres Prueba SA", "TALLERES PRUEBA, S.A.")
    # Equal cores only, never a substring.
    assert not same_company("Prueba", "Prueba Logistica SL")
    assert name_in_text("Talleres Prueba SL", "Talleres Prueba abre nueva planta en Teruel")
    assert not name_in_text("Talleres Prueba SL", "Talleres Pruebas del Norte abre planta")


def test_cif_and_province_normalisation():
    assert normalize_cif("B-12.345.678") == "B12345678"
    assert normalize_cif("ES A87654321") == "A87654321"
    assert normalize_cif("12345678Z") == ""          # a NIF of a person, not a CIF
    assert same_province("ALICANTE/ALACANT", "Alicante")
    assert same_province("BIZKAIA", "Vizcaya")
    assert same_province("ILLES BALEARS", "Baleares")
    assert not same_province("MADRID", "Barcelona")


@pytest.mark.parametrize("raw,expected", [
    ("1.200", 1200), ("1.200.000,50", 1200000.5), ("12,5 M€", 12_500_000), ("3,2M", 3_200_000),
    ("850", 850), ("51-200", 125.5), ("1,5", 1.5), ("2.500.000", 2_500_000), ("", None), ("n/d", None),
])
def test_spanish_number_formats(raw, expected):
    assert parse_number(raw)[0] == expected


def test_domains_are_normalised_or_rejected():
    assert normalize_domain("https://www.Ejemplo.example/contacto?x=1") == "ejemplo.example"
    assert normalize_domain("info@ejemplo.test") == "ejemplo.test"
    assert normalize_domain("not a domain") == ""


def test_rows_parse_spanish_headers_and_report_problems():
    rows, problems = read_rows(CSV)
    assert [r.domain for r in rows] == ["industrias-ejemplo.example", "distribuciones-prueba.test"]
    first = rows[0]
    assert (first.cif, first.segment, first.province, first.employees, first.revenue_eur) == (
        "B12345678", "industrial", "Zaragoza", 1200, 12_500_000)
    assert any("línea 4" in p and "dominio" in p for p in problems)


def test_a_file_without_name_and_domain_is_refused():
    rows, problems = read_rows("empresa,ciudad\nAcme,Soria\n")
    assert rows == [] and "name" in problems[0]


# ── import ──

@pytest.mark.asyncio
async def test_import_creates_companies_observations_and_tags(state, tmp_path):
    report = await import_accounts(state, _csv(tmp_path, CSV), batch="lote-01")
    assert (report.created, report.updated) == (2, 0)
    company = await state.get_company_by_domain("industrias-ejemplo.example")
    assert company.source == "import" and company.location == "Zaragoza"
    obs = {o["signal_code"]: o for o in await state.get_observations(company_id=company.id)}
    assert obs["ACCOUNT_TRACKED"]["value_text"] == "lote-01"
    assert obs["ACCOUNT_SEGMENT"]["value_text"] == "industrial"
    assert obs["EMPLOYEE_COUNT"]["value_num"] == 1200
    assert obs["REVENUE_EUR"]["value_num"] == 12_500_000
    assert obs["COMPANY_CIF"]["value_text"] == "B12345678"
    assert all(o["collector"] == "import" for o in obs.values())
    assert obs["EMPLOYEE_COUNT"]["evidence_url"] == "file:lote-01.csv#L2"

    tracked = await tracked_accounts(state)
    assert [t["domain"] for t in tracked] == ["distribuciones-prueba.test", "industrias-ejemplo.example"]
    assert [t["domain"] for t in await tracked_accounts(state, segment="Industrial")] == [
        "industrias-ejemplo.example"]
    assert await tracked_accounts(state, batch="lote-99") == []


@pytest.mark.asyncio
async def test_reimport_dedups_by_domain_and_writes_only_changes(state, tmp_path):
    await import_accounts(state, _csv(tmp_path, CSV), batch="lote-01")
    before = len(await state.get_observations())
    again = await import_accounts(state, _csv(tmp_path, CSV), batch="lote-01")
    assert (again.created, again.updated, again.observations) == (0, 2, 0)
    assert len(await state.get_observations()) == before

    changed = CSV.replace("1.200;", "1.350;")
    report = await import_accounts(state, _csv(tmp_path, changed), batch="lote-01")
    assert report.observations == 1
    company = await state.get_company_by_domain("industrias-ejemplo.example")
    [emp] = await state.get_observations(company_id=company.id, signal_code="EMPLOYEE_COUNT",
                                         latest_only=True)
    assert emp["value_num"] == 1350


@pytest.mark.asyncio
async def test_import_updates_a_company_discovered_earlier(state, tmp_path):
    from harvey.models.company import Company
    cid = await state.add_company(Company(name="Old Name", domain="industrias-ejemplo.example"))
    report = await import_accounts(state, _csv(tmp_path, CSV))
    assert report.updated == 1 and cid in report.company_ids
    assert (await state.get_company(cid)).name == "Industrias Ejemplo, S.L."
    # Default batch: the file's name.
    [t] = await tracked_accounts(state, segment="industrial")
    assert t["batch"] == "lote-01"


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(state, tmp_path):
    report = await import_accounts(state, _csv(tmp_path, CSV), dry_run=True)
    assert report.created == 2
    assert await tracked_accounts(state) == []


def test_new_signals_are_in_the_catalog_with_spanish_labels_and_free_cost_notes():
    codes = {s["code"]: s for s in SIGNAL_CATALOG}
    for code in ("ACCOUNT_TRACKED", "EMPLOYEE_COUNT", "MULTILANG_SITE", "HELPDESK_TOOL",
                 "ECOMMERCE_PLATFORM", "B2B_PORTAL", "ERP_MENTION", "HIRING_FUNCTION",
                 "BORME_APPOINTMENT", "BORME_CAPITAL", "BORME_MERGER", "NEWS_EXPANSION",
                 "NEWS_ACQUISITION", "NEWS_INVESTOR", "NEWS_LEADERSHIP", "ICP_SCORE"):
        assert code in codes
        assert codes[code]["cost_note"].lower().startswith("gratis")
    assert len(codes) == len(SIGNAL_CATALOG), "codes must be unique"
    assert "personal y no comercial" in codes["NEWS_EXPANSION"]["cost_note"]


# ── scoring ──

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _rule(**kw):
    return ScoringRule(**kw)


def test_rule_conditions_validate():
    with pytest.raises(ValueError):
        ScoringRule(signal="X", when={"older_than": 3}, points=1)
    with pytest.raises(ValueError):
        ScoringRule(signal="X", when={"between": [1]}, points=1)
    assert ScoringRule(signal="x", when="absent").when == {"exists": False}
    assert ScoringRule(signal="X", when={"contains_any": "SAP"}).when == {"contains_any": ["SAP"]}


def test_current_rows_are_the_newest_batch_and_positive():
    rows = [
        {"run_id": "r2", "value_num": None, "value_text": "a", "observed_at": "2026-10-20 10:00:00"},
        {"run_id": "r2", "value_num": 0, "value_text": "", "observed_at": "2026-10-20 10:00:00"},
        {"run_id": "r1", "value_num": None, "value_text": "old", "observed_at": "2026-09-01 10:00:00"},
    ]
    assert [r["value_text"] for r in current_rows(rows)] == ["a"]
    assert event_date({"value_text": "x · posted 2026-07-01", "observed_at": "2026-10-01"}).date().isoformat() \
        == "2026-07-01"


@pytest.mark.asyncio
async def test_score_is_explainable_and_stored(state, tmp_path):
    await import_accounts(state, _csv(tmp_path, CSV), batch="lote-01")
    company = await state.get_company_by_domain("industrias-ejemplo.example")
    old = (NOW - timedelta(days=75)).date().isoformat()
    await state.add_observations([
        {"signal_code": "HIRING_FUNCTION", "company_id": company.id, "collector": "jobs",
         "value_text": f"ventas internas · Comercial interno · Ventas · Zaragoza · posted {old} · Personio"},
        {"signal_code": "BORME_APPOINTMENT", "company_id": company.id, "collector": "borme",
         "value_text": f"{(NOW - timedelta(days=400)).date()} · Nombramientos. Adm. Unico: X."},
        {"signal_code": "TECH_STACK", "company_id": company.id, "collector": "profile",
         "value_text": "PrestaShop, Zendesk"},
        {"signal_code": "MULTILANG_SITE", "company_id": company.id, "collector": "profile",
         "value_num": 0},
    ], run_id="p1")
    config = ScoringConfig(threshold=40, rules=[
        _rule(signal="EMPLOYEE_COUNT", when={"between": [50, 1000]}, points=10),
        _rule(signal="REVENUE_EUR", when={"min": 10_000_000}, points=10),
    ], segments={"industrial": {"rules": [
        _rule(signal="HIRING_FUNCTION", when={"older_than_days": 60}, points=25),
        _rule(signal="BORME_APPOINTMENT", when={"within_months": 6}, points=20),
        _rule(signal="TECH_STACK", when={"contains_any": ["prestashop", "magento"]}, points=5),
        _rule(signal="MULTILANG_SITE", points=10),
        _rule(signal="HELPDESK_TOOL", when={"exists": False}, points=3, label="sin helpdesk"),
    ]}})
    score = await score_company(state, config, company.id, "industrial", now=NOW)
    # 1200 employees is outside 50-1000; the BORME act is too old; MULTILANG is a 0.
    assert score.score == 10 + 25 + 5 + 3
    assert [d for _, d in score.fired] == [
        "REVENUE_EUR min=10000000", "HIRING_FUNCTION older_than_days=60",
        "TECH_STACK contains_any=['prestashop', 'magento']", "sin helpdesk"]

    accounts = await tracked_accounts(state)
    results = await score_accounts(state, config, accounts, now=NOW)
    assert results[0][0]["id"] == company.id
    [stored] = await state.get_observations(company_id=company.id, signal_code="ICP_SCORE")
    assert stored["value_num"] == 43 and stored["collector"] == "scoring"
    assert "HIRING_FUNCTION older_than_days=60" in stored["value_text"]
    # The dashboard's cohort builder takes it as a range, unchanged.
    size, rows = await state.cohort_companies([], [], ranges=[{"code": "ICP_SCORE", "min": 40}])
    assert size == 1 and rows[0]["id"] == company.id


@pytest.mark.asyncio
async def test_a_rejected_icp_score_is_not_stored(state, tmp_path):
    await import_accounts(state, _csv(tmp_path, CSV))
    await state.set_signal_status("ICP_SCORE", "rejected")
    config = ScoringConfig(rules=[_rule(signal="EMPLOYEE_COUNT", points=5)])
    results = await score_accounts(state, config, await tracked_accounts(state), now=NOW)
    assert all(s.score == 5 for _, s in results)
    assert await state.get_observations(signal_code="ICP_SCORE") == []


def test_config_sections_are_optional_and_parse():
    from harvey.config import HarveyConfig
    base = dict(
        persona={"name": "A", "company": "B", "role": "C", "email": "a@example.com",
                 "linkedin": "", "tone": "x"},
        product={"name": "P", "description": "d", "pricing": "p", "key_benefits": [],
                 "objection_responses": {}},
        icp={"industries": [], "company_size": "50-1000", "titles": [], "geography": ["España"]},
    )
    plain = HarveyConfig(**base)
    assert not plain.scoring.configured() and plain.accounts.borme_days == 7
    full = HarveyConfig(**base, scoring={"threshold": 50, "segments": {"industrial": {"rules": [
        {"signal": "hiring_function", "when": {"older_than_days": 60}, "points": 20}]}}},
        accounts={"news_months": 12})
    assert full.scoring.segments["industrial"].rules[0].signal == "HIRING_FUNCTION"
    assert full.accounts.news_months == 12


def test_cli_registers_accounts_commands(monkeypatch, capsys):
    import sys
    from harvey import cli
    seen = {}
    monkeypatch.setattr("harvey.cli_accounts.cmd_accounts", lambda args: seen.update(vars(args)))
    import harvey.cli_accounts as ca
    monkeypatch.setattr(sys, "argv", ["harvey", "accounts", "enrich", "--only", "borme,news",
                                      "--segment", "industrial"])
    # register() binds cmd_accounts at parse time; re-point it for the test.
    real_register = ca.register

    def register(subparsers):
        real_register(subparsers)
        subparsers.choices["accounts"].set_defaults(func=lambda args: seen.update(vars(args)))

    monkeypatch.setattr(ca, "register", register)
    cli.main()
    assert seen["accounts_action"] == "enrich" and seen["only"] == "borme,news"
    assert seen["segment"] == "industrial"
