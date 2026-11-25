"""``harvey contacts import``: named people for accounts already on file
(harvey/contacts_import.py).

    harvey contacts import people.csv [--per-company 1] [--dry-run]

Columns (CSV with comma or semicolon, or a JSON list): domain, name, title,
linkedin_url, since, location, notes, company_description. Put the best
person for each company first.
"""

from __future__ import annotations

import asyncio


async def _import(args):
    from harvey import contacts_import as ci
    from harvey.config import load_env
    from harvey.state import StateManager

    state = StateManager()
    await state.init_db()
    rows = ci.load_rows(args.file)
    if not rows:
        print("\n  El archivo no tiene filas con dominio y nombre.\n")
        return
    report = await ci.import_contacts(state, rows, env=load_env(),
                                      per_company=args.per_company, dry_run=args.dry_run)
    head = "Simulación (no se ha guardado nada)" if args.dry_run else "Importado"
    print(f"\n  {head}: {len(report.added)} persona(s) con correo entregable "
          f"de {len(rows)} fila(s).")
    for e in report.added:
        print(f"    + {e['company']}: {e['name']} ({e['title']}) -> {e['email']} [{e['status']}]")
    if report.unreachable:
        print(f"\n  Sin correo entregable ({len(report.unreachable)}):")
        for e in report.unreachable:
            print(f"    - {e['company']}: {e['name']} [{e['status'] or 'sin candidato'}]")
    if report.skipped:
        print(f"\n  Omitidas: {len(report.skipped)}")
        reasons: dict[str, int] = {}
        for s in report.skipped:
            reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>4}  {reason}")
    if not args.dry_run:
        print(f"\n  Buzones genéricos sustituidos: {report.inboxes_replaced} "
              f"(correos pendientes rechazados: {report.outbox_rejected}). "
              f"Descripciones de empresa rellenadas: {report.descriptions_filled}.")
    print()


def cmd_contacts(args):
    asyncio.run(_import(args))


def register(subparsers) -> None:
    sub = subparsers.add_parser("contacts", help="Import named people for accounts on file")
    sub.add_argument("contacts_action", choices=["import"])
    sub.add_argument("file", help="CSV or JSON: domain, name, title, linkedin_url, since, notes…")
    sub.add_argument("--per-company", type=int, default=1,
                     help="People with a deliverable address to keep per company (default 1)")
    sub.add_argument("--dry-run", action="store_true", help="Work out the addresses, store nothing")
    sub.set_defaults(func=cmd_contacts)
