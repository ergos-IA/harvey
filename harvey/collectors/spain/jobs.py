"""Open roles in the functions the offer is built for (HIRING_FUNCTION).

A company hiring an "ingeniero de ofertas" or a second "administrativo de
pedidos" has that work piling up now; one that has had the role open for more
than 60 days can't fill it. Each row keeps the posting date ("posted
YYYY-MM-DD") so a scoring rule can ask for ``older_than_days: 60``.

Two sources, both strictly the company's own:
- the job board its website links to (harvey.collectors.ats, which includes
  the Spanish boards in ats_es) — never a guessed token;
- the official InfoJobs API, when INFOJOBS_CLIENT_ID/SECRET are set, keeping
  only offers whose author IS the company.
"""

import logging
import re

from harvey.collectors.spain.text import clean_snippet, fold

logger = logging.getLogger("harvey.collectors.spain.jobs")

# function → patterns over the folded title (lowercase, no accents, "/a" and
# "(a)" gender endings dropped).
DEFAULT_FUNCTIONS: dict[str, list[str]] = {
    "oficina técnica": [r"\boficina tecnica\b", r"\btechnical office\b"],
    "ingeniero de ofertas": [r"\b(?:ingenier[oa]s?|tecnic[oa]s?|responsable|jefe)(?: \w+)? de ofertas\b",
                             r"\bofertas? tecnicas?\b", r"\b(?:bid|proposals?|tender) (?:engineer|manager)\b",
                             r"\bestimador(?:a)?\b"],
    "técnico comercial": [r"\btecnic[oa]s? comercial(?:es)?\b", r"\bcomercial tecnic[oa]\b",
                          r"\bingenier[oa]s? (?:comercial|de ventas)\b", r"\btechnical sales\b",
                          r"\bsales engineer\b"],
    "ventas internas": [r"\bventas internas\b", r"\binside sales\b", r"\bcomercial intern[oa]\b",
                        r"\bback ?office comercial\b"],
    "atención al cliente": [r"\batencion al cliente\b", r"\bservicio al cliente\b", r"\bcustomer care\b",
                            r"\bcustomer service\b", r"\bcustomer support\b", r"\bsoporte al cliente\b",
                            r"\bservicio de atencion\b"],
    "administrativo de pedidos": [r"\badministrativ[oa]s? (?:de )?(?:pedidos|ventas|comercial)\b",
                                  r"\bgestion de pedidos\b", r"\bgestor(?:a)? de pedidos\b",
                                  r"\border (?:management|desk|entry)\b", r"\bcustomer order\b"],
}

_GENDER = re.compile(r"(?:/(?:a|as|os)\b|\((?:a|as)\)|\s*\(m/f(?:/d)?\)|\s*\(h/m\)|\s*\(f/m\))")


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", _GENDER.sub("", fold(title))).strip()


def compile_functions(functions: dict[str, list[str]] | None = None) -> dict[str, list[re.Pattern]]:
    """Watched functions as compiled patterns. Config patterns are plain
    lowercase phrases or regexes over the folded title; bad regexes are
    treated as literal phrases rather than failing the run."""
    out = {}
    for name, patterns in (functions or DEFAULT_FUNCTIONS).items():
        compiled = []
        for p in patterns or []:
            p = fold(p)
            try:
                compiled.append(re.compile(p))
            except re.error:
                compiled.append(re.compile(re.escape(p)))
        if compiled:
            out[name] = compiled
    return out


def function_of(title: str, functions: dict[str, list[re.Pattern]]) -> str:
    """The watched function a title belongs to, or ""."""
    text = normalize_title(title)
    for name, patterns in functions.items():
        if any(p.search(text) for p in patterns):
            return name
    return ""


def function_text(function: str, posting, source: str) -> str:
    """"técnico comercial · Técnico/a comercial · Ventas · Zaragoza · posted
    2026-08-01 · Personio"."""
    return clean_snippet(f"{function} · {posting.summary()} · {source}", 300)


def watched_rows(company_id: str, postings, functions, source: str, fallback_url: str = "",
                 limit: int = 8) -> list[dict]:
    rows = []
    for post in postings or []:
        fn = function_of(post.title, functions)
        if not fn:
            continue
        rows.append({
            "signal_code": "HIRING_FUNCTION", "company_id": company_id, "collector": "jobs",
            "value_num": None, "value_text": function_text(fn, post, source),
            "confidence": 1.0, "evidence_url": post.url or fallback_url,
        })
        if len(rows) >= limit:
            break
    return rows


async def collect_jobs(account: dict, functions, profile_collector=None, infojobs_creds=None,
                       infojobs_client=None) -> list[dict]:
    """HIRING_FUNCTION rows for one account.

    ``profile_collector`` is an open ProfileCollector (its client and its
    homepage/careers-page logic); ``None`` skips the board. When at least one
    source answered and listed nothing watched, one ``value_num=0`` row says
    so, so roles that closed stop counting.
    """
    from harvey.collectors.ats import detect_board, read_board
    from harvey.collectors.spain import infojobs
    from harvey.collectors.spain.accounts import names_for

    company_id, domain = account["id"], (account.get("domain") or "").lower()
    rows: list[dict] = []
    answered, evidence = False, ""

    if profile_collector is not None and domain:
        try:
            site, home = await profile_collector._resolve_site(domain)
            board = detect_board(home, domain) if home else None
            if home and board is None:
                _, chtml = await profile_collector._careers_page(site, home, domain)
                board = detect_board(chtml, domain)
            if board is not None:
                postings = await read_board(profile_collector._client, board)
                if postings is not None:
                    answered, evidence = True, board.page_url
                    rows += watched_rows(company_id, postings, functions, board.label, board.page_url)
        except Exception as e:
            logger.info(f"jobs: {domain} board unread: {type(e).__name__}: {e}")

    if infojobs_creds:
        offers = await infojobs.search_company(names_for(account), client=infojobs_client,
                                               creds=infojobs_creds)
        if offers is not None:
            answered = True
            evidence = evidence or "https://www.infojobs.net"
            seen = {r["value_text"].split(" · ")[1] for r in rows if " · " in r["value_text"]}
            for row in watched_rows(company_id, offers, functions, "InfoJobs"):
                if row["value_text"].split(" · ")[1] not in seen:
                    rows.append(row)

    if answered and not rows:
        rows.append({"signal_code": "HIRING_FUNCTION", "company_id": company_id, "collector": "jobs",
                     "value_num": 0, "value_text": "", "confidence": 1.0, "evidence_url": evidence})
    return rows
