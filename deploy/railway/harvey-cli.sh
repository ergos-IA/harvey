#!/bin/sh
# 'harvey <comando>' dentro del contenedor (p. ej. desde 'railway ssh'):
# ejecuta la CLI sobre la copia de trabajo del volumen, como el usuario harvey.
set -eu
cd "${RAILWAY_VOLUME_MOUNT_PATH:-/data}/app"
if [ "$(id -u)" = "0" ]; then
    exec setpriv --reuid=harvey --regid=harvey --init-groups \
        env HOME=/home/harvey python -m harvey "$@"
fi
exec python -m harvey "$@"
