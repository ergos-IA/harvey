"""LinkedIn outreach, PC side: do the queue's work in the operator's own browser.

    harvey linkedin login                       # once: log in by hand (2FA works)
    harvey linkedin work --server https://...   # one round: find, invite, check, message
    harvey linkedin work --dry-run              # everything but the final click, with screenshots

The data lives on the server (harvey.linkedin_queue); this only drives a
browser and reports back, authenticated with the dashboard token in
HARVEY_REMOTE_TOKEN. It runs on the operator's PC because a LinkedIn login
from a data centre IP gets the account checked.

The browser is a persistent Chromium profile in data/linkedin-profile: the
session survives between runs, no password is stored, and the fingerprint
is the machine's real one. Daily caps (data/linkedin-worker.json) and
office hours (Mon-Fri 09:00-19:00, Europe/Madrid) hold no matter what the
server hands out; actions are spaced out at random.

LinkedIn's markup changes often. Every lookup here tries the Spanish and
English labels and fails closed: if a button isn't where it should be,
nothing is clicked and the item is reported with the reason.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus

from harvey.paths import PROJECT_ROOT

logger = logging.getLogger("harvey.linkedin.worker")

DATA_DIR = PROJECT_ROOT / "data"
PROFILE_DIR = DATA_DIR / "linkedin-profile"
ACTIVITY_FILE = DATA_DIR / "linkedin-worker.json"
SHOTS_DIR = DATA_DIR / "linkedin-shots"

CAPS = {"search": 15, "invite": 10, "view": 40, "message": 10}
OFFICE_HOURS = (9, 19)
TIMEZONE = "Europe/Madrid"


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower()).strip()


# ── daily caps ──

class Activity:
    def __init__(self, path: Path = ACTIVITY_FILE, caps: dict | None = None):
        self.path = path
        self.caps = {**CAPS, **(caps or {})}
        self.counts = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("date") == date.today().isoformat():
                return data
        except (OSError, ValueError):
            pass
        return {"date": date.today().isoformat()}

    def left(self, kind: str) -> int:
        if self.counts.get("date") != date.today().isoformat():
            self.counts = {"date": date.today().isoformat()}
        return max(0, self.caps[kind] - int(self.counts.get(kind, 0)))

    def record(self, kind: str) -> None:
        self.left(kind)
        self.counts[kind] = int(self.counts.get(kind, 0)) + 1
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.counts), encoding="utf-8")
        except OSError as e:
            logger.warning(f"no se pudo guardar el contador diario: {e}")


def in_office_hours(now: datetime | None = None) -> bool:
    if now is None:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(TIMEZONE))
    return now.weekday() < 5 and OFFICE_HOURS[0] <= now.hour < OFFICE_HOURS[1]


# ── the server ──

class Server:
    def __init__(self, base_url: str, token: str):
        import httpx
        self.base = base_url.rstrip("/")
        self.http = httpx.AsyncClient(timeout=30, headers={"Authorization": f"Bearer {token}"})

    async def work(self, **limits) -> dict:
        r = await self.http.get(f"{self.base}/api/linkedin/work", params=limits)
        r.raise_for_status()
        return r.json()

    async def report(self, **body) -> None:
        r = await self.http.post(f"{self.base}/api/linkedin/report", json=body)
        r.raise_for_status()

    async def close(self) -> None:
        await self.http.aclose()


# ── picking people from a search ──

def pick_people(cards: list[dict], company: str, titles: list[str], limit: int = 2) -> list[dict]:
    """The search results that work at ``company`` (named in their headline),
    best title match first. People whose headline doesn't name the company
    are dropped: a wrong person is worse than nobody."""
    key = [w for w in fold(company).replace(",", " ").split()
           if len(w) > 2 and w not in {"sl", "sa", "slu", "sociedad", "limitada", "anonima", "grupo"}]
    if not key:
        return []
    wanted = [fold(t) for t in titles if t]
    scored = []
    for card in cards:
        head = fold(card.get("headline") or "")
        if not all(w in head for w in key[:2]):
            continue
        rank = next((i for i, t in enumerate(wanted) if t and t in head), len(wanted))
        scored.append((rank, card))
    scored.sort(key=lambda s: s[0])
    out, seen = [], set()
    for _, card in scored:
        url = card.get("profile_url") or ""
        if url and url not in seen:
            seen.add(url)
            out.append({"profile_url": url, "full_name": card.get("name") or "",
                        "title": card.get("headline") or ""})
    return out[:limit]


# ── the browser ──

CONNECT = re.compile(r"^(conectar|connect)$", re.I)
CONNECT_LABEL = re.compile(r"(invita a .* a conectar|invite .* to connect)", re.I)
PENDING = re.compile(r"^(pendiente|pending)$", re.I)
MESSAGE = re.compile(r"^(enviar mensaje|mensaje|message)$", re.I)
MORE = re.compile(r"^(más|mas|more)$", re.I)
ADD_NOTE = re.compile(r"(añadir una nota|anadir una nota|add a note)", re.I)
SEND = re.compile(r"^(enviar|send|enviar invitación|send invitation|send now)$", re.I)
SEND_WITHOUT = re.compile(r"(enviar sin nota|send without a note)", re.I)
FIRST_DEGREE = re.compile(r"(·\s*)?\b(1er|1st|1\.º)\b", re.I)


class Browser:
    """One persistent Chromium profile, driven gently."""

    def __init__(self, headless: bool = False, profile_dir: Path = PROFILE_DIR):
        self.headless = headless
        self.profile_dir = profile_dir
        self._pw = None
        self.context = None
        self.page = None

    async def start(self):
        from playwright.async_api import async_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            str(self.profile_dir), headless=self.headless, locale="es-ES",
            viewport={"width": 1280, "height": 860}, timezone_id=TIMEZONE)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def stop(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            if self._pw:
                await self._pw.stop()
            self._pw = self.context = self.page = None

    async def pause(self, lo: float = 2, hi: float = 5):
        await asyncio.sleep(random.uniform(lo, hi))

    async def goto(self, url: str):
        await self.page.goto(url, timeout=45000)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await self.pause(2, 4)
        for _ in range(random.randint(1, 3)):
            await self.page.mouse.wheel(0, random.randint(200, 500))
            await asyncio.sleep(random.uniform(0.4, 1.2))
        await self.page.mouse.wheel(0, -2000)

    async def logged_in(self) -> bool:
        await self.goto("https://www.linkedin.com/feed/")
        url = self.page.url
        return "/feed" in url and "login" not in url and "checkpoint" not in url

    async def wait_for_login(self, minutes: int = 10) -> bool:
        await self.page.goto("https://www.linkedin.com/login", timeout=45000)
        for _ in range(minutes * 30):
            if "/feed" in self.page.url:
                return True
            await asyncio.sleep(2)
        return False

    async def shot(self, name: str) -> str:
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{name}.png"
        await self.page.screenshot(path=str(path))
        return str(path)

    # -- search --

    async def search(self, company: str, titles: list[str]) -> list[dict]:
        query = company if not titles else f"{company} {titles[0]}"
        await self.goto(f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}")
        cards = await self.page.evaluate("""() => {
            const out = []; const seen = new Set();
            for (const a of document.querySelectorAll('main a[href*="/in/"]')) {
                const url = a.href.split('?')[0];
                if (seen.has(url)) continue;
                const card = a.closest('li') || a.closest('div[data-chameleon-result-urn]') || a.parentElement;
                const lines = (card ? card.innerText : a.innerText).split('\\n').map(s => s.trim()).filter(Boolean);
                const name = (a.innerText || '').split('\\n')[0].trim();
                if (!name || name.length > 80) continue;
                seen.add(url);
                const head = lines.find(l => l !== name && !/^(•|·)?\\s*(1er|2º|3er|1st|2nd|3rd)/i.test(l)
                                         && !/^(conectar|connect|seguir|follow|mensaje|message)$/i.test(l)
                                         && l.length > 3) || '';
                out.push({profile_url: url, name, headline: head});
            }
            return out;
        }""")
        return cards if isinstance(cards, list) else []

    # -- profile actions --

    async def _top(self):
        """The profile's top card (name, headline, action buttons)."""
        for sel in ("main section.artdeco-card", "main section", "main"):
            el = await self.page.query_selector(sel)
            if el:
                return el
        return None

    async def _button(self, scope, pattern: re.Pattern, label: re.Pattern | None = None):
        for b in await scope.query_selector_all("button, a[role='button'], div[role='button']"):
            try:
                if not await b.is_visible():
                    continue
                text = " ".join((await b.inner_text() or "").split())
                aria = await b.get_attribute("aria-label") or ""
            except Exception:
                continue
            if pattern.search(text) or (label and label.search(aria)):
                return b
        return None

    async def profile_state(self, url: str) -> str:
        """"connected", "pending", "connectable", "follow_only" or "unknown"."""
        await self.goto(url)
        top = await self._top()
        if top is None:
            return "unknown"
        if await self._button(top, PENDING):
            return "pending"
        if await self._button(top, CONNECT, CONNECT_LABEL):
            return "connectable"
        text = await top.inner_text()
        if FIRST_DEGREE.search(text) and await self._button(top, MESSAGE):
            return "connected"
        more = await self._button(top, MORE)
        if more:
            await more.click()
            await self.pause(1, 2)
            item = await self._button(self.page, CONNECT, CONNECT_LABEL)
            await self.page.keyboard.press("Escape")
            if item:
                return "connectable"
        return "follow_only"

    async def invite(self, url: str, note: str, dry_run: bool) -> tuple[bool, str]:
        state = await self.profile_state(url)
        if state == "pending":
            return True, "ya estaba pendiente"
        if state == "connected":
            return True, "ya era contacto"
        if state != "connectable":
            return False, f"no se puede conectar ({state})"
        top = await self._top()
        button = await self._button(top, CONNECT, CONNECT_LABEL)
        if button is None:
            more = await self._button(top, MORE)
            await more.click()
            await self.pause(1, 2)
            button = await self._button(self.page, CONNECT, CONNECT_LABEL)
        await button.click()
        await self.pause(1.5, 3)
        dialog = await self.page.query_selector("div[role='dialog']") or self.page
        add_note = await self._button(dialog, ADD_NOTE, ADD_NOTE)
        noted = False
        if add_note and note:
            await add_note.click()
            await self.pause(1, 2)
            box = await self.page.query_selector("div[role='dialog'] textarea")
            if box:
                await box.click()
                await box.type(note, delay=random.randint(25, 70))
                noted = True
            else:                      # the note allowance is used up: an upsell instead
                await self.page.keyboard.press("Escape")
                await self.pause(1, 2)
                return False, "LinkedIn no deja añadir nota (límite mensual); revisa a mano"
        await self.pause(1, 2)
        dialog = await self.page.query_selector("div[role='dialog']") or self.page
        send = await self._button(dialog, SEND, SEND) if noted else (
            await self._button(dialog, SEND_WITHOUT, SEND_WITHOUT) or await self._button(dialog, SEND, SEND))
        if send is None:
            await self.page.keyboard.press("Escape")
            return False, "no encuentro el botón de enviar"
        if dry_run:
            path = await self.shot("invite")
            await self.page.keyboard.press("Escape")
            return True, f"simulado, captura en {path}"
        await send.click()
        await self.pause(2, 4)
        return True, "" if noted else "enviada sin nota"

    async def send_message(self, url: str, text: str, dry_run: bool) -> tuple[bool, str]:
        state = await self.profile_state(url)
        if state != "connected":
            return False, f"todavía no es contacto ({state})"
        top = await self._top()
        button = await self._button(top, MESSAGE)
        await button.click()
        await self.pause(2, 3)
        box = await self.page.query_selector("div.msg-form__contenteditable[contenteditable='true']") or \
            await self.page.query_selector("div[role='textbox'][contenteditable='true']")
        if box is None:
            return False, "no se abre la ventana de mensaje"
        await box.click()
        for i, para in enumerate(p for p in text.split("\n") if p.strip()):
            if i:
                await self.page.keyboard.press("Shift+Enter")
                await self.page.keyboard.press("Shift+Enter")
            await self.page.keyboard.type(para.strip(), delay=random.randint(20, 60))
        await self.pause(1, 2)
        send = await self.page.query_selector("button.msg-form__send-button") or \
            await self._button(self.page, SEND, SEND)
        if send is None:
            return False, "no encuentro el botón de enviar"
        if dry_run:
            path = await self.shot("message")
            await self.page.keyboard.press("Escape")
            return True, f"simulado, captura en {path}"
        await send.click()
        await self.pause(2, 4)
        await self.page.keyboard.press("Escape")
        return True, ""


