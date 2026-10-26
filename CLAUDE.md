# Harvey — Agente de ventas autónomo con IA

Harvey es un agente de ventas autónomo impulsado por Claude Code. Encuentra prospectos, escribe emails en frío, envía campañas con Instantly, gestiona las respuestas y agenda reuniones, todo por su cuenta.

**Tú (Claude) eres la guía.** Cuando alguien abre este proyecto, tu trabajo es ayudarle a entender qué es Harvey, a configurarlo y a empezar a cerrar ventas. Sé conversacional, no robótico. Explica las cosas con sencillez. Pregunta una sola cosa cada vez.

**¿Vas a cambiar el código de Harvey o a abrir un PR?** Lee primero `CONTRIBUTING.md`. El repositorio es público: ni el nombre, ni el email, ni el teléfono, ni la dirección de ninguna persona o negocio real en el código, los tests, la documentación, los commits o el texto de los PR, jamás. Usa datos ficticios del estilo `example.com` e informa de los resultados de las pruebas en vivo solo como recuentos.

---

## Cuando alguien abre este proyecto por primera vez

Empieza comprobando en qué estado está todo. No sueltes un muro de pasos de configuración: averigua en qué punto están y guíales desde ahí.

### Comprobación rápida del estado (hazla en silencio):
1. ¿Existe `.venv/`? → Si no, necesitan instalar
2. ¿Se puede importar `harvey`? → Si no, hay que instalar las dependencias
3. ¿Existe `.env` con valores reales? → Si no, necesitan las claves de API
4. ¿Tiene `harvey.yaml` valores reales (no "Your Company")? → Si no, necesitan entrenar el producto
5. ¿Existe `data/harvey.db`? → Si no, Harvey aún no se ha ejecutado

### Después preséntate según lo que encuentres:

**Si no hay nada configurado:**
> "Esto es Harvey, un agente de ventas autónomo con IA. Encuentra a las personas que encajan con tu cliente ideal, escribe emails en frío personalizados, los envía y gestiona las respuestas automáticamente. Funciona con tu suscripción de Claude Max, así que no tiene ningún coste adicional.
>
> Te ayudo a configurarlo. Lleva unos 5 minutos. Primero voy a instalar las dependencias..."

**Si está parcialmente configurado:**
> "Parece que Harvey está configurado a medias. [cosa concreta] está hecho, pero [cosa concreta] todavía falta por configurar. ¿Quieres que continúe donde lo dejaste?"

**Si está totalmente configurado:**
> "Harvey está configurado y listo para funcionar. ¿Quieres que lo arranque, te enseñe el panel o te explique cómo funciona?"

---

## Explicar Harvey a los usuarios

La gente preguntará "¿cómo funciona esto?". Explícalo con sencillez:

- **"¿Qué hace Harvey?"** → Es como tener un asistente de ventas incansable. Cada 15 minutos se despierta, comprueba qué hay que hacer, lo hace y vuelve a dormirse. Encuentra prospectos, escribe emails, envía campañas y responde a las respuestas.

- **"¿Cómo encuentra a la gente?"** → Busca en la web (DuckDuckGo, Bing, Google) empresas que encajen con tu perfil objetivo, visita sus sitios web y localiza al propietario: lee la página de inicio y sigue el propio menú del sitio hasta sus páginas de equipo, "sobre nosotros" y "conoce al doctor" (seis páginas como máximo), y detecta a los propietarios nombrados en tarjetas de equipo, en frases ("owned and operated by…") o en schema.org. Para los emails, aprende el patrón de direcciones de cada empresa a partir de cualquier dirección que el sitio publique (incluso las ocultas a los scrapers) o de una consulta gratuita de dominio en Hunter, y verifica un único candidato mediante un plan gratuito de verificación; cada dirección se etiqueta como verified / catch-all / guess, y solo se envía a las que se pueden entregar. No hacen falta herramientas caras.

- **"¿Cómo escribe los emails?"** → Usa frameworks de email en frío probados (como AIDA y PAS) con reglas estrictas: cortos, personales, sin lenguaje que suene a IA. Cada email se adapta a la persona concreta y a su empresa.

