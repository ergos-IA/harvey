"""The prospecting pipeline: DISCOVER → PROFILE → (people, verification).

Each stage is independently runnable and independently re-runnable. That is
the point of the design, not an accident of it: profiling can re-run without
re-buying discovery, and discovery can widen without re-profiling everyone.

What chains them is a *query*, not a hand-off. PROFILE asks the database
"which companies have I not looked at, or not looked at lately?" rather than
being handed a list by DISCOVER. So a profile run started for any reason
picks up whatever discovery left behind, a crashed run resumes by itself, and
re-observing on a schedule turns the same signal into a time series.

Segment before you enrich: enrichment cost scales with list size and
conversion does not, so profile the businesses you would actually contact,
not every row you hold.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("harvey.pipeline")

# How long a profile observation stays fresh. Re-reading a site every quarter
# is what makes "they dropped their agency" a visible event.
PROFILE_STALE_DAYS = 90


@dataclass
class PipelineReport:
    """What a full pass did, stage by stage."""

    discover: dict | None = None
    profiled_companies: int = 0
    profile_observations: int = 0
    profile_run_id: str = ""
    skipped: str = ""
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "discover": self.discover,
            "profiled_companies": self.profiled_companies,
            "profile_observations": self.profile_observations,
            "profile_run_id": self.profile_run_id,
            "skipped": self.skipped,
            "errors": self.errors,
        }

    def summary_line(self) -> str:
        parts = []
        if self.discover:
            parts.append(f"{self.discover.get('new_companies', 0)} new companies")
        if self.profiled_companies:
            parts.append(f"{self.profiled_companies} profiled "
                         f"({self.profile_observations} observations)")
        return ", ".join(parts) or "nothing to do"


async def run_profile_stage(
    state,
    limit: int = 100,
    stale_days: int = PROFILE_STALE_DAYS,
    config=None,
) -> tuple[int, int, str]:
    """Profile whatever currently needs it.

    Returns (companies, observations, run_id). Free — three HTTP requests per
    business, no browser, no model call — so it is safe to run on every
    heartbeat without touching the Claude budget. ``config`` says which open
    roles count as hiring intent (``icp.hiring_signals``, else ``icp.titles``).
    """
    from harvey.collectors.profile import profile_companies

    pending = await state.companies_needing_profile(limit=limit,
                                                    stale_days=stale_days)
    if not pending:
        return 0, 0, ""

    logger.info("profile: %d companies need a look", len(pending))
    observations, run_id = await profile_companies(state, pending, config=config)
    return len(pending), observations, run_id


async def run_account_signals_stage(state, config, limit: int = 10) -> dict:
    """Jobs, BORME and press for tracked accounts, on a cadence.

    Account-based selling's equivalent of the profile stage: hand-picked
    accounts (``harvey accounts import``) get their Spain signals refreshed
    every ``accounts.enrich_every_days``, a few accounts per heartbeat so a
    cycle never runs long. Only confirmed signals are collected; with none
    confirmed, or no tracked accounts, it does nothing. Website signals need
    nothing here: the profile stage already reads every company's homepage.
    """
    from harvey.accounts_config import AccountsConfig
    from harvey.collectors.spain.enrich import BORME_CODES, JOBS_CODES, NEWS_CODES, enrich_accounts

    cfg = getattr(config, "accounts", None) or AccountsConfig()
    if not cfg.heartbeat:
        return {}
    confirmed = await state.confirmed_signal_codes()
    kinds = [kind for kind, codes in (("jobs", JOBS_CODES), ("borme", BORME_CODES),
                                      ("news", NEWS_CODES)) if codes & confirmed]
    if not kinds:
        return {}
    report = await enrich_accounts(state, config, only=kinds, stale_days=cfg.enrich_every_days,
                                   limit=limit)
    if any(report.written.values()):
        logger.info("account signals: " + ", ".join(report.summary_lines()))
        # New readings can move a score: keep ICP_SCORE current.
        from harvey.collectors.spain.accounts import tracked_accounts
        from harvey.products import score_products
        accounts = await tracked_accounts(state)
        scoring = getattr(config, "scoring", None)
        if scoring is not None and scoring.configured():
            from harvey.scoring import score_accounts
            await score_accounts(state, scoring, accounts)
        await score_products(state, accounts)
    return report.written


async def run_products_stage(state) -> int:
    """One sequence per company at a time: when a product's sequence has
    ended there without a reply, open the company's next product. Returns
    how many companies moved on. Free; no model call."""
    from harvey.products import advance_products, refresh_gates
    moved = await advance_products(state)
    await refresh_gates(state)
    return moved


async def run_prospecting(
    state,
    config,
    provider: str | None = None,
    queries=None,
    max_spend: float = 1.0,
    profile: bool = True,
    profile_limit: int = 200,
    dry_run: bool = False,
) -> PipelineReport:
    """Discover businesses, then read what their websites say about them.

    The two stages are deliberately not coupled through a list: profiling
    queries the database for what needs attention, so it also sweeps up
    anything an earlier run left unfinished.
    """
    from harvey.collectors.discover import DEFAULT_PROVIDER, run_discovery

    report = PipelineReport()

    discovery = await run_discovery(
        state, config, provider or DEFAULT_PROVIDER, queries,
        max_spend=max_spend, dry_run=dry_run,
    )
    report.discover = discovery.as_dict()
    report.errors.extend(discovery.errors)

    if dry_run:
        report.skipped = "dry run"
        return report
    if not profile:
        report.skipped = "profiling skipped"
        return report

    # Profile runs even when discovery found nothing new: a previous run may
    # have been interrupted, and observations go stale on a schedule.
    try:
        companies, observations, run_id = await run_profile_stage(
            state, limit=profile_limit, config=config)
        report.profiled_companies = companies
        report.profile_observations = observations
        report.profile_run_id = run_id
    except Exception as e:
        logger.exception("profile stage failed")
        report.errors.append(f"profile: {e}")

    return report
