"""Website-derived Spain signals, from homepage HTML PROFILE already holds.

Markup is hand-written with fictional companies; it reconstructs the shapes
these tools and plugins leave in a page, not any real site.
"""

import pytest

from harvey.collectors.profile import ProfileCollector
from harvey.collectors.spain.web import (
    detect_b2b_portal, detect_ecommerce, detect_erp, detect_helpdesk, detect_languages, exports,
    multilang, web_observations,
)
from harvey.integrations.tech_detect import detect_tech

HREFLANG = """<html lang="es"><head>
<link rel="alternate" hreflang="es-ES" href="https://ejemplo.example/" />
<link rel="alternate" hreflang="en" href="https://ejemplo.example/en/" />
<link rel="alternate" hreflang="fr-FR" href="https://ejemplo.example/fr/" />
<link rel="alternate" hreflang="x-default" href="https://ejemplo.example/" />
</head><body>Hola</body></html>"""

CATALAN_ONLY = """<html lang="es"><head>
<link rel="alternate" hreflang="es" href="https://ejemplo.example/" />
<link rel="alternate" hreflang="ca" href="https://ejemplo.example/ca/" />
</head><body></body></html>"""

SWITCHER = """<html lang="es"><body><ul class="wpml-ls">
<li><a href="/">ES</a></li><li><a href="/en/">EN</a></li><li><a href="/de/">DE</a></li></ul>
<a href="https://otra-empresa.example/en/">English</a></body></html>"""


def test_hreflang_languages():
    assert detect_languages(HREFLANG) == (["en", "es", "fr"], "hreflang")
    assert multilang(HREFLANG) == (["en", "es", "fr"], "hreflang")


def test_co_official_languages_are_not_an_export_signal():
    assert detect_languages(CATALAN_ONLY)[0] == ["ca", "es"]
    assert multilang(CATALAN_ONLY) is None


def test_language_switcher_on_their_own_site():
    langs, how = detect_languages(SWITCHER, "https://ejemplo.example", "ejemplo.example")
    assert langs == ["de", "en", "es"] and how == "selector"
    # Bare "EN" links outside a switcher, to another site, don't count.
    plain = '<html lang="es"><body><a href="https://otra.example/en/">EN</a></body></html>'
    assert multilang(plain, "https://ejemplo.example", "ejemplo.example") is None


def test_export_claims():
    page = "<p>Fabricamos en Teruel y exportamos a más de 40 países de todo el mundo.</p>"
    assert exports(page)[0] == 40
    page = "<p>Contamos con presencia en 25 países y una red de distribuidores.</p>"
    assert exports(page)[0] == 25
    page = "<h2>Departamento de exportación</h2><p>Contacte con nosotros.</p>"
    n, evidence = exports(page)
    assert n is None and "exportacion" in evidence.lower()
    assert exports("<p>Somos una empresa familiar de Soria.</p>") is None


@pytest.mark.parametrize("html,expected", [
    ('<script src="https://static.zdassets.com/ekr/snippet.js?key=x"></script>', ["Zendesk"]),
    ('<script src="//widget.freshworks.com/widgets/123.js"></script>', ["Freshdesk"]),
    ('<script src="https://config.gorgias.chat/bundle-loader/abc"></script>', ["Gorgias"]),
    ('<script src="https://widget.intercom.io/widget/abc"></script>', ["Intercom"]),
    ('<script src="https://desk.zoho.eu/portal/api/web/inapp/123"></script>', ["Zoho Desk"]),
    ('<script src="//js.usemessages.com/conversations-embed.js"></script>', ["HubSpot chat"]),
    ("<html><body>Atención al cliente: llámenos</body></html>", []),
])
def test_helpdesk_fingerprints(html, expected):
    assert detect_helpdesk(html) == expected


@pytest.mark.parametrize("html,expected", [
    ('<meta name="generator" content="PrestaShop" />', ["PrestaShop"]),
    ("<script>var prestashop = {};</script>", ["PrestaShop"]),
    ('<link href="/wp-content/plugins/woocommerce/style.css">', ["WooCommerce"]),
    ('<script type="text/x-magento-init">{}</script>', ["Magento / Adobe Commerce"]),
    ('<img src="/on/demandware.static/-/Sites/x.png">', ["Salesforce Commerce Cloud"]),
    ('<script src="https://ejemplo.vtexassets.com/_v/public/x.js"></script>', ["VTEX"]),
    ('<script src="https://cdn.shopify.com/s/x.js"></script>', ["Shopify"]),
])
def test_ecommerce_fingerprints(html, expected):
    assert detect_ecommerce(html) == expected


