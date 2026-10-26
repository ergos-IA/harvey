# Skills

Las skills son archivos Markdown editables que dan a Harvey conocimientos básicos de ventas. Cada agente carga las skills que necesita antes de tomar decisiones.

## Cómo funcionan las skills

Cuando se ejecuta un agente, llama a `brain.load_skills_for_agent("agent_name")`, que concatena los archivos de skills pertinentes y los inyecta en el prompt. Esto significa que puedes cambiar el comportamiento de Harvey editando estos archivos, sin tocar el código.

## Correspondencia entre skills y agentes

| Skill | Scout | Writer | Handler | Sender | LinkedIn |
|-------|-------|--------|---------|--------|----------|
| `prospecting_tactics.md` | x | | | | x |
| `lead_qualification.md` | x | | | | |
| `account_navigation.md` | x | | | | |
| `signal_playbook.md` | x | x | | | |
| `email_frameworks.md` | | x | | x | |
| `sales_methodology.md` | | x | x | | |
| `offer_strategy.md` | | x | x | | |
| `objection_handling.md` | | | x | | |
| `linkedin_outreach.md` | | | | | x |
| `product_knowledge.md` | x | x | x | x | x |
| `competitive_intel.md` | | x | x | | |
| `selling_to_startups.md` | | x* | x* | | |

\* Solo para prospectos cuya empresa es una startup según su propio sitio web (la señal `YC_BACKED` o `ACCELERATOR`, o un `FUNDING_ROUND` de los últimos 18 meses); no se carga para todos.

## Skills incluidas

- **`prospecting_tactics.md`** — consultas de Google dorking, scraping de sitios web de empresas, eventos desencadenantes, búsqueda de referidos
- **`lead_qualification.md`** — filtrado BANT, puntuación de ICP, marco MEDDIC, criterios de descalificación
- **`account_navigation.md`** — gestión de varios contactos, estrategia de punto de entrada, reglas de multi-threading
- **`selling_to_startups.md`** — cómo escribir a fundadores en fase inicial: quién lee, el momento adecuado en torno a un batch de YC o de una aceleradora y el Demo Day, cómo escribir a empresas que acaban de levantar capital (y cuándo una ronda es demasiado antigua para mencionarla), qué no hacer y cómo gestionar sus respuestas. Se usa automáticamente con prospectos respaldados por YC, por aceleradoras o con financiación reciente.
- **`signal_playbook.md`** — cómo convertir las señales de compra (contratación, stack tecnológico, financiación) en la primera línea del email; qué señal gana cuando hay varias; usar una oferta de empleo como gancho sin adivinar ni dar a entender que se tiene información interna
- **`email_frameworks.md`** — reglas de copywriting para email en frío, patrones de IA prohibidos, datos de tasa de respuesta de 2026 (longitud, CTA de oferta, cadencia, sin tracking), 5 frameworks (AIDA, PAS, BAB, QVC, 3Ps)
- **`sales_methodology.md`** — ABC Loop, flujo de la conversación, calibración del tono, pautas éticas
- **`offer_strategy.md`** — escalera de ofertas según el nivel de interés, mecánica de cierre, reglas de momento oportuno
- **`objection_handling.md`** — marco LAARC, 4 categorías de objeciones con sus respuestas
- **`linkedin_outreach.md`** — secuencias de conexión, plantillas de mensajes, límites de frecuencia

## Skills generadas automáticamente

Las crea `harvey train <url>` y son específicas de tu producto:

- **`product_knowledge.md`** — funcionalidades, beneficios, precios, casos de uso, puntos de dolor, desencadenantes de compra
- **`competitive_intel.md`** — battle cards de cada competidor, ángulos de diferenciación, rutas de migración

## Añadir o editar skills

1. Edita cualquier archivo `.md` de este directorio
2. Los cambios surten efecto en el siguiente ciclo de heartbeat (no hace falta reiniciar)
3. Para añadir una skill nueva, crea el archivo y añádelo al `skill_map` de `harvey/brain.py`
