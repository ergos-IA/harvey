#!/bin/sh
# Arranque de Harvey en Railway.
#
# Harvey escribe junto a su código (.env, harvey.local.yaml, data/,
# skills/product_knowledge.md...), y Railway borra el disco en cada deploy.
# Así que la copia de trabajo vive en el volumen: en cada arranque se
# refresca el código desde la imagen y se conserva lo que Harvey generó.
set -eu

VOLUME="${RAILWAY_VOLUME_MOUNT_PATH:-/data}"
APP="$VOLUME/app"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$APP/data" "$APP/skills"
    # Código y prompts: siempre los de la imagen.
    rm -rf "$APP/harvey" "$APP/prompts"
    cp -r /app/harvey /app/prompts "$APP/"
    # Skills del repo se actualizan; los generados (product_knowledge.md,
    # competitive_intel.md) no vienen en la imagen y se conservan.
    cp -r /app/skills/. "$APP/skills/"
    # La plantilla de config solo la primera vez: puede editarse desde el dashboard.
    [ -f "$APP/harvey.yaml" ] || cp /app/harvey.yaml "$APP/harvey.yaml"
    # Las claves vienen de las variables de Railway; .env solo guarda lo que
    # se cambie desde el dashboard (las variables de Railway tienen prioridad).
    [ -f "$APP/.env" ] || : > "$APP/.env"
    chmod 600 "$APP/.env"
    # Configuración privada desde variables de Railway (base64), para no
    # tenerla en el repo público. Si la variable existe, manda sobre el archivo.
    [ -z "${HARVEY_LOCAL_YAML_B64:-}" ] \
        || printf '%s' "$HARVEY_LOCAL_YAML_B64" | base64 -d > "$APP/harvey.local.yaml"
    [ -z "${HARVEY_PRODUCT_KNOWLEDGE_B64:-}" ] \
        || printf '%s' "$HARVEY_PRODUCT_KNOWLEDGE_B64" | base64 -d > "$APP/skills/product_knowledge.md"
    [ -z "${HARVEY_COMPETITIVE_INTEL_B64:-}" ] \
        || printf '%s' "$HARVEY_COMPETITIVE_INTEL_B64" | base64 -d > "$APP/skills/competitive_intel.md"
    chown -R harvey:harvey "$VOLUME"
    exec setpriv --reuid=harvey --regid=harvey --init-groups \
        env HOME=/home/harvey "$0" "$@"
fi

cd "$APP"

if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}${ANTHROPIC_API_KEY:-}" ]; then
    :
else
    echo "AVISO: falta CLAUDE_CODE_OAUTH_TOKEN (genéralo con 'claude setup-token')."
fi

# Señales confirmadas/rechazadas desde variables (HARVEY_SIGNALS_CONFIRM y
# HARVEY_SIGNALS_REJECT, códigos separados por comas). Se aplican solo cuando
# cambian, para no pisar lo que decidas después en el dashboard.
SIGNALS_WANT="${HARVEY_SIGNALS_CONFIRM:-}|${HARVEY_SIGNALS_REJECT:-}"
SIGNALS_MARK="data/.signals_applied"
if [ "$SIGNALS_WANT" != "|" ] \
    && [ "$(cat "$SIGNALS_MARK" 2>/dev/null)" != "$SIGNALS_WANT" ]; then
    echo "Aplicando la selección de señales de las variables..."
    ok=1
    [ -z "${HARVEY_SIGNALS_REJECT:-}" ] \
        || python -m harvey signals --reject "$HARVEY_SIGNALS_REJECT" || ok=0
    [ -z "${HARVEY_SIGNALS_CONFIRM:-}" ] \
        || python -m harvey signals --confirm "$HARVEY_SIGNALS_CONFIRM" || ok=0
    [ "$ok" = "0" ] || printf '%s' "$SIGNALS_WANT" > "$SIGNALS_MARK"
fi

# El bucle arranca solo si Harvey ya está configurado; si no, configúralo
# con 'railway ssh' (harvey setup / harvey train <url>) y arráncalo desde
# el dashboard.
if [ "${HARVEY_AUTOSTART:-1}" = "1" ] \
    && python -c "import sys; from harvey.main import _needs_setup; sys.exit(_needs_setup())"; then
    echo "Arrancando el bucle de Harvey..."
    (python -m harvey run 2>&1 | tee -a data/harvey.log) &
else
    echo "Harvey aún no está configurado (o HARVEY_AUTOSTART=0): solo el dashboard."
fi

exec python -m harvey dashboard --host 0.0.0.0 --port "${PORT:-5555}"
