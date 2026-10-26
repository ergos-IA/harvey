"""What a Spanish company's homepage says, read from HTML PROFILE already holds.

Zero extra requests: every detector here takes the homepage HTML the profile
stage fetched anyway. Patterns follow tech_detect's rule: distinctive script
hosts, generator tags and explicit wording, never generic words, so a false
positive stays rare. A wrong "uses Zendesk" in an email costs more than
saying nothing.
"""

import re
from html import unescape
from urllib.parse import urljoin, urlparse

from harvey.collectors.spain.text import clean_snippet, fold

# ── Helpdesk / chat ──
HELPDESK_FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "Zendesk": (r"static\.zdassets\.com", r"zendesk\.com/embeddable", r"ekr\.zdassets\.com",
                r"[\w-]+\.zendesk\.com"),
    "Freshdesk": (r"widget\.freshworks\.com", r"[\w-]+\.freshdesk\.com", r"freshdesk\.com/widget"),
    "Freshchat": (r"wchat\.freshchat\.com", r"[\w-]+\.freshchat\.com"),
    "Gorgias": (r"config\.gorgias\.chat", r"gorgias\.chat/", r"gorgias-chat"),
    "Intercom": (r"widget\.intercom\.io", r"js\.intercomcdn\.com"),
    "Zoho Desk": (r"desk\.zoho\.(?:com|eu|in)", r"zohodeskasap", r"asap-widget"),
    "Zoho SalesIQ": (r"salesiq\.zoho\.(?:com|eu|in)", r"\$zoho\.salesiq"),
    "HubSpot chat": (r"js\.usemessages\.com", r"hubspot-messages-iframe"),
    "Tidio": (r"code\.tidio\.co",),
    "Crisp": (r"client\.crisp\.chat",),
    "LiveChat": (r"cdn\.livechatinc\.com",),
    "Drift": (r"js\.driftt\.com",),
}

# ── E-commerce platforms ──
ECOMMERCE_FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "Shopify": (r"cdn\.shopify\.com", r"myshopify\.com"),
    "PrestaShop": (r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']PrestaShop',
                   r"var\s+prestashop\s*=", r"/modules/ps_[a-z]+/", r"prestashop\.com/"),
    "WooCommerce": (r"woocommerce", r"wc-ajax="),
    "Magento / Adobe Commerce": (r"Magento_[A-Z][a-zA-Z]+", r"mage/cookies", r"/static/version\d+/frontend/",
                                 r'data-mage-init', r"text/x-magento-init"),
    "Salesforce Commerce Cloud": (r"demandware\.static", r"/on/demandware\.store/", r"demandware\.net",
                                  r"dwanalytics"),
    "VTEX": (r"vteximg\.com\.br", r"vtexassets\.com", r"vtexcommercestable", r"vtex\.render"),
    "BigCommerce": (r"cdn\d*\.bigcommerce\.com",),
}

# ── ERP mentions (visible text, plus the rare generator tag) ──
ERP_PATTERNS: dict[str, tuple[str, ...]] = {
    # Case-sensitive where the word is also an ordinary one.
    "SAP": (r"(?-i:\bSAP\b)", r"\bS/4\s?HANA\b"),
    "Microsoft Dynamics": (r"\bDynamics\s?365\b", r"\bBusiness Central\b", r"\bDynamics (?:NAV|AX|GP)\b",
                           r"\bNavision\b"),
    "Oracle NetSuite": (r"\bNetSuite\b",),
    "JD Edwards": (r"\bJD\s?Edwards\b",),
    "Sage": (r"\bSage\s?(?:X3|200|100cloud|50|Despachos)\b",),
    "Odoo": (r"\bOdoo\b", r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']Odoo'),
    "Infor": (r"\bInfor\s?(?:LN|M3|CloudSuite|XA|SyteLine)\b",),
    "Epicor": (r"\bEpicor\b",),
    "a3ERP": (r"\ba3ERP\b", r"\ba3innuva\b"),
    "Ekon": (r"(?-i:\bEkon\b)",),
    "Holded": (r"(?-i:\bHolded\b)",),
}

