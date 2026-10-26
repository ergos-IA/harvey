"""Spanish job boards, InfoJobs, and the watched-function HIRING_FUNCTION signal.

Feed shapes follow what each vendor publishes (checked against the vendors'
own public boards, October 2026); every company and role here is fictional.
"""

import json

import httpx
import pytest

from harvey.collectors.ats import Board, detect_board, feed_url, read_board
from harvey.collectors.spain import ats_es, infojobs
from harvey.collectors.spain.jobs import collect_jobs, compile_functions, function_of, normalize_title

PERSONIO_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
<position><id>101</id><office>Zaragoza</office><department>Ventas</department>
  <name>T\xc3\xa9cnico/a comercial</name><createdAt>2026-07-01T09:00:00+00:00</createdAt></position>
<position><id>102</id><office>Zaragoza</office><department>Producci\xc3\xb3n</department>
  <name>Operario de producci\xc3\xb3n</name><createdAt>2026-10-01T09:00:00+00:00</createdAt></position>
</workzag-jobs>"""

TEAMTAILOR_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations"><channel><title>Ejemplo</title>
<item><title>Customer Care Specialist</title>
<link>https://ejemplo.teamtailor.com/jobs/1-customer-care</link>
<pubDate>Fri, 24 Jul 2026 09:05:16 +0200</pubDate>
<tt:locations><tt:location><tt:city>Valencia</tt:city></tt:location></tt:locations></item>
</channel></rss>"""

SMARTRECRUITERS = {"content": [
    {"id": "9001", "name": "Ingeniero/a de Ofertas", "releasedDate": "2026-06-15T10:00:00.000Z",
     "location": {"city": "Bilbao", "region": "Bizkaia"}, "department": {"label": "Oficina técnica"}},
]}

JOIN_HTML = ('<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {
    "pageProps": {"initialState": {"jobs": {"items": [
        {"idParam": "77-administrativo-pedidos", "title": "Administrativo/a de pedidos",
         "createdAt": "2026-08-10T10:00:00.000Z", "city": {"cityName": "Sevilla"},
         "category": {"name": "Administración"}},
    ]}}}}}) + "</script></html>")

FACTORIAL_HTML = ('<html><body><a href="/job_posting/oficina-tecnica-123">Técnico de oficina técnica</a>'
                  '<a href="/about">Sobre nosotros</a></body></html>')


@pytest.mark.parametrize("html,ats,token", [
    ('<a href="https://ejemplo.jobs.personio.de/">Empleo</a>', "personio", "ejemplo"),
    ('<a href="https://ejemplo.jobs.personio.com/">Empleo</a>', "personio_com", "ejemplo"),
    ('<a href="https://ejemplo.teamtailor.com/jobs">Trabaja con nosotros</a>', "teamtailor", "ejemplo"),
    ('<a href="https://careers.smartrecruiters.com/EjemploSA">Ofertas</a>', "smartrecruiters", "EjemploSA"),
    ('<a href="https://join.com/companies/ejemplo">Jobs</a>', "join", "ejemplo"),
    ('<a href="https://ejemplo.factorialhr.com/">Empleo</a>', "factorial", "ejemplo"),
])
def test_spanish_boards_are_detected_from_their_site(html, ats, token):
    assert detect_board(html, "ejemplo.example") == Board(ats, token)


def test_vendor_pages_are_not_boards():
    assert detect_board('<a href="https://www.personio.de/">HR software</a>'
                        '<a href="https://app.teamtailor.com/login">x</a>', "ejemplo.example") is None


def test_feed_and_page_urls():
    assert feed_url(Board("personio", "ejemplo")) == "https://ejemplo.jobs.personio.de/xml"
    assert feed_url(Board("teamtailor", "ejemplo")) == "https://ejemplo.teamtailor.com/jobs.rss"
    assert Board("join", "ejemplo").page_url == "https://join.com/companies/ejemplo"
    assert Board("smartrecruiters", "EjemploSA").label == "SmartRecruiters"


