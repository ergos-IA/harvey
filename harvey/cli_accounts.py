"""`harvey accounts …` — account-based selling to hand-picked companies.

    harvey accounts import cuentas.csv --batch lote-01 [--segment industrial]
    harvey accounts list [--segment X] [--batch Y]
    harvey accounts enrich [--only web,jobs,borme,news] [--segment X] [--batch Y]
    harvey accounts score [--segment X] [--batch Y] [--no-store]
    harvey accounts cohort [--segment X] [--min-score N] [--csv out.csv]

All of it is free: no model call, no paid API. Collection still needs the
signals confirmed first (`harvey signals --confirm CODE,...`).
"""

import asyncio
import csv
import sys


def _config_or_none():
    try:
        from harvey.config import load_config
        return load_config()
    except Exception:
        return None


def _scoring_config(config):
    from harvey.accounts_config import ScoringConfig
    return getattr(config, "scoring", None) or ScoringConfig()


async def _state():
    from harvey.state import StateManager
    state = StateManager()
    await state.init_db()
    return state


def _fmt_num(value) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}".replace(",", ".")


async def _import(args):
    from harvey.collectors.spain.accounts import import_accounts
    state = await _state()
    report = await import_accounts(state, args.file, batch=args.batch, segment=args.segment,
                                   dry_run=args.dry_run)
    if args.dry_run:
        print(f"\n  Dry run: {report.created} account(s) would be imported as batch "
              f"'{report.batch}'.")
    else:
        print(f"\n  Batch '{report.batch}': {report.created} new, {report.updated} updated, "
              f"{report.observations} observation(s) recorded.")
    for problem in report.skipped[:20]:
        print(f"    ! {problem}")
    if len(report.skipped) > 20:
        print(f"    ... and {len(report.skipped) - 20} more")
    if not args.dry_run:
        print("\n  Next: harvey signals --confirm <codes>, then harvey accounts enrich\n")


async def _list(args):
    from harvey.collectors.spain.accounts import tracked_accounts
    state = await _state()
    rows = await tracked_accounts(state, segment=args.segment, batch=args.batch)
    print(f"\n  {len(rows)} tracked account(s)\n")
    print(f"  {'Name':<34} {'Domain':<26} {'Segment':<14} {'Batch':<12} {'Province':<14} Empl.")
    for r in rows:
        print(f"  {(r['name'] or '')[:34]:<34} {(r['domain'] or '')[:26]:<26} "
              f"{(r['segment'] or '')[:14]:<14} {(r['batch'] or '')[:12]:<12} "
              f"{(r['province'] or '')[:14]:<14} {_fmt_num(r['employees'])}")
    print()


async def _enrich(args):
    from harvey.collectors.spain.enrich import KINDS, enrich_accounts
    only = [k.strip().lower() for k in (args.only or "").split(",") if k.strip()] or None
    bad = [k for k in only or [] if k not in KINDS]
    if bad:
        print(f"\n  Unknown --only value(s): {', '.join(bad)}. Choose from: {', '.join(KINDS)}\n")
        sys.exit(2)
    state = await _state()
    config = _config_or_none()
    report = await enrich_accounts(state, config, only=only, segment=args.segment, batch=args.batch,
                                   limit=args.limit, borme_days=args.borme_days,
                                   all_provinces=args.all_provinces)
    print(f"\n  Enriched {report.accounts} tracked account(s)")
    for line in report.summary_lines():
        print(f"    - {line}")
    print("\n  Next: harvey accounts score\n")


async def _score(args):
    from harvey.collectors.spain.accounts import tracked_accounts
    from harvey.scoring import score_accounts
    config = _config_or_none()
    scoring = _scoring_config(config)
    if not scoring.configured():
        print("\n  No scoring rules yet. Add a `scoring:` section to harvey.yaml "
              "(see harvey/accounts_config.py for the format).\n")
        return
    threshold = args.threshold if args.threshold is not None else scoring.threshold
    state = await _state()
    accounts = await tracked_accounts(state, segment=args.segment, batch=args.batch)
    results = await score_accounts(state, scoring, accounts, store=not args.no_store)
    above = sum(1 for _, s in results if s.score >= threshold)
    print(f"\n  {len(results)} account(s) scored — {above} at or above {threshold:g}\n")
    print(f"  {'#':>3} {'Score':>6}  {'Name':<32} {'Segment':<14} Rules that fired")
    for i, (account, score) in enumerate(results, start=1):
        mark = "*" if score.score >= threshold else " "
        fired = "; ".join(f"{p:+g} {d}" for p, d in score.fired) or "-"
        print(f"  {i:>3} {score.score:>6g}{mark} {(account['name'] or '')[:32]:<32} "
              f"{(account.get('segment') or '')[:14]:<14} {fired[:110]}")
    if not args.no_store:
        print("\n  Stored as ICP_SCORE. Build the cohort: harvey accounts cohort "
              f"--min-score {threshold:g}  (or Dashboard → Signals, range ICP_SCORE ≥ {threshold:g})\n")