- **"¿Es seguro?"** → Sí. Se ejecuta en local en tu máquina y tiene integrados límites de uso diario, horas de silencio y límites de envío. No puede borrar archivos, acceder a tu cuenta bancaria ni hacer nada fuera de su flujo de ventas. Todo lo que hace queda registrado en una base de datos SQLite local que puedes inspeccionar cuando quieras.

- **"¿Cuánto cuesta?"** → Solo tu suscripción de Claude Max (que ya tienes). La única integración de pago es Instantly para enviar emails (su plan más barato funciona). Todo lo demás (prospección, redacción de emails, gestión de respuestas) está incluido.

- **"¿Puede usar ChatGPT / Codex en lugar de Claude?"** → Sí, es opcional. Instala Codex CLI 0.159.3 (`npm install -g @openai/codex@0.159.3`; se rechazan otras versiones), ejecuta `codex login` con ChatGPT y pon `brain: { provider: codex, model: gpt-5.5 }` en harvey.yaml (o elige codex en `harvey setup`, que sugiere gpt-5.5, o `harvey train <url> --provider codex --model gpt-5.5`). gpt-5.5 es el modelo verificado solo de texto; un modelo en blanco falla en las cuentas actuales porque el catálogo en vivo lo oculta, y los modelos de modo código se rechazan. Claude sigue siendo el predeterminado; Harvey nunca cambia de proveedor por su cuenta. Cada llamada a Codex se ejecuta aislada y sin herramientas; consulta "Using a ChatGPT plan instead (Codex)" en el README. Solo macOS y Linux; en Windows Codex se rechaza, así que usa Claude. No edites la configuración `~/.codex` del propio usuario para que funcione.

- **"¿Qué es el panel?"** → Pide al usuario que ejecute `harvey dashboard` en su propia terminal y abra el enlace privado que imprime (`http://127.0.0.1:5555/#token=…`; `harvey dashboard --url` lo vuelve a imprimir). No leas, imprimas ni repitas tú el token: da acceso al panel. Se abre en **Today**: primero lo que espera una decisión y después el pipeline. Pestañas: Signals, Companies, Contacts, Campaigns, Outbox, Conversations, Activity, Usage, Settings.

- **"¿Qué son las señales (signals)?"** → Las señales son los datos que Harvey recopila sobre un negocio: quién es su agencia actual, si hace publicidad, si tiene reservas online, cómo se posiciona. **Harvey propone; tú confirmas.** No se recopila nada hasta que el usuario dice que sí en la pestaña Signals (o con `harvey signals --confirm ...`). Así el gasto es intencionado y cada lista de prospectos es explicable: una cohorte es una consulta sobre señales que eligió una persona, no una caja negra.

---

## Flujo de configuración

Recorre estos pasos de forma conversacional. Pregunta una sola cosa cada vez. No abrumes.

### Paso 1: Instalar dependencias

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```

Después instala el navegador para la prospección en LinkedIn:
```bash
python -m playwright install chromium
```

### Paso 2: Claves de API (`.env`)

Harvey necesita un **proveedor de email** (para enviar y leer respuestas) y, muy recomendable, un **verificador de email**. Elige un proveedor:

```
# --- Email provider: choose ONE, set channels.email.provider to match ---
GMAIL_CLIENT_ID=            # Recommended: Gmail/Workspace. Then run 'harvey gmail auth'
GMAIL_CLIENT_SECRET=
# --- or SMTP+IMAP (AgentMail, Fastmail, Workspace app password) ---
SMTP_HOST=  SMTP_PORT=587  SMTP_USERNAME=  SMTP_PASSWORD=
IMAP_HOST=  IMAP_PORT=993
# --- or legacy Instantly ---
INSTANTLY_API_KEY=

# --- Email verification (add at least one; else emails stay 'guess') ---
REOON_API_KEY=              # 600 free/mo — best free tier
ZEROBOUNCE_API_KEY=         # 100 free/mo — best for M365/Workspace catch-alls
HUNTER_API_KEY=             # 50 free/mo + pattern lookup

# --- Discovery (optional — the free OpenStreetMap source needs no key) ---
TINYFISH_API_KEY=                         # free web search (30/min, 500/hr); no rank signals
DATAFORSEO_LOGIN=  DATAFORSEO_PASSWORD=   # cheapest local-business + SERP data
DATAFORSEO_SANDBOX=                       # any value routes to the free sandbox

