from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from harvey.agents.scout import Scout

STRATEGIES = (
    "hunter", "known_companies", "linkedin",
    "hiring_boards", "profile_search", "company_discovery",
)


def _scout(linkedin_enabled: bool, linkedin_email: str = "", abm_only: bool = False) -> Scout:
    brain = SimpleNamespace(load_skills_for_agent=lambda name: "")
    state = SimpleNamespace(log_action=AsyncMock())
    config = SimpleNamespace(
        channels=SimpleNamespace(linkedin=SimpleNamespace(enabled=linkedin_enabled)),
        accounts=SimpleNamespace(abm_only=abm_only),
    )
    env = SimpleNamespace(linkedin_email=linkedin_email)
    scout = Scout(brain, state, config, env)
    for name in STRATEGIES:
        setattr(scout, f"_prospect_via_{name}", AsyncMock(return_value=0))
    return scout


@pytest.mark.asyncio
async def test_profile_search_rides_the_linkedin_switch():
    """site:linkedin.com/in searches yield names with no company or email,
    which Harvey can never verify or send to, so they are off by default."""
    scout = _scout(linkedin_enabled=False)
    await scout.run()
    scout._prospect_via_profile_search.assert_not_awaited()
    scout._prospect_via_company_discovery.assert_awaited_once()

    scout = _scout(linkedin_enabled=True, linkedin_email="me@example.com")
    await scout.run()
    scout._prospect_via_profile_search.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_search_needs_a_linkedin_login_like_the_linkedin_strategy():
    """Switched on but with no LinkedIn account, nothing could use the
    profiles, so the search would only spend the cycle's query budget."""
    scout = _scout(linkedin_enabled=True)
    await scout.run()
    scout._prospect_via_profile_search.assert_not_awaited()
    scout._prospect_via_linkedin.assert_not_awaited()


@pytest.mark.asyncio
async def test_abm_only_works_the_accounts_on_file_and_discovers_nothing():
    scout = _scout(linkedin_enabled=True, linkedin_email="me@example.com", abm_only=True)
    await scout.run()
    scout._prospect_via_hunter.assert_awaited_once()
    scout._prospect_via_known_companies.assert_awaited_once()
    for name in ("linkedin", "hiring_boards", "profile_search", "company_discovery"):
        getattr(scout, f"_prospect_via_{name}").assert_not_awaited()
