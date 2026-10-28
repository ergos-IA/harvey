"""The process, phase by phase, for one product: where every account is,
what moves it on, and what is holding it (the Proceso tab).

    0 Producto     its sheet: offer, ICP, scoring rules, gates
    1 Cuentas      the accounts assigned to it
    2 Señales      what Harvey has read about each one
    3 Puntuación   its rules over those signals; the contacts gate
    4 Contactos    people found there, with a sendable email
    5 Redacción    its sequence drafted; the write gate
    6 Envío        reviewed in the Outbox and sent
    7 Respuesta    replies, meetings, opt-outs

Each account sits at one phase with a state: ok (Harvey is on it), you
(waiting for your decision), wait (queued behind another product),
blocked (something has to change), stopped (out, by you or by them), done.
Read-only: the decisions are harvey.products.set_decision.
"""

from harvey.products import Product, assignments, choose_product, passes_threshold

PHASES = [
    ("producto", "Producto"),
    ("cuentas", "Cuentas"),
    ("senales", "Señales"),
    ("puntuacion", "Puntuación"),
    ("contactos", "Contactos"),
    ("redaccion", "Redacción"),
    ("envio", "Envío"),
    ("respuesta", "Respuesta"),
]
STATES = ("ok", "you", "wait", "blocked", "stopped", "done")

# Written by the account import, not read by enrichment.
_IMPORT_CODES = ("ACCOUNT_TRACKED", "ACCOUNT_SEGMENT", "EMPLOYEE_COUNT", "REVENUE_EUR",
                 "HQ_PROVINCE", "COMPANY_CIF", "ICP_SCORE")
_SENDABLE = ("verified", "risky")


def _fmt(n) -> str:
    return f"{n:g}" if isinstance(n, (int, float)) else str(n)


async def _facts(state) -> dict:
    """Everything the phases read, in a handful of queries."""
    facts = {"enriched": set(), "signals": {}, "prospects": {}, "checked": {}, "outbox": {}}
    marks = ",".join("?" * len(_IMPORT_CODES))
    async with state._connect() as db:
        async with db.execute("SELECT key FROM settings WHERE key LIKE 'accounts_enriched:%:%'") as cur:
            for (key,) in await cur.fetchall():
                facts["enriched"].add(key.split(":", 2)[2])
        async with db.execute(
            f"SELECT company_id, COUNT(DISTINCT signal_code) FROM observations "
            f"WHERE signal_code NOT IN ({marks}) GROUP BY company_id", _IMPORT_CODES) as cur:
            facts["signals"] = {cid: n for cid, n in await cur.fetchall()}
        async with db.execute(
            "SELECT company_id, status, COALESCE(email, ''), COALESCE(email_status, '') FROM prospects"
        ) as cur:
            for cid, status, email, email_status in await cur.fetchall():
                facts["prospects"].setdefault(cid, []).append(
                    (status or "", bool(email) and email_status in _SENDABLE))
        async with db.execute(
            "SELECT id, prospects_checked_at FROM companies WHERE prospects_checked_at IS NOT NULL"
        ) as cur:
            facts["checked"] = {cid: at for cid, at in await cur.fetchall()}
        async with db.execute(
            "SELECT c.product_id, p.company_id, o.status, COUNT(*) FROM outbox o "
            "JOIN campaigns c ON c.id = o.campaign_id JOIN prospects p ON p.id = o.prospect_id "
            "WHERE o.kind = 'sequence' AND c.product_id != '' "
            "GROUP BY c.product_id, p.company_id, o.status") as cur:
            for pid, cid, status, n in await cur.fetchall():
                facts["outbox"].setdefault((pid, cid), {})[status] = n
    return facts


def _closed_contacts(product: Product, row: dict, score) -> tuple[int, str, str]:
    """(phase, state, label) for an account whose contacts gate is shut."""
    if product.status != "active":
        return 3, "blocked", "Producto en pausa"
    if (row.get("contacts_decision") or "") == "stop":
        return 3, "stopped", "Descartada por ti"
    if product.gates.contacts == "manual":
        return 3, "you", "Espera tu aprobación para buscar contactos"
    if score is None:
        return 3, "ok", "Sin puntuar todavía"
    return 3, "blocked", (f"Por debajo del corte ({_fmt(score)} de "
                          f"{_fmt(product.scoring.threshold)})")


