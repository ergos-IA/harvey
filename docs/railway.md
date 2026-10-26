# Desplegar Harvey en Railway

Este fork incluye un modo "hosted" para que Harvey funcione 24/7 en Railway
sin depender de tu ordenador. El Docker original y el uso en local no cambian.

## Qué se añade

| Archivo | Para qué |
|---|---|
| `Dockerfile.railway` | Imagen con el CLI de Claude, Chromium y un entrypoint para Railway |
| `deploy/railway/entrypoint.sh` | Prepara el volumen, arranca el bucle (si Harvey está configurado) y el dashboard en `$PORT` |
| `deploy/railway/harvey-cli.sh` | Comando `harvey` dentro del contenedor (para `railway ssh`) |
| `railway.json` | Le dice a Railway que use `Dockerfile.railway` |

El dashboard solo escucha en localhost por diseño. En modo hosted acepta también
los dominios de `HARVEY_PUBLIC_HOSTS` y `RAILWAY_PUBLIC_DOMAIN`, por HTTPS y siempre
con el token de `HARVEY_DASHBOARD_TOKEN`. Sin esas variables, el comportamiento
es el original.

## Persistencia

Harvey escribe junto a su código: `.env`, `harvey.local.yaml`, `data/` (base de datos,
tokens de Gmail/M365, logs) y `skills/product_knowledge.md`. En Railway, la copia de
trabajo vive en el volumen (`/data/app`). En cada arranque se refrescan el código y
los prompts desde la imagen, y se conserva todo lo que Harvey haya generado.

## Variables de entorno

| Variable | Obligatoria | Valor |
|---|:-:|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | sí | Ejecuta `claude setup-token` en tu ordenador y pega el token. Usa tu suscripción Pro/Max. |
| `HARVEY_DASHBOARD_TOKEN` | sí | Secreto para entrar al dashboard (43-128 caracteres). Por ejemplo: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `HARVEY_PUBLIC_HOSTS` | no | Dominios propios extra, separados por comas. El dominio `*.up.railway.app` se detecta solo. |
| `HARVEY_AUTOSTART` | no | `1` (por defecto) arranca el bucle al iniciar si Harvey está configurado; `0` lo desactiva. |
| `SMTP_*`, `IMAP_*`, `REOON_API_KEY`... | según uso | Las mismas de `.env.example`. Las variables de Railway tienen prioridad sobre el `.env` del volumen. |

## Pasos

1. Crea el servicio desde este repo (Railway detecta `railway.json`).
2. Añade un volumen montado en `/data`.
3. Configura las variables de arriba.
4. Genera un dominio público (Settings → Networking → Generate Domain).
5. Abre `https://<tu-dominio>/#token=<HARVEY_DASHBOARD_TOKEN>`.

## Primera configuración (dentro del contenedor)

`harvey setup` y `harvey train` son interactivos. Ejecútalos con:

```bash
railway ssh
harvey setup              # asistente inicial
harvey train https://tu-web.com
harvey status --check     # comprueba el CLI de Claude
```

Después reinicia el servicio (o pulsa Start en el dashboard) para arrancar el bucle.

## Correo

- **SMTP + IMAP** (`provider: smtp`) es lo más sencillo en un servidor: solo variables.
- **Gmail** usa OAuth de "aplicación de escritorio", que necesita un navegador en la
  misma máquina. Ejecuta `harvey gmail auth` en tu ordenador y sube el
  `data/gmail_token.json` resultante a `/data/app/data/` del volumen.
- **Microsoft 365**: lo mismo con `harvey microsoft auth` y `data/m365_token.json`.

## Limitaciones

- Codex (ChatGPT) no está soportado en Docker; en Railway solo funciona con Claude.
- Lo que consume Harvey cuenta contra tu cuota de Claude. Ajusta
  `max_daily_claude_percent` en `harvey.yaml`.
- Una sola réplica: dos bucles sobre la misma base de datos enviarían por duplicado.