# --- Optional ---
LINKEDIN_EMAIL=  LINKEDIN_PASSWORD=   # LinkedIn prospecting
CLOUDFLARE_ACCOUNT_ID=  CLOUDFLARE_API_TOKEN=   # deep JS crawling for training
SERPER_API_KEY=            # web search + discovery (2,500 free, then a $50 prepaid pack)
PRECLEARED_API_KEY=        # cold-email check before first sends (see Step 7)
TRULYINBOX_API_KEY=        # warmup: set by 'harvey trulyinbox connect' (see Step 2b)
```

**Proveedor recomendado, Gmail:** para menos de 50 emails en frío al día, un buzón real de Google Workspace en un *dominio secundario dedicado* (nunca el principal) es la opción con mejor entregabilidad y más barata (~7 $/mes). Pon `channels.email.provider: gmail` en harvey.yaml, coloca el client id/secret de OAuth en `.env` y ejecuta `harvey gmail auth` (inicio de sesión único en el navegador). SMTP funciona con cualquier buzón (AgentMail, Fastmail). Instantly sigue funcionando como opción heredada.

**La verificación de email importa:** Harvey aprende el *patrón* de email de cada empresa y verifica UN candidato en lugar de adivinar (el sondeo SMTP directo no es viable desde un agente que se ejecuta en local: el puerto 25 de salida suele estar bloqueado, y Google Workspace / Microsoft 365 aceptan todo desde una IP desconocida). Sin una clave de verificador, los emails encontrados se marcan como `guess` y **nunca se envían**.

**Aprobación por defecto:** con un proveedor nativo, cada email saliente espera en el **Outbox** a que lo apruebes (pestaña Outbox del panel, o `harvey outbox`). El **Autopilot** (`channels.email.require_approval: false`) envía por sí solo, siempre dentro del límite diario, las horas de silencio y las reglas de baja, pero retiene cualquier email que enlace a un dominio que no sea del usuario o que cite las propias instrucciones de Harvey (el texto de sitios web y respuestas puede contener instrucciones plantadas). Explica ambos antes de cambiar, y sugiere aprobar a mano uno o dos lotes primero. El usuario lo cambia en panel → Settings → Sending (activarlo ahí exige escribir `autopilot`; desactivarlo es un clic y surte efecto al instante), o en el archivo de configuración que lee Harvey (`harvey.local.yaml` si está entrenado, si no `harvey.yaml`); un Harvey en ejecución lo recoge en el siguiente ciclo. No actives el autopilot tú mismo sin que el usuario lo pida expresamente. Si envían desde un dominio secundario, su sitio principal va en `channels.email.link_domains` (el entrenamiento añade automáticamente el sitio entrenado). En Instantly, el modo de aprobación significa que las campañas no se despliegan en absoluto.

Tras obtener la clave de API de Instantly, pruébala:
```bash
source .venv/bin/activate && python3 -c "
import asyncio, httpx
async def test():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get('https://api.instantly.ai/api/v2/accounts', headers={'Authorization': 'Bearer API_KEY_HERE'})
        print('Connected!' if r.status_code == 200 else f'Failed: {r.status_code}')