def place(product: Product, row: dict, facts: dict, first: Product | None) -> dict:
    """Where one account of this product is, and why."""
    cid = row["company_id"]
    people = facts["prospects"].get(cid, [])
    statuses = {s for s, _ in people}
    sendable = sum(1 for _, ok in people if ok)
    box = facts["outbox"].get((product.id, cid), {})
    sent, review = box.get("sent", 0), box.get("pending_review", 0)
    queued = box.get("approved", 0) + box.get("sending", 0)
    score = row.get("score")
    enriched = cid in facts["enriched"] or facts["signals"].get(cid, 0) > 0

    if "closed" in statuses:
        where = (7, "done", "Cerrada")
    elif "meeting" in statuses:
        where = (7, "done", "Reunión agendada")
    elif "replied" in statuses:
        where = (7, "ok", "Ha respondido: conversación en curso")
    elif "opted_out" in statuses:
        where = (7, "stopped", "Pidió la baja")
    elif "lost" in statuses:
        where = (7, "stopped", "Perdida")
    elif row.get("status") == "done":
        where = (6, "done", "Secuencia terminada sin respuesta")
    elif sent or queued:
        total = sum(box.values())
        label = f"Enviados {sent} de {total}" + (f" · {queued} programados" if queued else "")
        where = (6, "ok", label)
    elif review:
        where = (5, "you", f"{review} email(s) esperan tu revisión en la Bandeja")
    elif first is not None and first.id != product.id and row.get("status") == "pending" \
            and (sendable or people):
        # One sequence per company: another product goes there first.
        where = (5 if sendable else 4, "wait", f"En cola: antes va «{first.name}»")
    elif sendable:
        if not row.get("can_contact"):
            phase, state, label = _closed_contacts(product, row, score)
            where = (5, state, label + ": no se redacta")
        elif (row.get("write_decision") or "") == "stop":
            where = (5, "stopped", "Redacción detenida por ti")
        elif not row.get("can_write"):
            where = (5, "you", "Lista para redactar: espera tu aprobación")
        else:
            where = (5, "ok", "Lista: Harvey la redacta en el próximo ciclo")
    elif people:
        where = (4, "blocked", f"{len(people)} contacto(s) sin email verificable")
    elif row.get("can_contact"):
        if cid in facts["checked"]:
            where = (4, "blocked", "Revisó su web sin encontrar a nadie; reintenta en 14 días")
        else:
            where = (4, "ok", "Buscando contactos")
    elif not enriched and product.status == "active" \
            and (row.get("contacts_decision") or "") != "stop" and product.gates.contacts == "auto":
        where = (2, "ok", "Pendiente de enriquecer")
    else:
        where = _closed_contacts(product, row, score)

    phase, state, label = where
    return {
        "company_id": cid, "batch": row.get("batch") or "", "status": row.get("status"),
        "score": score, "why": row.get("why") or "",
        "above": passes_threshold(product, score) if product.scoring.configured() else None,
        "contacts_decision": row.get("contacts_decision") or "",
        "write_decision": row.get("write_decision") or "",
        "can_contact": bool(row.get("can_contact")), "can_write": bool(row.get("can_write")),
        "enriched": enriched, "signals": facts["signals"].get(cid, 0),
        "contacts": len(people), "sendable": sendable,
        "outbox": {"review": review, "queued": queued, "sent": sent},
        "phase": phase, "state": state, "label": label,
    }


def _check(level: str, text: str, tab: str = "") -> dict:
    return {"level": level, "text": text, "tab": tab}


