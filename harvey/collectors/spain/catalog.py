"""Signals for account-based selling to Spanish mid-sized companies.

Appended to harvey.signals.SIGNAL_CATALOG. Labels and descriptions are in
Spanish (the operator's language for this market); codes stay English like
the rest of the vocabulary. Categories are the dashboard's existing ones
(discovery / profile), so the Signals tab renders them without changes.

Cost notes start with "gratis" only when collection really costs nothing, and
say what the catch is when there is one.
"""

NEWS_COST = (
    "gratis (RSS de Google News, una petición por cuenta; las condiciones del feed "
    "hablan de uso personal y no comercial: comprueba que encajan con tu uso)")

SPAIN_SIGNALS: list[dict] = [
    # ── Import: hand-picked accounts (data you supplied, never collected) ──
    {
        "code": "ACCOUNT_TRACKED",
        "label": "Cuenta objetivo (importada)",
        "description": (
            "La empresa entró por `harvey accounts import`: es una de las cuentas elegidas a "
            "mano (o exportadas de Clay) para un lote. El valor es el nombre del lote. Es la "
            "base de todo lo demás en este flujo: BORME, prensa, empleo y la puntuación ICP "
            "solo se calculan para cuentas objetivo."
        ),
        "category": "discovery",
        "value_type": "bool",
        "collector": "import",
        "cost_note": "gratis (tu importación CSV)",
        "confidence_floor": 0.0,
    },
    {
        "code": "ACCOUNT_SEGMENT",
        "label": "Segmento de la cuenta",
        "description": (
            "El segmento con el que se importó la cuenta (p. ej. industrial, distribución). "
            "Decide qué reglas de puntuación (scoring.segments) se le aplican."
        ),
        "category": "discovery",
        "value_type": "text",
        "collector": "import",
        "cost_note": "gratis (tu importación CSV)",
        "confidence_floor": 0.0,
    },
    {
        "code": "EMPLOYEE_COUNT",
        "label": "Número de empleados",
        "description": "Plantilla según el fichero importado (columna employees). El ICP es 50–1.000.",
        "category": "discovery",
        "value_type": "num",
        "collector": "import",
        "cost_note": "gratis (tu importación CSV)",
        "confidence_floor": 0.0,
    },
    {
        "code": "REVENUE_EUR",
        "label": "Facturación (EUR)",
        "description": "Facturación anual en euros según el fichero importado (columna revenue_eur).",
        "category": "discovery",
        "value_type": "num",
        "collector": "import",
        "cost_note": "gratis (tu importación CSV)",
        "confidence_floor": 0.0,
    },
    {
        "code": "HQ_PROVINCE",
        "label": "Provincia",
        "description": (
            "Provincia de la cuenta según el fichero importado. El BORME se lee solo para las "
            "provincias de las cuentas objetivo, así que conviene que sea la del Registro "
            "Mercantil donde está inscrita."
        ),
        "category": "discovery",
        "value_type": "text",
        "collector": "import",
        "cost_note": "gratis (tu importación CSV)",
        "confidence_floor": 0.0,
    },
    {
        "code": "COMPANY_CIF",
        "label": "CIF",
        "description": "El CIF de la sociedad según el fichero importado (solo se guarda si tiene forma de CIF).",
        "category": "discovery",
        "value_type": "text",
        "collector": "import",
        "cost_note": "gratis (tu importación CSV)",
        "confidence_floor": 0.0,
    },

    # ── Web: from the homepage PROFILE already fetches (no extra requests) ──
    {
        "code": "MULTILANG_SITE",
        "label": "Web en varios idiomas",
        "description": (
            "La web se ofrece en al menos dos idiomas y uno es extranjero (hreflang o selector "
            "de idioma), sin contar catalán, euskera o gallego. Indica clientes fuera de España: "
            "más pedidos, más consultas y más soporte en otros idiomas. El valor lista los idiomas."
        ),
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "EXPORTS",
        "label": "Exporta / presencia internacional",
        "description": (
            "La propia web dice que exporta o que vende en otros países (\"exportamos a 40 "
            "países\", \"presencia en 25 países\"). El número de países se guarda cuando lo dice."
        ),
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "HELPDESK_TOOL",
        "label": "Herramienta de atención al cliente",
        "description": (
            "Chat o helpdesk instalado en la web: Zendesk, Freshdesk/Freshchat, Gorgias, "
            "Intercom, Zoho Desk/SalesIQ, chat de HubSpot, Tidio, Crisp, LiveChat. Ya tienen un "
            "volumen de consultas que gestionan con software."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "ECOMMERCE_PLATFORM",
        "label": "Plataforma de comercio electrónico",
        "description": (
            "Tienda online detectada en la web: Shopify, PrestaShop, WooCommerce, Magento/Adobe "
            "Commerce, Salesforce Commerce Cloud, VTEX o BigCommerce."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "B2B_PORTAL",
        "label": "Portal B2B / área de clientes",
        "description": (
            "La web enlaza un portal para clientes profesionales o distribuidores (\"área de "
            "clientes\", \"acceso distribuidores\", \"portal B2B\"). Pedidos recurrentes de "
            "empresa: el terreno de la oficina técnica y los administrativos de pedidos."
        ),
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "ERP_MENTION",
        "label": "ERP mencionado",
        "description": (
            "Un ERP nombrado en la web (SAP, Microsoft Dynamics/Navision/Business Central, "
            "Oracle NetSuite/JD Edwards, Sage X3/200, Odoo, Infor, Epicor, a3ERP, Ekon, "
            "Holded). Rara vez aparece en la home; cuando aparece es un dato de integración."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },

    # ── Empleo: open roles in the functions the offer is built for ──
    {
        "code": "HIRING_FUNCTION",
        "label": "Vacante en una función vigilada",
        "description": (
            "Una vacante abierta en las funciones que vigilas (oficina técnica, ingeniero de "
            "ofertas, técnico comercial, ventas internas, atención al cliente / customer care, "
            "administrativo de pedidos), con la fecha de publicación para saber si lleva más "
            "de 60 días abierta. Fuentes: el portal de empleo que su web enlaza (Personio, "
            "Teamtailor, Factorial, JOIN, SmartRecruiters, Workable, Greenhouse, Lever, Ashby) "
            "y la API oficial de InfoJobs."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "jobs",
        "cost_note": ("gratis (feed público del portal de empleo; la API de InfoJobs necesita una cuenta "
                      "gratuita de desarrollador: INFOJOBS_CLIENT_ID / INFOJOBS_CLIENT_SECRET)"),
        "confidence_floor": 0.0,
    },

    # ── BORME: acts registered at the Registro Mercantil ──
    {
        "code": "BORME_APPOINTMENT",
        "label": "BORME: relevo en la administración",
        "description": (
            "Nombramientos o ceses de administradores, consejero delegado, presidente o "
            "director general publicados en el BORME (Sección A). Un relevo en la dirección "
            "es el momento en que se revisan proveedores y prioridades. Se guardan la fecha "
            "y el extracto del acto."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "borme",
        "cost_note": ("gratis (API de datos abiertos del BOE; una petición por provincia y día leído, "
                      "solo de las provincias de tus cuentas)"),
        "confidence_floor": 0.0,
    },
    {
        "code": "BORME_CAPITAL",
        "label": "BORME: ampliación de capital o cambio de socio",
        "description": (
            "Ampliación de capital, cambio de identidad del socio único o declaración de "
            "unipersonalidad publicados en el BORME. Dinero nuevo o dueño nuevo."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "borme",
        "cost_note": "gratis (API de datos abiertos del BOE, las mismas peticiones que arriba)",
        "confidence_floor": 0.0,
    },
    {
        "code": "BORME_MERGER",
        "label": "BORME: fusión, absorción o escisión",
        "description": (
            "Fusión, absorción o escisión inscrita en el BORME. Integrar dos empresas "
            "multiplica el trabajo de procesos, sistemas y atención al cliente."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "borme",
        "cost_note": "gratis (API de datos abiertos del BOE, las mismas peticiones que arriba)",
        "confidence_floor": 0.0,
    },

    # ── Prensa: Spanish press headlines ──
    {
        "code": "NEWS_EXPANSION",
        "label": "Prensa: expansión",
        "description": (
            "Un titular de prensa sobre la cuenta habla de expansión: nueva planta, "
            "ampliación, nueva línea, aperturas, nuevas tiendas, nueva delegación. Se guardan "
            "titular, enlace y fecha."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "news",
        "cost_note": NEWS_COST,
        "confidence_floor": 0.0,
    },
    {
        "code": "NEWS_ACQUISITION",
        "label": "Prensa: adquisición",
        "description": "Un titular sobre la cuenta habla de una compra, adquisición, absorción o fusión.",
        "category": "profile",
        "value_type": "text",
        "collector": "news",
        "cost_note": NEWS_COST,
        "confidence_floor": 0.0,
    },
    {
        "code": "NEWS_INVESTOR",
        "label": "Prensa: entrada de inversor",
        "description": (
            "Un titular sobre la cuenta habla de un fondo, private equity, capital riesgo o "
            "de una entrada en el capital (o de que es una participada)."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "news",
        "cost_note": NEWS_COST,
        "confidence_floor": 0.0,
    },
    {
        "code": "NEWS_LEADERSHIP",
        "label": "Prensa: cambio en la dirección",
        "description": "Un titular sobre la cuenta anuncia un nombramiento: nuevo director general, CEO, relevo.",
        "category": "profile",
        "value_type": "text",
        "collector": "news",
        "cost_note": NEWS_COST,
        "confidence_floor": 0.0,
    },

    # ── Scoring ──
    {
        "code": "ICP_SCORE",
        "label": "Puntuación ICP",
        "description": (
            "La puntuación de la cuenta según las reglas de scoring de harvey.yaml, con la "
            "lista de reglas que han sumado (explicable). Filtra en el constructor de cohortes "
            "con un rango (ICP_SCORE ≥ umbral) o con `harvey accounts cohort`."
        ),
        "category": "discovery",
        "value_type": "num",
        "collector": "scoring",
        "cost_note": "gratis (se calcula con las señales ya recogidas)",
        "confidence_floor": 0.0,
    },
]
