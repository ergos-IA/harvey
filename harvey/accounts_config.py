"""Config sections for account-based selling: ``accounts:`` and ``scoring:``.

Both are optional and default to empty, so an existing harvey.yaml loads
unchanged. Kept out of harvey/config.py (which only references them) so the
account work doesn't touch the sending and compliance settings there.

    accounts:
      abm_only: false               # true: only the imported accounts, no web discovery
      borme_days: 7                 # BORME days read per enrichment run
      news_months: 18               # how far back headlines count
      heartbeat: true               # enrich tracked accounts on the heartbeat
      enrich_every_days: 7          # ... at most this often per collector
      watched_functions:            # replaces the built-in list when set
        oficina técnica: ["oficina tecnica"]
        ventas internas: ["ventas internas", "inside sales"]

    scoring:
      threshold: 60
      rules:                        # apply to every account
        - {signal: EMPLOYEE_COUNT, when: {between: [50, 1000]}, points: 10}
      segments:
        industrial:
          rules:
            - {signal: HIRING_FUNCTION, when: {older_than_days: 60}, points: 25}
            - {signal: BORME_APPOINTMENT, when: {within_months: 6}, points: 20}
            - {signal: TECH_STACK, when: {contains_any: [PrestaShop, Magento]}, points: 5}
            - {signal: MULTILANG_SITE, points: 10}       # no `when`: the signal is present
            - {signal: HELPDESK_TOOL, when: {exists: false}, points: 5}
"""

from pydantic import BaseModel, field_validator

# Conditions a rule's ``when`` may use. All given conditions must hold.
CONDITIONS = frozenset({
    "exists",           # true (default) / false: the signal is (not) currently present
    "min", "max",       # value_num bounds, inclusive
    "between",          # [min, max] on value_num, inclusive
    "older_than_days",  # the event (posting, act, headline) is at least N days old
    "within_days",      # ... at most N days old
    "within_months",    # ... at most N months (30 days) old
    "contains_any",     # value_text contains any of these (case and accents ignored)
    "contains_none",    # value_text contains none of these
    "min_confidence",   # the observation's confidence is at least this
})


class ScoringRule(BaseModel):
    signal: str
    when: dict | str | None = None
    points: float = 0
    label: str = ""

    @field_validator("signal")
    @classmethod
    def _code(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise ValueError("una regla de puntuación necesita un código de señal")
        return v

    @field_validator("when")
    @classmethod
    def _when(cls, v):
        if v is None:
            return {}
        if isinstance(v, str):
            word = v.strip().lower()
            if word in ("exists", "present", ""):
                return {}
            if word in ("absent", "missing", "not exists"):
                return {"exists": False}
            raise ValueError(f"condición desconocida {v!r}; usa un mapa como {{older_than_days: 60}}")
        unknown = set(v) - CONDITIONS
        if unknown:
            raise ValueError(f"condiciones desconocidas {sorted(unknown)}; "
                             f"admitidas: {', '.join(sorted(CONDITIONS))}")
        if "between" in v:
            b = v["between"]
            if not (isinstance(b, (list, tuple)) and len(b) == 2):
                raise ValueError("between necesita dos números: [min, max]")
        for key in ("contains_any", "contains_none"):
            if key in v and isinstance(v[key], str):
                v = {**v, key: [v[key]]}
        return v


class SegmentScoring(BaseModel):
    rules: list[ScoringRule] = []


class ScoringConfig(BaseModel):
    threshold: float = 60
    rules: list[ScoringRule] = []
    segments: dict[str, SegmentScoring] = {}

    def configured(self) -> bool:
        return bool(self.rules or any(s.rules for s in self.segments.values()))


class AccountsConfig(BaseModel):
    # Account-based only: the Scout looks for people at the companies already
    # on file (the imported accounts) and never searches the web for new ones.
    abm_only: bool = False
    borme_days: int = 7
    news_months: int = 18
    news_use_domain_brand: bool = False
    heartbeat: bool = True
    enrich_every_days: int = 7
    watched_functions: dict[str, list[str]] = {}