def phase_cards(product: Product, rows: list[dict], system: dict) -> list[dict]:
    """One card per phase: how many accounts sit there, by state, and what
    the phase needs from you (level ok | info | warn | block)."""
    counts = [{s: 0 for s in STATES} for _ in PHASES]
    for r in rows:
        counts[r["phase"]][r["state"]] += 1
    total = len(rows)
    reached = [sum(1 for r in rows if r["phase"] >= i) for i in range(len(PHASES))]
    checks: list[list[dict]] = [[] for _ in PHASES]

    c = checks[0]
    if product.status != "active":
        c.append(_check("block", "Producto en pausa: no avanza ninguna cuenta", "products"))
    if not product.description:
        c.append(_check("warn", "Sin descripción: el Writer no sabe qué vende", "products"))
    c.append(_check("ok", f"{len(product.icp.titles)} cargos objetivo", "products") if product.icp.titles
             else _check("info", "Sin cargos propios: usa los de la configuración", "products"))
    if product.scoring.configured():
        n = len(product.scoring.rules) + sum(len(s.rules) for s in product.scoring.segments.values())
        c.append(_check("ok", f"{n} {'regla' if n == 1 else 'reglas'} de puntuación · corte {_fmt(product.scoring.threshold)}",
                        "products"))
    else:
        c.append(_check("info", "Sin reglas de puntuación: todas las cuentas pasan el corte", "products"))
    if not product.knowledge:
        c.append(_check("info", "Sin conocimiento propio: usa el archivo entrenado", "products"))

    c = checks[1]
    if not total:
        c.append(_check("block", "Ninguna cuenta asignada: impórtalas o añádelas", "accounts"))
    else:
        batches = sorted({r["batch"] for r in rows if r["batch"]})
        c.append(_check("ok", f"{total} cuentas" + (f" · {', '.join(batches)}" if batches else ""),
                        "accounts"))

    c = checks[2]
    confirmed = system.get("confirmed_signals", 0)
    c.append(_check("ok", f"{confirmed} señales confirmadas", "signals") if confirmed
             else _check("block", "Ninguna señal confirmada: no se puede enriquecer", "signals"))
    enriched = sum(1 for r in rows if r["enriched"])
    if total:
        c.append(_check("ok" if enriched == total else "info", f"{enriched} de {total} enriquecidas",
                        "accounts"))
    if system.get("enrich_running"):
        c.append(_check("info", "Enriquecimiento en curso", "accounts"))

    c = checks[3]
    mode = {"auto": "pasan solas las que superan el corte", "manual": "solo las que apruebes",
            "all": "pasan todas, sin mirar el corte"}[product.gates.contacts]
    c.append(_check("info", f"Puerta: {mode}"))
    if product.scoring.configured() and total:
        above = sum(1 for r in rows if r["above"])
        c.append(_check("ok" if above else "warn", f"{above} de {total} superan el corte"))
    if counts[3]["you"]:
        c.append(_check("warn", f"{counts[3]['you']} esperan tu aprobación"))

    c = checks[4]
    c.append(_check("ok", "Verificador de emails configurado") if system.get("verifier_ok")
             else _check("block", "Sin verificador de emails: los encontrados nunca se envían", "settings"))
    with_people = sum(1 for r in rows if r["contacts"])
    sendable = sum(1 for r in rows if r["sendable"])
    c.append(_check("ok" if sendable else "info",
                    f"{with_people} con contactos · {sendable} con email enviable", "prospects"))

    c = checks[5]
    mode = {"auto": "redacta sola en cuanto hay contacto", "manual": "solo las que apruebes"}[
        product.gates.write]
    c.append(_check("info", f"Puerta: {mode}"))
    if counts[5]["you"]:
        c.append(_check("warn", f"{counts[5]['you']} te esperan (aprobar o revisar)", "outbox"))

    c = checks[6]
    c.append(_check("ok", f"Buzón configurado ({system.get('provider', '')})") if system.get("provider_ok")
             else _check("block", f"Sin buzón de envío ({system.get('provider', '')})", "settings"))
    if system.get("sending_paused"):
        c.append(_check("block", "Envíos en pausa", "controls"))
    c.append(_check("info", "Cada email espera tu aprobación" if system.get("approval", True)
                    else "Piloto automático: envía sin preguntar", "settings"))

    c = checks[7]
    replied = sum(1 for r in rows if r["phase"] == 7 and r["state"] in ("ok", "done"))
    c.append(_check("ok" if replied else "info", f"{replied} han respondido", "conversations"))

    cards = []
    for i, (key, label) in enumerate(PHASES):
        level = "ok"
        for chk in checks[i]:
            if chk["level"] == "block":
                level = "block"
                break
            if chk["level"] == "warn":
                level = "warn"
        cards.append({"key": key, "label": label, "here": counts[i], "reached": reached[i],
                      "checks": checks[i], "level": level})
    return cards


async def product_process(state, product: Product, accounts: dict[str, dict], system: dict,
                          facts: dict | None = None) -> dict:
    """The Proceso tab for one product: its phase cards and its accounts."""
    facts = facts if facts is not None else await _facts(state)
    cache: dict = {}
    rows = []
    for row in await assignments(state, product_id=product.id):
        account = accounts.get(row["company_id"])
        if account is None:
            continue
        first, _ = await choose_product(state, row["company_id"], cache)
        placed = place(product, row, facts, first)
        placed.update(name=account.get("name") or "", domain=account.get("domain") or "",
                      segment=account.get("segment") or "")
        rows.append(placed)
    rows.sort(key=lambda r: (-r["phase"], r["score"] is None, -(r["score"] or 0), r["name"].lower()))
    return {"phases": phase_cards(product, rows, system), "accounts": rows}