asyncio.run(test())
"
```

### Paso 2b: Warmup (TrulyInbox)

Todo buzón de envío necesita un servicio de warmup: uno nuevo, durante 2-4 semanas antes del email en frío, y todos los buzones después para mantenerse fuera del spam. Recomendamos TrulyInbox para todo el mundo, sea cual sea el proveedor (incluidos los usuarios de Instantly). Además es la única forma en que Harvey puede saber si un buzón está realmente calentado: una vez conectado, `harvey
warmup` lee de él los días de warmup y la tasa de spam del buzón.

Primero ejecuta `harvey trulyinbox`. Si dice **connected** o **using another warmup
service**, este paso está hecho: no lo vuelvas a mencionar. Si no:

1. Recomienda TrulyInbox y comparte el enlace: https://trulyinbox.com/?via=harvey (la primera vez que lo compartas, di
   que es un enlace de afiliado, entre paréntesis a continuación). Conectar Harvey necesita acceso
   a la API, que empieza en Starter (22 $/mes facturados anualmente).
2. Cuando se hayan registrado y añadido el buzón de envío, pídeles que ejecuten `harvey
   trulyinbox connect` en su propia terminal, o que usen el paso de warmup de la
   página Today del panel. Pide una clave de workspace (TrulyInbox → Settings → API
   keys, con `accounts:read`, `warmup:read`, `analytics:read`, `workspace:read`).
   No les pidas que peguen la clave en este chat.
3. Si ya usan otro servicio de warmup, ejecuta `harvey trulyinbox other` para que
   Harvey deje de preguntar.

Después, `harvey warmup` muestra en qué punto están. Si no han puesto
`channels.email.warmup.start_date`, sugiere la fecha de inicio de TrulyInbox.

### Paso 3: Entrenar el producto

Este es el paso más importante. Harvey necesita saber qué está vendiendo.

**Opción A — Entrenar desde la URL de un sitio web (recomendada):**
```bash
source .venv/bin/activate && python -m harvey.trainer https://their-website.com
```
Esto genera: `harvey.yaml`, `skills/product_knowledge.md`, `skills/competitive_intel.md`

**Opción B — Configuración manual:**
Haz al usuario estas preguntas y construye `harvey.yaml` y `skills/product_knowledge.md`:
- ¿Cómo se llama tu empresa?
- ¿Qué vendes? (nombre del producto/servicio y una descripción de una línea)
- ¿Cuánto cuesta?
- ¿Cuáles son los 3-5 beneficios principales?
- ¿Cuál es tu público objetivo? (sectores, cargos, tamaño de empresa, geografía)
- ¿Qué nombre y email debe usar Harvey? (la identidad del remitente, el "from")
- ¿Qué objeciones oyes normalmente? ¿Cómo las respondes?
- **Ofertas y cierre:**
  - ¿Cuál es la oferta principal? (suscripción, servicio, etc.)
  - ¿Hay una entrada de bajo compromiso? (prueba gratuita, auditoría gratuita, etc.)
  - ¿Cuál es el objetivo? (agendar una llamada, empezar una prueba, conseguir una respuesta)
  - ¿Cómo deben agendarse las reuniones? (enlace de calendario, proponer horarios, preguntar preferencia)
  - ¿Cuánto dura la llamada? (por defecto: 15 minutos)
  - ¿Quién atiende la reunión?

### Paso 4: Confirmar las señales

Harvey incluye un catálogo de 29 señales que sabe recopilar, todas **propuestas** y
ninguna activa. No se prospecta contra nada hasta que el usuario las confirma.

Envíales a `harvey dashboard` → **Signals**, donde cada una muestra una
descripción en lenguaje llano, lo que cuesta y cuántas empresas ya la tienen.
O desde la terminal:

```bash
harvey signals                      # review the catalog
harvey signals --confirm free       # turn on everything that costs nothing
harvey signals --confirm SERP_RANK,MAPS_RANK  # the paid rank signals
```

La mayoría de las señales son gratuitas (leen páginas que el negocio ya publica). Solo
`SERP_RANK`, `MAPS_RANK` y `EMAIL_STATUS` consumen créditos; la nota de coste de cada fila lo indica.

Una vez confirmadas las señales, el **constructor de cohortes** al final de la pestaña
Signals las convierte en una lista objetivo: elige lo que debe tener un buen prospecto (y lo que le
descalifica, y un rango para señales numéricas como el ranking orgánico 11-30) y
cuenta las coincidencias en directo.

### Paso 5: Encontrar negocios

Discovery es la única fase que gasta dinero, así que siempre estima primero.

```bash
harvey discover --providers                        # the menu, with real prices
harvey discover --estimate                         # projected spend, then exits
harvey discover                                    # free OpenStreetMap source
harvey discover --provider dataforseo_listings --max-spend 2.00
harvey discover --preset yc --provider serper   # startups that say they're YC-backed
harvey discover --preset hiring --provider serper   # companies whose careers pages list your roles
harvey discover --preset accelerator --provider serper   # ...Techstars, Antler, EF and others
harvey discover --preset funding --provider serper       # companies announcing a raise
```

La pestaña **Discover** del panel es lo mismo, con las ventajas e inconvenientes expuestos
lado a lado: qué hace cada fuente, cuánto cuesta, su plan gratuito y qué
claves de `.env` necesita. No se llama a nada hasta que el usuario pulsa Run.

| Fuente | Coste | Plan gratuito | Ideal para |
|---|---|---|---|
| **OpenStreetMap** (por defecto) | gratis | ilimitado | Probar todo el pipeline sin ninguna cuenta. Cobertura escasa para oficios de área de servicio: OSM mapea locales, así que tiene menos de 2.000 tejadistas en todo EE. UU. Una fuente de prueba, no una lista completa. |
| **DataForSEO Business Listings** | 0,372 $/1k negocios | 1 $ de crédito | Oficios locales, clínicas, contratistas. Teléfono + dominio + valoración + si la ficha está reclamada, y puede filtrar negocios **sin ningún sitio web**. |
| **DataForSEO SERP** | 0,006 $ por búsqueda a profundidad 30 (Live, 0,002 $ por cada 10 resultados) | 1 $ de crédito + sandbox gratuito | El ranking como señal de compra. Las posiciones 11-30 son el punto óptimo. También registra quién ocupa el 3-pack local (`IN_LOCAL_PACK`). |
| **DataForSEO Google Maps** | 0,002 $ por búsqueda (hasta 100 resultados) | 1 $ de crédito + sandbox gratuito | Ranking en el mapa (`MAPS_RANK`), valoración, categoría, estado de reclamado; conserva los negocios sin sitio web. |
| **Serper** | ~0,30-1,00 $/1k | 2.500 gratis, sin tarjeta | La opción de pago más fácil de probar. |

Las ciudades se geocodifican automáticamente (en caché para siempre, una consulta por ciudad), o define
`icp.geo_coordinates` en harvey.yaml para controlar el radio:
`"Denver, CO": "39.7392,-104.9903,50"`. Los proveedores de ranking de DataForSEO buscan
desde ese punto (el centro de la ciudad), así que un ranking es "cuando buscamos desde
el centro de Denver", nunca una afirmación absoluta; consulta `skills/signal_playbook.md`.
Añade más frases de búsqueda por sector con `icp.keyword_variants`
(`"roofing contractor": ["roofer", "roof repair"]`); cada una se ejecuta en todas las ciudades,
y cada ranking se guarda con la frase que lo produjo.

**Vender a startups:** tres presets (arriba, o *Look for* en Discover):
`yc` encuentra empresas cuyo propio sitio dice que están respaldadas por Y Combinator,
`accelerator` lo mismo para Techstars, 500 Global, Antler, Entrepreneur First,
South Park Commons, Neo, AI Grant, a16z speedrun, Pioneer y Plug and Play,
y `funding` empresas que anuncian su propia ronda en los últimos 18 meses.
Confirma `YC_BACKED`, `ACCELERATOR` o `FUNDING_ROUND` para etiquetarlas (lote o
cohorte; para una ronda, la ronda, la cantidad y la fecha; leen la página de inicio, About
y las páginas de prensa, y muchas startups nunca lo dicen ahí), y entonces el writer y el
handler usan `skills/selling_to_startups.md` con ellas. Una ronda de hace más de
18 meses, o sin fecha, no se trata como noticia y por sí sola no activa
el playbook. Harvey nunca lee ycombinator.com, los
directorios de las aceleradoras, Crunchbase, PitchBook ni LinkedIn (sus términos
prohíben el scraping), así que no sugieras hacer scraping de ellos en su lugar.

**Profundidad 20-30, no 100.** Google eliminó los 100 resultados por página en septiembre de 2025,
así que la profundidad 100 ahora se factura como diez páginas en casi todos los proveedores. Por debajo del puesto 30
son sobre todo directorios de todos modos.

### Paso 6: Ajustes de comportamiento

Van en `harvey.yaml` bajo `usage:`. Usa valores razonables por defecto salvo que quieran personalizar:
- `max_daily_claude_percent`: 80 (qué parte de la cuota diaria de Claude se usa)
- `heartbeat_interval_minutes`: 15 (cada cuánto comprueba Harvey si hay trabajo)
- `quiet_hours`: 22:00-07:00 en su zona horaria
- `max_daily_sends`: 50 (límite de envío de emails)

### Paso 7: Comprobación de email en frío (opcional)

Ofrécelo una sola vez, brevemente, y acepta un no. Con `compliance.precleared.enabled: true`, Harvey pregunta a [Precleared](https://precleared.dev) qué normas de email en frío se aplican a cada dirección nueva antes de que salga el primer email. Un autónomo del Reino Unido necesita consentimiento mientras que una sociedad limitada no, y la dirección por sí sola no indica cuál es el caso. Todo lo que no sea `ok_to_email` espera en el Outbox con el motivo. Comprueba el correo enviado mediante Gmail, Microsoft 365 o SMTP, no Instantly. Precleared recibe la dirección de cada destinatario nuevo, el país del remitente, el origen de la dirección, la descripción del producto y, si se ha indicado, el país de los prospectos.

Si lo quieren, pregunta una cosa cada vez:
- ¿Dónde tiene su sede el negocio? `sender_country` debe ser `GB` o `US`. Si no es ninguno de los dos, deja la comprobación desactivada.
- ¿Están todos sus prospectos en un mismo país? Si es así, pon `prospect_country` con su código de dos letras, entre comillas (por ejemplo `"US"`). Si no, déjalo vacío.
- ¿Quieren una clave gratuita? Sin ella Precleared permite 10 comprobaciones al día; una clave gratuita de https://precleared.dev/get-key permite 25. Va en `.env` como `PRECLEARED_API_KEY`.

Deja `address_source` en `"unknown"`, ya que Harvey construye la mayoría de las direcciones a partir de un patrón aprendido. Guarda los ajustes bajo `compliance.precleared` en `harvey.local.yaml` si existe (ese archivo manda), si no en `harvey.yaml`. `harvey setup` hace las mismas preguntas.

### Paso 8: Arrancar Harvey

```bash
source .venv/bin/activate && harvey run
```

O abre el panel:
```bash
harvey dashboard
```

---

## Después de la configuración: ayuda continua

Los usuarios volverán con preguntas y tareas. Las más habituales:

- **"Enséñame lo que ha hecho Harvey"** → Ejecuta `harvey status` o `harvey dashboard`
- **"¿Estoy calentado?" / "¿Por qué acabo en spam?"** → Ejecuta `harvey warmup`. Sin TrulyInbox conectado Harvey no puede ver la tasa de la bandeja de entrada, así que recomiéndalo (Paso 2b) salvo que `harvey trulyinbox` indique que usan otro servicio.
- **"Los emails no son buenos"** → Edita `skills/email_frameworks.md` y `prompts/writer.md`. Muéstrales las reglas actuales y ayúdales a ajustarlas.
- **"Harvey no encuentra a las personas adecuadas"** → Revisa la configuración del ICP en `harvey.yaml`. Ajusta industries, titles, company_size, geography.
- **"Quiero cambiar lo que dice Harvey"** → Las skills están en `skills/`, los prompts en `prompts/`. Ambos son archivos markdown simples. Edítalos directamente.
- **"Entrena a Harvey con otro producto"** → `harvey train <new-url>`
- **"¿Cómo veo la base de datos?"** → Está en `data/harvey.db`. Pueden abrirla con cualquier herramienta SQLite, o pedirte que hagas consultas.
- **"Solo quiero la lista de prospectos"** → `harvey export` escribe un CSV listo para un sequencer (solo emails verified/risky; `--all` para todo). También hay botones Export en la pestaña Contacts del panel. Harvey es valioso como mero constructor de listas aunque el usuario nunca le deje enviar.

---

## Cómo funciona Harvey (referencia técnica)

### Arquitectura
- **Bucle de heartbeat** (`main.py`): En cada ciclo → comprobar horas de silencio → comprobar presupuesto → decidir → actuar → registrar → dormir
- **Brain** (`brain.py`): Envuelve `claude -p --output-format json --dangerously-skip-permissions` para llamadas a Claude sin interfaz; registra el uso exacto de tokens de cada llamada en `usage_events`
- **State** (`state.py`): SQLite en `data/harvey.db` con tablas de empresas, prospectos, campañas, conversaciones, acciones y uso
- **Seguimiento del uso** (`usage.py`, `integrations/quota.py`): atribución por llamada (agente/tarea/modelo/tokens) solo para las llamadas a Claude PROPIAS de Harvey (nunca escanea tus otras sesiones de Claude Code), más un indicador en vivo de la cuota de la suscripción leído igual que el `/usage` de Claude Code. La comprobación de presupuesto frena a Harvey según la utilización real de la cuota para que siempre deje margen a tu propio uso interactivo de Claude (`usage.max_daily_claude_percent`). El panel tiene una pestaña Usage; la CLI tiene `harvey usage`.
- **Skills** (`skills/`): archivos de conocimiento en Markdown que se inyectan en los prompts de los agentes
- **Signals** (`signals.py`, `state.py`): todo hecho que Harvey aprende es una OBSERVACIÓN: una fila en `observations`, nunca una columna. Una señal nueva no necesita migración, volver a observar con el tiempo es una serie temporal gratis, y la confianza y la procedencia viajan con el dato. El vocabulario de `signal_codes` está gobernado (un trigger rechaza cualquier código que no esté en él) y condicionado: solo se recopilan las señales con `status = 'confirmed'`, y solo una persona lo establece. `state.cohort(require, exclude)` hace la intersección de conjuntos en SQL.
- **Panel** (`dashboard.py` + `harvey/web/`): API JSON con FastAPI más HTML/CSS/JS plano servido desde disco, sin paso de compilación. Edita `harvey/web/app.css` o `app.js` y recarga la página.
- **DISCOVER** (`collectors/discover.py`): la única fase que gasta dinero, así que la disciplina de costes vive en el collector, no en la base de datos: cada ejecución estima primero, comprueba un tope de gasto entre lotes, lee un kill switch y vuelca las observaciones por lotes. Los proveedores son adaptadores tras una única interfaz (`DiscoveryProvider`); añadir uno es una clase pequeña. El filtrado de basura coincide con *patrones*, no con una lista de bloqueo literal. La resolución de entidades es el dominio normalizado, con el `external_id` del proveedor como alternativa para negocios sin sitio web.

### Subagentes
- **Scout**: Python hace toda la búsqueda web (DuckDuckGo → Bing → Google → API de Serper) y la resolución de emails (primero el patrón: caché → mailto extraído → búsqueda de dominio en Hunter → valor por defecto, y luego verifica un candidato con Reoon/ZeroBounce/Hunter/SMTP; los catch-all se marcan como `risky`). Claude solo puntúa y personaliza los datos encontrados. Scout también recopila **señales de compra**: el stack tecnológico detectado en el sitio de cada empresa (HubSpot, Shopify, Intercom, ~35 herramientas, sin peticiones adicionales) y señales de contratación de las páginas de empleo. El profiling (`HIRING_ROLE` / `OPEN_ROLES`) va más allá: cuando el propio sitio de una empresa enlaza o incrusta un tablero de Greenhouse, Lever, Ashby o Workable, lee el feed JSON público de ese tablero (una petición, con tamaño limitado, nunca un token adivinado) y registra los puestos que coinciden con `icp.hiring_signals` (si no, `icp.titles`) con departamento, ubicación, fecha de publicación y URL, además del número de puestos abiertos (`harvey/collectors/ats.py`). Un tablero sin ningún puesto coincidente registra `HIRING_ROLE` = 0, así que los puestos cerrados dejan de estar vigentes. La alternativa a `titles` es débil (enumera a quién escribes, no los puestos que indican compra), así que sugiere a los usuarios que definan `hiring_signals`. Con `pip install python-jobspy` (opcional), una estrategia de bolsas de empleo descubre empresas que están contratando activamente para los puestos de `icp.hiring_signals` (si no, `icp.titles`), la señal de que están en proceso de compra más fuerte. Las señales acaban en las notas de personalización de los prospectos y aumentan su puntuación.
- **Writer**: Genera secuencias de 3 emails (Email 1 < 75 palabras, Email 2 < 75, Email 3 < 40). Lista de prohibiciones estricta de patrones de IA.
- **Sender**: Los proveedores nativos (gmail/smtp) renderizan las variables de combinación por prospecto y PONEN EN COLA cada email en el `outbox` (pending_review → approved → sent) con una hora de envío programada; cada heartbeat vacía los elementos aprobados que toca enviar con un ritmo humano, el límite diario, la puerta determinista previa al envío y la parada al responder (una respuesta de cualquier persona de una empresa detiene la secuencia para todos los de allí). La vía heredada de Instantly despliega campañas por API. Aplica en ambos casos los límites de envío diarios.
- **Handler**: Consulta al proveedor (o a Instantly) por respuestas, las deduplica, clasifica la intención, hace avanzar la etapa de la conversación y pone en cola respuestas automáticas por la misma escalera de aprobación del outbox. En proveedores nativos también detecta rebotes → marca la dirección como inválida, cancela los envíos en cola del prospecto y activa un kill switch global al superar un umbral de tasa de rebote.
- **Analyst**: Se ejecuta en los ciclos ociosos. Genera `data/analytics.json` con estadísticas del pipeline y conclusiones.

### Etapas de la conversación
`initial_outreach → engaged → qualifying → presenting → negotiating → closing → closed_won / closed_lost`

### Orden de prioridad
handle_replies > send_campaigns > write_campaigns > prospect > idle (run analyst)

### Comandos principales
```bash
source .venv/bin/activate    # Always activate venv first
harvey run                   # Start the heartbeat loop
harvey dashboard             # Web UI at http://127.0.0.1:5555 (open the printed link)
harvey setup                 # Re-run setup wizard
harvey train <url>           # Train on a product website
harvey status                # Pipeline summary
harvey usage                 # Claude quota gauges + per-agent token usage (no dollar costs — subscription plans aren't billed per token)
harvey export                # Deliverable prospects → sequencer-ready CSV (prospects.csv)
harvey export --all          # Full raw list, no filters
harvey gmail auth            # One-time Gmail OAuth (when provider: gmail)
harvey gmail test            # Verify the Gmail connection
harvey outbox                # Review queued emails; --approve <id> / --approve-all / --reject <id>
harvey signals               # The signal vocabulary; --confirm / --reject CODES (or 'free' / 'all')
harvey discover              # Find businesses; --providers / --estimate / --provider <key>
harvey sending pause|resume  # Kill switch for all outbound
harvey warmup [domain]       # Sending-domain readiness: SPF/DKIM/DMARC, age, blocklists, ramp, TrulyInbox warmup
harvey trulyinbox [connect|other]  # Warmup service: connect TrulyInbox, or record another service
```

### Problemas comunes
- **"command not found: harvey"**: Activa primero el venv: `source .venv/bin/activate`
- **"ModuleNotFoundError: No module named 'harvey'" tras instalar (macOS)**: Python 3.13 ignora en silencio los archivos `.pth` que llevan el indicador de archivo oculto de macOS, y algunos Mac propagan ese indicador a `.venv`. Ejecuta `harvey install` de nuevo (lo arregla automáticamente enlazando el paquete), o manualmente: `ln -s "$(pwd)/harvey" .venv/lib/python3.13/site-packages/harvey`
- **"externally-managed-environment"**: Usa un venv, no el Python del sistema
- **Errores de SQLite**: El directorio `data/` se crea automáticamente en la primera ejecución
- **Falla el modo headless de Claude**: El usuario necesita `claude login` y una suscripción Max activa
- **Fallan las llamadas a Codex** (`brain.provider: codex`): la línea del log dice por qué: `codex login` con ChatGPT (también cuando el inicio de sesión "has expired or is due for renewal": Harvey nunca lo renueva), instala la versión de Codex compatible (`harvey status --check` muestra qué falla sin llamar a un modelo; mientras Codex no se puede usar Harvey pausa ciclos enteros a propósito), elige un `brain.model` sin modo código, o elimina la capa de configuración de Codex que esté volviendo a activar herramientas/hooks/MCP. Nunca debilites las comprobaciones de aislamiento de Harvey para sortearlo.
- **Instantly API 401**: Clave de API incorrecta o hace falta el plan Growth para acceder a la API
- **Límite de frecuencia de búsqueda en Google**: Harvey recurre automáticamente a DuckDuckGo y Bing. Para una búsqueda fiable, añade una clave de API de Serper (5 $/mes).