# ── B2B portal / customer area ──
_B2B_PHRASES = (
    r"portal b2b", r"tienda b2b", r"\bb2b\b(?: online)? (?:shop|store|portal)",
    r"area (?:de |para )?(?:clientes|profesionales|distribuidores)",
    r"acceso (?:a )?(?:clientes|profesionales|distribuidores)",
    r"portal (?:de |del |para )?(?:clientes|distribuidor(?:es)?|profesionales)",
    r"zona (?:de |para )?(?:clientes|profesionales|distribuidores)",
    r"login (?:de )?(?:clientes|distribuidores)",
    r"pedidos online para profesionales",
    r"customer portal", r"dealer portal", r"distributor (?:portal|login|area)",
)
_B2B_RE = re.compile(r"(?:" + "|".join(_B2B_PHRASES) + r")")
_B2B_HOST = re.compile(r"^(?:b2b|portal|clientes|distribuidores|pedidos)\.", re.I)

# ── Languages ──
_HREFLANG_RE = re.compile(
    r"""<link\b[^>]*\bhreflang\s*=\s*["']([A-Za-z]{2,3})(?:[-_][A-Za-z0-9]+)?["'][^>]*>""", re.I)
_A_HREFLANG_RE = re.compile(
    r"""<a\b[^>]*\bhreflang\s*=\s*["']([A-Za-z]{2,3})(?:[-_][A-Za-z0-9]+)?["']""", re.I)
