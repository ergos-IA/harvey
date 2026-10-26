"""Job boards common at Spanish mid-sized companies.

Personio, Teamtailor, Factorial, JOIN and SmartRecruiters, alongside the
Greenhouse/Lever/Ashby/Workable boards harvey.collectors.ats already reads.
The rule is the same as there: which board a company uses comes from links
and embeds on its OWN site, never from guessing a token. A guessed token that
exists is somebody else's board.

Feeds, as each vendor publishes them without authentication:

- Personio:        https://<t>.jobs.personio.de/xml (or .com) — XML
- Teamtailor:      https://<t>.teamtailor.com/jobs.rss — RSS
- SmartRecruiters: https://api.smartrecruiters.com/v1/companies/<t>/postings — JSON
- JOIN:            https://join.com/companies/<t> — the page's embedded __NEXT_DATA__ JSON
- Factorial:       https://<t>.factorialhr.com/ — the careers page HTML (no
                   public feed; best effort, links to job postings only, no dates)
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

logger = logging.getLogger("harvey.collectors.spain.ats_es")

MAX_FEED_BYTES = 8 * 1024 * 1024

LABELS = {
    "personio": "Personio", "personio_com": "Personio", "teamtailor": "Teamtailor",
    "smartrecruiters": "SmartRecruiters", "join": "JOIN", "factorial": "Factorial",
    "factorial_es": "Factorial",
}

_S = r"\\?/"
_SUB = r"([a-z0-9][a-z0-9-]{1,62})"
# (ats, pattern); the token is group 1.
BOARD_RES = (
    ("personio", re.compile(rf"(?<![\w.@-]){_SUB}\.jobs\.personio\.de(?![\w-])", re.I)),
    ("personio_com", re.compile(rf"(?<![\w.@-]){_SUB}\.jobs\.personio\.com(?![\w-])", re.I)),
    ("teamtailor", re.compile(rf"(?<![\w.@-]){_SUB}\.teamtailor\.com(?![\w-])", re.I)),
    ("smartrecruiters", re.compile(
        rf"(?<![\w.@-])(?:careers|jobs)\.smartrecruiters\.com{_S}([A-Za-z0-9][A-Za-z0-9_-]+)", re.I)),
    ("smartrecruiters", re.compile(
        rf"api\.smartrecruiters\.com{_S}v1{_S}companies{_S}([A-Za-z0-9][A-Za-z0-9_-]+)", re.I)),
    ("join", re.compile(rf"(?<![\w.@-])join\.com{_S}companies{_S}([A-Za-z0-9][A-Za-z0-9_-]+)", re.I)),
    ("factorial", re.compile(rf"(?<![\w.@-]){_SUB}\.factorialhr\.com(?![\w-])", re.I)),
    ("factorial_es", re.compile(rf"(?<![\w.@-]){_SUB}\.factorialhr\.es(?![\w-])", re.I)),
)
# Vendor subdomains that are the vendor's own pages, not a company's board.
NOT_TOKENS = frozenset("""
www app api help support status assets static cdn scripts media images img blog docs
career careers jobs login signin marketplace partners developer developers
""".split())


def page_url(ats: str, token: str) -> str:
    return {
        "personio": f"https://{token}.jobs.personio.de/",
        "personio_com": f"https://{token}.jobs.personio.com/",
        "teamtailor": f"https://{token}.teamtailor.com/jobs",
        "smartrecruiters": f"https://careers.smartrecruiters.com/{token}",
        "join": f"https://join.com/companies/{token}",
        "factorial": f"https://{token}.factorialhr.com/",
        "factorial_es": f"https://{token}.factorialhr.es/",
    }[ats]


def feed_url(ats: str, token: str) -> str:
    return {
        "personio": f"https://{token}.jobs.personio.de/xml",
        "personio_com": f"https://{token}.jobs.personio.com/xml",
        "teamtailor": f"https://{token}.teamtailor.com/jobs.rss",
        "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100",
        "join": f"https://join.com/companies/{token}",
        "factorial": f"https://{token}.factorialhr.com/",
        "factorial_es": f"https://{token}.factorialhr.es/",
    }[ats]


def _s(value) -> str:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def _iso_day(value: str) -> str:
    text = _s(value)
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    try:
        return parsedate_to_datetime(text).date().isoformat() if text else ""
    except (TypeError, ValueError, IndexError):
        return ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def _xml(payload: bytes):
    # ElementTree never fetches external entities; a DOCTYPE in a job feed
    # has no business being there, so refuse one rather than expand it.
    if b"<!DOCTYPE" in payload[:2048].upper() or b"<!ENTITY" in payload.upper():
        return None
    try:
        return ET.fromstring(payload)
    except ET.ParseError:
        return None


def parse_personio(payload: bytes, base: str = ""):
    from harvey.collectors.ats import Posting
    root = _xml(payload)
    if root is None:
        return None
    out = []
    for pos in root.iter():
        if _local(pos.tag) != "position":
            continue
        fields = {_local(child.tag): (child.text or "") for child in pos}
        title = _s(fields.get("name"))
        if not title:
            continue
        out.append(Posting(title=title, department=_s(fields.get("department")),
                           location=_s(fields.get("office")), posted=_iso_day(fields.get("createdat", "")),
                           url=f"{base}job/{_s(fields.get('id'))}" if base and _s(fields.get("id")) else ""))
    return out


def parse_teamtailor(payload: bytes):
    from harvey.collectors.ats import Posting
    root = _xml(payload)
    if root is None:
        return None
    out = []
    for item in root.iter():
        if _local(item.tag) != "item":
            continue
        title = link = posted = dept = city = ""
        for child in item.iter():
            name = _local(child.tag)
            if name == "title" and not title:
                title = _s(child.text)
            elif name == "link" and not link:
                link = _s(child.text)
            elif name == "pubdate":
                posted = _iso_day(child.text or "")
            elif name == "department" and not dept:
                dept = _s(child.text)
            elif name == "city" and not city:
                city = _s(child.text)
        if title:
            out.append(Posting(title=title, department=dept, location=city, posted=posted, url=link))
    return out


def parse_smartrecruiters(payload, token: str = ""):
    from harvey.collectors.ats import Posting
    out = []
    content = payload.get("content") if isinstance(payload, dict) else None
    for job in content if isinstance(content, list) else []:
        if not isinstance(job, dict) or not _s(job.get("name")):
            continue
        loc = job.get("location") if isinstance(job.get("location"), dict) else {}
        dept = job.get("department") if isinstance(job.get("department"), dict) else {}
        jid = _s(str(job.get("id") or ""))
        out.append(Posting(
            title=_s(job["name"]), department=_s(dept.get("label")),
            location=", ".join(p for p in (_s(loc.get("city")), _s(loc.get("region"))) if p),
            posted=_iso_day(job.get("releasedDate") or ""),
            url=f"https://jobs.smartrecruiters.com/{token}/{jid}" if token and jid else "",
        ))
    return out


_NEXT_DATA_RE = re.compile(r'(?s)<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>')


def _walk_jobs(node, depth=0):
    """Dicts that look like JOIN job items: a title plus an idParam."""
    if depth > 12:
        return
    if isinstance(node, dict):
        if isinstance(node.get("title"), str) and isinstance(node.get("idParam"), str):
            yield node
        for value in node.values():
            yield from _walk_jobs(value, depth + 1)
    elif isinstance(node, list):
        for value in node[:500]:
            yield from _walk_jobs(value, depth + 1)


def parse_join(html: str, token: str = ""):
    from harvey.collectors.ats import Posting
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (ValueError, RecursionError):
        return None
    out, seen = [], set()
    for job in _walk_jobs(data):
        if job["idParam"] in seen:
            continue
        seen.add(job["idParam"])
        city = job.get("city") if isinstance(job.get("city"), dict) else {}
        cat = job.get("category") if isinstance(job.get("category"), dict) else {}
        out.append(Posting(
            title=_s(job["title"]), department=_s(cat.get("name")),
            location=_s(city.get("cityName")), posted=_iso_day(job.get("createdAt") or ""),
            url=f"https://join.com/companies/{token}/{job['idParam']}" if token else "",
        ))
    return out


_FACTORIAL_LINK_RE = re.compile(
    r"""(?is)<a\b[^>]*href=["']([^"']*/job_posting/[^"']+)["'][^>]*>(.*?)</a>""")


