"""Hand-picked accounts: how they enter Harvey, and how they're found again.

``harvey accounts import accounts.csv`` replaces map discovery for
account-based selling. Each row is a company chosen by hand (or exported from
Clay): it is created, or updated when its domain is already known, and the
firmographics the file provides are recorded as observations with collector
"import", so they sit next to every collected signal with their provenance.

Every imported company is tagged ACCOUNT_TRACKED (value: the batch, a "lote")
and, when the file gives one, ACCOUNT_SEGMENT. "Tracked accounts" are exactly
the companies whose current ACCOUNT_TRACKED reading is positive; BORME, press,
jobs and scoring only ever look at those.

Columns (header names in Spanish or English, any case; "," or ";"):
    name, domain                       required
    cif, segment, province, employees, revenue_eur, notes, legal_name, batch
"""

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite

from harvey.collectors.spain.text import clean_snippet, fold, normalize_cif

logger = logging.getLogger("harvey.collectors.spain.accounts")

COLUMN_ALIASES = {
    "name": ("name", "nombre", "empresa", "company", "company name", "account", "account name",
             "nombre comercial"),
    "domain": ("domain", "dominio", "web", "website", "url", "sitio web", "company domain"),
    "cif": ("cif", "nif", "vat", "cif/nif", "tax id"),
    "segment": ("segment", "segmento", "vertical"),
    "province": ("province", "provincia", "region", "state"),
    "employees": ("employees", "empleados", "plantilla", "employee count", "num employees",
                  "numero de empleados", "headcount", "size"),
    "revenue_eur": ("revenue_eur", "revenue", "facturacion", "ventas", "annual revenue",
                    "facturacion eur", "ingresos"),
    "notes": ("notes", "notas", "comentarios", "observaciones"),
    "legal_name": ("legal_name", "legal name", "razon social", "denominacion social"),
    "batch": ("batch", "lote", "cohort"),
}
_HEADER = {fold(alias).replace("_", " "): key
           for key, aliases in COLUMN_ALIASES.items() for alias in aliases}


def normalize_domain(value: str) -> str:
    """"https://www.Ejemplo.es/contacto" → "ejemplo.es"; "" if it isn't one."""
    text = (value or "").strip().lower()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/")[0].split("?")[0].split("#")[0].split("@")[-1].split(":")[0]
    text = text.removeprefix("www.").strip(".")
    return text if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", text) else ""


def parse_number(value: str) -> tuple[float | None, str]:
    """A number as Spanish and English spreadsheets write it.

    "1.200" → 1200, "1.200.000,50" → 1200000.5, "12,5M" → 12500000,
    "3,2 M€" → 3200000, "51-200" → 125.5 (a range's midpoint; the raw text
    is kept alongside). Returns (number or None, raw text).
    """
    raw = (value or "").strip()
    if not raw:
        return None, ""
    text = fold(raw).replace("€", "").replace("eur", "").replace(" ", "")
    rng = re.fullmatch(r"(\d[\d.,]*)\s*[-–a]\s*(\d[\d.,]*)", text)
    if rng:
        lo, _ = parse_number(rng.group(1))
        hi, _ = parse_number(rng.group(2))
        if lo is not None and hi is not None:
            return (lo + hi) / 2, raw
    m = re.fullmatch(r"(\d[\d.,]*)(k|m|mm|mill|millones|mn|bn|b)?\+?", text)
    if not m:
        return None, raw
    digits, suffix = m.group(1), m.group(2) or ""
    if "," in digits and "." in digits:
        if digits.rfind(",") > digits.rfind("."):
            digits = digits.replace(".", "").replace(",", ".")
        else:
            digits = digits.replace(",", "")
    elif "," in digits:
        parts = digits.split(",")
        digits = digits.replace(",", "") if len(parts) > 2 or len(parts[-1]) == 3 else digits.replace(",", ".")
    elif "." in digits:
        parts = digits.split(".")
        if len(parts) > 2 or len(parts[-1]) == 3:
            digits = digits.replace(".", "")
    try:
        number = float(digits)
    except ValueError:
        return None, raw
    number *= {"k": 1e3, "m": 1e6, "mm": 1e6, "mill": 1e6, "millones": 1e6, "mn": 1e6,
               "bn": 1e9, "b": 1e9}.get(suffix, 1)
    return number, raw


