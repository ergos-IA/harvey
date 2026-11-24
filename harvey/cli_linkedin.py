"""``harvey linkedin``: LinkedIn outreach (harvey/linkedin_queue.py, harvey/linkedin_worker.py).

On the server (where the accounts are):
    harvey linkedin                      # summary and the queue
    harvey linkedin plan [--min-score 70] [--limit 20]
    harvey linkedin draft [--limit 10]   # Claude writes note + message
    harvey linkedin approve <id>... | --all
    harvey linkedin reject <id>

On the operator's PC (where the browser is):
    harvey linkedin login                # once: log in by hand in the window that opens
    harvey linkedin work [--server URL] [--dry-run] [--now] [--headless]
"""

from __future__ import annotations

import asyncio


async def _state():
    from harvey import linkedin_queue as lq
    from harvey.state import StateManager
    state = StateManager()
    await state.init_db()
    await lq.ensure_tables(state)
    return state


def _config():
    try:
        from harvey.config import load_config
        return load_config()
    except Exception:
        return None


async def _show(args):
    from harvey import linkedin_queue as lq
    state = await _state()
    s = await lq.summary(state)
    counts = ", ".join(f"{k} {v}" for k, v in s["queue"].items() if v)
    print(f"\n  Cola: {counts}" if counts else "\n  Cola vacía")
    if s["jobs"]:
        print("  Búsquedas: " + ", ".join(f"{k} {v}" for k, v in s["jobs"].items()))
    for item in await lq.queue(state, args.status or ""):
        print(f"\n  [{item['id']}] {item['status']:<14} {item['full_name']} · {item['title'][:60]}"
              f" · {item['company_name']}\n    {item['profile_url']}")
        if item["note"]:
            print(f"    Nota: {item['note']}")
        if item["message"]:
            print("    Mensaje: " + item["message"].replace("\n", "\n             "))
        if item["flags"]:
            print(f"    ! Revisar: {item['flags']}")
        if item["error"]:
            print(f"    ! {item['error']}")
    print()


async def _plan(args):
    from harvey import linkedin_queue as lq
    created = await lq.plan(await _state(), _config(), min_score=args.min_score, limit=args.limit)
    print(f"\n  {created} cuenta(s)/persona(s) nuevas para LinkedIn. "
          "Las búsquedas las hace `harvey linkedin work` en el PC; luego: harvey linkedin draft\n")


async def _draft(args):
    from harvey import linkedin_queue as lq
    from harvey.brain import Brain
    config = _config()
    if config is None:
        raise SystemExit("No se puede cargar la configuración.")
    state = await _state()
    made = await lq.draft(state, config, Brain(state, config.brain), limit=args.limit)
    print(f"\n  {made} borrador(es) listos. Revísalos: harvey linkedin --status pending_review\n")


async def _approve(args):
    from harvey import linkedin_queue as lq
    state = await _state()
    if args.all:
        n = await lq.approve(state, None)
        print(f"\n  {n} aprobado(s). Los marcados con «Revisar» se aprueban uno a uno, por id.\n")
    elif args.ids:
        print(f"\n  {await lq.approve(state, args.ids)} aprobado(s).\n")
    else:
        raise SystemExit("Uso: harvey linkedin approve <id>... | --all")


async def _reject(args):
    from harvey import linkedin_queue as lq
    if not args.ids:
        raise SystemExit("Uso: harvey linkedin reject <id>...")
    state = await _state()
    n = sum([await lq.reject(state, i) for i in args.ids])
    print(f"\n  {n} descartado(s).\n")


async def _login(args):
    from harvey.linkedin_worker import PROFILE_DIR, Browser
    browser = Browser(headless=False)
    await browser.start()
    try:
        print("\n  Inicia sesión en LinkedIn en la ventana que se ha abierto (tienes 10 minutos).")
        ok = await browser.wait_for_login()
    finally:
        await browser.stop()
    print(f"  {'Sesión guardada' if ok else 'No se completó el inicio de sesión'} en {PROFILE_DIR}\n")


async def _work(args):
    from harvey.linkedin_worker import Activity, Browser, Server, in_office_hours, run_once, server_settings
    url, token = server_settings(args.server)
    if not args.now and not in_office_hours():
        print("\n  Fuera de horario (lunes a viernes, 9:00-19:00 en Madrid). Usa --now para forzarlo.\n")
        return
    activity = Activity()
    server = Server(url, token)
    browser = Browser(headless=args.headless)
    await browser.start()
    try:
        if not await browser.logged_in():
            raise SystemExit("La sesión de LinkedIn no está iniciada: harvey linkedin login")
        mode = " (simulación: no se pulsa enviar ni se informa al servidor)" if args.dry_run else ""
        print(f"\n  Trabajando{mode}...")
        gap = (3, 8) if args.dry_run else (40, 110)
        done = await run_once(server, browser, activity, dry_run=args.dry_run, gap=gap)
        print(f"\n  Hecho: {done['find']} búsqueda(s), {done['invite']} invitación(es), "
              f"{done['check']} comprobación(es), {done['message']} mensaje(s), {done['errors']} error(es).\n")
    finally:
        await browser.stop()
        await server.close()


def cmd_linkedin(args):
    action = {"plan": _plan, "draft": _draft, "approve": _approve, "reject": _reject,
              "login": _login, "work": _work}.get(args.linkedin_action, _show)
    _default_limits(args)
    asyncio.run(action(args))


def register(subparsers) -> None:
    sub = subparsers.add_parser("linkedin", help="LinkedIn outreach: queue (server) and worker (your PC)")
    sub.add_argument("linkedin_action", nargs="?", default="show",
                     choices=["show", "plan", "draft", "approve", "reject", "login", "work"])
    sub.add_argument("ids", nargs="*", default=[])
    sub.add_argument("--status", default="", help="show: only this status")
    sub.add_argument("--min-score", type=float, default=70, help="plan: minimum product score")
    sub.add_argument("--limit", type=int, default=None)
    sub.add_argument("--all", action="store_true", help="approve: every unflagged draft")
    sub.add_argument("--server", default="", help="work: the Harvey server (or HARVEY_REMOTE_URL)")
    sub.add_argument("--dry-run", action="store_true", help="work: everything but the final click")
    sub.add_argument("--now", action="store_true", help="work: ignore office hours")
    sub.add_argument("--headless", action="store_true", help="work: no visible window")
    sub.set_defaults(func=cmd_linkedin)


def _default_limits(args):
    if args.limit is None:
        args.limit = 20 if args.linkedin_action == "plan" else 10