def parse_factorial(html: str, base: str = ""):
    from harvey.collectors.ats import Posting
    out, seen = [], set()
    for m in _FACTORIAL_LINK_RE.finditer(html or ""):
        href = m.group(1)
        title = _s(unescape(re.sub(r"(?s)<[^>]+>", " ", m.group(2))))
        if not title or len(title) > 120 or href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else base.rstrip("/") + "/" + href.lstrip("/")
        out.append(Posting(title=title, url=url))
    return out


async def read(client: httpx.AsyncClient, ats: str, token: str):
    """Read one board. A list of Postings, or None when it doesn't answer
    with what that vendor publishes (gone, renamed, never existed)."""
    url = feed_url(ats, token)
    body = bytearray()
    try:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                logger.debug(f"ats_es: {url} → {resp.status_code}")
                return None
            ctype = resp.headers.get("content-type", "")
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) > MAX_FEED_BYTES:
                    logger.info(f"ats_es: {LABELS.get(ats, ats)} board {token} too large, skipped")
                    return None
    except (httpx.HTTPError, ValueError) as e:
        logger.debug(f"ats_es: fetch failed {url}: {e}")
        return None
    raw = bytes(body)
    if ats in ("personio", "personio_com"):
        return parse_personio(raw, page_url(ats, token)) if "xml" in ctype or raw.lstrip().startswith(b"<?xml") else None
    if ats == "teamtailor":
        return parse_teamtailor(raw) if "xml" in ctype or "rss" in ctype or raw.lstrip().startswith(b"<?xml") \
            else None
    if ats == "smartrecruiters":
        if "json" not in ctype:
            return None
        try:
            return parse_smartrecruiters(json.loads(raw), token)
        except (ValueError, RecursionError):
            return None
    text = raw.decode("utf-8", errors="replace")
    if ats == "join":
        return parse_join(text, token)
    if ats in ("factorial", "factorial_es"):
        return parse_factorial(text, page_url(ats, token))
    return None