def test_parsers():
    [p1, _] = ats_es.parse_personio(PERSONIO_XML, "https://ejemplo.jobs.personio.de/")
    assert (p1.title, p1.department, p1.location, p1.posted, p1.url) == (
        "Técnico/a comercial", "Ventas", "Zaragoza", "2026-07-01", "https://ejemplo.jobs.personio.de/job/101")
    [t] = ats_es.parse_teamtailor(TEAMTAILOR_RSS)
    assert (t.title, t.location, t.posted) == ("Customer Care Specialist", "Valencia", "2026-07-24")
    [s] = ats_es.parse_smartrecruiters(SMARTRECRUITERS, "EjemploSA")
    assert s.posted == "2026-06-15" and s.url == "https://jobs.smartrecruiters.com/EjemploSA/9001"
    [j] = ats_es.parse_join(JOIN_HTML, "ejemplo")
    assert (j.title, j.posted, j.location) == ("Administrativo/a de pedidos", "2026-08-10", "Sevilla")
    [f] = ats_es.parse_factorial(FACTORIAL_HTML, "https://ejemplo.factorialhr.com/")
    assert f.url == "https://ejemplo.factorialhr.com/job_posting/oficina-tecnica-123"


def test_xml_with_entities_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><workzag-jobs>&a;</workzag-jobs>'
    assert ats_es.parse_personio(bomb) is None


def _client(routes: dict):
    def handler(request):
        body = routes.get(str(request.url).split("?")[0])
        if body is None:
            return httpx.Response(404, text="")
        if isinstance(body, httpx.Response):
            return body
        if isinstance(body, (dict, list)):
            return httpx.Response(200, json=body)
        ctype = "application/xml" if isinstance(body, bytes) else "text/html"
        return httpx.Response(200, content=body if isinstance(body, bytes) else body.encode(),
                              headers={"content-type": ctype})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_read_board_dispatches_to_the_spanish_readers():
    async with _client({"https://ejemplo.jobs.personio.de/xml": PERSONIO_XML,
                        "https://api.smartrecruiters.com/v1/companies/EjemploSA/postings": SMARTRECRUITERS}) as c:
        assert len(await read_board(c, Board("personio", "ejemplo"))) == 2
        assert len(await read_board(c, Board("smartrecruiters", "EjemploSA"))) == 1
        assert await read_board(c, Board("teamtailor", "gone")) is None


# ── watched functions ──

@pytest.mark.parametrize("title,function", [
    ("Técnico/a comercial", "técnico comercial"),
    ("Ingeniero/a de Ofertas (m/f/d)", "ingeniero de ofertas"),
    ("Responsable de Oficina Técnica", "oficina técnica"),
    ("Comercial interno - Ventas internas", "ventas internas"),
    ("Customer Care Specialist", "atención al cliente"),
    ("Agente de Atención al Cliente", "atención al cliente"),
    ("Administrativa de pedidos", "administrativo de pedidos"),
    ("Operario de producción", ""),
    ("Ingeniero de procesos", ""),
])
def test_watched_functions(title, function):
    assert function_of(title, compile_functions()) == function


def test_custom_functions_replace_the_defaults():
    fns = compile_functions({"compras": ["comprador", "buyer", "(bad regex"]})
    assert function_of("Comprador/a senior", fns) == "compras"
    assert function_of("Técnico comercial", fns) == ""
    assert normalize_title("Técnico/a (H/M)") == "tecnico"


# ── InfoJobs ──

INFOJOBS = {"offers": [
    {"id": "a1", "title": "Ingeniero de ofertas", "city": "Zaragoza", "province": {"value": "Zaragoza"},
     "link": "https://www.infojobs.net/zaragoza/ingeniero-ofertas/of-a1", "category": {"value": "Ingenieros"},
     "author": {"id": "x", "name": "INDUSTRIAS EJEMPLO, S.L."}, "published": "2026-07-20T08:00:00.000Z"},
    # Another company whose name contains the account's: not the account.
    {"id": "a2", "title": "Técnico comercial", "author": {"name": "Industrias Ejemplo Norte SL"},
     "published": "2026-10-01T08:00:00.000Z"},
    # A staffing agency hiring for a client: not the account either.
    {"id": "a3", "title": "Administrativo de pedidos", "author": {"name": "ETT Prueba"},
     "published": "2026-10-01T08:00:00.000Z"},
]}


