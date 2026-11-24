"""The sign-off under each cold email, built from ``persona:``.

    José Miguel Valenzuela
    AI FAST TRACK · aifasttrack.tech

Name, then company and website (the first of channels.email.link_domains,
the user's own site). Plain text like the rest of the email. It goes
between the body and the compliance footer, added at send time like the
footer, so it reaches mail already queued and the Outbox shows it before
anyone approves. Nothing is added when the body already ends with the
name, full or first name only (the writer signed it), or the persona has no name.
"""

from __future__ import annotations


def signature_lines(config) -> list[str]:
    persona = getattr(config, "persona", None)
    name = " ".join(str(getattr(persona, "name", "") or "").split())
    if not name:
        return []
    company = " ".join(str(getattr(persona, "company", "") or "").split())
    if company.lower() in ("your company",):
        company = ""
    email = getattr(getattr(config, "channels", None), "email", None)
    domains = [str(d).strip().lower() for d in getattr(email, "link_domains", None) or [] if str(d).strip()]
    second = " · ".join(x for x in (company, domains[0] if domains else "") if x)
    return [name] + ([second] if second else [])


def is_signed(body: str, config) -> bool:
    """The last lines of the body already carry the persona's name."""
    lines = signature_lines(config)
    if not lines:
        return True
    name = lines[0].lower()
    tail_lines = [l.strip().lower() for l in (body or "").rstrip().splitlines()[-4:]]
    if name in "\n".join(tail_lines):
        return True
    # Signed with the first name only ("Un saludo,\nJosé Miguel").
    first = name.split()[0]
    last = [l for l in tail_lines if l][-1:] or [""]
    return last[0].split()[:1] == [first] and len(last[0]) <= len(name)


def outgoing_footer(config, body: str = "") -> str:
    """What goes under a cold email: the signature (unless the body is
    already signed), a blank line, then the compliance footer."""
    from harvey.config import compliance_footer_lines
    sign = [] if is_signed(body, config) else signature_lines(config)
    legal = compliance_footer_lines(config)
    parts = ["\n".join(sign)] if sign else []
    if legal:
        parts.append("\n".join(legal))
    return "\n\n".join(parts)
