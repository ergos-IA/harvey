"""BORME: acts registered at the Registro Mercantil, from the BOE's open data.

Cost: $0. The BOE open-data API (https://www.boe.es/datosabiertos/) gives the
BORME summary for a day as JSON:

    GET https://www.boe.es/datosabiertos/api/borme/sumario/YYYYMMDD
        (Accept: application/json)

Section A ("Empresarios. Actos inscritos") has one item per province, and
each item links a PDF and the same text as XML (``url_xml``): one
``<p class="articulo">`` per company ("123456 - EJEMPLO INDUSTRIAL, S.L.")
followed by a ``<p class="parrafo">`` with its acts ("Nombramientos. Adm.
Unico: ..."). Harvey reads the XML, so no PDF library is needed.

Only the provinces of tracked accounts are read, for the last few days.
Each company named there is matched to a tracked account by its name with the
legal form dropped (harvey.collectors.spain.text.same_company) — strictly
equal, never a substring. Section A doesn't print the CIF, so the CIF can't
be used to match; importing the registered name as ``legal_name`` is what
makes trading-name accounts match.

Signals: BORME_APPOINTMENT (administrators, consejero delegado, presidente,
director general appointed or removed), BORME_CAPITAL (capital increase,
new sole shareholder), BORME_MERGER (merger, absorption, demerger). Each row
holds the publication date and an excerpt of the act; the evidence URL is the
BOE's page for that province's section.
"""

import asyncio
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx

from harvey.collectors.spain.accounts import names_for
from harvey.collectors.spain.text import clean_snippet, company_key, same_province

logger = logging.getLogger("harvey.collectors.spain.borme")

SUMARIO_URL = "https://www.boe.es/datosabiertos/api/borme/sumario/{day}"
MAX_DOC_BYTES = 6 * 1024 * 1024

# Act headings as the BORME prints them, folded (lowercase, no accents).
HEADINGS = (
    "constitucion", "nombramientos", "ceses/dimisiones", "revocaciones", "reelecciones",
    "modificaciones estatutarias", "cambio de domicilio social", "cambio de objeto social",
    "ampliacion del objeto social", "cambio de denominacion social", "ampliacion de capital",
    "reduccion de capital", "fusion por absorcion", "fusion por union", "escision parcial",
    "escision total", "segregacion", "declaracion de unipersonalidad",
    "perdida del caracter de unipersonalidad", "cambio de identidad del socio unico",
    "socio unico", "disolucion", "extincion", "otros conceptos", "datos registrales",
    "transformacion de sociedad", "cesion global de activo y pasivo", "situacion concursal",
    "fe de erratas", "desembolso de dividendos pasivos", "sociedad unipersonal",
    "primera inscripcion", "reapertura hoja registral", "cierre provisional hoja registral",
    "emision de obligaciones", "modificacion de poderes", "revocacion de poderes",
    "adaptacion ley 2/95", "articulo 378.5 del reglamento del registro mercantil",
    "anotacion preventiva", "cancelaciones de oficio de nombramientos",
)
_HEADING_RE = re.compile(r"(?:^|(?<=[.\s]))(" + "|".join(
    re.escape(h) for h in sorted(HEADINGS, key=len, reverse=True)) + r")\s*[.:]")

APPOINTMENT_HEADINGS = {"nombramientos", "ceses/dimisiones", "revocaciones",
                        "cancelaciones de oficio de nombramientos"}
CAPITAL_HEADINGS = {"ampliacion de capital", "cambio de identidad del socio unico",
                    "declaracion de unipersonalidad", "socio unico"}
MERGER_PREFIXES = ("fusion", "escision", "segregacion")
# Roles that make an appointment a change at the top, not a new proxy.
_TOP_ROLE_RE = re.compile(
    r"(?:\badm\.?\s*(?:unico|solid\w*|mancom\w*|unic)|\badministrador\w*|\bconsejer\w*|"
    r"\bcons\.?\s*del\w*|\bcon\.?\s*delegad\w*|\bpresident\w*|\bpres\.?\s*(?:del\s*)?c|"
    r"\bvicepresid\w*|\bdir\.?\s*(?:general|gral\.?)|\bdirector(?:a)?\s+(?:general|gerente)|"
    r"\bgerente\b|\bm\.?\s*com\.?\s*ej|\bmiem\.?\s*com|\bceo\b)\s*:")


def _fold1(text: str) -> str:
    """Lowercase, accents dropped, ONE output character per input character,
    so positions found in the folded text slice the original."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", ch)[:1] or ch
        low = base.lower()
        out.append(low if len(low) == 1 else base)
    return "".join(out)


@dataclass
class Act:
    """One company's entry in a day's BORME, split into its acts."""

    number: str
    name: str
    text: str
    segments: list[tuple[str, str]] = field(default_factory=list)   # (heading, original text)


def split_acts(text: str) -> list[tuple[str, str]]:
    """[(folded heading, original segment)] in the order printed."""
    folded = _fold1(text)
    marks = [(m.start(1), m.group(1)) for m in _HEADING_RE.finditer(folded)]
    out = []
    for i, (start, heading) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append((heading, text[start:end].strip()))
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_section_xml(payload: bytes) -> list[Act]:
    """The entries in one province's Section A document (BOE XML)."""
    if b"<!DOCTYPE" in payload[:2048].upper() or b"<!ENTITY" in payload.upper():
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    acts: list[Act] = []
    for node in root.iter():
        if _local(node.tag) != "p":
            continue
        cls = (node.get("class") or "").lower()
        text = re.sub(r"\s+", " ", "".join(node.itertext())).strip()
        if cls == "articulo":
            m = re.match(r"^\s*(\d+)\s*-\s*(.+?)\s*\.?\s*$", text)
            if m:
                acts.append(Act(number=m.group(1), name=m.group(2).rstrip("."), text=""))
        elif cls == "parrafo" and acts:
            acts[-1].text = (acts[-1].text + " " + text).strip()
    for act in acts:
        act.segments = split_acts(act.text)
    return acts