def test_infojobs_keeps_only_the_accounts_own_offers():
    offers = infojobs.parse_offers(INFOJOBS, ["Industrias Ejemplo SL"])
    assert [(o.title, o.posted, o.location) for o in offers] == [
        ("Ingeniero de ofertas", "2026-07-20", "Zaragoza, Zaragoza")]


@pytest.mark.asyncio
async def test_infojobs_needs_credentials(monkeypatch):
    monkeypatch.delenv("INFOJOBS_CLIENT_ID", raising=False)
    monkeypatch.delenv("INFOJOBS_CLIENT_SECRET", raising=False)
    assert infojobs.credentials() is None
    assert await infojobs.search_company(["Industrias Ejemplo"]) is None


@pytest.mark.asyncio
async def test_infojobs_search_sends_basic_auth_and_the_name_core():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["q"] = request.url.params.get("q")
        return httpx.Response(200, json=INFOJOBS)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        offers = await infojobs.search_company(["Industrias Ejemplo, S.L."], client=c, creds=("id", "secret"))
    assert seen["auth"] == "Basic aWQ6c2VjcmV0" and seen["q"] == "industrias ejemplo"
    assert len(offers) == 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as c:
        assert await infojobs.search_company(["Industrias Ejemplo"], client=c, creds=("id", "x")) is None


# ── HIRING_FUNCTION for one account ──

class _FakeProfile:
    """Stands in for an open ProfileCollector: site resolution and its client."""

    def __init__(self, home, client, careers=("", "")):
        self.home, self._client, self.careers = home, client, careers

    async def _resolve_site(self, domain):
        return f"https://{domain}", self.home

    async def _careers_page(self, site, home, domain):
        return self.careers


ACCOUNT = {"id": "c1", "name": "Industrias Ejemplo, S.L.", "domain": "industrias-ejemplo.example",
           "legal_name": ""}


@pytest.mark.asyncio
async def test_collect_jobs_from_board_and_infojobs():
    home = '<a href="https://ejemplo.jobs.personio.de/">Trabaja con nosotros</a>'
    async with _client({"https://ejemplo.jobs.personio.de/xml": PERSONIO_XML}) as board_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=INFOJOBS))) as ij:
        rows = await collect_jobs(ACCOUNT, compile_functions(), _FakeProfile(home, board_client),
                                  ("id", "secret"), ij)
    assert [r["value_text"] for r in rows] == [
        "técnico comercial · Técnico/a comercial · Ventas · Zaragoza · posted 2026-07-01 · Personio",
        "ingeniero de ofertas · Ingeniero de ofertas · Ingenieros · Zaragoza, Zaragoza · posted 2026-07-20 · InfoJobs",
    ]
    assert rows[0]["evidence_url"] == "https://ejemplo.jobs.personio.de/job/101"
    assert all(r["collector"] == "jobs" and r["signal_code"] == "HIRING_FUNCTION" for r in rows)


@pytest.mark.asyncio
async def test_collect_jobs_says_none_when_a_source_answered_empty():
    home = '<a href="https://ejemplo.jobs.personio.de/">Empleo</a>'
    xml = b'<?xml version="1.0"?><workzag-jobs></workzag-jobs>'
    async with _client({"https://ejemplo.jobs.personio.de/xml": xml}) as c:
        rows = await collect_jobs(ACCOUNT, compile_functions(), _FakeProfile(home, c))
    assert [(r["value_num"], r["evidence_url"]) for r in rows] == [(0, "https://ejemplo.jobs.personio.de/")]
    # No board and no InfoJobs: nothing is known, nothing is written.
    async with _client({}) as c:
        assert await collect_jobs(ACCOUNT, compile_functions(), _FakeProfile("<html></html>", c)) == []