async def _cohort(args):
    from harvey.collectors.spain.accounts import tracked_accounts
    config = _config_or_none()
    threshold = args.min_score if args.min_score is not None else _scoring_config(config).threshold
    state = await _state()
    accounts = await tracked_accounts(state, segment=args.segment, batch=args.batch)
    rows = []
    for a in accounts:
        latest = await state.get_observations(company_id=a["id"], signal_code="ICP_SCORE",
                                              latest_only=True, limit=1)
        if latest and latest[0].get("value_num") is not None and latest[0]["value_num"] >= threshold:
            rows.append({**a, "score": latest[0]["value_num"], "why": latest[0].get("value_text") or ""})
    rows.sort(key=lambda r: -r["score"])
    print(f"\n  Cohort: {len(rows)} account(s) with ICP_SCORE ≥ {threshold:g}"
          + (f" in segment '{args.segment}'" if args.segment else "") + "\n")
    for r in rows:
        print(f"  {r['score']:>6g}  {(r['name'] or '')[:36]:<36} {r['domain']}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["name", "domain", "segment", "batch", "province", "score", "why"])
            for r in rows:
                writer.writerow([r["name"], r["domain"], r.get("segment") or "", r.get("batch") or "",
                                 r.get("province") or "", f"{r['score']:g}", r["why"]])
        print(f"\n  Written to {args.csv}")
    if not rows and not accounts:
        print("  No tracked accounts yet: harvey accounts import <file.csv>")
    print()


def cmd_accounts(args):
    action = {"import": _import, "list": _list, "enrich": _enrich, "score": _score,
              "cohort": _cohort}.get(getattr(args, "accounts_action", None))
    if action is None:
        print(__doc__)
        return
    asyncio.run(action(args))


def register(subparsers) -> None:
    """Add `harvey accounts` and its subcommands to the CLI."""
    sub = subparsers.add_parser(
        "accounts", help="Account-based selling: import hand-picked accounts, enrich, score")
    actions = sub.add_subparsers(dest="accounts_action")

    def filters(p):
        p.add_argument("--segment", default="", help="Only accounts in this segment")
        p.add_argument("--batch", default="", help="Only accounts in this batch (lote)")

    p = actions.add_parser("import", help="Import accounts from a CSV (name, domain, ...)")
    p.add_argument("file", help="CSV with at least name and domain columns")
    p.add_argument("--batch", default="", help="Batch (lote) name (default: the file's name)")
    p.add_argument("--segment", default="", help="Segment for rows that don't give one")
    p.add_argument("--dry-run", action="store_true", help="Check the file without importing")

    p = actions.add_parser("list", help="List tracked accounts")
    filters(p)

    p = actions.add_parser("enrich", help="Collect web, jobs, BORME and press signals")
    filters(p)
    p.add_argument("--only", default="", help="Comma-separated: web, jobs, borme, news")
    p.add_argument("--limit", type=int, default=None, help="Max accounts per collector")
    p.add_argument("--borme-days", type=int, default=None,
                   help="BORME days to read (default: accounts.borme_days, 7)")
    p.add_argument("--all-provinces", action="store_true",
                   help="Read every province's BORME, not just the accounts' provinces")

    p = actions.add_parser("score", help="Score accounts with the scoring rules (ranked table)")
    filters(p)
    p.add_argument("--threshold", type=float, default=None, help="Override scoring.threshold")
    p.add_argument("--no-store", action="store_true", help="Print only; don't store ICP_SCORE")

    p = actions.add_parser("cohort", help="Accounts at or above the score threshold")
    filters(p)
    p.add_argument("--min-score", type=float, default=None, help="Default: scoring.threshold")
    p.add_argument("--csv", default="", help="Also write the cohort to this CSV file")

    sub.set_defaults(func=cmd_accounts)