# ── one round ──

async def run_once(server, browser, activity: Activity, dry_run: bool = False,
                   gap: tuple[float, float] = (40, 110), log=print) -> dict:
    """Pull the work and do as much as today's caps allow. In a dry run
    nothing is reported back, so the server's queue doesn't move."""
    done = {"find": 0, "invite": 0, "check": 0, "message": 0, "errors": 0}
    batch = await server.work(find=activity.left("search"), invite=activity.left("invite"),
                              check=activity.left("view"), message=activity.left("message"))

    async def report(**body):
        if not dry_run:
            await server.report(**body)

    async def spaced():
        await asyncio.sleep(random.uniform(*gap))

    for job in batch.get("find") or []:
        if activity.left("search") <= 0:
            break
        try:
            cards = await browser.search(job["company_name"], job.get("titles") or [])
            activity.record("search")
            people = pick_people(cards, job["company_name"], job.get("titles") or [])
            log(f"  buscar {job['company_name']}: {len(people)} persona(s)")
            await report(kind="find", id=job["id"], ok=True, people=people)
            done["find"] += 1
        except Exception as e:
            done["errors"] += 1
            log(f"  buscar {job.get('company_name')}: error {e}")
            await report(kind="find", id=job["id"], ok=False, error=str(e))
        await spaced()

    for item in batch.get("invite") or []:
        if activity.left("invite") <= 0 or activity.left("view") <= 0:
            break
        try:
            ok, why = await browser.invite(item["profile_url"], item.get("note") or "", dry_run)
            activity.record("view")
            if ok and not dry_run:
                activity.record("invite")
            log(f"  invitar {item.get('full_name')}: {'ok' if ok else 'no'} {why}".rstrip())
            await report(kind="invite", id=item["id"], ok=ok, error=why)
            done["invite"] += ok
        except Exception as e:
            done["errors"] += 1
            log(f"  invitar {item.get('full_name')}: error {e}")
            await report(kind="invite", id=item["id"], ok=False, error=str(e))
        await spaced()

    for item in batch.get("check") or []:
        if activity.left("view") <= 0:
            break
        try:
            state = await browser.profile_state(item["profile_url"])
            activity.record("view")
            await report(kind="check", id=item["id"], connected=state == "connected",
                         error="" if state in ("connected", "pending") else state)
            done["check"] += 1
            if state == "connected":
                log(f"  {item.get('full_name')} ha aceptado")
        except Exception as e:
            done["errors"] += 1
            log(f"  comprobar {item.get('full_name')}: error {e}")
        await spaced()

    for item in batch.get("message") or []:
        if activity.left("message") <= 0 or activity.left("view") <= 0:
            break
        try:
            ok, why = await browser.send_message(item["profile_url"], item.get("message") or "", dry_run)
            activity.record("view")
            if ok and not dry_run:
                activity.record("message")
            log(f"  mensaje a {item.get('full_name')}: {'ok' if ok else 'no'} {why}".rstrip())
            await report(kind="message", id=item["id"], ok=ok, error=why)
            done["message"] += ok
        except Exception as e:
            done["errors"] += 1
            log(f"  mensaje a {item.get('full_name')}: error {e}")
            await report(kind="message", id=item["id"], ok=False, error=str(e))
        await spaced()
    return done


def server_settings(server: str = "") -> tuple[str, str]:
    url = (server or os.environ.get("HARVEY_REMOTE_URL", "")).strip()
    token = os.environ.get("HARVEY_REMOTE_TOKEN", "").strip()
    if not url:
        raise SystemExit("Falta el servidor: --server https://... o HARVEY_REMOTE_URL en .env")
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
        raise SystemExit("El servidor tiene que ir por https://")
    if not token:
        raise SystemExit("Falta HARVEY_REMOTE_TOKEN en .env (el token del panel de producción)")
    return url, token