@dataclass
class AccountRow:
    line: int
    name: str
    domain: str
    cif: str = ""
    segment: str = ""
    province: str = ""
    employees: float | None = None
    employees_raw: str = ""
    revenue_eur: float | None = None
    revenue_raw: str = ""
    notes: str = ""
    legal_name: str = ""
    batch: str = ""


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    observations: int = 0
    skipped: list[str] = field(default_factory=list)
    company_ids: list[str] = field(default_factory=list)
    batch: str = ""


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_rows(text: str) -> tuple[list[AccountRow], list[str]]:
    """Parse the CSV. Returns (rows, problems); a bad row never stops the rest."""
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    if "\t" in sample.split("\n", 1)[0] and sample.count("\t") > sample.count(delimiter):
        delimiter = "\t"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return [], ["el archivo está vacío"]
    columns = [_HEADER.get(fold(h).replace("_", " ").strip()) for h in header]
    if "name" not in columns or "domain" not in columns:
        return [], ["la cabecera necesita al menos las columnas 'name' (o nombre) y 'domain' (o web) "
                    f"(encontradas: {', '.join(h.strip() for h in header)})"]
    rows, problems, seen = [], [], set()
    for line, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        record = {}
        for key, value in zip(columns, values):
            if key and key not in record:
                record[key] = value.strip()
        name = clean_snippet(record.get("name", ""), 160)
        domain = normalize_domain(record.get("domain", ""))
        if not domain:
            problems.append(f"línea {line}: sin un dominio válido ({record.get('domain', '')!r}), omitida")
            continue
        if domain in seen:
            problems.append(f"línea {line}: {domain} está repetido; vale la primera fila")
            continue
        seen.add(domain)
        employees, employees_raw = parse_number(record.get("employees", ""))
        revenue, revenue_raw = parse_number(record.get("revenue_eur", ""))
        raw_cif = record.get("cif", "")
        cif = normalize_cif(raw_cif)
        if raw_cif and not cif:
            problems.append(f"línea {line}: {raw_cif!r} no parece un CIF, no se guarda")
        rows.append(AccountRow(
            line=line, name=name or domain, domain=domain, cif=cif,
            segment=clean_snippet(record.get("segment", ""), 60).lower(),
            province=clean_snippet(record.get("province", ""), 60),
            employees=employees, employees_raw=employees_raw,
            revenue_eur=revenue, revenue_raw=revenue_raw,
            notes=clean_snippet(record.get("notes", ""), 1000),
            legal_name=clean_snippet(record.get("legal_name", ""), 160),
            batch=clean_snippet(record.get("batch", ""), 60),
        ))
    return rows, problems


async def _latest(state, company_id: str, code: str) -> dict | None:
    rows = await state.get_observations(company_id=company_id, signal_code=code,
                                        latest_only=True, limit=1)
    return rows[0] if rows else None


def _same_reading(prev: dict | None, num, text: str) -> bool:
    if prev is None:
        return False
    pnum = prev.get("value_num")
    return (pnum == num or (pnum is not None and num is not None and abs(pnum - num) < 1e-9)) \
        and (prev.get("value_text") or "") == (text or "")


async def _update_company(state, company_id: str, row: AccountRow) -> None:
    sets, params = ["updated_at = CURRENT_TIMESTAMP"], []
    if row.name:
        sets.append("name = ?")
        params.append(row.name)
    if row.province:
        sets.append("location = ?")
        params.append(row.province)
    if row.notes:
        sets.append("notes = ?")
        params.append(row.notes)
    if row.employees_raw:
        sets.append("company_size = ?")
        params.append(row.employees_raw)
    async with state._connect() as db:
        await db.execute(f"UPDATE companies SET {', '.join(sets)} WHERE id = ?", (*params, company_id))
        await db.commit()


