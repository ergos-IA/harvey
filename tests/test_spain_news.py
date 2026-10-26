"""Spanish press headlines (Google News RSS), classified deterministically.

The feed shape follows Google News RSS (checked October 2026); every company,
headline and outlet here is fictional.
"""

from datetime import datetime, timezone
from urllib.parse import unquote

import httpx
import pytest

from harvey.collectors.spain.news import (
    build_query, classify_headline, collect_news, news_rows, parse_rss,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _item(title, source, day, link):
    return (f"<item><title>{title} - {source}</title><link>{link}</link>"
            f"<pubDate>{day}</pubDate><source url=\"https://diario.example\">{source}</source></item>")


FEED = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel><title>x</title>"
        + _item("Industrias Ejemplo abre una nueva planta en Teruel", "Diario Ejemplo",
                "Mon, 05 Oct 2026 08:00:00 GMT", "https://news.google.com/rss/articles/a1")
        + _item("Un fondo de private equity entra en el capital de Industrias Ejemplo", "Economía Test",
                "Tue, 10 Mar 2026 08:00:00 GMT", "https://news.google.com/rss/articles/a2")
        + _item("Industrias Ejemplo nombra nuevo director general", "Diario Ejemplo",
                "Wed, 01 Jul 2026 08:00:00 GMT", "https://news.google.com/rss/articles/a3")
        # Too old (more than 18 months).
        + _item("Industrias Ejemplo adquiere un competidor", "Diario Ejemplo",
                "Thu, 01 Feb 2024 08:00:00 GMT", "https://news.google.com/rss/articles/a4")
        # Names another company: the search matched the body, not the headline.
        + _item("Industrias Ejemplares compra una nave", "Diario Ejemplo",
                "Thu, 01 Oct 2026 08:00:00 GMT", "https://news.google.com/rss/articles/a5")
        # Names the account but isn't one of the categories.
        + _item("Industrias Ejemplo patrocina el torneo local", "Diario Ejemplo",
                "Thu, 01 Oct 2026 08:00:00 GMT", "https://news.google.com/rss/articles/a6")
        + "</channel></rss>").encode()

ACCOUNT = {"id": "c1", "name": "Industrias Ejemplo, S.L.", "legal_name": "",
           "domain": "industrias-ejemplo.example"}


@pytest.mark.parametrize("headline,codes", [
    ("X abre una nueva planta en Teruel", ["NEWS_EXPANSION"]),
    ("X inaugura su nueva delegación en Valencia", ["NEWS_EXPANSION"]),
    ("X adquiere la división de Y", ["NEWS_ACQUISITION"]),
    ("X absorbe a su filial", ["NEWS_ACQUISITION"]),
    ("Un fondo entra en el capital de X", ["NEWS_INVESTOR"]),
    ("X, participada por un private equity, crece", ["NEWS_INVESTOR"]),
    ("X nombra a una nueva CEO", ["NEWS_LEADERSHIP"]),
    ("Relevo en la dirección de X", ["NEWS_LEADERSHIP"]),
    ("X analiza a fondo el mercado", []),
    ("X celebra su aniversario", []),
])
def test_classify_headline(headline, codes):
    assert classify_headline(headline) == codes


def test_build_query():
    assert build_query("Industrias Ejemplo, S.L.") == '"Industrias Ejemplo"'
    assert build_query("Talleres Prueba SA", "tprueba.example", use_brand=True) == '"Talleres Prueba" OR "tprueba"'
    assert build_query("Talleres Prueba", "talleresprueba.example", use_brand=True) == '"Talleres Prueba"'


def test_parse_rss_splits_the_source_suffix():
    items = parse_rss(FEED)
    assert items[0]["title"] == "Industrias Ejemplo abre una nueva planta en Teruel"
    assert items[0]["source"] == "Diario Ejemplo"
    assert items[0]["date"].date().isoformat() == "2026-10-05"
    assert parse_rss(b"<not xml") == []


def test_news_rows_keep_headline_link_and_date():
    rows = news_rows(ACCOUNT, parse_rss(FEED), months=18, now=NOW)
    got = [(r["signal_code"], r["evidence_url"].rsplit("/", 1)[-1]) for r in rows]
    assert got == [("NEWS_EXPANSION", "a1"), ("NEWS_LEADERSHIP", "a3"), ("NEWS_INVESTOR", "a2")]
    assert rows[0]["value_text"] == ("2026-10-05 · Industrias Ejemplo abre una nueva planta en Teruel · "
                                     "Diario Ejemplo")
    assert all(r["collector"] == "news" and r["confidence"] == 0.85 for r in rows)
    only = news_rows(ACCOUNT, parse_rss(FEED), now=NOW, wanted={"NEWS_INVESTOR"})
    assert [r["signal_code"] for r in only] == ["NEWS_INVESTOR"]


def test_headline_text_is_cleaned():
    evil = FEED.replace(b"abre una nueva planta en Teruel",
                        b"abre una nueva planta &lt;script&gt;x&lt;/script&gt;\xe2\x80\x8b en Teruel")
    [first, *_] = news_rows(ACCOUNT, parse_rss(evil), now=NOW)
    assert "<" not in first["value_text"] and "​" not in first["value_text"]


@pytest.mark.asyncio
async def test_collect_news_queries_google_news_in_spanish():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=FEED, headers={"content-type": "application/xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await collect_news(ACCOUNT, client, now=NOW)
    assert len(rows) == 3
    assert unquote(seen[0]) == ('https://news.google.com/rss/search?q="Industrias Ejemplo"'
                                "&hl=es&gl=ES&ceid=ES:es")

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        assert await collect_news(ACCOUNT, client, now=NOW) is None