def classify(act: Act) -> dict[str, str]:
    """{signal_code: excerpt} for the acts that matter in one entry."""
    found: dict[str, list[str]] = {}
    # A newly constituted company's first administrators are not a change.
    new_company = any(h == "constitucion" for h, _ in act.segments)
    for heading, segment in act.segments:
        if heading in APPOINTMENT_HEADINGS and not new_company and _TOP_ROLE_RE.search(_fold1(segment)):
            found.setdefault("BORME_APPOINTMENT", []).append(segment)
        elif heading in CAPITAL_HEADINGS and not (new_company and heading != "ampliacion de capital"):
            found.setdefault("BORME_CAPITAL", []).append(segment)
        elif heading.startswith(MERGER_PREFIXES):
            found.setdefault("BORME_MERGER", []).append(segment)
    # Mergers are often only in "Otros conceptos: ... fusión por absorción ...".
    if "BORME_MERGER" not in found:
        for heading, segment in act.segments:
            if heading == "otros conceptos" and re.search(
                    r"\b(?:fusion|absorcion|escision)\b", _fold1(segment)):
                found["BORME_MERGER"] = [segment]
                break
    return {code: clean_snippet(" | ".join(parts), 380) for code, parts in found.items()}


def parse_sumario(payload) -> list[dict]:
    """Section A items of a day's summary: [{id, province, url_xml, url_html, url_pdf}]."""
    def as_list(value):
        return value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])

    data = payload.get("data") if isinstance(payload, dict) else None
    sumario = data.get("sumario") if isinstance(data, dict) else None
    out = []
    for diario in as_list(sumario.get("diario") if isinstance(sumario, dict) else None):
        for seccion in as_list(diario.get("seccion")):
            if str(seccion.get("codigo") or "").upper() != "A":
                continue
            for item in as_list(seccion.get("item")):
                pdf = item.get("url_pdf")
                out.append({
                    "id": str(item.get("identificador") or ""),
                    "province": str(item.get("titulo") or ""),
                    "url_xml": str(item.get("url_xml") or ""),
                    "url_html": str(item.get("url_html") or ""),
                    "url_pdf": str(pdf.get("texto") if isinstance(pdf, dict) else pdf or ""),
                })
    return [i for i in out if i["url_xml"].startswith("https://www.boe.es/")]


def recent_days(days: int, today: date | None = None) -> list[date]:
    """The last ``days`` calendar days that can have a BORME (weekdays)."""
    today = today or date.today()
    out = [today - timedelta(days=i) for i in range(max(0, days))]
    return [d for d in out if d.weekday() < 5]


@dataclass
class BormeReport:
    days: int = 0
    documents: int = 0
    entries: int = 0
    matched: int = 0
    observations: list[dict] = field(default_factory=list)
    no_province: int = 0
    errors: list[str] = field(default_factory=list)


async def _get(client: httpx.AsyncClient, url: str, accept: str) -> httpx.Response | None:
    try:
        resp = await client.get(url, headers={"Accept": accept})
    except httpx.HTTPError as e:
        logger.info(f"borme: {url} failed: {type(e).__name__}")
        return None
    if resp.status_code != 200 or len(resp.content) > MAX_DOC_BYTES:
        logger.debug(f"borme: {url} → {resp.status_code}")
        return None
    return resp


async def collect_borme(accounts: list[dict], client: httpx.AsyncClient, days: int = 7,
                        all_provinces: bool = False, today: date | None = None,
                        wanted: set[str] | None = None, pause: float = 0.3) -> BormeReport:
    """BORME observations for tracked accounts over the last ``days`` days."""
    report = BormeReport()
    wanted = wanted or {"BORME_APPOINTMENT", "BORME_CAPITAL", "BORME_MERGER"}
    by_key: dict[str, list[dict]] = {}
    for account in accounts:
        for name in names_for(account):
            key = company_key(name)
            if len(key) >= 3:
                by_key.setdefault(key, []).append(account)
    provinces = [a.get("province") or "" for a in accounts]
    report.no_province = sum(1 for p in provinces if not p)
    provinces = [p for p in provinces if p]
    if not by_key or (not provinces and not all_provinces):
        return report

    for day in recent_days(days, today):
        resp = await _get(client, SUMARIO_URL.format(day=day.strftime("%Y%m%d")), "application/json")
        if resp is None:
            continue
        try:
            items = parse_sumario(resp.json())
        except (ValueError, RecursionError):
            report.errors.append(f"{day}: summary unreadable")
            continue
        report.days += 1
        for item in items:
            if not all_provinces and not any(same_province(item["province"], p) for p in provinces):
                continue
            doc = await _get(client, item["url_xml"], "application/xml")
            if pause:
                await asyncio.sleep(pause)
            if doc is None:
                continue
            report.documents += 1
            acts = parse_section_xml(doc.content)
            report.entries += len(acts)
            for act in acts:
                matches = by_key.get(company_key(act.name))
                if not matches:
                    continue
                classified = {c: t for c, t in classify(act).items() if c in wanted}
                if not classified:
                    continue
                report.matched += 1
                for account in {a["id"]: a for a in matches}.values():
                    for code, excerpt in classified.items():
                        report.observations.append({
                            "signal_code": code, "company_id": account["id"], "collector": "borme",
                            "value_num": None,
                            "value_text": clean_snippet(f"{day.isoformat()} · {excerpt}", 400),
                            "confidence": 0.95, "evidence_url": item["url_html"] or item["url_pdf"],
                        })
    return report
