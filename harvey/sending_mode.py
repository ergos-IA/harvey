"""Approval or autopilot, picked up while Harvey runs.

The dashboard switch (or a hand edit) changes channels.email.require_approval
in the config file. Whatever part of Harvey notices first, the loop, the
sender, the writer or the handler, calls sync_sending_mode, so going back to
approval always brings what autopilot approved (and hasn't sent) back to the
Outbox, whoever noticed.
"""

import logging

from harvey.config import refresh_sending_mode

logger = logging.getLogger("harvey.sending_mode")


async def sync_sending_mode(config, state) -> bool:
    """Bring ``config`` in line with its file. True when the mode changed."""
    if not refresh_sending_mode(config):
        return False
    if config.channels.email.require_approval:
        back = await state.requeue_autopilot_approved()
        logger.warning("Sending mode is now APPROVAL: every email waits in the Outbox for you."
                       + (f" {back} queued by autopilot came back to the Outbox." if back else ""))
    else:
        logger.warning("Sending mode is now AUTOPILOT: Harvey sends on its own "
                       "(emails it holds still wait for you).")
    return True


def held_message(hold: dict, waiting: int) -> tuple[str, str]:
    """What Today and `harvey status` say while sending is held because
    replies couldn't all be read or handled: (title, detail)."""
    reason = str(hold.get("reason") or "no se pudieron leer todas las respuestas").strip().rstrip(".")
    low = reason.lower()
    # The reasons come from the handler and the mail providers, in English
    # or (once translated) in Spanish: match both.
    if low.startswith(("a reply from", "una respuesta de")):
        # The inbox was read; handling one reply failed. Its text and the
        # sender's address are no guide to a fix, so match nothing in it.
        title = "Harvey no está enviando: no pudo gestionar una respuesta"
        fix = "Harvey lo reintenta en cada ciclo; si se alarga, revisa el registro."
    else:
        title = "Harvey no está enviando: no pudo leer tu bandeja de entrada"
        # Only the providers' own messages name a fix.
        if "harvey gmail auth" in low:
            fix = "Ejecuta `harvey gmail auth` para volver a iniciar sesión."
        elif "harvey microsoft auth" in low:
            fix = "Ejecuta `harvey microsoft auth` para volver a iniciar sesión."
        elif "refusing a partial read" in low or "lectura parcial" in low:
            fix = ("El buzón recibió la última semana más correo del que Harvey lee, así que no "
                   "puede asegurar que vio todas las respuestas. Envía desde un buzón dedicado "
                   "o archiva el correo antiguo.")
        else:
            fix = "Harvey lo reintenta en cada ciclo; si se alarga, revisa el registro."
    emails = "1 correo espera" if waiting == 1 else f"{waiting} correos esperan"
    return (title,
            f"{reason}. {fix} {emails}: primero se leen las respuestas, para que una baja "
            f"detenga su seguimiento antes de que salga nada. Retenido desde "
            f"{str(hold.get('since', '?'))[:16].replace('T', ' ')} UTC.")