def test_tech_stack_detection_includes_the_new_fingerprints():
    html = '<meta name="generator" content="PrestaShop" /><script src="//wchat.freshchat.com/js/x.js"></script>'
    assert {"PrestaShop", "Freshchat"} <= set(detect_tech(html))
    assert {"PrestaShop", "Freshchat"} <= set(ProfileCollector(None).detect_tech(html))


def test_b2b_portal_links_not_prose():
    html = '<nav><a href="/area-clientes">Área de clientes</a></nav>'
    assert detect_b2b_portal(html, "https://ejemplo.example", "ejemplo.example") == (
        "area de clientes", "https://ejemplo.example/area-clientes")
    html = '<a href="https://b2b.ejemplo.example/login">Entrar</a>'
    assert detect_b2b_portal(html, "https://ejemplo.example", "ejemplo.example")[0] == "b2b.ejemplo.example"
    assert detect_b2b_portal("<p>Más de 500 clientes y distribuidores confían en nosotros.</p>",
                             "https://ejemplo.example", "ejemplo.example") is None


def test_erp_mentions_in_visible_text_only():
    assert detect_erp("<p>Integración con SAP y Microsoft Dynamics 365 Business Central.</p>") == [
        "Microsoft Dynamics", "SAP"]
    assert detect_erp("<p>Trabajamos con Navision y Sage 200.</p>") == ["Microsoft Dynamics", "Sage"]
    # Code isn't text; "sap" lowercase and "sage" alone aren't the ERPs.
    assert detect_erp("<script>var SAP = 1;</script><p>sap de la madera, a sage choice</p>") == []


def test_web_observations_shape():
    html = HREFLANG.replace("<body>Hola", '<body><a href="/acceso-distribuidores">Acceso distribuidores</a>'
                            '<script src="https://static.zdassets.com/ekr/snippet.js"></script>Hola')
    got = dict(web_observations(html, "https://ejemplo.example", "ejemplo.example"))
    assert got["MULTILANG_SITE"]["num"] == 1 and got["MULTILANG_SITE"]["text"] == "en, es, fr (hreflang)"
    assert got["EXPORTS"]["num"] == 0
    assert got["HELPDESK_TOOL"]["text"] == "Zendesk"
    assert got["B2B_PORTAL"]["num"] == 1
    assert "ECOMMERCE_PLATFORM" not in got and "ERP_MENTION" not in got


@pytest.mark.asyncio
async def test_profile_records_confirmed_web_signals_without_extra_requests():
    home = HREFLANG.replace("<body>Hola", "<body>" + "x" * 600 +
                            '<meta name="generator" content="PrestaShop" />Exportamos a 30 países.')
    requested = []

    async def fake_get(url):
        requested.append(url)
        return home if url == "https://ejemplo.example" else ""

    c = ProfileCollector(None, {"MULTILANG_SITE", "EXPORTS", "ECOMMERCE_PLATFORM"})
    c._get = fake_get
    obs = await c.profile_company("c1", "ejemplo.example")
    by_code = {o["signal_code"]: o for o in obs}
    assert set(by_code) == {"MULTILANG_SITE", "EXPORTS", "ECOMMERCE_PLATFORM"}
    assert by_code["EXPORTS"]["value_num"] == 1 and by_code["EXPORTS"]["value_text"].startswith("30 países")
    assert by_code["ECOMMERCE_PLATFORM"]["value_text"] == "PrestaShop"
    assert all(o["collector"] == "profile" for o in obs)
    assert requested == ["https://ejemplo.example"]


@pytest.mark.asyncio
async def test_unconfirmed_web_signals_are_not_collected():
    async def fake_get(url):
        return HREFLANG if url == "https://ejemplo.example" else ""

    c = ProfileCollector(None, set())
    c._get = fake_get
    assert await c.profile_company("c1", "ejemplo.example") == []
