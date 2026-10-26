# Harvey

**Un agente de ventas autónomo que funciona con tu suscripción de Claude Code o Codex.**

Harvey encuentra negocios a los que merece la pena vender, aprende algo concreto de cada uno, escribe correos en frío que lo mencionan, los envía, lee las respuestas y conduce la conversación hasta una reunión. Funciona en tu máquina, en bucle, por sí solo.

Lo poco habitual: **no hay factura de API de modelos.** Harvey usa tu suscripción Claude Pro o Max a través de Claude Code, o tu suscripción de ChatGPT a través de Codex. Las llamadas al modelo usan el plan que ya pagas, sin clave de API ni facturación de API por token. Claude es el proveedor por defecto; [Codex es un proveedor opcional en macOS y Linux](#usar-un-plan-de-chatgpt-en-su-lugar-codex).

```
$ harvey run

============================================================
Harvey is online. Always Be Closing.
============================================================
Checking pipeline state...
Decision: handle_replies (2 new replies)
  handler   → Elena Park, Harbor Dental Studio     interested, answer drafted
  handler   → Priya Nair, Highline Roofing         objection, answer drafted
Decision: write_campaign (3 new prospects with no drafts)
  writer    → 2-email sequence: Phoenix HVAC hiring a dispatcher
  outbox    → 5 emails waiting for your approval
Cycle complete. Sleeping for 15 minutes.
```

Y el panel que mantiene, en `localhost:5555`. En este orden: la pantalla Today, una
conversación que Harvey te devolvió porque un prospecto pidió un contrato, la aprobación
de una respuesta redactada desde la bandeja de salida, la confirmación de una señal, la creación de una cohorte
a partir de señales confirmadas, la búsqueda de contactos y la misma pantalla en modo oscuro:

![Panel de Harvey: la pantalla Today, una conversación devuelta a una persona, la aprobación de una respuesta en la bandeja de salida, la confirmación de una señal y la creación de una cohorte, la búsqueda de contactos y, por último, el modo oscuro](docs/dashboard.gif)

<sub>Los datos de la demo son inventados: "Bookwell" vendiendo reservas online a tejadistas, clínicas dentales y negocios de climatización, en dominios `.test`.</sub>

---

## Tabla de contenidos

- [Por qué importa lo de la suscripción](#por-qué-importa-lo-de-la-suscripción)
- [Qué hace realmente Harvey](#qué-hace-realmente-harvey)
- [Inicio rápido](#inicio-rápido)
- [Tú confirmas qué busca](#tú-confirmas-qué-busca)
- [El pipeline de prospección](#el-pipeline-de-prospección)
- [La biblioteca de skills](#la-biblioteca-de-skills)
- [Los subagentes](#los-subagentes)
- [Nada se envía sin ti](#nada-se-envía-sin-ti)
- [El panel](#el-panel)
- [Cómo se almacenan los datos](#cómo-se-almacenan-los-datos)
- [Configuración](#configuración)
- [Usar un plan de ChatGPT en su lugar (Codex)](#usar-un-plan-de-chatgpt-en-su-lugar-codex)
- [Aspectos legales y entregabilidad](#aspectos-legales-y-entregabilidad)
- [Solución de problemas](#solución-de-problemas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Filosofía](#filosofía)
- [Hoja de ruta](#hoja-de-ruta)

---

## Por qué importa lo de la suscripción

Todos los demás agentes de ventas autónomos te facturan por token. Esa es la razón de que cuesten lo que cuestan: un agente que piensa en bucle, todo el día, es un agente que quema créditos de API en bucle, todo el día. Los proveedores lo resuelven pensando menos: prompts más cortos, modelos más baratos, menos pasadas.

Harvey usa la CLI respaldada por suscripción del proveedor que elijas: `claude` para Claude Code, o un `codex app-server` aislado para Codex. Ambas devuelven texto con las herramientas del modelo desactivadas. Harvey se encarga por sí mismo de la prospección y de las operaciones de correo.

Las llamadas a Claude se ejecutan sin nada de tu propia configuración de Claude Code: sin `CLAUDE.md` (ni el tuyo, ni el del proyecto, ni el de ninguna carpeta superior), sin hooks, skills, plugins, servidores MCP ni archivos de ajustes, sin herramientas, en una carpeta temporal vacía y sin guardar nada en tus transcripciones de Claude. Tu inicio de sesión (suscripción o `claude setup-token`) y cualquier política gestionada por un administrador siguen aplicándose. Esto requiere una CLI de Claude con `--safe-mode`; con una más antigua, Harvey se pausa en lugar de enviar prompts sin aislar y te indica que ejecutes `claude update`. Para comprobarlo sin conexión contra tu CLI instalada, sin credenciales ni red: `HARVEY_CLAUDE_CLI_TESTS=1 pytest tests/test_claude_cli_isolation.py`.

Tu suscripción seleccionada cubre las llamadas al modelo, sujeta a sus límites de uso. Eso permite a Harvey usar su biblioteca de skills para personalizar y gestionar respuestas sin una factura de API de modelos aparte.

**Lo que esto te cuesta:**

| | |
|---|---|
| Claude Pro/Max o un plan de ChatGPT con acceso a Codex | tu suscripción actual |
| Encontrar negocios | **0 $** con la fuente por defecto, o ~0,37 $ por cada 1.000 con la de pago más barata |
| Leer sus sitios web | **0 $** — tres peticiones HTTP cada uno, sin llamada al modelo |
| Escribir y enviar | tu suscripción + un buzón (~7 $/mes de Google Workspace) |
| Herramientas de prospección | **ninguna.** Ni Apollo, ni ZoomInfo, ni Clearbit, ni Clay. |

A modo de comparación, las herramientas que Harvey sustituye empiezan en 250–500 $/mes, y son más débiles justo donde Harvey es más fuerte: los negocios locales pequeños de 5 a 50 personas, donde la cobertura de contactos de un solo proveedor se queda en torno al 30 % y las microempresas suelen estar ausentes por completo.

**Harvey también se presupuesta a sí mismo.** Lee la cuota de suscripción del proveedor activo y se modera para dejar margen a tu propio trabajo con Claude o Codex. Define `max_daily_claude_percent: 80` para cualquiera de los dos proveedores (el nombre del ajuste es anterior al soporte de Codex). Si no se puede leer la cuota, Harvey la indica como no disponible y recurre a su presupuesto diario de llamadas.

Harvey se ejecuta en local con tu propio inicio de sesión. Revisa los términos y los límites de uso del proveedor que elijas.

---

## Qué hace realmente Harvey

Harvey funciona con un latido: despierta, comprueba el presupuesto, decide qué es lo que más necesita hacerse, lo hace, lo registra y duerme. Cada 15 minutos por defecto.

```
                 ┌──────────────────────────────────────┐
                 ↓                                      │
   Wake  →  Quiet hours?  →  Budget OK?  →  Decide  →  Act  →  Log  →  Sleep
                 │               │
              (sleep)         (sleep)
```

Decide de forma determinista, no preguntando a un modelo qué hacer: eso gastaría una llamada en algo que se deduce de cuatro contadores:

```
handle replies  >  send campaigns  >  write campaigns  >  prospect  >  idle (analyze)
```

El perfilado y el vaciado de la bandeja de salida se hacen en **cada** ciclo, pase lo que pase, porque no cuestan nada y tienen que ocurrir según lo programado.

---

## Inicio rápido

### Requisitos previos

- **Python 3.11+** — compruébalo con `python3 --version`. macOS incluye la 3.9; si es la que tienes, ejecuta antes `brew install python@3.13`.
- Una suscripción activa de **Claude Pro o Max**, con la CLI con sesión iniciada (`claude login`) — o, de forma opcional, un **plan de ChatGPT con la CLI de Codex** ([ver más abajo](#usar-un-plan-de-chatgpt-en-su-lugar-codex))
- Un buzón desde el que enviar — se recomienda Gmail/Workspace, en un *dominio secundario dedicado*. Microsoft 365 también funciona ([configuración](docs/microsoft365.md))
- Un servicio de warmup sobre ese buzón — recomendamos [TrulyInbox](https://trulyinbox.com/?via=harvey). Calienta un buzón nuevo antes del correo en frío, lo mantiene fuera del spam después, y Harvey lee su tasa de bandeja de entrada para avisarte de cuándo estás listo ([Warmup](#warmup-con-trulyinbox))

### Lo más fácil: deja que Claude lo configure

```bash
git clone https://github.com/ethanplusai/harvey.git
cd harvey
claude
```

Después di: **"set up Harvey for me"**. El repositorio incluye un `CLAUDE.md` que convierte Claude Code en el asistente de configuración: comprueba en qué estado estás, instala lo que falta, te pregunta lo que necesita y entrena a Harvey con tu producto.

### O hazlo tú mismo

```bash
# 1. Install — note python3.13, not python3. On macOS bare `python3` is the
#    system 3.9, and a venv built from it can't run Harvey.
python3.13 -m venv .venv && source .venv/bin/activate && pip install -e .

# 2. Configure — every variable is documented inline with where to get it
cp .env.example .env && $EDITOR .env

# 3. Learn your product from your website (writes harvey.local.yaml; re-running
#    it updates the product, targeting and company and keeps your other settings)
harvey train https://your-company.com

# 4. Choose what makes a good prospect (see below — this one matters)
harvey signals --confirm free

# 5. Find businesses. Free source, no account needed.
harvey discover

# 6. Watch it work
harvey dashboard          # prints a private link to http://127.0.0.1:5555
harvey run
```

---

## Tú confirmas qué busca

Esta es la parte que distingue a Harvey de una caja negra, y a propósito no se puede saltar.

Harvey sabe recopilar **29 señales** sobre un negocio. No recopila ninguna hasta que tú lo dices. En la primera ejecución te *propone* el catálogo; tú confirmas, omites o rechazas cada una en el panel o desde el terminal:

```bash
harvey signals                       # review the catalog
harvey signals --confirm free        # everything that costs nothing (26 of them)
harvey signals --confirm SERP_RANK   # a paid one, opted into explicitly
```

Cada señal muestra en lenguaje claro qué es, **cuánto cuesta** y cuántas empresas ya la tienen.

| | Señal | Qué te dice |
|---|---|---|
| **Discovery** | `SERP_RANK` | Dónde se posicionan en su propia búsqueda principal, guardado junto con la frase buscada. Las posiciones 11–30 son el punto ideal: lo bastante visibles como para estar intentándolo, y perdiendo. |
| | `IN_LOCAL_PACK` / `MAPS_RANK` | Si ocupan uno de los tres huecos del mapa sobre los resultados y en qué posición están en Google Maps. |
| | `NO_WEBSITE` | Tienen ficha y teléfono, pero no web. Si vendes sitios web, la señal de mayor intención que existe. |
| | `UNCLAIMED_LISTING` | Nadie ha reclamado su perfil de empresa de Google. |
| | `REVIEW_RATING` / `REVIEW_COUNT` | Buenos pero invisibles, o visibles pero con dificultades. |
| **Profile** | `INCUMBENT_AGENCY` | Quién lleva ahora la cuenta, con crédito en su propio pie de página. Cada detección construye un listado que puedes atacar como una cartera de negocio completa. |
| | `RUNNING_GOOGLE_ADS` / `RUNNING_META_ADS` | Están gastando en captación *hoy*. La señal de presupuesto más fuerte disponible gratis. |
| | `NO_ONLINE_BOOKING` | Los clientes potenciales tienen que llamar por teléfono, así que se pierde la demanda fuera de horario. |
| | `NO_SCHEMA_MARKUP` | Una carencia de SEO concreta y comprobable que puedes nombrar en un correo. |
| | `BLOG_STALE` | Empezaron con el marketing de contenidos y lo abandonaron. |
| | `SITE_PAGE_COUNT`, `TECH_STACK`, `BLOCKS_AI_CRAWLERS` | Tamaño, plataforma, visibilidad en búsqueda con IA. |
| | `HIRING_ROLE` / `OPEN_ROLES` | Qué perfiles están contratando y cuántos puestos tienen abiertos. Cuando su sitio enlaza un tablero de Greenhouse, Lever, Ashby o Workable, Harvey lee el feed público de ese tablero (una petición): los puestos que coinciden con `icp.hiring_signals` (si no, `icp.titles`), con departamento, ubicación, fecha de publicación y la URL de la oferta; cuando el tablero no lista ninguno, registra "not hiring" para que un puesto cerrado deje de contar. Si no, lee la página de empleo. Define `hiring_signals` con los puestos que indican que van a comprar: el respaldo de `titles` nombra a quién escribes, así que "CEO" solo coincide con una vacante de CEO (nunca con "Assistant to the CEO"), que rara vez es la señal que quieres. |
| | `YC_BACKED`, `ACCELERATOR`, `FUNDING_ROUND` | Una startup, según su propio sitio: YC u otra aceleradora (con el batch o la cohorte), o una ronda que anunció (tipo de ronda, importe, fecha). |
| **People** | `CONTACT_FOUND`, `DECISION_MAKER_TITLE`, `LIKELY_OWNER`, `REGISTRY_VERIFIED` | Quién decide y si es el dueño del negocio. |
| **Contact** | `EMAIL_PATTERN`, `EMAIL_STATUS`, `CONTACT_FORM_URL` | Si realmente puedes contactarles. |

### Entonces una cohorte es una consulta, no una lista

Una vez confirmadas las señales, el constructor de cohortes del panel las convierte en un conjunto objetivo: eliges lo que un buen prospecto **debe tener**, lo que lo **descalifica** y un **rango** para las señales numéricas (posición orgánica de 11 a 30), y cuenta las coincidencias en directo:

```
Has a marketing agency  AND  running Google Ads  AND NOT  already has online booking
→ 23 companies
```

Eso es una campaña con una razón detrás. Sabes exactamente por qué cada una de esas 23 está en la lista, y también lo sabe el correo que Harvey les escribe.

---

## El pipeline de prospección

Cuatro etapas. Cada una funciona de forma independiente, se puede volver a ejecutar sin riesgo y declara su coste.

### 1. DESCUBRIR — quién existe

La única etapa que gasta dinero, así que siempre estima primero y no llama a nada hasta que tú das el visto bueno.

```bash
harvey discover --providers   # the menu, with real prices
harvey discover --estimate    # projected spend, then exits
harvey discover               # go
```

| Fuente | Coste | Nivel gratuito | Ideal para |
|---|---|---|---|
| **OpenStreetMap** *(por defecto)* | gratis | ilimitado, sin cuenta | Probar todo el pipeline antes de pagar a nadie. La cobertura es escasa para negocios sin local a pie de calle: OSM cartografía locales, así que oficios enteros apenas aparecen (menos de 2.000 tejadistas y menos de 2.300 fontaneros en todo EE. UU.). Harvey lo dice en la interfaz en lugar de quedarse corto sin avisar. |
| **TinyFish** | gratis | 30 búsquedas por minuto, 500 por hora, sin tarjeta | Encontrar negocios por frase (incluidos los presets de startups y contratación) sin coste. No registra posición de búsqueda: su orden no es el de Google y no admite ubicación, así que usa Serper o DataForSEO SERP para las señales de posición. |
| **DataForSEO Business Listings** | 0,372 $ / 1.000 | 1 $ de crédito | Oficios locales, clínicas, contratistas. Teléfono, dominio, valoración, estado de reclamación, y puede filtrar negocios **sin ningún sitio web**. |
| **DataForSEO SERP** | 0,006 $ / búsqueda con profundidad 30 (Live, 0,002 $ por cada 10 resultados) | 1 $ de crédito + sandbox gratuito | La posición orgánica como señal de compra, más quién ocupa el paquete local de 3, buscado desde el centro de la ciudad. |
| **DataForSEO Google Maps** | 0,002 $ / búsqueda (hasta 100 resultados) | 1 $ de crédito + sandbox gratuito | Posición en el mapa, valoración, categoría y estado de reclamación, incluidos los negocios sin sitio web. |
| **Serper** | ~0,30–1,00 $ / 1.000 | 2.500 gratis, sin tarjeta | La de pago más fácil de probar. |

**¿Vendes a startups?** Harvey tiene una skill de startups integrada, formada por tres
partes:

- **Las búsquedas** (cada una es una búsqueda web, así que Serper o DataForSEO SERP):

  | Preset | Encuentra | Señal |
  |---|---|---|
  | `yc` (*YC startups*) | Empresas cuyo propio sitio dice que cuentan con el respaldo de Y Combinator | `YC_BACKED`, con el batch (W24, S23) |
  | `accelerator` (*Accelerator startups*) | Las respaldadas por Techstars, 500 Global, Antler, Entrepreneur First, South Park Commons, Neo, AI Grant, a16z speedrun o Plug and Play (dos búsquedas por sector; la señal también lee Pioneer) | `ACCELERATOR`, con el programa y la cohorte ("Techstars 2024") |
  | `funding` (*Recently funded*) | Empresas que anuncian su propia ronda ("we raised", "announces $X Series A") en los últimos 18 meses, con medios de noticias y bases de datos de financiación excluidos | `FUNDING_ROUND`: ronda, importe y fecha |

  `harvey discover --preset accelerator --provider serper`, o el menú *Look for*
  de la pestaña Discover.
- **Las señales:** actívalas en la pestaña Signals. Leen la página principal y la
  página About (y, en el caso de una ronda, la página que encontró la búsqueda en su propio sitio y
  su página de prensa o noticias) en busca de una frase en la que la empresa lo dice de sí misma
  ("we went through Y Combinator", "Acme (Techstars '24)", "we raised a $4M
  seed round"), un muro de logos "Backed by", o un enlace a su propia página de YC. Las frases
  sobre clientes o audiencia ("trusted by YC-backed startups", "we help founders raise
  their seed round") no cuentan. Muchas startups nunca lo dicen en su sitio, así que
  estas encuentran las que sí lo hacen; un acierto de un preset de YC o de aceleradora también cuenta como un sí.
  La fecha de una ronda sale de su propia cláusula, o de la fecha de publicación de una
  nota de prensa, noticia o entrada de blog. El dinero que no es una ronda (préstamos cerrados, sentencias
  ganadas, dinero recaudado para una causa benéfica, la ronda de un inversor en otra empresa)
  no cuenta.
- **La redacción:** el redactor y el gestor de respuestas usan
  `skills/selling_to_startups.md`, un manual para escribir a fundadores con una
  sección sobre empresas que acaban de levantar capital, sobre empresas respaldadas por YC y aceleradoras
  y sobre rondas fechadas en los últimos 18 meses. Una ronda más antigua o
  sin fecha, por sí sola, no activa el manual y nunca se trata como
  noticia.

Harvey nunca lee ycombinator.com, los directorios de las aceleradoras, Crunchbase,
PitchBook ni LinkedIn, cuyos términos prohíben rastrearlos; todo procede de
los sitios propios de las empresas y de tu proveedor de búsqueda.

**¿Buscas empresas que contratan un perfil?** `harvey discover --preset hiring
--provider serper` (o *Look for: Companies hiring for your roles*) busca
en tus sectores empresas cuyas propias páginas de empleo listan uno de tus
puestos de `icp.hiring_signals` (si no, `icp.titles`). Los tableros alojados y los portales de empleo
se excluyen de la búsqueda, ya que la página de un tablero nombra un tablero, no un sitio web
que perfilar. Confirma `HIRING_ROLE` y el perfilado lee el tablero al que enlaza su sitio
y registra el puesto; el acierto de la búsqueda por sí solo no registra nada.

Las ciudades se geocodifican solas (en caché para siempre, una consulta cada una). Los directorios, agregadores e instituciones se filtran por patrón, no con una lista de bloqueo: `en.wikipedia.org` y `biz.yelp.com` nunca entran.

> **Profundidad 20–30, no 100.** Google eliminó los 100 resultados por página en septiembre de 2025, así que la profundidad 100 ahora se factura como diez páginas casi en todas partes. Por debajo de la posición 30 son sobre todo directorios de todos modos.

### 2. PERFILAR — qué son

**Gratis.** Tres peticiones HTTP por negocio. Sin navegador, sin llamada al modelo. Es la etapa con mayor valor por esfuerzo de todo el sistema, porque produce los hechos que hacen específico un correo.

Las peticiones web de Scout, Profile y el rastreador local de entrenamiento se limitan
a destinos HTTP(S) públicos. Se comprueba cada respuesta DNS y cada redirección; se
rechazan las direcciones locales, privadas, de enlace local y de metadatos. Las conexiones usan
una IP validada y conservan la identidad TLS del sitio web. Estos clientes web
ignoran los proxies del entorno, de modo que el enrutado por proxy no puede saltarse ese límite.

Página principal, `robots.txt`, `sitemap.xml`, más las páginas de equipo y empleo cuando existen; después, regex sobre el HTML que ya se tiene. De ahí salen la agencia que lleva la cuenta, los píxeles de anuncios, el schema que falta, el blog abandonado, los puestos abiertos y las personas con nombre.

La detección de agencias es la que se acumula con el tiempo. Casi todas las agencias se acreditan en el pie de página, y Harvey puntúa la redacción: *"Powered by"* / *"Website by"* → 0,9 de confianza; un enlace descriptivo sin más → 0,75; un enlace sin etiqueta → 0,35 y **no se registra**. Una agencia equivocada en un correo es peor que no decir nada.

### 3. ENRIQUECER — quién decide

El dueño, a partir del propio sitio de la empresa. Harvey lee la página principal y sigue el menú del propio sitio hasta las páginas donde se nombra a las personas (equipo, about, nuestra historia, conoce a los dentistas, abogados, contacto), seis páginas como máximo, omitiendo los enlaces que vuelven a la página principal. En esas páginas lee:

- **tarjetas y listas**: un nombre con un cargo debajo, incluso cuando el cargo está solo a un `<br>` de distancia dentro de un span;
- **frases**: "owned and operated by Gary Pruitt", "led today by President Ilan Brooks", "Ines Varga started Countwise";
- **schema.org**: las entradas `founder` y `employee` del propio negocio (el autor de una entrada de blog no es plantilla);
- **el nombre en la puerta**: cuando dos personas tienen cargos de dueño, va primero aquella cuyo apellido está en el nombre del negocio. Un apellido por sí solo nunca convierte a nadie en dueño: Linda Smith, Office Manager, en Smith & Sons no lo es.

Los dueños van primero, y como máximo dos personas por empresa se convierten en prospectos. Los encabezados hechos de palabras corrientes ("Team of Experts"), los clientes citados en testimonios o tuits ("Founder at Quillnest"), los directivos de otras organizaciones ("KTR President Vic Hale"), los dueños anteriores o fallecidos ("Past President", "the late Harold Smith") y los eslóganes no son personas. Los cargos coinciden con tu ICP por palabra completa: "Vice President" no cuenta como "President" a menos que lo incluyas, y Proprietor, Principal, Managing Partner, Founder y CEO cuentan todos como dueño. Con `LIKELY_OWNER` confirmada, cada dueño se registra como una observación con la evidencia que lo respalda.

Cuando el sitio de una empresa no nombra a nadie, o nombra a un dueño cuya dirección es solo una suposición, y Harvey aún no tiene un contacto allí (algo habitual en los oficios pequeños), también usa una dirección general que la empresa publica en sus propias páginas (solo buzones generales como `owner@`, `office@`, `info@` o `hello@`, nunca la dirección personal de alguien). Harvey lee páginas completas en busca de ella, incluidos schema.org y direcciones ocultas a los rastreadores, y acepta una dirección de otro dominio solo cuando ese dominio lleva al propio sitio de la empresa. Nunca se adivina, se verifica como cualquier otra dirección, y esos correos saludan al equipo de la empresa en lugar de a un nombre de pila.

Un sitio tras un desafío anti-bots ("sgcaptcha" de SiteGround, "Just a moment…" de Cloudflare) se indica como protegido por desafío, no como inaccesible, y no se reintenta.

### 4. VERIFICAR — puedes llegar a ellos

Harvey aprende el **patrón de direcciones** de cada empresa y verifica un solo candidato, en lugar de probar variantes de nombres por fuerza bruta. Cualquier dirección que publique el sitio puede enseñárselo: `nvale@` junto a Nora Vale es `{inicial del nombre}{apellido}`, y `j.smith@` es una inicial y un apellido. Una dirección suelta sin punto que ninguna persona nombrada posea (`kmorrow@`: ¿Kmorrow o K. Morrow?) es ambigua y no enseña nada. Una dirección que podrían poseer dos personas nombradas (`jsmith@` cuando John y Jane Smith trabajan ahí) es solo evidencia de formato, y Harvey nunca adivina ni verifica una dirección que otra persona nombrada podría poseer: un verificador confirmaría el buzón *de ella*. Decodifica los trucos habituales de ocultación (protección de correo de Cloudflare, los atributos `data-user`/`data-domain` de un enlace de correo, `name [at] domain [dot] com`) y nunca inventa una dirección a partir de texto corriente. La dirección publicada por una persona se usa tal cual. Sin ninguna evidencia, adivina `first.last@`, o `first@` cuando algo aparte del sitio web indica que la empresa es pequeña (el tamaño de empresa de tu ICP, o un listado de negocio local como fuente). Una suposición en caché nunca impide que una dirección real o una consulta a Hunter la sustituya, y a Hunter se le pregunta una vez por dominio (un tiempo de espera agotado o un límite de peticiones no cuentan). El sondeo SMTP directo no es viable desde un portátil: el puerto 25 saliente suele estar bloqueado, y Google Workspace y Microsoft 365 aceptan todo desde una IP desconocida.

Cada dirección se etiqueta con honestidad: `verified` / `risky` (catch-all) / `guess` / `invalid`. **Solo se envía a las entregables.** Una suposición nunca se trata como un acierto.

> Harvey merece la pena aunque nunca le dejes enviar. `harvey export` escribe un CSV listo para un secuenciador con todo lo que encontró.

---

## La biblioteca de skills

El conocimiento de ventas de Harvey vive en `skills/` como **Markdown plano que puedes editar**. No hay fine-tuning, ni almacén de vectores, ni paso de recuperación. Antes de que un agente se ejecute, las skills que necesita se concatenan directamente en su prompt. Cambias un archivo y el siguiente latido se comporta de otra manera: sin reiniciar, sin tocar código.

Esta es la principal forma de moldear a Harvey. Si sus correos son demasiado insistentes, edita `email_frameworks.md`. Si gestiona mal una objeción concreta, edita `objection_handling.md` y añade la respuesta que darías tú de verdad.

### Qué incluye

**`email_frameworks.md`** — 301 líneas, el archivo más importante del repositorio. Abre con la única regla que importa: *escribe como una persona real que envía un correo real.* Contiene una lista de prohibiciones estricta sobre los tics de la IA (nada de "I hope this finds you well", nada de "I wanted to reach out", nada de "circling back"), reglas de cumplimiento normativo que prevalecen sobre todas las reglas de estilo que tienen debajo, datos de 2026 sobre tasa de respuesta según longitud y cadencia y por qué el seguimiento de enlaces te perjudica, y cinco frameworks —**AIDA, PAS, BAB, QVC, 3Ps**— con reglas de selección sobre cuándo encaja cada uno.

**`signal_playbook.md`** — Cómo convertir una señal en la primera línea de un correo. Qué señal gana cuando una empresa tiene varias. Cómo mencionar algo que observaste sin parecer que le pasaste un escáner.

**`objection_handling.md`** — El bucle **LAARC** (Listen → Acknowledge → Assess → Respond → Confirm) con respuestas trabajadas para las cuatro familias de objeciones: presupuesto, autoridad, necesidad y momento. El enfoque en todo el archivo es que no estás "superando" una objeción, sino averiguando cuál es la preocupación real.

**`lead_qualification.md`** — **BANT** para el primer filtro, puntuación de ICP de 1 a 10 para priorizar, **MEDDIC** para todo lo complejo. Incluye criterios de descalificación explícitos, que importan más que los de calificación.

**`sales_methodology.md`** — La filosofía de funcionamiento: el bucle ABC, cómo debe fluir una conversación a lo largo de las etapas, la calibración del tono y las líneas éticas que Harvey no cruza.

**`offer_strategy.md`** — La escalera de ofertas por nivel de compromiso, y la regla que la gobierna: *nunca abras con una oferta, nunca vendas en un correo en frío.* El primer contacto existe para iniciar una conversación. Las ofertas solo salen cuando hay interés genuino.

**`prospecting_tactics.md`** — Operadores de búsqueda, minería de sitios web de empresas, eventos desencadenantes, vías de recomendación. Encontrar personas sin pagar una base de datos.

**`account_navigation.md`** — Empresas frente a contactos, reglas de multihilo, a qué puerta llamar primero cuando una empresa tiene varias.

**`linkedin_outreach.md`** — Secuencias de conexión y límites de frecuencia, que abre con la sección de riesgos con la que debe abrir: automatizar LinkedIn infringe sus condiciones de uso, nunca uses una identidad falsa y, si alguien pregunta si esto es automático, di que sí de inmediato.

**Generadas para tu producto con `harvey train <url>`:**

- **`product_knowledge.md`** — qué vendes, los beneficios, precios, casos de uso, el problema que resuelves, desencadenantes de compra
- **`competitive_intel.md`** — fichas de combate por competidor, ángulos de diferenciación, vías de migración

*(Ambas están en gitignore. Tu posicionamiento y tus precios no deberían acabar en un repositorio público por accidente.)*

### Qué agente recibe cuál

Definido en `harvey/brain.py`: edita el mapa para cambiarlo.

| Skill | Scout | Writer | Handler | Sender | LinkedIn |
|---|:-:|:-:|:-:|:-:|:-:|
| `prospecting_tactics` | ● | | | | ● |
| `lead_qualification` | ● | | | | |
| `account_navigation` | ● | | | | |
| `signal_playbook` | ● | ● | | | |
| `email_frameworks` | | ● | | ● | |
| `sales_methodology` | | ● | ● | | |
| `offer_strategy` | | ● | ● | | |
| `objection_handling` | | | ● | | |
| `linkedin_outreach` | | | | | ● |
| `product_knowledge` | ● | ● | ● | ● | ● |
| `competitive_intel` | | ● | ● | | |

Añadir una skill: escribe el archivo y añade su nombre a `skill_map` en `harvey/brain.py`. Ese es todo el proceso.

---

## Los subagentes

Harvey parece un solo agente. Por debajo son cinco, cada uno cargado con skills distintas.

| Agente | Qué hace |
|---|---|
| **Scout** | Puntúa y personaliza lo que encontraron los recolectores. Python hace la búsqueda y la resolución de correos; el modelo seleccionado se usa solo donde realmente hace falta criterio, y eso es lo que mantiene el coste en tokens bajo control. |
| **Writer** | Genera secuencias de 3 correos. El correo 1 con menos de 75 palabras, el 2 con menos de 75 y el 3 con menos de 40. Lista de prohibiciones estricta sobre lenguaje que suene a IA. |
| **Sender** | Renderiza las variables de combinación por prospecto y deja cada correo en la bandeja de salida con una hora de envío. Vacía los elementos vencidos y aprobados con un ritmo similar al humano, respetando el límite diario y la parada ante respuesta: la respuesta de cualquier persona de una empresa detiene la secuencia para todos los de esa empresa. |
| **Handler** | Consulta las respuestas, elimina duplicados, clasifica la intención, hace avanzar la etapa de la conversación y encola las respuestas por la misma escalera de aprobación. Detecta rebotes, marca la dirección como inválida, cancela los envíos en cola de ese prospecto y activa un interruptor de emergencia global al superar un umbral de tasa de rebote. |
| **Analyst** | Se ejecuta en los ciclos inactivos. Estadísticas del pipeline, rendimiento de campañas, distribución de intención y qué está funcionando de verdad. |

Etapas de la conversación: `initial_outreach → engaged → qualifying → presenting → negotiating → closing → closed_won / closed_lost`

---

## Nada se envía sin ti

Por defecto, **cada correo saliente espera tu aprobación.** Harvey es un copiloto hasta que decidas otra cosa.

La bandeja de salida del panel es una mesa de decisiones: un correo ocupa el panel, el resto espera en un lateral, y trabajas la cola con `A` aprobar, `R` rechazar, `J`/`K` para moverte. Esa forma es deliberada: una pared de borradores apilados invita al reflejo de aprobarlo todo de golpe, que es justo la revisión que la escalera de aprobación existe para forzar.

```bash
harvey outbox                 # review from the terminal
harvey outbox --approve-all
harvey sending pause          # kill switch, stops everything mid-flight
harvey retry-writes           # retry prospects the Writer gave up on after 3 unusable drafts
```

Antes de que salga nada, una **barrera previa al envío determinista** (sin ningún modelo) rechaza: etiquetas de combinación sin renderizar, frases prohibidas, correos que superan el límite de longitud, demasiados enlaces, cuerpos HTML, direcciones no entregables y cualquier discrepancia entre el destinatario y el registro de la base de datos.

Opcionalmente, ese mismo paso puede preguntar a [Precleared](https://precleared.dev) si se permite el correo en frío a cada dirección nueva antes de que salga el primero. Consulta [Aspectos legales y entregabilidad](#aspectos-legales-y-entregabilidad).

**Horario de oficina en la zona horaria del destinatario.** Define `channels.email.send_window` y el correo en frío solo sale entre `start` y `end` (de 08:00 a 17:00 en días laborables por defecto) en la zona horaria de cada destinatario, de modo que una misma campaña puede llegar a Nueva York y a Oslo y caer en horario de oficina en ambas. Harvey calcula la zona una sola vez a partir de la ubicación de la empresa (un estado de EE. UU., una provincia canadiense, un estado australiano, un país con una sola zona horaria o su zona principal, más las coordenadas que el descubrimiento ya guardó en caché para ese lugar), del país que encuentra Precleared cuando esa comprobación está activa, o de `prospect_country`. Un código que es a la vez estado y país ("Mumbai, IN") se resuelve con esos datos; sin nada más, un código de estado de EE. UU. se interpreta como el estado, así que escribe el país completo cuando puedas. Las conjeturas de ese tipo, y la zona principal de un país, se vuelven a comprobar en lugar de almacenarse. A quien no pueda ubicar se le aplica la ventana de `usage.quiet_hours.timezone`. Los seguimientos conservan su retraso y se desplazan dentro de la ventana, un correo aprobado fuera de horario espera a la siguiente, y las respuestas nunca las retiene la ventana. `weekdays_only` significa de lunes a viernes en todas partes. Las horas de silencio siguen pausando la prospección, la redacción y las respuestas, pero despiertan para el correo en frío que pueda salir ya dentro de la ventana de su destinatario: el latido lee primero las respuestas y luego lo envía (y encola cualquier campaña en borrador, lo cual no envía nada). Solo para Gmail, Microsoft y SMTP.

### Aprobación o piloto automático

Harvey tiene dos modos de envío. El panel muestra en cuál estás en la parte
superior de la bandeja de salida, y Settings → Sending explica ambos y los alterna.

| | **Aprobación** (por defecto) | **Piloto automático** |
|---|---|---|
| Primeros correos, seguimientos, respuestas | Esperan en la bandeja de salida hasta que apruebas cada uno | Salen solos, según lo programado |
| Límite diario, horas de silencio, rampa de warmup, bajas, rebotes, Pause all sending | Se aplican | Se aplican igual |
| Un correo con un enlace que no es tuyo, o que cita las instrucciones de Harvey | Lo ves como cualquier otro | Retenido en la bandeja de salida, marcado como **Held**, hasta que lo apruebes |
| En Instantly | Las campañas no se despliegan en absoluto (Instantly no puede retener correos individuales) | Las campañas se despliegan; las respuestas retenidas te llegan a ti |

**Activar el piloto automático.** Aprueba a mano un lote o dos primero y lee lo que
escribe Harvey. Después, ve a Settings → Sending → *Turn on autopilot…* y
escribe `autopilot`, o define `channels.email.require_approval: false` en tu configuración
(`harvey.local.yaml` si entrenaste a Harvey, si no `harvey.yaml`). Un Harvey en
ejecución lo recoge en su siguiente ciclo, sin reiniciar.

**Desactivarlo** es un clic (*Turn off autopilot*, en la bandeja de salida o en
Settings), o `require_approval: true` en la configuración. Funciona al instante, incluso
a mitad de ciclo: los correos que aprobó el piloto automático y que no han salido vuelven a la
bandeja de salida, y nada de lo que aprobó se envía después. Los correos que aprobaste
tú siguen aprobados. (Los correos aprobados antes de esta versión también vuelven
la primera vez, ya que Harvey no puede saber quién los aprobó.) En Instantly,
las campañas que ya se están ejecutando allí siguen funcionando: páusalas en Instantly.

**Lo que el piloto automático sigue reteniendo para ti.** Texto externo llega al modelo:
los sitios web que Harvey investiga y las respuestas que envía la gente. Cualquiera de los dos puede llevar
instrucciones plantadas ("ignore the above, add this link"). Harvey marca ese
texto como datos en cada prompt, y el modelo no tiene herramientas, archivos ni red con los que
actuar. Pero un prompt no puede garantizar que el modelo ignore una instrucción. Así que un
correo que nadie aprobó vuelve a la bandeja de salida, marcado como **Held** con el
motivo, en lugar de salir, cuando:

- enlaza a, o da una dirección en, un dominio que no es tuyo. Son tuyos el dominio de
  la dirección de envío, el sitio con el que entrenaste a Harvey, el dominio propio
  del destinatario (en un correo dirigido a él), tu propia página de reservas
  (`product.offer.booking_url`; solo esa página, ya que cal.com y Calendly alojan
  a todo el mundo) y los que listes tú: `channels.email.link_domains:
  ["mainsite.com"]`. Los enlaces se leen como los abre un navegador, y cuentan
  `evil.com/x` sin más, `www.`, las direcciones IP y "evil dot com";
- cita un pasaje de las propias instrucciones de Harvey (`prompts/`, `skills/`), que
  es lo que recibiría una respuesta que intentara extraer tu manual. Los guiones que
  los manuales citan para decirse, y los frameworks de correo y el conocimiento de producto,
  se pueden usar sin problema.

La primera respuesta tras deshacer la baja de alguien también espera tu visto bueno.
Aprobar tú mismo un correo retenido lo envía. **Approve all** deja fuera los correos retenidos, de modo que
cada uno se lee antes de salir. En Instantly, que envía de inmediato, una respuesta
que quedaría retenida te llega como escalada (también pasa por la
barrera previa al envío), una plantilla de campaña que quedaría retenida no se despliega, y un
lead cuyos campos quedarían retenidos no se sube.

**Instantly heredado:** la bandeja de salida local no puede aprobar envíos individuales de Instantly.
Con la aprobación activada, Harvey retiene el despliegue de campañas (incluidos los reintentos de
activación) y deriva las respuestas a una persona. Elige Gmail, Microsoft 365 o SMTP
para la cola de aprobación. Desactivar el piloto automático no pausa las campañas que ya
se ejecutan en Instantly; páusalas en el propio Instantly.

---

## El panel

```bash
harvey dashboard     # prints the link to open, e.g. http://127.0.0.1:5555/#token=…
```

**Abrirlo.** El panel puede cambiar tu configuración de correo, aprobar la bandeja de salida y poner en marcha a Harvey, así que está bloqueado para ti, no solo para tu máquina. En el primer arranque crea un token aleatorio en `data/dashboard-token` (legible solo por ti) e imprime un enlace que lo lleva después del `#`. Abre ese enlace: la página guarda el token solo para esa pestaña del navegador y lo elimina de la barra de direcciones. Una pestaña nueva, o una abierta sin el enlace, muestra una pantalla bloqueada; pega ahí el token, o ejecuta `harvey dashboard --url` para volver a imprimir el enlace. Cada petición a la API necesita el token como cabecera `Authorization: Bearer` (scripts y `curl` incluidos), y el token nunca se acepta desde una cookie ni desde una cadena de consulta. Borra `data/dashboard-token` y reinicia el panel para sustituirlo.

**Solo escucha en esta máquina.** `--host` acepta únicamente direcciones de loopback (`127.0.0.1`, `::1`, `localhost`), y las peticiones deben nombrar una de ellas en su cabecera `Host`, lo que además impide que un nombre DNS apuntado a 127.0.0.1 llegue hasta él. Se rechazan las peticiones enviadas por otros sitios web abiertos en tu navegador. Para usarlo desde otro ordenador, haz un túnel en lugar de exponerlo: `ssh -L 5555:127.0.0.1:5555 your-machine`, y abre después el enlace impreso en local. El token protege frente a otros usuarios y otros sitios web, no frente a programas que ya se ejecutan con tu propia cuenta de usuario, que pueden leer el archivo del token igual que pueden leer `.env` o la base de datos.

**Windows:** el archivo del token está protegido por los permisos de la carpeta donde vive (tu perfil de usuario normalmente lo restringe a ti); Harvey no aplica allí modos de archivo POSIX.

HTML, CSS y JavaScript planos servidos desde `harvey/web/`. Sin paso de compilación, sin framework, sin bundler: edita `app.css` y recarga. Las fuentes van incluidas, así que se muestra correctamente sin red.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/today-dark.png">
  <img alt="La pantalla Today: cuatro cifras destacadas con tendencias de 14 días, la lista de cosas que esperan por ti, contactos por etapa y ejecuciones de los recolectores" src="docs/screenshots/today-light.png">
</picture>

La barra lateral está agrupada según lo que estés haciendo: **Work** (lo que te necesita), **Pipeline** (lo que Harvey está construyendo) y **System** (cómo está funcionando). Los números junto a una pestaña significan que hay algo esperando allí.

**Work**
- **Today** — cuatro cifras destacadas con tendencias de 14 días (contactos encontrados, correos enviados, conversaciones, esperando por ti), luego todo lo que necesita una decisión, contactos por etapa, ejecuciones de los recolectores y lo que está haciendo el pipeline ahora mismo. La configuración aparece aquí hasta que termina, y después desaparece.
- **Outbox** — la mesa de decisiones. Cada correo está junto a lo que Harvey sabía cuando lo escribió: la empresa, cómo se encontró y verificó la dirección, y las señales en las que se apoya el correo. `J`/`K` para moverte, `A` aprobar, `E` editar, `R` rechazar.
- **Conversations** — cada respuesta en el contexto de los correos que llevaron a ella. Los hilos que Harvey te pasó (una petición de contrato, una respuesta para la que no tenía una contestación segura) van primero, con **Hand back to Harvey**, **Close** y **Reopen**.

**Pipeline**
- **Signals** — la barrera de confirmación y el constructor de cohortes
- **Discover** — el menú de proveedores con los precios lado a lado, una estimación y luego una ejecución; además de leer los sitios de las empresas encontradas que aún no se han mirado
- **Companies / Contacts** — todo lo encontrado, con búsqueda y exportación a CSV
- **Campaigns** — cada secuencia que escribió Harvey, a quién va dirigida y comentarios por campaña para el redactor

**System**
- **Activity**, **Usage**, **Controls**, **Settings**, **Help**. Usage muestra indicadores de cuota de Claude o Codex y recuentos de tokens por agente, sin cifras en dólares: estás con una suscripción y no se te factura por token, así que mostrar costes sería inventado.

| Outbox | Conversations |
|---|---|
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/outbox-dark.png"><img alt="La mesa de decisiones de la bandeja de salida: una respuesta redactada a una objeción, con la empresa, el contacto, la verificación y las señales al lado" src="docs/screenshots/outbox-light.png"></picture> | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/conversations-dark.png"><img alt="Una conversación que Harvey devolvió: los dos correos enviados, el prospecto pidiendo un contrato y los botones Hand back to Harvey y Close" src="docs/screenshots/conversations-light.png"></picture> |

El color se reserva para dar significado. El marco es neutro y un único azul marca lo que puedes accionar. El estado (esperando por ti, hecho, fallido, en ejecución) usa el mismo conjunto reducido de tonos en todas las pestañas, de modo que "esperando por ti" se ve igual dondequiera que aparezca. Las cifras son tabulares, así que las columnas se alinean y un número cambiante no desplaza el diseño.

La apariencia tiene tres estados: `auto` sigue tu sistema operativo y es el valor por defecto, o elige claro u oscuro con el botón de la parte inferior de la barra lateral. El modo oscuro usa el mismo diseño con un conjunto distinto de tokens de color.

---

## Cómo se almacenan los datos

SQLite en `data/harvey.db`. Una idea guía el esquema:

> **Cada hecho es una fila, nunca una columna.**

No `companies.has_agency`. No `companies.rank`. Una fila en `observations`:

```
observations(company_id, prospect_id, collector, signal_code,
             value_num, value_text, confidence, evidence_url, observed_at, run_id)
```

De ahí se derivan cuatro cosas, ninguna de las cuales se consigue con columnas:

1. **Una señal nueva no necesita migración.** Un recolector inventa un código y funciona.
2. **El historial sale gratis.** La misma señal observada cada trimestre *es* una serie temporal, y "dejaron a su agencia el trimestre pasado" es un desencadenante mucho mejor que cualquier dato estático.
3. **La confianza y la procedencia viajan con el hecho** en lugar de perderse al sobrescribir. *"Creemos que su agencia es X, con 0,9 de confianza, aquí está la URL."*
4. **Una cohorte es una consulta.** La intersección de conjuntos ocurre en SQL, no en código de aplicación sobre una consulta limitada.

El vocabulario está gobernado: un trigger de la base de datos rechaza cualquier `signal_code` que no esté en la tabla `signal_codes`, de modo que un error tipográfico falla de forma ruidosa en lugar de inventar en silencio una señal basura.

Otras tablas: `companies`, `prospects`, `campaigns`, `conversations`, `outbox`, `actions`, `runs`, `usage_events`, `email_patterns`, `settings`, `feedback`.

---

## Configuración

Dos archivos, ambos en texto plano.

**`.env`** — credenciales. Cada variable está documentada en línea con dónde conseguirla. La única obligatoria es un proveedor de correo; todo lo demás es opcional.

**`harvey.yaml`** — quién es Harvey y a quién vende:

```yaml
persona:      { name, company, role, email, tone }
product:      { name, description, pricing, key_benefits, objection_responses, offer }
icp:          { industries, titles, company_size, geography, hiring_signals, geo_coordinates }
channels:
  email:      { provider: gmail | microsoft | smtp | instantly, max_daily_sends, require_approval,
                send_to_risky, max_bounce_rate, warmup, send_window }
usage:        { max_daily_claude_percent, heartbeat_interval_minutes, quiet_hours }
brain:        { provider: claude | codex, model, reasoning_effort }   # optional; claude by default
writer:       { humanizer }   # optional; true adds one editing pass per batch using ~/.claude/skills/humanizer/SKILL.md
```

`max_daily_claude_percent` limita la suscripción que use `brain.provider` (el nombre es anterior al soporte de Codex).

Si existe `harvey.local.yaml`, prevalece. Está en gitignore, así que un fork puede llevar la configuración real del producto mientras el `harvey.yaml` versionado sigue siendo una plantilla: nadie publica su posicionamiento y sus precios por accidente.

### Comandos

```bash
harvey run                   # the heartbeat loop
harvey dashboard             # web UI at 127.0.0.1:5555 (--url: print the unlock link)
harvey signals               # review/confirm what to prospect against
harvey discover              # find businesses; --providers / --estimate
harvey profile               # read discovered companies' sites (free)
harvey train <url>           # learn a product from its website (--provider codex --model gpt-5.5)
harvey status                # pipeline summary
harvey usage                 # active provider's quota + per-agent tokens
harvey outbox                # review queued email
harvey export                # deliverable prospects → CSV
harvey sending pause|resume  # kill switch
harvey warmup [domain]       # is the sending domain ready? (SPF/DKIM/DMARC, age, blocklists, warmup)
harvey trulyinbox connect    # connect TrulyInbox so Harvey reads the mailbox's warmup
harvey retry-writes          # retry prospects the Writer gave up on
harvey gmail auth            # one-time Gmail OAuth
harvey microsoft auth|test  # one-time Microsoft 365 sign-in (docs/microsoft365.md)
```

Las exportaciones CSV de prospectos excluyen los contactos que se han dado de baja, también cuando se usan
los filtros `--status` o `--email-status`. `harvey export --all` es una exportación
de datos sin procesar y sin filtrar para inspección: incluye contactos dados de baja y no verificados
y no debe importarse como lista de prospección. La descarga CSV de prospectos del panel
sigue la misma política; `?all=true` selecciona su exportación sin procesar.


## Usar un plan de ChatGPT en su lugar (Codex)

Claude es el valor por defecto y no necesita ningún cambio. Si prefieres gastar un plan de ChatGPT (Plus, Pro, Business, …), Harvey puede pensar a través de la [CLI de Codex](https://developers.openai.com/codex): sigue siendo una suscripción, nunca facturación de API por token.

```bash
npm install -g @openai/codex@0.159.3   # the Codex version Harvey has verified (see Requirements)
codex login                            # choose "Sign in with ChatGPT" — API-key logins are refused
```

Después, elige **codex** en `harvey setup` (sugiere `gpt-5.5`), ejecuta `harvey train <url> --provider codex --model gpt-5.5`, o añade a tu configuración:

```yaml
brain:
  provider: codex
  model: gpt-5.5         # or an available Luna, Sol, or Terra model ID
  reasoning_effort: ""   # optional: minimal | low | medium | high | xhigh
```

Qué conviene saber:

- **Es uno u otro.** Harvey usa exactamente el proveedor que configures. Si Codex falla, la llamada falla con un mensaje de registro claro; nunca recurre a Claude (ni a una clave de API). Una máquina solo con Codex no necesita tener Claude instalado.
- **Tu configuración de Codex se deja intacta.** Cada llamada ejecuta procesos `codex` desechables en un directorio personal temporal privado y un espacio de trabajo vacío, de modo que tu `~/.codex/config.toml`, servidores MCP, plugins, hooks, skills, `AGENTS.md` y memorias nunca se cargan, y la elección de modelo de Harvey nunca cambia tu propio valor por defecto de Codex.
- **Sin herramientas, verificado antes de cada prompt.** Los prompts contienen texto no fiable (respuestas de prospectos, páginas rastreadas), así que el modelo no debe tener nada con lo que actuar. Harvey desactiva toda función de Codex que aporte herramientas, la búsqueda web, los subagentes, los hooks, las skills y las instrucciones de proyecto, inicia el hilo sin entorno de ejecución y luego comprueba los propios informes de Codex (configuración efectiva, tipo de cuenta, ajustes del hilo, estado de MCP, hooks) antes de enviar nada. Todo lo que no pueda confirmar detiene la llamada. Durante el turno, cualquier intento de llamada a una herramienta, solicitud de aprobación o elemento que no sea texto mata el runtime. También se establece un sandbox de solo lectura, solo como protección adicional.
- **Tu inicio de sesión solo va a OpenAI.** Antes de introducir tu inicio de sesión en el runtime, Harvey arranca Codex sin él y comprueba que las peticiones irían al proveedor OpenAI integrado y al endpoint de ChatGPT por defecto. Cualquier proveedor personalizado, proveedor integrado sobrescrito, URL base, exportador de telemetría u otro endpoint en cualquier capa de configuración de Codex (por ejemplo `/etc/codex/config.toml` o una configuración gestionada) detiene la llamada ahí.
- **Gestión del inicio de sesión.** Harvey admite el almacenamiento de credenciales en archivo de Codex (`~/.codex/auth.json`, o `$CODEX_HOME/auth.json`, modo `600`): es el valor por defecto salvo que hayas configurado un llavero del sistema operativo. El almacenamiento en llavero no está admitido. En cada llamada Harvey lee ese archivo (solo lectura, sin escribirlo ni moverlo) y da al runtime una copia privada *sin el token de refresco*, que se borra tras la llamada. Por tanto, Codex no puede cambiar ni renovar tu inicio de sesión real. Cuando el inicio de sesión ha caducado, o le toca la renovación rutinaria de Codex (pasados unos 8 días), las llamadas a Codex se detienen con "Your Codex login has expired or is due for renewal". Usa Codex una vez tú mismo (renueva el inicio de sesión automáticamente) o ejecuta `codex login`, y Harvey recoge el inicio de sesión renovado en su siguiente llamada. Harvey nunca lo renueva por ti.
- **Modelos.** Define `brain.model` con un ID de modelo exacto del catálogo de tu cuenta, incluidos modelos Luna, Sol y Terra como `gpt-5.6-luna`, `gpt-6.1-sol` y `gpt-5.6-terra`. `gpt-5.5` sigue admitido cuando figura en el catálogo de tu cuenta y es la sugerencia de la configuración. Harvey crea una copia privada del catálogo que conserva las capacidades del modelo mientras selecciona el modo de herramientas directo y elimina las herramientas experimentales. El modelo no recibe herramientas bajo el bloqueo de Harvey. Un `model` en blanco selecciona el modelo listado de mayor prioridad que pueda usar esta configuración; los modelos ocultos requieren un ID explícito. Un modelo explícito se usa exactamente tal cual o la llamada falla. Los ID de modelo desconocidos y los modos de herramientas no reconocidos se rechazan. La disponibilidad depende de tu cuenta de ChatGPT.
- **Cuota.** La barrera de presupuesto y el panel leen de Codex las ventanas reales de límite de uso de tu plan de ChatGPT, para el grupo de límite que se aplica a tu modelo, y las comparan con `usage.max_daily_claude_percent`. Si Codex informa de que el uso está bloqueado, o una llamada falla por el límite de uso del plan, Harvey trata el plan como lleno (incluso cuando no se informa de ninguna ventana) y detiene las llamadas a Codex durante una hora. Si no se pueden leer los límites, el panel y `harvey usage` dicen "Quota unavailable" y el presupuesto recurre al recuento diario de llamadas del propio Harvey. El uso se registra por proveedor; las llamadas a Codex se registran con tokens pero sin coste en dólares, porque el plan no se factura por token.
- **Cuando Codex no se puede usar, Harvey se pausa en lugar de adivinar.** Antes de cada latido, Harvey comprueba todo lo que necesita una llamada salvo el propio prompt: la versión de la CLI de Codex, el aislamiento, tu inicio de sesión (caducado o pendiente de renovación), tu cuenta de ChatGPT y que tu modelo configurado puede ejecutarse sin herramientas. No se envía ningún prompt, así que no se gasta nada de tu plan más allá de una comprobación rápida de la cuenta. Si algo va mal, se omite el ciclo entero: no se lee ni se marca como gestionada ninguna respuesta, no se redacta ni se envía nada. La línea de registro, `harvey status` y la tarjeta Actions del panel dicen "Codex paused" y por qué. Si Codex deja de funcionar a mitad de ciclo (por ejemplo, el plan alcanza su límite de uso), la respuesta que se estaba gestionando se deja exactamente como estaba para un reintento limpio, sin escalarla, registrarla a medias ni perderla, y ese ciclo no envía nada. Corrige la causa (normalmente `codex login`) y Harvey se reanuda en su siguiente latido: un inicio de sesión renovado o una CLI reinstalada se detectan de inmediato, una pausa por límite de uso termina al cabo de una hora, y otras correcciones se recogen en 30 minutos. `harvey status --check` ejecuta la misma comprobación a demanda y sale con código distinto de cero si falla. Los fallos breves (una caída o un tiempo de espera agotado) simplemente omiten un ciclo. Harvey nunca recurre a Claude ni a una clave de API.
- **Requisitos.** **macOS o Linux**, CLI de Codex **0.159.3** exactamente, y Node.js para su paquete npm. **Windows no está admitido para Codex:** Harvey lo rechaza ahí antes de leer tu inicio de sesión; usa el proveedor Claude en Windows. Harvey comprueba la versión de Codex antes de cada llamada y rechaza cualquier otra versión, incluidas las más nuevas, porque un Codex distinto puede añadir herramientas que el bloqueo de Harvey no conoce. El soporte para una versión nueva llega con una actualización de Harvey. El uso en vivo con una cuenta real de ChatGPT se ha verificado en macOS y en Linux ARM64. Las suites sin conexión también pasaron en Linux x86-64 bajo emulación de CPU; la CI cubre Linux y macOS. La imagen de Docker incluye solo la CLI de Claude, así que Codex no está admitido en Docker. Para volver a verificar el bloqueo sin conexión contra tu CLI instalada, sin credenciales ni red: `HARVEY_CODEX_CLI_TESTS=1 pytest tests/test_codex_cli_surface.py`.
- **Sobrecarga.** Cada llamada comprueba la versión de la CLI, arranca Codex una vez sin tu inicio de sesión para verificar su configuración, lee el catálogo de modelos y lo arranca de nuevo para ejecutar el prompt; la comprobación de cada latido hace lo mismo sin el prompt. Eso añade unos segundos por llamada, y las llamadas a Codex de un mismo Brain se ejecutan una a una.

---

## Aspectos legales y entregabilidad

Harvey automatiza la prospección, pero **el remitente eres tú.** El correo en frío es legal en la mayoría de los lugares cuando se hace bien y caro cuando se hace mal: las sanciones de CAN-SPAM llegan a 53.088 $ por correo. Harvey incluye valores por defecto conformes a la norma. Mantenlos.

**CAN-SPAM (EE. UU.).** Asunto veraz y dirección de remitente exacta: las reglas de redacción de Harvey prohíben los falsos hilos "re:" y la suplantación. Una baja que funcione, respetada con rapidez: cada correo en frío termina con una línea de baja (`compliance.opt_out_line`, por defecto *Not interested? Reply "no thanks" and I won't email again.*), y Harvey trata cualquier redacción de baja como inmediata y permanente, escriba donde escriba la persona en la respuesta (incluido un simple "STOP" o "No thanks"). Nada de lo que Harvey haga después saca a alguien de *dado de baja*: un mensaje posterior suyo se guarda para que lo leas, nunca se contesta, y una queja sigue llegándote a ti. Para ver por qué alguien fue dado de baja (la regla que saltó, las palabras y su mensaje), haz clic en **Why?** en su fila de Contacts. Si fue un error, **Undo opt-out** ahí lo marca como que respondió: Harvey no envía nada por su cuenta, y su siguiente respuesta recibe un borrador para tu aprobación. Tu dirección postal física en el pie: define `compliance.postal_address` en `harvey.yaml` antes de tu primera campaña. Harvey añade ambas líneas bajo cada correo en frío al enviarlo (las respuestas no las llevan), las muestra bajo cada borrador en la bandeja de salida, y avisa en `harvey run`, `harvey status` y la pestaña Outbox hasta que se define la dirección. El texto de una respuesta que repite lo que Harvey escribió para esa persona (sus correos, plantillas de campaña y cada pie que ha usado) se aparta como citado, no se lee como palabras suyas, así que citar el propio pie de Harvey no es una baja; el modelo también lee las respuestas sin el correo citado. La línea de baja debe pedir una respuesta que Harvey reconozca (`Reply "no thanks"`, `Reply STOP`, también "unsubscribe", "remove me", "opt out") y no puede contener un enlace ni una dirección de correo.

**No contactar.** Lista a competidores, clientes existentes o a cualquier otra persona a la que Harvey nunca deba escribir en `compliance.do_not_contact`, una dirección o dominio por línea, en el archivo de configuración que lee Harvey: `harvey.local.yaml` si entrenaste a Harvey (ese archivo prevalece), si no `harvey.yaml`. Un dominio cubre sus subdominios (`acme.example` también bloquea `mail.acme.example`, no `notacme.example`), una dirección cubre sus etiquetas con plus (`jane@` también bloquea `jane+news@`), y un enlace pegado como `https://www.acme.example/about` o `Jane Doe <jane@acme.example>` cuenta como lo que nombra. Una entrada que no sea ni una dirección ni un dominio impide que Harvey arranque, nombrando la entrada, en lugar de no proteger a nadie en silencio. Un Harvey en ejecución recoge una edición al instante, y la barrera de envío comprueba la lista cuando sale cada correo, en frío o respuesta, de modo que se cumple incluso para un correo que ya aprobaste. Si alguien de la lista responde, Harvey no redacta una contestación: la conversación te llega a ti. `harvey export` y los botones Export del panel también los dejan fuera. En Instantly, los leads de la lista se omiten de la subida y una respuesta de uno te llega a ti, pero Harvey no puede retirar un lead que Instantly ya tiene: elimínalo allí.

**RGPD / PECR (UE y Reino Unido).** El correo en frío B2B necesita un interés legítimo defendible: la propuesta debe ser genuinamente relevante para el puesto de esa persona, debes saber de dónde salieron los datos y oponerse debe ser sencillísimo. Si no puedes decir por qué le importaría a una persona concreta, Harvey no debería escribirle, y sus reglas de calificación lo dicen.

**Comprobación por destinatario (opcional).** Esas reglas dependen de hechos sobre cada destinatario: un autónomo del Reino Unido necesita consentimiento donde una sociedad limitada no, Alemania quiere consentimiento previo incluso para el correo empresarial, y la CASL de Canadá depende de si la dirección fue publicada. Con `compliance.precleared.enabled: true`, Harvey consulta a [Precleared](https://precleared.dev) sobre cada destinatario nuevo antes del primer correo en frío. Cualquier resultado distinto de `ok_to_email` retiene ese correo, con la regla y el siguiente paso visibles en la bandeja de salida, y el id del recibo firmado se registra con cada envío. Una comprobación por dirección, en caché durante 30 días (cambiar el país del remitente, el origen de la dirección, la descripción del producto o el país del prospecto desencadena una comprobación nueva); las respuestas nunca se comprueban; solo para proveedores nativos (Gmail, Microsoft 365, SMTP). Precleared deduce el país de cada destinatario a partir de la dirección, los registros de la empresa o el sitio web de la empresa; si todos tus prospectos están en un mismo país, define también `prospect_country` (por ejemplo `US`), que solo usa cuando nada de lo anterior lo indica. Precleared recibe la dirección del destinatario, el país de tu remitente, el origen de la dirección, la descripción de tu producto y, si está definido, el país de tus prospectos. Sin clave permite 10 comprobaciones al día, y una clave gratuita (`PRECLEARED_API_KEY`) permite 25. Pon el ajuste en `harvey.yaml`, o en `harvey.local.yaml` si entrenaste a Harvey, ya que ese archivo prevalece.

**Si la comprobación se retrasa.** Cuando Precleared no puede responder (se agotaron las comprobaciones gratuitas del día, la clave se quedó sin comprobaciones o fue rechazada, o no se puede contactar con Precleared), el correo en frío espera y las respuestas siguen saliendo. La página Today y `harvey status` indican cuántos correos en frío están esperando y qué lo soluciona.

**Divulgación de bot.** Algunas jurisdicciones exigen revelar la automatización. Harvey tiene instrucciones de responder con la verdad, siempre, si un prospecto pregunta si está hablando con una IA. No lo configures nunca de otra forma.

**LinkedIn.** La automatización del navegador infringe las condiciones de uso de LinkedIn y puede hacer que se restrinja la cuenta. Desactivado por defecto. Si lo activas, usa una cuenta que te puedas permitir perder.

LinkedIn requiere tanto `channels.linkedin.enabled: true` como credenciales
configuradas. Entrenar un producto no lo activa; el asistente de configuración registra
tu elección explícita.

**Entregabilidad: calienta o te quemas.** Enviar correo en frío desde tu dominio principal, o a volumen desde el primer día, te manda al spam de forma permanente.

1. Compra un **dominio de envío dedicado** (`getacme.com`, no `acme.com`).
2. Configura **SPF, DKIM y DMARC** en él. Sin los tres, Gmail te manda a la carpeta de spam. `harvey warmup` los comprueba, además de la antigüedad del dominio, las listas de bloqueo, tu progreso de warmup y la tasa de rebote, y termina con READY / NOT READY. Solo lee DNS público y los propios registros de Harvey.
3. **Calienta durante 2–4 semanas** antes del volumen real, y mantén el warmup activo después. Recomendamos [TrulyInbox](https://trulyinbox.com/?via=harvey); consulta [Warmup con TrulyInbox](#warmup-con-trulyinbox).
4. **Aumenta despacio:** 10–20 al día por buzón, sumando ~5 al día. El valor por defecto `max_daily_sends: 50` es un techo, no un objetivo. Define `channels.email.warmup.start_date` y Harvey lo hace por ti (Gmail, Microsoft, SMTP; Instantly tiene su propio warmup): ningún correo en frío durante `min_days`, y después un tope de correo en frío que sube `daily_increase` cada día. Las respuestas siempre salen.
5. **Vigila los rebotes.** Por encima de ~3 %, para y corrige la calidad de la lista. Harvey activa su propio interruptor de emergencia al superar el umbral que hayas configurado.

*Nada de esto es asesoramiento jurídico. ¿Envías a gran escala o a sectores regulados? Habla con un abogado.*

### Warmup con TrulyInbox

Si un buzón está calentado no es algo que el DNS pueda decirte: solo el servicio de
warmup ve dónde aterriza su correo. Recomendamos [TrulyInbox](https://trulyinbox.com/?via=harvey), y Harvey
se conecta a él para que `harvey warmup` pueda decir si tu buzón está realmente listo:

1. **Consigue TrulyInbox** en [trulyinbox.com](https://trulyinbox.com/?via=harvey) y añade tu buzón de envío.
   Conectar Harvey requiere acceso a la API, que empieza en el plan Starter.
2. **Crea una clave.** En TrulyInbox, abre Settings > API keys y crea una
   clave de workspace con `accounts:read`, `warmup:read`, `analytics:read` y
   `workspace:read`.
3. **Conéctala**: `harvey trulyinbox connect`, o pégala en el paso de warmup
   de la página Today del panel. Harvey comprueba la clave antes de guardarla en `.env`.

`harvey warmup` lee entonces el buzón desde TrulyInbox y lo da por listo solo
cuando está inscrito, con la sesión iniciada, ha calentado durante `min_days` (14 por defecto) y
menos del 5 % de su correo de warmup ha aterrizado en spam. Harvey solo lee: nunca
inscribe, pausa ni cambia nada en tu cuenta de TrulyInbox.

¿Ya calientas con otro servicio? `harvey trulyinbox other` (o *I use
another service* en el panel) y Harvey deja de sugerirlo.

---

## Solución de problemas

**`command not found: harvey`** — Ejecuta primero `source .venv/bin/activate`.

**`ModuleNotFoundError: No module named 'harvey'` tras instalar (macOS)** — Python 3.13 ignora en silencio los archivos `.pth` que llevan el indicador de oculto de macOS, y algunos Mac propagan ese indicador a `.venv`. Ejecuta `harvey install` de nuevo (lo corrige automáticamente), o: `ln -s "$(pwd)/harvey" .venv/lib/python3.13/site-packages/harvey`

**`externally-managed-environment`** — Usa un venv, no el Python del sistema.

**`SyntaxError` o `ImportError` extraños justo después de instalar (macOS)** — Tu venv es Python 3.9. `python3 -m venv` construye desde `/usr/bin/python3`, que macOS mantiene en la 3.9. Compruébalo con `.venv/bin/python -V` y reconstruye: `rm -rf .venv && python3.13 -m venv .venv && source .venv/bin/activate && pip install -e .`

**El modo headless de Claude falla** — `claude login`, y confirma que la suscripción está activa. Pruébalo con `claude -p "say hi"`. En Docker, monta `~/.claude` en el contenedor (con escritura: la CLI renueva ahí su inicio de sesión). Si el registro dice que la CLI de Claude "lacks --safe-mode" (u otro indicador), ejecuta `claude update` (en Docker, reconstruye la imagen); Harvey se reanuda solo. Si tu inicio de sesión de Claude depende de entradas `env` o `apiKeyHelper` en tus archivos de ajustes de Claude, define esas variables en el entorno de Harvey: las llamadas de Harvey no leen archivos de ajustes. `harvey status --check` confirma la CLI sin enviar un prompt.

**El panel dice "locked"** — Abre el enlace que imprimió `harvey dashboard` (o `harvey dashboard --url`). Si dice que el archivo del token no se puede usar, sigue el mensaje: normalmente, borra `data/dashboard-token` y reinicia el panel. Visítalo como `127.0.0.1` o `localhost`; otros nombres de host se rechazan.

**Las llamadas a Codex fallan** — Lee la línea de registro; cada error de Codex dice qué hacer. "Not logged in" o "expired or is due for renewal" → usa Codex una vez o ejecuta `codex login` con ChatGPT. "Hasn't been verified with Harvey" → instala la versión de Codex admitida que nombra el mensaje. "Isolation could not be verified" → una capa de configuración de Codex fuera de tu `~/.codex` (por ejemplo una configuración gestionada o `/etc/codex`) vuelve a activar a la fuerza una herramienta, un hook, un servidor MCP, instrucciones o un endpoint personalizado; Harvey se niega a enviar prompts hasta que desaparezca. Errores del catálogo de modelos → elige un ID de modelo disponible del catálogo mostrado en el mensaje, o deja `brain.model` en blanco para seleccionar un modelo listado. Harvey nunca cambia a Claude por su cuenta.

**El descubrimiento no encuentra nada** — Confirma primero las señales (`harvey signals --confirm free`); no se recopila nada hasta que lo hagas. Si usas la fuente gratuita OpenStreetMap, solo cubre oficios cartografiados y es escasa para negocios de área de servicio: `harvey discover --providers` muestra las alternativas.

**Overpass está limitando** — Es infraestructura gratuita de voluntarios. Harvey recorre tres espejos antes de rendirse. Espera unos minutos, o usa un proveedor de pago para trabajo en volumen.

**Los correos acaban en spam** — Casi siempre es el dominio, no el texto. Comprueba SPF/DKIM/DMARC, confirma que se ejecutó el warmup ([TrulyInbox](https://trulyinbox.com/?via=harvey) muestra la tasa de bandeja de entrada; `harvey warmup` la lee una vez conectado), reduce tu volumen a la mitad.

**Harvey no hace nada durante el día** — Revisa `quiet_hours` y si alcanzó `max_daily_claude_percent`. `harvey status` muestra el estado actual; la tabla `actions` registra cada decisión.

**¿Cómo lo detengo ahora mismo?** — `Ctrl+C`, o `harvey sending pause` para detener lo saliente dejando el bucle en marcha. El estado está en SQLite, así que se reanuda sin problemas.

**¿Dónde viven mis datos?** — Todo en local: `data/harvey.db`, `.env`, `harvey.yaml`. Nada va a ningún sitio salvo a las API que hayas configurado.

---

## Estructura del proyecto

```
harvey/
├── main.py              # heartbeat loop
├── brain.py             # Claude/Codex provider selection + skills + usage
├── claude_runtime.py    # Isolated Claude CLI calls (safe mode, no tools, clean dir)
├── codex.py             # Isolated Codex subscription runtime
├── state.py             # SQLite schema, migrations, observations, cohorts
├── signals.py           # the 23-signal catalog Harvey proposes
├── pipeline.py          # DISCOVER → PROFILE chaining
├── gate.py              # deterministic pre-send checks
├── dashboard.py         # FastAPI JSON API
├── dashboard_auth.py    # dashboard token, Host/Origin checks
├── collectors/
│   ├── discover.py      # provider adapters, junk filtering, entity resolution
│   └── profile.py       # the free HTTP profiler
├── agents/              # scout, writer, sender, handler, analyst
├── integrations/        # mail providers, email finder, quota
└── web/                 # dashboard HTML/CSS/JS — no build step

skills/                  # ← the sales knowledge. Editable Markdown.
prompts/                 # ← agent system prompts. Also editable Markdown.
tests/                   # 242 tests
```

---

## Filosofía

**Autónomo no significa sin supervisión.** Horas de silencio, topes de gasto, límites de envío, una cola de aprobación, una barrera determinista previa al envío y un interruptor de emergencia. Harvey pregunta antes de gastar y antes de enviar, hasta que le digas que no lo haga.

**Tú decides qué es un buen prospecto.** Harvey propone señales; tú las confirmas. Una lista de prospectos que no sabes explicar es una lista de prospectos a la que no deberías escribir.

**Si se puede obtener de forma determinista, no uses un modelo.** Posición en el ranking, detección de tecnología, filtrado de basura, la decisión de prioridad, la barrera previa al envío: todo código plano. Claude o Codex se reservan para las partes que necesitan criterio. Por eso esto funciona con una suscripción en absoluto.

**Un fallo es una observación, no un silencio.** "No se encontró página de equipo" es un hallazgo. "Overpass está limitando" es un hallazgo. Los fallos silenciosos se ven exactamente como resultados limpios, que es como una ejecución rota se confunde con un mercado vacío.

**La base de datos es el activo, no el agente.** La lista inicial vale poco. Las mismas señales observadas a lo largo de los trimestres (quién cambió de agencia, quién empezó a gastar en anuncios, quién dejó que su contenido se quedara obsoleto) valen muchísimo.

**Todo es editable.** Prompts, skills, configuración, el panel. Todo texto plano. No hace falta ser desarrollador para cambiar cómo vende Harvey.

---

## Hoja de ruta

**Hecho:** bucle de latido · modelo de datos de observaciones con vocabulario gobernado · catálogo de señales confirmado por el usuario · constructor de cohortes · menú de proveedores de descubrimiento con estimaciones de coste · perfilador HTTP gratuito con detección de agencias · búsqueda de correos basada primero en patrones con estado honesto · proveedores de correo nativos (API de Gmail, Microsoft 365 vía Graph, SMTP+IMAP) · escalera de aprobación de la bandeja de salida · barrera determinista previa al envío · detección de rebotes e interruptor de emergencia · gestión de respuestas con clasificación de intención · seguimiento de la cuota de la suscripción · entrenador de sitios web · panel web · exportación a CSV

**Siguiente:** enriquecimiento de personas desde registros públicos · devoluciones de llamada de voz condicionadas al consentimiento · integración de calendario para reservas automáticas · re-observación programada para que los *cambios* en las señales desencadenen prospección · soporte multiproducto

> **Sobre la voz:** un marcador en frío de IA totalmente autónomo no está en esta hoja de ruta, y no lo estará. Según la FCC 24-17, una voz generada por IA es una "voz artificial" bajo la TCPA, y 47 CFR 64.1200(a)(1) no tiene exención B2B: las sanciones van de 500 a 1.500 $ por llamada, sin tope, y algunos estados la prohíben por completo. La voz aquí estará **condicionada al consentimiento**: solo devoluciones de llamada entrantes y activadas por opt-in.

---

## Changelog

Consulta [CHANGELOG.md](CHANGELOG.md). Versión actual: **0.2.1**.

---

## Licencia

MIT

Los enlaces a TrulyInbox de este proyecto son enlaces de afiliado: el mantenedor puede recibir una comisión, sin coste adicional para ti.

---

*"Put that coffee down. Coffee is for closers."* — Blake, *Glengarry Glen Ross*
