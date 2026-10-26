"""Open offers on InfoJobs, through its official API.

https://developer.infojobs.net — register an application (free) and put its
credentials in .env as INFOJOBS_CLIENT_ID and INFOJOBS_CLIENT_SECRET. Without
them this collector does nothing and says so; it never scrapes the site.

Offers are searched by company name and then filtered by the offer's
AUTHOR, compared strictly (harvey.collectors.spain.text.same_company): the
search matches words anywhere in an offer, so "Ejemplo" finds offers from
"Ejemplo Logística" and from staffing agencies hiring for a client called
Ejemplo. Only offers the account itself published are kept. Offers a staffing
agency publishes for an unnamed client are, by construction, missed.
"""

import base64
import logging
import os

import httpx

from harvey.collectors.spain.text import clean_snippet, company_key, same_company

logger = logging.getLogger("harvey.collectors.spain.infojobs")

API_URL = "https://api.infojobs.net/api/9/offer"
TIMEOUT = httpx.Timeout(connect=8.0, read=20.0, write=8.0, pool=8.0)


def credentials() -> tuple[str, str] | None:
    cid = os.environ.get("INFOJOBS_CLIENT_ID", "").strip()
    secret = os.environ.get("INFOJOBS_CLIENT_SECRET", "").strip()
    return (cid, secret) if cid and secret else None


def _auth_header(cid: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()


def _day(value) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else ""


def _value(field) -> str:
    if isinstance(field, dict):
        return clean_snippet(field.get("value") or "", 80)
    return clean_snippet(field or "", 80) if isinstance(field, str) else ""


def parse_offers(payload, company_names: list[str]):
    """The offers in an API response whose author is one of ``company_names``."""
    from harvey.collectors.ats import Posting
    offers = payload.get("offers") if isinstance(payload, dict) else None
    out = []
    for offer in offers if isinstance(offers, list) else []:
        if not isinstance(offer, dict):
            continue
        author = offer.get("author") if isinstance(offer.get("author"), dict) else {}
        author_name = author.get("name") if isinstance(author.get("name"), str) else ""
        if not any(same_company(author_name, n) for n in company_names if n):
            continue
        title = clean_snippet(offer.get("title") or "", 120)
        if not title:
            continue
        place = ", ".join(p for p in (clean_snippet(offer.get("city") or "", 60),
                                      _value(offer.get("province"))) if p)
        out.append(Posting(
            title=title, department=_value(offer.get("category")), location=place,
            posted=_day(offer.get("published")) or _day(offer.get("updated")),
            url=clean_snippet(offer.get("link") or "", 300),
        ))
    return out


async def search_company(company_names: list[str], client: httpx.AsyncClient | None = None,
                         creds: tuple[str, str] | None = None, max_results: int = 50):
    """Offers published by the company, or None when InfoJobs can't be asked
    (no credentials, auth refused, API down)."""
    creds = creds or credentials()
    query = next((company_key(n) for n in company_names if company_key(n)), "")
    if not creds or not query:
        return None
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        resp = await client.get(API_URL, params={"q": query, "maxResults": max_results},
                                headers={"Authorization": _auth_header(*creds),
                                         "Accept": "application/json"})
        if resp.status_code in (401, 403):
            logger.warning("infojobs: credentials refused (check INFOJOBS_CLIENT_ID/SECRET)")
            return None
        if resp.status_code != 200:
            logger.info(f"infojobs: search answered {resp.status_code}")
            return None
        return parse_offers(resp.json(), company_names)
    except (httpx.HTTPError, ValueError) as e:
        logger.info(f"infojobs: search failed: {type(e).__name__}")
        return None
    finally:
        if own:
            await client.aclose()