_LANG_ATTR_RE = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([A-Za-z]{2,3})""", re.I)
_ANCHOR_RE = re.compile(r"""(?is)<a\b([^>]*)>(.*?)</a>""")
_HREF_RE = re.compile(r"""\bhref\s*=\s*["']([^"'#]+)["']""", re.I)
# Language switcher plugins (WPML, Polylang, Weglot, GTranslate, TranslatePress).
_SWITCHER_RE = re.compile(r"wpml-ls|lang-item|weglot|gtranslate|trp-language|language-switcher|"
                          r"lang-switcher|selector-idioma|idiomas", re.I)
_LANG_NAMES = {
    "espanol": "es", "castellano": "es", "spanish": "es", "es": "es",
    "english": "en", "ingles": "en", "en": "en",
    "francais": "fr", "frances": "fr", "french": "fr", "fr": "fr",
    "deutsch": "de", "aleman": "de", "german": "de", "de": "de",
    "italiano": "it", "italian": "it", "it": "it",
    "portugues": "pt", "portuguese": "pt", "pt": "pt",
    "catala": "ca", "catalan": "ca", "ca": "ca",
    "euskara": "eu", "euskera": "eu", "eu": "eu",
    "galego": "gl", "gallego": "gl", "gl": "gl",
    "nederlands": "nl", "nl": "nl", "polski": "pl", "pl": "pl",
    "chinese": "zh", "zh": "zh", "arabic": "ar", "ar": "ar",
}
# Spain's co-official languages: a Catalan version is not an export signal.
DOMESTIC_LANGS = frozenset({"es", "ca", "eu", "gl", "va", "an", "ast", "oc"})
_PATH_LANG_RE = re.compile(r"^/([a-z]{2})(?:[-_][a-z]{2})?(?:/|$)")

# ── Export claims ──
_EXPORT_RES = (
    re.compile(r"\bexport(?:amos|an|a|acion|aciones|ador(?:a|es)?)\b[^.]{0,80}?\b(\d{1,3})\s+paises\b"),
    re.compile(r"\b(?:presencia|presentes|clientes|distribuidores|vendemos|venta)\b[^.]{0,40}?"
               r"\ben (?:mas de )?(\d{1,3})\s+paises\b"),
    re.compile(r"\b(?:mas de )?(\d{1,3})\s+paises\b[^.]{0,30}?\b(?:exporta|exportamos|presencia|clientes)\b"),
    re.compile(r"\b(?:we )?export(?:s|ing)? to (?:over |more than )?(\d{1,3})\s+countries\b"),
    re.compile(r"\bpresence in (?:over |more than )?(\d{1,3})\s+countries\b"),
)
_EXPORT_WORDS = re.compile(r"\b(?:exportamos|exportacion|exportaciones|departamento de exportacion|"
                           r"comercio exterior|mercados internacionales|presencia internacional|"
                           r"export department)\b")


def _compiled(table: dict[str, tuple[str, ...]]) -> dict[str, list[re.Pattern]]:
    return {name: [re.compile(p, re.I) for p in pats] for name, pats in table.items()}


_HELPDESK = _compiled(HELPDESK_FINGERPRINTS)
_ECOMMERCE = _compiled(ECOMMERCE_FINGERPRINTS)
_ERP = _compiled(ERP_PATTERNS)


def _strip_code(html: str) -> str:
    return re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html or "")


def visible_text(html: str, max_chars: int = 200_000) -> str:
    text = re.sub(r"(?s)<[^>]+>", " ", _strip_code(html)[:max_chars * 2])
    return re.sub(r"\s+", " ", unescape(text)).strip()[:max_chars]


def _match(table: dict[str, list[re.Pattern]], html: str) -> list[str]:
    sample = html[:400_000]
    return sorted(name for name, pats in table.items() if any(p.search(sample) for p in pats))


def detect_helpdesk(html: str) -> list[str]:
    return _match(_HELPDESK, html or "")


def detect_ecommerce(html: str) -> list[str]:
    return _match(_ECOMMERCE, html or "")


def detect_erp(html: str) -> list[str]:
    """ERPs named in the page's visible text (or an Odoo generator tag).
    Script code is ignored: a tracking variable named "sap" is not SAP."""
    if not html:
        return []
    text = visible_text(html)
    found = set(_match(_ERP, text))
    if re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']Odoo', html, re.I):
        found.add("Odoo")
    return sorted(found)


def detect_b2b_portal(html: str, site: str = "", domain: str = "") -> tuple[str, str] | None:
    """(evidence phrase, url) of a link to a customer/distributor portal, or None.
    Only links count, not prose: "nuestros clientes" is not a portal."""
    if not html:
        return None
    for m in _ANCHOR_RE.finditer(_strip_code(html)):
        attrs, inner = m.group(1), m.group(2)
        href_m = _HREF_RE.search(attrs)
        href = href_m.group(1).strip() if href_m else ""
        label = fold(unescape(re.sub(r"(?s)<[^>]+>", " ", inner)))
        title = re.search(r"""\b(?:title|aria-label)\s*=\s*["']([^"']{0,120})["']""", attrs, re.I)
        blob = label + " " + fold(unescape(title.group(1))) if title else label
        url = urljoin(site + "/", href) if (href and site) else href
        host = (urlparse(url).hostname or "").lower().removeprefix("www.") if url else ""
        hit = _B2B_RE.search(blob)
        if hit:
            return clean_snippet(hit.group(0), 80), url
        own = domain and (host == domain or host.endswith("." + domain))
        if own and _B2B_HOST.match(host):
            return clean_snippet(host, 80), url
    return None


def detect_languages(html: str, site: str = "", domain: str = "") -> tuple[list[str], str]:
    """(languages, how) the site is offered in. ``how`` is "hreflang" or
    "selector". Codes are ISO 639-1, lowercased, sorted."""
    if not html:
        return [], ""
    langs = {m.group(1).lower() for m in _HREFLANG_RE.finditer(html)}
    langs.discard("x")   # x-default
    if len(langs) >= 2:
        return sorted(langs), "hreflang"
    # A switcher: anchors with hreflang, or anchors labelled as a language that
    # point at a language path on the site's own domain.
    found = set(langs)
    page = _LANG_ATTR_RE.search(html)
    if page:
        found.add(page.group(1).lower())
    found |= {m.group(1).lower() for m in _A_HREFLANG_RE.finditer(html)}
    has_switcher = bool(_SWITCHER_RE.search(html))
    for m in _ANCHOR_RE.finditer(_strip_code(html)):
        attrs, inner = m.group(1), m.group(2)
        href_m = _HREF_RE.search(attrs)
        if not href_m:
            continue
        label = fold(unescape(re.sub(r"(?s)<[^>]+>", " ", inner))).strip(" |/·-")
        code = _LANG_NAMES.get(label)
        if not code:
            continue
        url = urljoin((site or f"https://{domain}") + "/", href_m.group(1).strip())
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        path_lang = _PATH_LANG_RE.match(parsed.path or "")
        own = not domain or host == domain or host.endswith("." + domain) or (
            host.split(".")[0] == domain.split(".")[0])
        if not own:
            continue
        # A two-letter label ("EN") only counts inside a switcher or when the
        # link goes to that language's path ("/en/"); a full name always does.
        if len(label) == 2 and not (has_switcher or (path_lang and path_lang.group(1) == code)):
            continue
        found.add(code)
    found.discard("x")
    return sorted(found), ("selector" if len(found) > len(langs) else "hreflang")


def multilang(html: str, site: str = "", domain: str = "") -> tuple[list[str], str] | None:
    """(languages, how) when the site has ≥2 languages incl. a foreign one."""
    langs, how = detect_languages(html, site, domain)
    if len(langs) >= 2 and set(langs) - DOMESTIC_LANGS:
        return langs, how
    return None


def exports(html: str) -> tuple[int | None, str] | None:
    """(countries or None, evidence sentence) when the site claims exports."""
    if not html:
        return None
    text = fold(visible_text(html))
    for pattern in _EXPORT_RES:
        m = pattern.search(text)
        if m:
            n = int(m.group(1))
            if 2 <= n <= 250:
                return n, clean_snippet(m.group(0), 160)
    m = _EXPORT_WORDS.search(text)
    if m:
        return None, clean_snippet(text[max(0, m.start() - 60):m.end() + 60], 160)
    return None


def web_observations(html: str, site: str = "", domain: str = "") -> list[tuple[str, dict]]:
    """Every website-derived Spain signal, as (code, add() kwargs).

    Booleans are recorded either way (a site that dropped its English version
    is a real change); text signals only when something was found.
    """
    out: list[tuple[str, dict]] = []
    ml = multilang(html, site, domain)
    out.append(("MULTILANG_SITE", {"num": 1 if ml else 0,
                                   "text": f"{', '.join(ml[0])} ({ml[1]})" if ml else ""}))
    ex = exports(html)
    out.append(("EXPORTS", {"num": 1 if ex else 0,
                            "text": (f"{ex[0]} países · " if ex and ex[0] else "") + (ex[1] if ex else ""),
                            "conf": 0.9 if ex and ex[0] else (0.7 if ex else 1.0)}))
    helpdesk = detect_helpdesk(html)
    if helpdesk:
        out.append(("HELPDESK_TOOL", {"text": ", ".join(helpdesk)}))
    shop = detect_ecommerce(html)
    if shop:
        out.append(("ECOMMERCE_PLATFORM", {"text": ", ".join(shop)}))
    b2b = detect_b2b_portal(html, site, domain)
    out.append(("B2B_PORTAL", {"num": 1 if b2b else 0, "text": b2b[0] if b2b else "",
                               **({"url": b2b[1]} if b2b and b2b[1] else {})}))
    erp = detect_erp(html)
    if erp:
        out.append(("ERP_MENTION", {"text": ", ".join(erp), "conf": 0.7}))
    return out
