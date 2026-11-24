"""``harvey users``: dashboard users (email + password). See dashboard_users.py.

Passwords are read with a hidden prompt, or from stdin with
``--password-stdin`` (for ``railway ssh`` and scripts). Never from argv,
where other local users can read them (``ps``) and shells keep history.
"""

from __future__ import annotations

import getpass
import sys


def _read_password(args, confirm: bool) -> str:
    if args.password_stdin:
        # Windows PowerShell pipes a byte-order mark ahead of the text.
        return sys.stdin.readline().rstrip("\r\n").lstrip("﻿")
    first = getpass.getpass("Contraseña: ")
    if confirm and getpass.getpass("Repite la contraseña: ") != first:
        raise SystemExit("Las contraseñas no coinciden.")
    return first


def cmd_users(args):
    from harvey.dashboard_users import MIN_PASSWORD_LENGTH, UserError, user_store

    action = args.users_action or "list"
    try:
        if action == "list":
            emails = user_store.emails()
            if not emails:
                print("No hay usuarios. Añade uno con: harvey users add <email>")
            for e in emails:
                print(e)
            print(f"\nArchivo: {user_store.path}")
        elif action in ("add", "passwd"):
            if not args.email:
                raise SystemExit(f"Uso: harvey users {action} <email>")
            print(f"Mínimo {MIN_PASSWORD_LENGTH} caracteres.", file=sys.stderr)
            email = user_store.set_password(args.email, _read_password(args, confirm=True),
                                            create=(action == "add"))
            verb = "Creado" if action == "add" else "Contraseña cambiada para"
            print(f"{verb} {email}. Las sesiones abiertas de ese usuario se han cerrado "
                  "(solo en este proceso; reinicia el panel si ya estaba en marcha).")
        elif action == "remove":
            if not args.email:
                raise SystemExit("Uso: harvey users remove <email>")
            user_store.remove(args.email)
            print(f"Eliminado {args.email}. Reinicia el panel para cerrar sus sesiones abiertas.")
    except UserError as e:
        raise SystemExit(str(e)) from None


def register(subparsers) -> None:
    sub = subparsers.add_parser("users", help="Dashboard users (email + password)")
    sub.add_argument("users_action", nargs="?", default="list",
                     choices=["list", "add", "passwd", "remove"])
    sub.add_argument("email", nargs="?", default="")
    sub.add_argument("--password-stdin", action="store_true",
                     help="Read the password from the first line of stdin")
    sub.set_defaults(func=cmd_users)
