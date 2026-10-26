"""The signal vocabulary Harvey proposes, and the user confirms.

Harvey never decides on its own what makes a good prospect. It proposes a
catalog of signals it knows how to collect — each with a plain-language
description, what it costs, and why it might matter — and the user confirms,
edits, or rejects them in the dashboard before any collection runs.

Only ``confirmed`` signals get collected. That keeps spend intentional and
keeps the resulting cohorts explainable: a prospect list is a query over
signals a human chose, not a black box.

Design note: every signal is recorded as an OBSERVATION (a row), never a
column. A new signal needs no migration, history comes free, and confidence
and provenance travel with the fact.
"""

# category: discovery | profile | people | verification
# value_type: num | text | bool
# cost_note: what collecting it actually costs, in plain language
SIGNAL_CATALOG: list[dict] = [
    # ── Discovery: who exists, and how visible are they ──
    {
        "code": "SERP_RANK",
        "label": "Posición en Google",
        "description": (
            "Dónde aparece el negocio en los resultados orgánicos de una búsqueda "
            "'<servicio> <ciudad>' (se guarda la búsqueda). Es la señal de prospección "
            "más útil: las posiciones 11-30 son el punto dulce, visibles para estar "
            "intentándolo pero sin ganar todavía. El top 10 ya gana (venta más difícil); "
            "del 31 en adelante son más baratos pero están menos motivados. La posición "
            "depende de dónde busca uno: esta es la vista desde el centro de la ciudad."
        ),
        "category": "discovery",
        "value_type": "num",
        "collector": "discover",
        "cost_note": "~0,006 $ por búsqueda a profundidad 30 (API de SERP de pago, endpoint Live)",
        "confidence_floor": 0.0,
    },
    {
        "code": "IN_LOCAL_PACK",
        "label": "En el pack local de Google (top 3 del mapa)",
        "description": (
            "Ocupa uno de los tres huecos del mapa encima de los resultados orgánicos "
            "en una búsqueda '<servicio> <ciudad>' (valor = hueco 1-3; sin anuncios). "
            "Estos negocios ya ganan en búsqueda local: exclúyelos para encontrar a los "
            "que no, o ofréceles otra cosa."
        ),
        "category": "discovery",
        "value_type": "num",
        "collector": "discover",
        "cost_note": "incluido en la búsqueda de posición orgánica anterior",
        "confidence_floor": 0.0,
    },
    {
        "code": "MAPS_RANK",
        "label": "Posición en Google Maps",
        "description": (
            "Dónde aparece el negocio en Google Maps para una búsqueda '<servicio> "
            "<ciudad>' desde el centro de la ciudad (se guarda la búsqueda). Fuera del "
            "top 3 del mapa significa fuera del pack local que ve la mayoría. También "
            "encuentra negocios sin web."
        ),
        "category": "discovery",
        "value_type": "num",
        "collector": "discover",
        "cost_note": "~0,002 $ por búsqueda en Maps de hasta 100 resultados (API de SERP de pago)",
        "confidence_floor": 0.0,
    },
    {
        "code": "FOUND_IN_SERP",
        "label": "Encontrado en una búsqueda",
        "description": "El negocio apareció en una búsqueda del mercado objetivo: así es como Harvey lo encontró.",
        "category": "discovery",
        "value_type": "text",
        "collector": "discover",
        "cost_note": "incluido en la búsqueda anterior",
        "confidence_floor": 0.0,
    },

    {
        "code": "NO_WEBSITE",
        "label": "Sin web",
        "description": (
            "El negocio tiene ficha y teléfono pero no web. Si vendes webs, es la "
            "señal de mayor intención que existe, y se puede filtrar directamente, "
            "no hay que deducirla."
        ),
        "category": "discovery",
        "value_type": "bool",
        "collector": "discover",
        "cost_note": "incluido en la consulta de la ficha del negocio",
        "confidence_floor": 0.0,
    },
    {
        "code": "UNCLAIMED_LISTING",
        "label": "Ficha de Google sin reclamar",
        "description": (
            "Nadie ha reclamado su Perfil de Empresa de Google, así que no gestionan "
            "cómo aparecen en búsquedas locales. Señal fuerte si vendes marketing local."
        ),
        "category": "discovery",
        "value_type": "bool",
        "collector": "discover",
        "cost_note": "incluido en la consulta de la ficha del negocio",
        "confidence_floor": 0.0,
    },
    {
        "code": "REVIEW_RATING",
        "label": "Valoración media",
        "description": (
            "Su media de estrellas. Sirve en los dos sentidos: una nota baja es un "
            "problema de reputación que resolver; una alta con pocas reseñas demuestra "
            "que son buenos pero invisibles."
        ),
        "category": "discovery",
        "value_type": "num",
        "collector": "discover",
        "cost_note": "incluido en la consulta de la ficha del negocio",
        "confidence_floor": 0.0,
    },
    {
        "code": "REVIEW_COUNT",
        "label": "Número de reseñas",
        "description": (
            "Cuántas reseñas tienen. Una aproximación a su tamaño y a cuánto cuidan "
            "su presencia online."
        ),
        "category": "discovery",
        "value_type": "num",
        "collector": "discover",
        "cost_note": "incluido en la consulta de la ficha del negocio",
        "confidence_floor": 0.0,
    },

    # ── Profile: what they are (free — HTML Harvey already fetches) ──
    {
        "code": "INCUMBENT_AGENCY",
        "label": "Trabaja con una agencia de marketing/web",
        "description": (
            "Una agencia citada en el pie de la web ('Web por X'). Muy valiosa: dice "
            "a quién desplazas, y cada detección construye una lista de clientes de esa "
            "agencia a la que dirigirte en bloque. Solo se guarda cuando el crédito es "
            "explícito: una agencia equivocada es peor que ninguna."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.75,
    },
    {
        "code": "RUNNING_GOOGLE_ADS",
        "label": "Invierte en Google Ads",
        "description": "Etiqueta de Google Ads en la web: invierten en captación HOY. Señal fuerte de presupuesto.",
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "RUNNING_META_ADS",
        "label": "Invierte en anuncios de Meta/Facebook",
        "description": "Píxel de Meta en la web: invierten activamente en redes sociales de pago.",
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "TECH_STACK",
        "label": "Plataforma y herramientas de la web",
        "description": "Con qué está hecha la web y qué herramientas usa (WordPress, Shopify, PrestaShop, HubSpot, chats, helpdesk, reservas).",
        "category": "profile",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "NO_SCHEMA_MARKUP",
        "label": "Sin datos estructurados",
        "description": "Sin marcado schema JSON-LD: una carencia de SEO concreta y comprobable que se puede citar en un email.",
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "NO_ONLINE_BOOKING",
        "label": "Sin reserva o cita online",
        "description": "No se detecta ningún sistema de reservas o citas: los clientes tienen que llamar y se pierde la demanda fuera de horario.",
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "SITE_PAGE_COUNT",
        "label": "Tamaño de la web",
        "description": "Número de páginas según sitemap.xml. Una web muy pequeña sugiere poca inversión; una grande y parada, abandono.",
        "category": "profile",
        "value_type": "num",
        "collector": "profile",
        "cost_note": "gratis (sitemap.xml)",
        "confidence_floor": 0.0,
    },
    {
        "code": "BLOG_STALE",
        "label": "Contenido abandonado",
        "description": "Hace mucho que no publican nada: empezaron con el marketing de contenidos y lo dejaron.",
        "category": "profile",
        "value_type": "num",
        "collector": "profile",
        "cost_note": "gratis (sitemap.xml)",
        "confidence_floor": 0.0,
    },
    {
        "code": "BLOCKS_AI_CRAWLERS",
        "label": "Bloquea los rastreadores de IA",
        "description": "Su robots.txt bloquea los rastreadores de IA: serán invisibles en las respuestas de los buscadores con IA.",
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (robots.txt)",
        "confidence_floor": 0.0,
    },
    {
        "code": "YC_BACKED",
        "label": "Respaldada por Y Combinator",
        "description": ("La empresa dice en su propia web que la respalda YC (una batch como W24, "
                        "un distintivo de YC o un enlace a su página de YC). Va con el preset de "
                        "descubrimiento de startups de YC y la guía para escribir a fundadores."),
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (HTML de la portada)",
        "confidence_floor": 0.0,
    },
    {
        "code": "ACCELERATOR",
        "label": "Pasó por una aceleradora",
        "description": ("La empresa dice en su propia web que la respaldó una aceleradora: Techstars, "
                        "500 Global, Antler, Entrepreneur First, South Park Commons, Neo, AI Grant, "
                        "a16z speedrun, Pioneer o Plug and Play, con la promoción si la indica. YC va "
                        "en YC_BACKED. Va con el preset de descubrimiento de aceleradoras y la guía "
                        "para escribir a fundadores."),
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (portada y página 'Quiénes somos')",
        "confidence_floor": 0.0,
    },
    {
        "code": "FUNDING_ROUND",
        "label": "Anunció una ronda de financiación",
        "description": ("La empresa anuncia en su web su propia ronda (\"hemos levantado\", \"Acme "
                        "levanta 12 M$ en Serie A\"): ronda, importe y fecha si los indica. Las rondas "
                        "de hace más de 18 meses no se usan como noticia. Va con el preset de "
                        "empresas recién financiadas."),
        "category": "profile",
        "value_type": "bool",
        "collector": "profile",
        "cost_note": "gratis (portada, 'Quiénes somos' y página de prensa)",
        "confidence_floor": 0.0,
    },
    {
        "code": "HIRING_ROLE",
        "label": "Contrata un puesto relevante",
        "description": (
            "Una vacante que indica que ahora mismo compran en tu categoría: uno de "
            "tus puestos de hiring_signals (o cargos del ICP) en el portal de empleo "
            "(Greenhouse, Lever, Ashby, Workable…) que enlaza su web, con departamento, "
            "ubicación y fecha de publicación, o un puesto de su página de empleo."
        ),
        "category": "profile",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (página de empleo o feed público del portal de empleo)",
        "confidence_floor": 0.0,
    },
    {
        "code": "OPEN_ROLES",
        "label": "Vacantes abiertas en su portal de empleo",
        "description": (
            "Cuántas vacantes hay abiertas en el portal de empleo que enlaza su web. "
            "Un equipo que crece es señal de presupuesto; cero es una señal de calma."
        ),
        "category": "profile",
        "value_type": "num",
        "collector": "profile",
        "cost_note": "gratis (feed público del portal de empleo, una petición)",
        "confidence_floor": 0.0,
    },

    # ── People: who decides ──
    {
        "code": "CONTACT_FOUND",
        "label": "Contacto con nombre encontrado",
        "description": "Una persona con nombre y cargo sacada de la página de equipo o 'Quiénes somos'.",
        "category": "people",
        "value_type": "text",
        "collector": "people",
        "cost_note": "gratis (página de equipo)",
        "confidence_floor": 0.0,
    },
    {
        "code": "DECISION_MAKER_TITLE",
        "label": "Cargo de decisor",
        "description": "El cargo encaja con un decisor (gerente, director general, CEO, presidente, director comercial o de operaciones).",
        "category": "people",
        "value_type": "text",
        "collector": "people",
        "cost_note": "gratis (página de equipo)",
        "confidence_floor": 0.0,
    },
    {
        "code": "REGISTRY_VERIFIED",
        "label": "Confirmado en un registro público",
        "description": (
            "La persona aparece en un registro público fiable (colegio profesional, "
            "registro oficial). También filtra errores de extracción: un nombre que no "
            "coincide con nada normalmente no era una persona."
        ),
        "category": "people",
        "value_type": "text",
        "collector": "people",
        "cost_note": "gratis (API de registro público)",
        "confidence_floor": 0.0,
    },
    {
        "code": "LIKELY_OWNER",
        "label": "Probablemente el dueño",
        "description": (
            "La web de la empresa dice que esta persona la posee o la fundó: un cargo "
            "de dueño, fundador o presidente, una frase como 'empresa dirigida por' o "
            "un fundador en schema.org. Los dueños anteriores, jubilados o fallecidos no "
            "cuentan. La prueba se guarda con el dato."
        ),
        "category": "people",
        "value_type": "bool",
        "collector": "people",
        "cost_note": "gratis (web de la empresa)",
        "confidence_floor": 0.0,
    },

    # ── Verification ──
    {
        "code": "EMAIL_PATTERN",
        "label": "Patrón de email de la empresa",
        "description": "El formato de las direcciones del dominio (nombre.apellido@, napellido@). Una dirección real descifra toda la empresa.",
        "category": "verification",
        "value_type": "text",
        "collector": "verify",
        "cost_note": "gratis, o ~1 crédito de búsqueda",
        "confidence_floor": 0.0,
    },
    {
        "code": "EMAIL_STATUS",
        "label": "Entregabilidad del email",
        "description": "Si la dirección está verificada, es catch-all/arriesgada, es una suposición sin verificar o no es válida.",
        "category": "verification",
        "value_type": "text",
        "collector": "verify",
        "cost_note": "1 crédito de verificación (hay planes gratuitos)",
        "confidence_floor": 0.0,
    },
    {
        "code": "CONTACT_FORM_URL",
        "label": "Tiene formulario de contacto",
        "description": (
            "Un formulario de contacto en la web. Conviene saberlo porque llega a la "
            "empresa sin necesitar una dirección de email, y aproximadamente la mitad "
            "de los dominios no se pueden verificar."
        ),
        "category": "verification",
        "value_type": "text",
        "collector": "profile",
        "cost_note": "gratis (HTML de la web)",
        "confidence_floor": 0.0,
    },
]

# Account-based selling to Spanish mid-sized companies (imported accounts,
# BORME, press, Spanish job boards, ICP score). Kept in their own module.
from harvey.collectors.spain.catalog import SPAIN_SIGNALS  # noqa: E402

SIGNAL_CATALOG += SPAIN_SIGNALS


async def seed_signal_catalog(state) -> int:
    """Register the catalog as PROPOSED signals awaiting user confirmation.

    Idempotent, and never overrides a decision the user already made: an
    existing signal keeps its confirmed/rejected status.
    """
    for sig in SIGNAL_CATALOG:
        await state.upsert_signal_code(
            sig["code"],
            label=sig["label"],
            description=sig["description"],
            category=sig["category"],
            value_type=sig["value_type"],
            collector=sig["collector"],
            cost_note=sig["cost_note"],
            confidence_floor=sig.get("confidence_floor", 0.0),
        )
    return len(SIGNAL_CATALOG)
