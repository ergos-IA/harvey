# LinkedIn: invitaciones y primeros mensajes

Harvey redacta, tú apruebas y un trabajador en **tu PC** lo envía con tu propia sesión de LinkedIn.
Los datos están en el servidor, pero el navegador no: un inicio de sesión desde la IP de un centro de datos
hace que LinkedIn revise la cuenta.

```
servidor (panel → LinkedIn)                    tu PC (harvey linkedin work)
  Buscar personas: cuentas de 70 puntos o más   busca en LinkedIn a quién escribir en ellas
  Redactar: nota + mensaje (Claude)              envía las invitaciones aprobadas
  Tú apruebas o editas                           comprueba quién acepta y le envía el mensaje
```

Estados: `candidate → pending_review → approved → invited → connected → messaged` (o `rejected` / `failed`).
Nada sale sin aprobación. Un borrador con enlaces a otros dominios o que repita las instrucciones de Harvey
queda marcado como «Revisar» y no entra en «Aprobar todas».

## Puesta en marcha en el PC

1. `pip install -e .` y `python -m playwright install chromium`.
2. En el `.env` del PC: `HARVEY_REMOTE_URL=https://<tu panel>` y `HARVEY_REMOTE_TOKEN=<token del panel del servidor>`.
3. `harvey linkedin login`: se abre una ventana, inicias sesión a mano (con la verificación en dos pasos) y la
   sesión queda en `data/linkedin-profile`. No se guarda la contraseña.
4. `harvey linkedin work --dry-run --now`: hace todo salvo el último clic y deja capturas en `data/linkedin-shots`.
5. `harvey linkedin work`: una ronda de verdad. Para que sea automático, prográmalo en el Programador de tareas
   de Windows dos veces al día laborable (por ejemplo, a las 10:00 y a las 16:00).

## Límites

- **Horario:** de lunes a viernes, de 9:00 a 19:00, hora de Madrid. `--now` se lo salta.
- **Límites diarios:** 10 invitaciones, 10 mensajes, 15 búsquedas y 40 perfiles vistos. Se guardan en `data/linkedin-worker.json`.
- **Ritmo:** entre 40 y 110 segundos entre acciones, con desplazamientos y escritura a velocidad humana.
- **Personas por cuenta:** como mucho 2. Solo se toman de la búsqueda las personas cuyo titular nombra la empresa.
- **Exclusiones:** no se escribe a empresas donde alguien respondió o se dio de baja, ni a dominios de `compliance.do_not_contact`.
- **Nota de invitación:** con una cuenta gratuita LinkedIn permite pocas al mes. Cuando no deja añadirla, la invitación
  queda como `failed` con el motivo, en lugar de enviarse sin nota.

Automatizar LinkedIn incumple sus condiciones de uso. Úsalo con tu propia cuenta, a poco volumen.
