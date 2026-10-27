"""`harvey accounts enrich` and the heartbeat stage: confirmed signals only,
tracked accounts only, safe to re-run. All HTTP is mocked; all data fictional."""

import os
import tempfile
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

import harvey.collectors.profile as profile_mod
from harvey.accounts_config import AccountsConfig
from harvey.collectors.profile import ProfileCollector
from harvey.collectors.spain import borme as borme_mod
from harvey.collectors.spain.accounts import import_accounts
from harvey.collectors.spain.enrich import enrich_accounts
from harvey.pipeline import run_account_signals_stage
from harvey.signals import seed_signal_catalog
from harvey.state import StateManager
from tests.test_spain_borme import SECTION_XML, SUMARIO
from tests.test_spain_news import FEED

CSV = ("name,domain,province,segment\n"
       "Industrias Ejemplo SL,industrias-ejemplo.example,Zaragoza,industrial\n"
       "Talleres Muestra SL,muestra.test,Zaragoza,industrial\n")


@pytest_asyncio.fixture
async def state(tmp_path):
    with tempfile.TemporaryDirectory() as tmp:
        sm = StateManager(os.path.join(tmp, "t.db"))
        await sm.init_db()
        await seed_signal_catalog(sm)
        path = tmp_path / "lote.csv"
        path.write_text(CSV, encoding="utf-8")
        await import_accounts(sm, path, batch="lote-01")
        yield sm


def _http(seen):
    def handler(request):
        url = str(request.url)
        seen.append(url)
        if "/api/borme/sumario/" in url:
            return httpx.Response(200, json=SUMARIO) if url.endswith("20261023") else httpx.Response(404)
        if url.endswith("BORME-A-2026-205-50"):
            return httpx.Response(200, content=SECTION_XML, headers={"content-type": "application/xml"})
        if url.startswith("https://news.google.com/rss/search"):
            return httpx.Response(200, content=FEED, headers={"content-type": "application/xml"})
        return httpx.Response(404, text="")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _fixed_borme_day(monkeypatch):
    monkeypatch.setattr(borme_mod, "recent_days", lambda days, today=None: [date(2026, 10, 23)])


async def _confirm(state, *codes):
    for code in codes:
        await state.set_signal_status(code, "confirmed")


@pytest.mark.asyncio
async def test_nothing_is_collected_until_confirmed(state):
    seen = []
    async with _http(seen) as http:
        report = await enrich_accounts(state, only=["borme", "news", "jobs"], http_client=http)
    assert seen == []
    assert set(report.skipped) == {"borme", "news", "jobs"}


@pytest.mark.asyncio
async def test_borme_and_news_write_once(state):
    await _confirm(state, "BORME_MERGER", "BORME_APPOINTMENT", "NEWS_EXPANSION", "NEWS_LEADERSHIP")
    seen = []
    async with _http(seen) as http:
        first = await enrich_accounts(state, only=["borme", "news"], http_client=http)
        again = await enrich_accounts(state, only=["borme", "news"], http_client=http)
    assert first.written == {"borme": 2, "news": 2}
    assert again.written == {"borme": 0, "news": 0}, "re-running must not duplicate events"
    company = await state.get_company_by_domain("industrias-ejemplo.example")
    codes = sorted(o["signal_code"] for o in await state.get_observations(company_id=company.id)
                   if o["collector"] in ("borme", "news"))
    assert codes == ["BORME_APPOINTMENT", "NEWS_EXPANSION", "NEWS_LEADERSHIP"]
    # Talleres Muestra's merger; its headlines don't name it.
    muestra = await state.get_company_by_domain("muestra.test")
    assert [o["signal_code"] for o in await state.get_observations(company_id=muestra.id)
            if o["collector"] == "borme"] == ["BORME_MERGER"]
    # Unconfirmed BORME_CAPITAL / NEWS_INVESTOR were left alone.
    assert await state.get_observations(signal_code="NEWS_INVESTOR") == []


@pytest.mark.asyncio
async def test_segment_filter_and_no_accounts(state):
    seen = []
    await _confirm(state, "NEWS_EXPANSION")
    async with _http(seen) as http:
        report = await enrich_accounts(state, only="news", segment="otro", http_client=http)
    assert report.accounts == 0 and seen == []
    assert "harvey accounts import" in report.notes[0]


@pytest.mark.asyncio
async def test_web_profiles_tracked_accounts_and_keeps_their_names(state, monkeypatch):
    await _confirm(state, "MULTILANG_SITE", "HELPDESK_TOOL")
    monkeypatch.setattr(profile_mod.random, "uniform", lambda a, b: 0)
    home = ("<html lang='es'><head><title>Otro Nombre Comercial</title>"
            "<link rel='alternate' hreflang='es' href='/'><link rel='alternate' hreflang='en' href='/en/'>"
            "</head><body><script src='https://widget.intercom.io/widget/x'></script></body></html>")
    collector = ProfileCollector(state, await state.confirmed_signal_codes())

    async def fake_get(url):
        return home if url == "https://industrias-ejemplo.example" else ""

    collector._get = fake_get
    report = await enrich_accounts(state, only="web", profile_collector=collector,
                                   http_client=_http([]))
    assert report.written["web"] == 2
    company = await state.get_company_by_domain("industrias-ejemplo.example")
    got = {o["signal_code"]: o for o in await state.get_observations(company_id=company.id)
           if o["collector"] == "profile"}
    assert got["MULTILANG_SITE"]["value_num"] == 1 and got["HELPDESK_TOOL"]["value_text"] == "Intercom"
    assert company.name == "Industrias Ejemplo SL"


@pytest.mark.asyncio
async def test_jobs_without_infojobs_credentials_notes_it(state, monkeypatch):
    monkeypatch.delenv("INFOJOBS_CLIENT_ID", raising=False)
    monkeypatch.delenv("INFOJOBS_CLIENT_SECRET", raising=False)
    await _confirm(state, "HIRING_FUNCTION")

    class NoSite:
        _client = None

        async def _resolve_site(self, domain):
            return "", ""

    report = await enrich_accounts(state, only="jobs", profile_collector=NoSite(), http_client=_http([]))
    assert report.written["jobs"] == 0
    assert any("INFOJOBS_CLIENT_ID" in n for n in report.notes)


@pytest.mark.asyncio
async def test_heartbeat_stage_respects_cadence_and_switch(state, monkeypatch):
    calls = []

    async def fake_enrich(state, config, only=None, stale_days=None, limit=None, **kw):
        calls.append((tuple(only), stale_days, limit))
        return SimpleNamespace(written={k: 0 for k in only}, summary_lines=lambda: [])

    monkeypatch.setattr("harvey.collectors.spain.enrich.enrich_accounts", fake_enrich)
    config = SimpleNamespace(accounts=AccountsConfig())
    assert await run_account_signals_stage(state, config) == {}      # nothing confirmed
    await _confirm(state, "BORME_APPOINTMENT", "NEWS_EXPANSION")
    await run_account_signals_stage(state, config)
    assert calls == [(("borme", "news"), 7, 10)]
    off = SimpleNamespace(accounts=AccountsConfig(heartbeat=False))
    assert await run_account_signals_stage(state, off) == {}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_heartbeat_cadence_skips_borme_read_recently(state):
    await _confirm(state, "BORME_APPOINTMENT")
    seen = []
    async with _http(seen) as http:
        await enrich_accounts(state, only="borme", stale_days=7, http_client=http)
        n = len(seen)
        report = await enrich_accounts(state, only="borme", stale_days=7, http_client=http)
    assert len(seen) == n and report.skipped == {"borme": "leído hace poco"}