async def import_accounts(state, path: str | Path, batch: str = "", segment: str = "",
                          dry_run: bool = False) -> ImportReport:
    """Create or update every account in the file and record its firmographics.

    ``batch`` names the lote (default: the file's name); a ``batch`` column
    overrides it per row. ``segment`` applies to rows without one. Readings
    identical to the current one aren't written again, so re-importing the
    same file is a no-op.
    """
    from harvey.models.company import Company
    from harvey.signals import seed_signal_catalog

    path = Path(path)
    rows, problems = read_rows(_decode(path.read_bytes()))
    report = ImportReport(skipped=problems, batch=batch or path.stem)
    if dry_run or not rows:
        report.created = len(rows)
        return report
    await seed_signal_catalog(state)
    run_id = await state.start_run("import", provider="csv",
                                   params={"file": path.name, "batch": report.batch})
    try:
        for row in rows:
            existing = await state.get_company_by_domain(row.domain)
            if existing:
                company_id = existing.id
                await _update_company(state, company_id, row)
                report.updated += 1
            else:
                company_id = await state.add_company(Company(
                    name=row.name, domain=row.domain, website=f"https://{row.domain}",
                    location=row.province, notes=row.notes, company_size=row.employees_raw,
                    source="import", source_url=f"file:{path.name}",
                ))
                report.created += 1
            report.company_ids.append(company_id)
            obs = []

            async def put(code, num=None, text=""):
                if _same_reading(await _latest(state, company_id, code), num, text):
                    return
                obs.append({"signal_code": code, "company_id": company_id, "collector": "import",
                            "value_num": num, "value_text": text, "confidence": 1.0,
                            "evidence_url": f"file:{path.name}#L{row.line}"})

            await put("ACCOUNT_TRACKED", 1, row.batch or report.batch)
            seg = row.segment or (segment or "").strip().lower()
            if seg:
                await put("ACCOUNT_SEGMENT", None, seg)
            if row.employees is not None:
                await put("EMPLOYEE_COUNT", row.employees, row.employees_raw)
            if row.revenue_eur is not None:
                await put("REVENUE_EUR", row.revenue_eur, row.revenue_raw)
            if row.province:
                await put("HQ_PROVINCE", None, row.province)
            if row.cif:
                await put("COMPANY_CIF", None, row.cif)
            if row.legal_name:
                await _set_legal_name(state, company_id, row.legal_name)
            report.observations += await state.add_observations(obs, run_id=run_id)
        await state.finish_run(run_id, records=report.observations, cost_usd=0.0)
    except Exception as e:
        await state.finish_run(run_id, status="failed", error=str(e))
        raise
    return report


# The registered name, when it differs from the trading name, is what the
# BORME and InfoJobs print. Kept as a setting, not a signal: it's identity,
# not a buying signal.
async def _set_legal_name(state, company_id: str, legal_name: str) -> None:
    await state.set_setting(f"account_legal_name:{company_id}", legal_name)


async def legal_name(state, company_id: str) -> str:
    return await state.get_setting(f"account_legal_name:{company_id}", "")


# ── which companies are tracked accounts ──

_LATEST_TEXT = """(SELECT o.value_text FROM observations o
                  WHERE o.company_id = c.id AND o.signal_code = '{code}'
                  ORDER BY o.observed_at DESC, o.rowid DESC LIMIT 1)"""
_LATEST_NUM = """(SELECT o.value_num FROM observations o
                 WHERE o.company_id = c.id AND o.signal_code = '{code}'
                 ORDER BY o.observed_at DESC, o.rowid DESC LIMIT 1)"""


async def tracked_accounts(state, segment: str = "", batch: str = "",
                           limit: int | None = None) -> list[dict]:
    """Tracked accounts, each as {id, name, domain, segment, batch, province,
    cif, employees}, ordered by name. ``segment``/``batch`` filter exactly
    (case-insensitive)."""
    sql = f"""
        SELECT c.id, c.name, c.domain, c.location,
               {_LATEST_NUM.format(code='ACCOUNT_TRACKED')} AS tracked,
               {_LATEST_TEXT.format(code='ACCOUNT_TRACKED')} AS batch,
               {_LATEST_TEXT.format(code='ACCOUNT_SEGMENT')} AS segment,
               {_LATEST_TEXT.format(code='HQ_PROVINCE')} AS province,
               {_LATEST_TEXT.format(code='COMPANY_CIF')} AS cif,
               {_LATEST_NUM.format(code='EMPLOYEE_COUNT')} AS employees
        FROM companies c
        WHERE c.id IN (SELECT company_id FROM observations WHERE signal_code = 'ACCOUNT_TRACKED')
        ORDER BY LOWER(COALESCE(c.name, '')), c.id"""
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    out = []
    for r in rows:
        if not r.get("tracked"):
            continue
        if segment and (r.get("segment") or "").lower() != segment.strip().lower():
            continue
        if batch and (r.get("batch") or "").lower() != batch.strip().lower():
            continue
        r["province"] = r.get("province") or r.get("location") or ""
        r["legal_name"] = await legal_name(state, r["id"])
        out.append(r)
    return out[:limit] if limit else out


def names_for(account: dict) -> list[str]:
    """The names an account may appear under: legal name first, then trading."""
    names = [account.get("legal_name") or "", account.get("name") or ""]
    return [n for i, n in enumerate(names) if n and n not in names[:i]]
