"""Spanish press headlines about a tracked account, from Google News RSS.

One request per account:

    https://news.google.com/rss/search?q="<name>"&hl=es&gl=ES&ceid=ES:es

Headlines from the last ``months`` months are classified deterministically,
by wording, into NEWS_EXPANSION, NEWS_ACQUISITION, NEWS_INVESTOR and
NEWS_LEADERSHIP. Only headlines that name the company (its name with the
legal form dropped, as whole words) count: the search also matches article
bodies, and a headline about someone else is not news about the account.

Each row keeps "YYYY-MM-DD · headline · source" and the article link. All of
it is untrusted text from the open web: cleaned and capped here, and fenced
(harvey.untrusted) wherever it reaches a prompt.

Google's feed terms describe it as for personal, non-commercial use; that is
noted in the signals' cost notes so the operator decides whether it fits.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

from harvey.collectors.spain.text import clean_snippet, company_key, fold, name_in_text

logger = logging.getLogger("harvey.collectors.spain.news")

RSS_URL = "https://news.google.com/rss/search?q={q}&hl=es&gl=ES&ceid=ES:es"
MAX_FEED_BYTES = 3 * 1024 * 1024
MAX_PER_SIGNAL = 5

# Over the folded headline (lowercase, no accents).
CATEGORIES: dict[str, tuple[str, ...]] = {
    "NEWS_EXPANSION": (
        r"\bnueva planta\b", r"\bnuevas plantas\b", r"\bnueva fabrica\b", r"\bnueva nave\b",
        r"\bampliacion\b", r"\bamplia (?:su|sus|la|el|las|los)\b", r"\bnueva linea\b",
        r"\bnuevas lineas\b", r"\babre\b", r"\babrira\b", r"\bapertura(?:s)?\b", r"\binaugura\b",
        r"\bnuevas tiendas\b", r"\bnueva tienda\b", r"\bnueva delegacion\b", r"\bdelegacion en\b",
        r"\bnueva sede\b", r"\bnuevo centro\b", r"\bse expande\b", r"\bexpansion\b",
        r"\bdesembarca\b",
    ),
    "NEWS_ACQUISITION": (
        r"\badquiere\b", r"\badquieren\b", r"\badquisicion\b", r"\bcompra\b(?! (?:online|de entradas))",
        r"\bcompran\b", r"\babsorbe\b", r"\babsorcion\b", r"\bfusion\b", r"\bse fusiona\b",
        r"\bse hace con\b", r"\btoma el control\b",
    ),
    "NEWS_INVESTOR": (
        r"(?<!\ba )\bfondo\b", r"\bfondos\b", r"\bentra en el capital\b", r"\bentra en su capital\b",
        r"\bprivate equity\b", r"\bparticipada\b", r"\bcapital riesgo\b", r"\bcapital privado\b",
        r"\bfamily office\b", r"\bminoritaria\b", r"\bmayoritaria\b",
    ),
    "NEWS_LEADERSHIP": (
        r"\bnombra\b", r"\bnombramiento\b", r"\bficha a\b", r"\bnuev[oa] director(?:a)? general\b",
        r"\bnuev[oa] (?:ceo|consejer[oa] delegad[oa]|presidente|presidenta)\b", r"\brelevo\b",
        r"\bsustituye a\b",
    ),
}
_COMPILED = {code: [re.compile(p) for p in pats] for code, pats in CATEGORIES.items()}


def classify_headline(headline: str) -> list[str]:
    text = fold(headline)
    return [code for code, pats in _COMPILED.items() if any(p.search(text) for p in pats)]


_LEGAL_SUFFIX = re.compile(
    r"(?i),?\s+(?:S\.?\s?L\.?(?:\s?[UNLP]\.?)?|S\.?\s?A\.?(?:\s?U\.?)?|"
    r"Sociedad Limitada(?: Unipersonal)?|Sociedad An[oó]nima(?: Unipersonal)?)\.?$")


def build_query(name: str, domain: str = "", use_brand: bool = False) -> str:
    """'"Ejemplo Industrial"' (legal form dropped), plus '"ejemplo"' from the
    domain when asked and it differs."""
    core = re.sub(r"\s+", " ", _LEGAL_SUFFIX.sub("", (name or "").strip())).strip(" ,.")
    terms = [f'"{core}"'] if core else []
    brand = (domain or "").split(".")[0]
    if use_brand and len(brand) >= 4 and \
            company_key(brand).replace(" ", "") != company_key(core).replace(" ", ""):
        terms.append(f'"{brand}"')
    return " OR ".join(terms)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_rss(payload: bytes) -> list[dict]:
    """[{title, source, link, date}] from a Google News RSS feed."""
    if b"<!DOCTYPE" in payload[:2048].upper() or b"<!ENTITY" in payload.upper():
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter():
        if _local(item.tag) != "item":
            continue
        fields = {}
        for child in item:
            fields.setdefault(_local(child.tag), (child.text or "").strip())
        title = fields.get("title", "")
        source = fields.get("source", "")
        # "Headline - Source": the source is Google's suffix, not the headline.
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        elif " - " in title:
            head, tail = title.rsplit(" - ", 1)
            if len(tail) <= 40:
                title, source = head, source or tail
        when = None
        try:
            when = parsedate_to_datetime(fields.get("pubdate", ""))
            if when and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, IndexError):
            when = None
        out.append({"title": clean_snippet(title, 240), "source": clean_snippet(source, 60),
                    "link": clean_snippet(fields.get("link", ""), 500), "date": when})
    return out


def news_rows(account: dict, items: list[dict], months: int = 18, now: datetime | None = None,
              wanted: set[str] | None = None, use_brand: bool = False) -> list[dict]:
    """Observation rows for the headlines that name the account and classify."""
    from harvey.collectors.spain.accounts import names_for
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30 * months)
    names = names_for(account)
    brand = (account.get("domain") or "").split(".")[0]
    per_code: dict[str, int] = {}
    rows, seen = [], set()
    for item in sorted(items, key=lambda i: i["date"] or cutoff, reverse=True):
        if not item["title"] or item["date"] is None or item["date"] < cutoff or item["date"] > now + timedelta(days=1):
            continue
        named = any(name_in_text(n, item["title"]) for n in names)
        by_brand = use_brand and not named and len(brand) >= 4 and name_in_text(brand, item["title"])
        if not (named or by_brand):
            continue
        key = fold(item["title"])
        if key in seen:
            continue
        seen.add(key)
        for code in classify_headline(item["title"]):
            if wanted is not None and code not in wanted:
                continue
            if per_code.get(code, 0) >= MAX_PER_SIGNAL:
                continue
            per_code[code] = per_code.get(code, 0) + 1
            text = " · ".join(p for p in (item["date"].date().isoformat(), item["title"], item["source"]) if p)
            rows.append({
                "signal_code": code, "company_id": account["id"], "collector": "news",
                "value_num": None, "value_text": clean_snippet(text, 320),
                "confidence": 0.85 if named else 0.6, "evidence_url": item["link"],
            })
    return rows


async def fetch_news(client: httpx.AsyncClient, query: str) -> list[dict] | None:
    """The feed for one query, or None when Google News didn't answer."""
    if not query:
        return None
    url = RSS_URL.format(q=quote(query, safe=""))
    try:
        resp = await client.get(url, headers={"Accept": "application/rss+xml, application/xml"})
    except httpx.HTTPError as e:
        logger.info(f"news: fetch failed: {type(e).__name__}")
        return None
    if resp.status_code != 200 or len(resp.content) > MAX_FEED_BYTES:
        logger.info(f"news: feed answered {resp.status_code}")
        return None
    return parse_rss(resp.content)


async def collect_news(account: dict, client: httpx.AsyncClient, months: int = 18,
                       use_brand: bool = False, wanted: set[str] | None = None,
                       now: datetime | None = None) -> list[dict] | None:
    from harvey.collectors.spain.accounts import names_for
    names = names_for(account)
    query = build_query(account.get("name") or (names[0] if names else ""),
                        account.get("domain") or "", use_brand)
    items = await fetch_news(client, query)
    if items is None:
        return None
    return news_rows(account, items, months=months, now=now, wanted=wanted, use_brand=use_brand)
