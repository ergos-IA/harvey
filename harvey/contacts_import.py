"""Import named people (from Clay or any list) into accounts already on file.

The account flow (``harvey accounts import``) brings companies but nobody at
them; the scout then reads each site for a team page, and most industrial or
wholesale sites have none, so the company ends up written to through its
published inbox (info@). This module fills that gap with people found
elsewhere (a Clay people search, a spreadsheet):

    domain, name, title, linkedin_url, since, location, notes, company_description

For each company, people are tried in the order given (put the best first).
Each one's address is worked out the usual way (the company's email pattern,
then one candidate checked with the verifier) and only a ``verified`` or
``risky`` address counts. Up to ``per_company`` people per company are added
as prospects; the rest are reported, not stored.

When a company gains a reachable person, its general-inbox prospect steps
aside: if it was never sent to, it is marked ``replaced`` and any of its mail
still waiting for review is rejected. Inbox mail already sent is left alone.

``notes`` (what the person does, how long in the role) goes to the prospect's
research notes, which the writer may cite. ``company_description`` fills the
company's own description when it has none.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from harvey.models.prospect import COMPANY_INBOX_SOURCE, Prospect

SOURCE = "imported_contact"
REACHABLE = ("verified", "risky")
REPLACED = "replaced"

# Second given names common enough in Spain that "Francisco José Tarín"
# reads as two given names and one surname, not one and two.
_GIVEN = {
    "jose", "josé", "maria", "maría", "luis", "angel", "ángel", "antonio", "manuel",
    "carlos", "javier", "ignacio", "jesus", "jesús", "miguel", "juan", "pedro", "pablo",
    "ramon", "ramón", "francisco", "alberto", "andres", "andrés", "elena", "isabel",
    "carmen", "pilar", "teresa", "luisa", "josep", "joan", "enrique",
    "vicente", "rafael", "fernando", "eugenia", "victoria", "dolores", "jordi",
}
_PARTICLES = {"de", "del", "la", "las", "los", "y", "i", "van", "von", "da", "dos"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _proper(name: str) -> str:
    """'MARIA JOSE GONZALEZ' / 'esteve vilardell' -> title case; mixed case kept."""
    name = " ".join((name or "").split())
    if name and (name.isupper() or name.islower()):
        return " ".join(w if w.lower() in _PARTICLES else w.capitalize() for w in name.split())
    return name


def split_name(full: str) -> tuple[str, str, str, str]:
    """(first, last, email_first, email_last): given names and surnames as
    stored, and the two words an address is built from (the first given name
    and the first surname, Spanish style)."""
    words = _proper(full).split()
    if not words:
        return "", "", "", ""
    if len(words) == 1:
        return words[0], "", words[0], ""
    given = 1
    core = [w for w in words if w.lower() not in _PARTICLES]
    if words[1].lower() not in _PARTICLES and (
            len(core) >= 4 or (len(core) == 3 and core[1].lower() in _GIVEN)):
        given = 2
    first = " ".join(words[:given])
    surnames = words[given:]
    email_last = next((w for w in surnames if w.lower() not in _PARTICLES), "")
    return first, " ".join(surnames), words[0], email_last


def seniority(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ("ceo", "gerente", "director general", "consejero delegado", "fundador",
                            "founder", "owner", "propietari", "presidente", "managing director")):
        return "c_suite"
    if "director" in t or "head of" in t or "jefe" in t or "responsable" in t:
        return "director"
    if "manager" in t:
        return "manager"
    return "individual"


@dataclass
class Row:
    domain: str
    name: str
    title: str = ""
    linkedin_url: str = ""
    since: str = ""
    location: str = ""
    notes: str = ""
    company_description: str = ""


@dataclass
class Report:
    added: list[dict] = field(default_factory=list)          # {company, name, title, email, status}
    unreachable: list[dict] = field(default_factory=list)    # tried, no deliverable address
    skipped: list[dict] = field(default_factory=list)        # {domain, name, reason}
    inboxes_replaced: int = 0
    outbox_rejected: int = 0
    descriptions_filled: int = 0


def _clean_domain(value: str) -> str:
    d = (value or "").strip().lower()
    for prefix in ("https://", "http://"):
        d = d.removeprefix(prefix)
    d = d.removeprefix("www.").split("/")[0]
    return d


def load_rows(path: str | Path) -> list[Row]:
    """A JSON list of objects, or a CSV (comma or semicolon) with a header."""
    text = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() == ".json":
        data = json.loads(text)
        items = data.get("contacts", data) if isinstance(data, dict) else data
    else:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;")
        items = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item = {str(k).strip().lower(): ("" if v is None else str(v).strip()) for k, v in item.items()}
        domain = _clean_domain(item.get("domain") or item.get("website") or "")
        name = item.get("name") or item.get("full_name") or \
            f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
        if not domain or not name:
            continue
        rows.append(Row(domain=domain, name=name, title=item.get("title", ""),
                        linkedin_url=item.get("linkedin_url") or item.get("url", ""),
                        since=item.get("since", ""), location=item.get("location", ""),
                        notes=item.get("notes", ""),
                        company_description=item.get("company_description", "")))
    return rows


def research_notes(row: Row, company: str) -> str:
    parts = []
    if row.title:
        role = f"{row.title} en {company}" if company else row.title
        if row.since:
            role += f" desde {row.since[:4]}"
        parts.append(role + ".")
    if row.notes:
        parts.append(row.notes.strip())
    return " ".join(parts)[:500]


async def _fill_description(state, company_id: str, text: str) -> bool:
    if not text.strip():
        return False
    async with state._connect() as db:
        cursor = await db.execute(
            "UPDATE companies SET description = ? WHERE id = ? "
            "AND (description IS NULL OR description = '')",
            (text.strip()[:2000], company_id))
        await db.commit()
        return cursor.rowcount > 0


async def _retire_inbox(state, inbox: Prospect) -> tuple[int, int]:
    """Step a never-sent inbox prospect aside. Returns (retired, rejected)."""
    async with state._connect() as db:
        async with db.execute(
                "SELECT COUNT(*) FROM outbox WHERE prospect_id = ? AND status IN ('sending', 'sent')",
                (inbox.id,)) as cursor:
            if (await cursor.fetchone())[0]:
                return 0, 0
        now = _utcnow()
        cursor = await db.execute(
            "UPDATE outbox SET status = 'rejected', updated_at = ? "
            "WHERE prospect_id = ? AND status IN ('pending_review', 'approved')", (now, inbox.id))
        rejected = cursor.rowcount
        cursor = await db.execute(
            f"UPDATE prospects SET status = '{REPLACED}', updated_at = ? "
            "WHERE id = ? AND status IN ('new', 'queued', 'write_failed')", (now, inbox.id))
        retired = cursor.rowcount
        await db.commit()
    return retired, rejected


async def import_contacts(state, rows: list[Row], *, env=None, per_company: int = 1,
                          dry_run: bool = False, finder=None) -> Report:
    """Add up to ``per_company`` reachable people to each company in ``rows``."""
    if finder is None:
        from harvey.integrations.email_finder import find_email as finder
    report = Report()
    by_domain: dict[str, list[Row]] = {}
    for row in rows:
        by_domain.setdefault(row.domain, []).append(row)

    for domain, people in by_domain.items():
        company = await state.get_company_by_domain(domain)
        if company is None:
            report.skipped += [{"domain": domain, "name": p.name, "reason": "empresa no importada"}
                               for p in people]
            continue
        if not dry_run and await _fill_description(state, company.id, people[0].company_description):
            report.descriptions_filled += 1

        existing = await state.get_contacts_for_company(company.id)
        named = [p for p in existing if p.source != COMPANY_INBOX_SOURCE
                 and (p.email_status or "") in REACHABLE]
        room = max(per_company - len(named), 0)
        known_names = {p.full_name().lower() for p in existing}
        others = [split_name(p.name)[2:] for p in people]
        others = [(f, el) for f, el in others if f and el]

        added_here = 0
        for row in people:
            first, last, email_first, email_last = split_name(row.name)
            label = {"domain": domain, "name": _proper(row.name)}
            if added_here >= room:
                report.skipped.append({**label, "reason": "ya hay persona en esta empresa"})
                continue
            if not (email_first and email_last):
                report.skipped.append({**label, "reason": "sin apellido"})
                continue
            if f"{first} {last}".lower() in known_names:
                report.skipped.append({**label, "reason": "ya estaba"})
                continue
            mine = (email_first, email_last)
            result = await finder(email_first, email_last, domain, verify=True, env=env, state=state,
                                  other_people=[o for o in others if o != mine] or None)
            entry = {"company": company.name, "name": f"{first} {last}", "title": row.title,
                     "email": result.email, "status": result.status}
            if result.status not in REACHABLE or not result.email:
                report.unreachable.append(entry)
                continue
            if await state.get_prospect_by_email(result.email):
                report.skipped.append({**label, "reason": f"{result.email} ya está en Harvey"})
                continue
            prospect = Prospect(
                first_name=first, last_name=last, email=result.email,
                email_status=result.status, email_verified=(result.status == "verified"),
                linkedin_url=row.linkedin_url, title=row.title or "", seniority=seniority(row.title),
                company=company.name, company_id=company.id, industry=company.industry or "",
                source=SOURCE, source_url=row.linkedin_url or f"https://{domain}",
                personalization_notes=research_notes(row, company.name))
            if not dry_run:
                await state.add_prospect(prospect)
            report.added.append(entry)
            added_here += 1

        if added_here and not dry_run:
            for inbox in (p for p in existing if p.source == COMPANY_INBOX_SOURCE):
                retired, rejected = await _retire_inbox(state, inbox)
                report.inboxes_replaced += retired
                report.outbox_rejected += rejected
    return report
