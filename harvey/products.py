"""Products: several offers, each with its own ICP, scoring and campaigns.

Without products Harvey sells the one thing harvey.yaml describes
(``product:`` + ``icp:``). With them, every campaign sells one product:

    product        name, description, pricing, benefits, objections, offer,
                   knowledge (its own brief for the Writer and Handler)
      icp          segments, size, provinces, the titles to write to
      scoring      its own rules and threshold over the account's signals
      accounts     the companies it targets (product_accounts)

How a product reaches the agents: ``config_for(config, product)`` is a copy
of the config with ``product:`` and ``icp:`` replaced, so the Writer,
Handler and Scout read it exactly as they read harvey.yaml.

One sequence per company at a time. An account in two products gets the
first one (best score) and the second waits: ``advance_products`` marks a
product done for a company once its sequence has ended without a reply and
a cool-down has passed, and only then re-opens that company's contacts for
the next product. A reply from anyone there stops everything, as before.

Products live in the database (the Productos tab edits them), not in a
YAML file: they're the user's own data, like their accounts.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite
from pydantic import BaseModel, field_validator

from harvey.accounts_config import ScoringConfig
from harvey.config import OfferConfig

logger = logging.getLogger("harvey.products")

PRODUCT_STATUSES = ("active", "paused")
ASSIGNMENT_STATUSES = ("pending", "active", "done")
# A sequence that ended without a reply waits this long before the same
# company hears about its next product.
NEXT_PRODUCT_COOLDOWN_DAYS = 21
SEEDED_KEY = "products_seeded"
UNTRAINED = {"", "your company", "your product"}

_LIMITS = {"name": 80, "description": 600, "pricing": 300, "knowledge": 20000}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clean_list(values, limit: int = 40, size: int = 120) -> list[str]:
    out = []
    for v in values or []:
        text = " ".join(str(v or "").split())[:size]
        if text and text.lower() not in (o.lower() for o in out):
            out.append(text)
    return out[:limit]


class ProductICP(BaseModel):
    segments: list[str] = []       # account segments this product is for ("" = any)
    company_size: str = ""
    geography: list[str] = []
    titles: list[str] = []         # who to write to; empty = the configured titles
    hiring_signals: list[str] = []

    @field_validator("segments")
    @classmethod
    def _segments(cls, v):
        return [s.lower() for s in _clean_list(v, 20, 40)]

    @field_validator("geography", "titles", "hiring_signals")
    @classmethod
    def _lists(cls, v):
        return _clean_list(v)

    @field_validator("company_size")
    @classmethod
    def _size(cls, v):
        return " ".join(str(v or "").split())[:80]


class Product(BaseModel):
    id: str = ""
    name: str
    status: str = "active"
    description: str = ""
    pricing: str = ""
    key_benefits: list[str] = []
    objection_responses: dict[str, str] = {}
    offer: OfferConfig = OfferConfig()
    knowledge: str = ""
    icp: ProductICP = ProductICP()
    scoring: ScoringConfig = ScoringConfig()

    @field_validator("name", "description", "pricing", "knowledge")
    @classmethod
    def _text(cls, v, info):
        text = str(v or "").strip()
        if info.field_name != "knowledge":
            text = " ".join(text.split())
        return text[:_LIMITS[info.field_name]]

    @field_validator("name")
    @classmethod
    def _named(cls, v):
        if not v:
            raise ValueError("el producto necesita un nombre")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        v = (v or "active").strip().lower()
        if v not in PRODUCT_STATUSES:
            raise ValueError(f"estado no válido: {v}")
        return v

    @field_validator("key_benefits")
    @classmethod
    def _benefits(cls, v):
        return _clean_list(v, 12, 300)

    @field_validator("objection_responses")
    @classmethod
    def _objections(cls, v):
        out = {}
        for k, r in (v or {}).items():
            k, r = " ".join(str(k or "").split())[:120], " ".join(str(r or "").split())[:600]
            if k and r:
                out[k] = r
        return dict(list(out.items())[:20])

    def data(self) -> dict:
        return self.model_dump(exclude={"id", "name", "status"})

    def brief(self) -> str:
        """The product as the Writer and Handler read it (replaces the
        trained product_knowledge file for this product's campaigns)."""
        lines = [f"# {self.name}", ""]
        if self.description:
            lines += [self.description, ""]
        if self.pricing:
            lines.append(f"Precio: {self.pricing}")
        if self.key_benefits:
            lines += ["", "Beneficios:"] + [f"- {b}" for b in self.key_benefits]
        offer = self.offer
        offer_lines = [f"- {label}: {value}" for label, value in (
            ("Oferta principal", offer.primary), ("Entrada de bajo compromiso", offer.entry),
            ("Objetivo", offer.goal), ("Reunión", offer.meeting_duration),
            ("Quién atiende", offer.meeting_owner)) if value]
        if offer_lines:
            lines += ["", "Oferta:"] + offer_lines
        icp = self.icp
        icp_lines = [f"- {label}: {value}" for label, value in (
            ("Segmentos", ", ".join(icp.segments)), ("Tamaño", icp.company_size),
            ("Zona", ", ".join(icp.geography)), ("Cargos", ", ".join(icp.titles))) if value]
        if icp_lines:
            lines += ["", "Cliente ideal:"] + icp_lines
        if self.objection_responses:
            lines += ["", "Objeciones habituales:"] + [
                f"- {k}: {r}" for k, r in self.objection_responses.items()]
        if self.knowledge:
            lines += ["", self.knowledge]
        return "\n".join(lines).strip()


def _from_row(row: dict) -> Product:
    try:
        data = json.loads(row.get("data_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        return Product(id=row["id"], name=row["name"], status=row.get("status") or "active", **data)
    except Exception as e:     # a hand-edited row must not take the tab down
        logger.warning(f"product {row.get('id')}: unreadable fields ({e}); showing the name only")
        return Product(id=row["id"], name=row["name"] or "?", status="paused")


# ── products ──

async def list_products(state, status: str | None = None) -> list[Product]:
    sql, params = "SELECT * FROM products", ()
    if status:
        sql, params = sql + " WHERE status = ?", (status,)
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql + " ORDER BY created_at, rowid", params) as cursor:
            return [_from_row(dict(r)) for r in await cursor.fetchall()]


async def get_product(state, product_id: str) -> Product | None:
    if not product_id:
        return None
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id = ?", (product_id,)) as cursor:
            row = await cursor.fetchone()
    return _from_row(dict(row)) if row else None


async def save_product(state, product: Product) -> Product:
    now = _utcnow().isoformat()
    data = json.dumps(product.data(), ensure_ascii=False)
    async with state._connect() as db:
        if product.id:
            cursor = await db.execute(
                "UPDATE products SET name = ?, status = ?, data_json = ?, updated_at = ? WHERE id = ?",
                (product.name, product.status, data, now, product.id))
            if cursor.rowcount == 0:
                raise KeyError(product.id)
        else:
            product.id = uuid.uuid4().hex[:12]
            await db.execute(
                "INSERT INTO products (id, name, status, data_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)", (product.id, product.name, product.status, data, now, now))
        await db.commit()
    return product


async def delete_product(state, product_id: str) -> bool:
    """Delete a product that never had a campaign. One that did is paused
    instead (its campaigns and conversations keep pointing at it)."""
    async with state._connect() as db:
        async with db.execute("SELECT COUNT(*) FROM campaigns WHERE product_id = ?",
                              (product_id,)) as cursor:
            if (await cursor.fetchone())[0]:
                return False
        await db.execute("DELETE FROM product_accounts WHERE product_id = ?", (product_id,))
        cursor = await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()
        return cursor.rowcount > 0


# ── which accounts each product targets ──

async def assign_accounts(state, product_id: str, company_ids: list[str], batch: str = "") -> int:
    """Add accounts to a product; returns how many were new to it. An account
    already there keeps its status (a re-import never restarts a campaign)."""
    added = 0
    now = _utcnow().isoformat()
    async with state._connect() as db:
        for cid in dict.fromkeys(c for c in company_ids if c):
            cursor = await db.execute(
                "INSERT OR IGNORE INTO product_accounts (product_id, company_id, batch, added_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)", (product_id, cid, batch[:60], now, now))
            added += cursor.rowcount
            if not cursor.rowcount and batch:
                await db.execute("UPDATE product_accounts SET batch = ? WHERE product_id = ? AND company_id = ?",
                                 (batch[:60], product_id, cid))
        await db.commit()
    return added


async def unassign_account(state, product_id: str, company_id: str) -> bool:
    async with state._connect() as db:
        cursor = await db.execute(
            "DELETE FROM product_accounts WHERE product_id = ? AND company_id = ? AND status = 'pending'",
            (product_id, company_id))
        await db.commit()
        return cursor.rowcount > 0


async def assignments(state, product_id: str = "", company_id: str = "") -> list[dict]:
    where, params = [], []
    if product_id:
        where.append("product_id = ?")
        params.append(product_id)
    if company_id:
        where.append("company_id = ?")
        params.append(company_id)
    sql = "SELECT * FROM product_accounts" + (" WHERE " + " AND ".join(where) if where else "")
    async with state._connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql + " ORDER BY added_at, rowid", params) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def _set_assignment(state, product_id: str, company_id: str, status: str,
                          only_from: tuple[str, ...] = ()) -> bool:
    sql = "UPDATE product_accounts SET status = ?, updated_at = ? WHERE product_id = ? AND company_id = ?"
    params = [status, _utcnow().isoformat(), product_id, company_id]
    if only_from:
        sql += f" AND status IN ({','.join('?' * len(only_from))})"
        params += list(only_from)
    async with state._connect() as db:
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount > 0


async def mark_started(state, product_id: str, company_id: str) -> None:
    """The Writer wrote this product's sequence for this company."""
    if product_id and company_id:
        await _set_assignment(state, product_id, company_id, "active", only_from=("pending",))


# ── scoring ──

async def score_products(state, accounts: list[dict], products: list[Product] | None = None) -> int:
    """Score every assigned account with its product's own rules. Products
    with no rules leave their accounts unscored. Returns rows scored."""
    from harvey.scoring import score_company

    by_id = {a["id"]: a for a in accounts}
    scored = 0
    now = _utcnow().isoformat()
    for product in products if products is not None else await list_products(state):
        if not product.scoring.configured():
            continue
        rows = await assignments(state, product_id=product.id)
        updates = []
        for row in rows:
            account = by_id.get(row["company_id"])
            if account is None:
                continue
            s = await score_company(state, product.scoring, row["company_id"],
                                    account.get("segment") or "")
            updates.append((s.score, s.explanation(), now, product.id, row["company_id"]))
        if updates:
            async with state._connect() as db:
                await db.executemany(
                    "UPDATE product_accounts SET score = ?, why = ?, updated_at = ? "
                    "WHERE product_id = ? AND company_id = ?", updates)
                await db.commit()
            scored += len(updates)
    return scored


# ── what the agents read ──

def config_for(config, product: Product | None):
    """``config`` with this product's offer and ICP in place of harvey.yaml's.
    Titles, places and size the product leaves empty keep the configured ones."""
    if product is None:
        return config
    from harvey.config import ProductConfig

    cfg = config.model_copy(deep=True)
    cfg.product = ProductConfig(
        name=product.name, description=product.description, pricing=product.pricing,
        key_benefits=list(product.key_benefits), objection_responses=dict(product.objection_responses),
        offer=product.offer.model_copy(),
    )
    icp = product.icp
    if icp.titles:
        cfg.icp.titles = list(icp.titles)
    if icp.geography:
        cfg.icp.geography = list(icp.geography)
    if icp.company_size:
        cfg.icp.company_size = icp.company_size
    if icp.hiring_signals:
        cfg.icp.hiring_signals = list(icp.hiring_signals)
    if getattr(config, "_source_path", None):
        cfg._source_path = config._source_path
    return cfg


def knowledge_for(product: Product | None) -> str | None:
    """The product_knowledge skill for this product's campaigns, or None to
    keep the trained file (a product with no knowledge of its own, such as
    the one seeded from harvey.yaml)."""
    if product is None or not product.knowledge:
        return None
    return product.brief()


async def choose_product(state, company_id: str,
                         cache: dict | None = None) -> tuple[Product | None, bool]:
    """Which product the next email to this company sells: (product, skip).

    (None, False): the company is in no product, so the configured one.
    (product, False): the one already running there, else the best-scored
    pending one of an active product.
    (None, True): wait. Its products are all done or paused.
    """
    if cache is not None and company_id in cache:
        return cache[company_id]
    result: tuple[Product | None, bool] = (None, False)
    try:
        rows = await assignments(state, company_id=company_id) if company_id else []
        products = {p.id: p for p in await list_products(state)} if rows else {}
    except Exception as e:   # no products table (an old database), or a stand-in state
        logger.debug(f"choose_product: {e}")
        rows = []
    if rows:
        running = [r for r in rows if r["status"] == "active" and r["product_id"] in products]
        pending = [r for r in rows if r["status"] == "pending"
                   and products.get(r["product_id"]) and products[r["product_id"]].status == "active"]
        pending.sort(key=lambda r: -(r["score"] if r["score"] is not None else -1))
        if running:
            result = (products[running[0]["product_id"]], False)
        elif pending:
            result = (products[pending[0]["product_id"]], False)
        else:
            result = (None, True)
    if cache is not None:
        cache[company_id] = result
    return result


async def product_of_campaign(state, campaign_id: str) -> Product | None:
    if not campaign_id:
        return None
    async with state._connect() as db:
        async with db.execute("SELECT product_id FROM campaigns WHERE id = ?", (campaign_id,)) as cursor:
            row = await cursor.fetchone()
    return await get_product(state, row[0]) if row and row[0] else None


async def titles_for_company(state, company_id: str) -> list[str]:
    """Every title the company's products write to (empty: the configured ones)."""
    titles: list[str] = []
    rows = await assignments(state, company_id=company_id) if company_id else []
    for row in rows:
        if row["status"] == "done":
            continue
        product = await get_product(state, row["product_id"])
        if product and product.status == "active":
            titles += [t for t in product.icp.titles if t.lower() not in (x.lower() for x in titles)]
    return titles


# ── one sequence at a time ──

_WAITING = ("pending_review", "approved", "sending")
_STOPPED = ("replied", "opted_out", "lost", "meeting", "closed")


async def advance_products(state, cooldown_days: int = NEXT_PRODUCT_COOLDOWN_DAYS,
                           now: datetime | None = None) -> int:
    """Close each running product whose sequence has ended, and open the
    company's next one. Returns how many companies moved to a next product.

    Ended: no email of it waiting (review, approved, sending) and the last
    one sent (or dropped) at least ``cooldown_days`` ago. If anyone at the
    company replied or opted out, it ends there and nothing more is opened.
    """
    now = now or _utcnow()
    cutoff = (now - timedelta(days=cooldown_days)).isoformat()
    moved = 0
    for row in [r for r in await assignments(state) if r["status"] == "active"]:
        pid, cid = row["product_id"], row["company_id"]
        async with state._connect() as db:
            async with db.execute(
                "SELECT o.status, COALESCE(o.sent_at, ''), COALESCE(o.updated_at, '') FROM outbox o "
                "JOIN campaigns c ON c.id = o.campaign_id JOIN prospects p ON p.id = o.prospect_id "
                "WHERE c.product_id = ? AND p.company_id = ? AND o.kind = 'sequence'", (pid, cid),
            ) as cursor:
                items = await cursor.fetchall()
            async with db.execute(
                f"SELECT COUNT(*) FROM prospects WHERE company_id = ? AND status IN "
                f"({','.join('?' * len(_STOPPED))})", (cid, *_STOPPED),
            ) as cursor:
                stopped = (await cursor.fetchone())[0]
        if not items:
            continue          # written but not queued yet (or the legacy Instantly path)
        if any(status in _WAITING for status, _, _ in items):
            continue
        last = max(max(sent, updated) for _, sent, updated in items)
        if stopped:
            await _set_assignment(state, pid, cid, "done", only_from=("active",))
            continue
        if last > cutoff:
            continue
        await _set_assignment(state, pid, cid, "done", only_from=("active",))
        nxt, skip = await choose_product(state, cid)
        if nxt is None or skip:
            continue
        # The company's contacts get a fresh first email, about the next product.
        async with state._connect() as db:
            cursor = await db.execute(
                "UPDATE prospects SET status = 'new', updated_at = ? "
                "WHERE company_id = ? AND status = 'contacted'", (now.isoformat(), cid))
            await db.commit()
        if cursor.rowcount:
            moved += 1
            logger.info(f"products: company {cid} moves on to '{nxt.name}'")
    return moved


# ── the product harvey.yaml describes ──

async def ensure_default_product(state, config) -> Product | None:
    """Once: turn the configured product into the first product, with every
    tracked account assigned to it, so nothing changes for an existing
    install. Never again after that, even if the user deletes it."""
    if config is None or await state.get_setting(SEEDED_KEY):
        return None
    if await list_products(state):
        await state.set_setting(SEEDED_KEY, "1")
        return None
    prod, icp = config.product, config.icp
    if prod.name.strip().lower() in UNTRAINED or config.persona.company.strip().lower() in UNTRAINED:
        return None
    scoring = getattr(config, "scoring", None) or ScoringConfig()
    product = await save_product(state, Product(
        name=prod.name, description=prod.description, pricing=prod.pricing,
        key_benefits=prod.key_benefits, objection_responses=prod.objection_responses,
        offer=prod.offer, icp=ProductICP(
            segments=list(scoring.segments), company_size=icp.company_size,
            geography=icp.geography, titles=icp.titles, hiring_signals=icp.hiring_signals),
        scoring=scoring,
    ))
    from harvey.collectors.spain.accounts import tracked_accounts
    accounts = await tracked_accounts(state)
    for account in accounts:
        await assign_accounts(state, product.id, [account["id"]], account.get("batch") or "")
    await state.set_setting(SEEDED_KEY, "1")
    if accounts:
        await score_products(state, accounts, [product])
    logger.info(f"products: '{product.name}' created from the config, {len(accounts)} account(s)")
    return product
