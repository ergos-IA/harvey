# Enviar desde un buzón de Microsoft 365

Harvey puede enviar y leer correo a través de un buzón de Microsoft 365 / Outlook
(Exchange Online) mediante Microsoft Graph. Úsalo cuando el correo del dominio desde el que envías
esté en Microsoft 365.

## ¿Por qué no SMTP + IMAP?

Exchange Online ya no acepta contraseña para IMAP, y SMTP AUTH está desactivado
por defecto en la mayoría de los tenants. El proveedor `smtp` a veces todavía puede enviar, pero
no puede leer la bandeja de entrada. Harvey tiene que leer las respuestas para detener secuencias, respetar
las bajas y detectar rebotes. Si puede enviar pero no leer, sigue escribiendo
a gente que ya ha respondido.

El proveedor `microsoft` inicia sesión con OAuth (código de autorización + PKCE)
en su lugar. Harvey nunca guarda una contraseña ni un secreto de cliente.

## Configuración

### 1. Registra una aplicación en Entra ID

En [entra.microsoft.com](https://entra.microsoft.com), ve a
**Applications → App registrations → New registration**:

| Campo | Valor |
|---|---|
| Name | `Harvey` |
| Supported account types | *Accounts in this organizational directory only* |
| Redirect URI, platform | **Public client/native (mobile & desktop)** |
| Redirect URI, value | `http://localhost:8766` |

En el **Overview** de la aplicación, copia el **Application (client) ID** y el
**Directory (tenant) ID**.

No crees un secreto de cliente. Harvey es un cliente público.

### 2. Configura Harvey

`.env`:

```
M365_CLIENT_ID=<Application (client) ID>
M365_TENANT_ID=<Directory (tenant) ID>
```

`harvey.yaml` (o `harvey.local.yaml`):

```yaml
persona:
  email: "you@yourdomain.com"   # must be the mailbox you sign in with
channels:
  email:
    provider: "microsoft"
```

### 3. Inicia sesión una vez

```bash
harvey microsoft auth   # opens the browser; sign in as persona.email
harvey microsoft test   # → ✓ Connected as you@yourdomain.com
```

Harvey solicita cuatro permisos **delegados**:

| Permiso | Por qué se necesita |
|---|---|
| `Mail.ReadWrite` | leer respuestas y crear borradores (hilos de respuesta) |
| `Mail.Send` | enviarlos |
| `User.Read` | comprobar a qué buzón pertenece el token |
| `offline_access` | seguir funcionando sin volver a iniciar sesión |

El token de actualización se guarda en `data/m365_token.json` (ignorado por git). En macOS
y Linux el archivo tiene modo 600 (solo el propietario). Windows no tiene esos bits de modo:
el archivo solo está protegido por los permisos de acceso (ACL) de la carpeta en la que
vive Harvey, así que mantén Harvey en una carpeta que solo tú puedas leer.
Microsoft lo rota en cada uso, y Harvey guarda el nuevo cada vez.

### Si ves "Need admin approval"

Tu tenant no permite que los usuarios den su consentimiento a aplicaciones por sí mismos. Un administrador tiene que
aprobar la aplicación una vez:

1. En Entra, abre **App registrations → Harvey → API permissions**. Añade los
   cuatro permisos delegados de Microsoft Graph indicados arriba y luego haz clic en
   **Grant admin consent**.
2. Ejecuta `harvey microsoft auth` de nuevo e inicia sesión con el **buzón remitente**,
   no con el administrador. Harvey siempre actúa como quien inicia sesión.

Para asegurarte de que nadie más del tenant pueda usar la aplicación, ve a
**Enterprise applications → Harvey**:

1. **Users and groups**: asigna solo el buzón remitente.
2. **Properties**: pon **Assignment required?** en **Yes**. Hazlo después del
   paso 1, o el buzón remitente también quedará bloqueado.

## Cómo se comporta

- **Envío.** Harvey crea un borrador y luego lo envía, de modo que se conoce el
  `Message-ID` RFC del email. Los rebotes y las respuestas se emparejan con él. Los cuerpos
  son texto plano.
- **Las respuestas van en hilo.** Harvey responde con `createReply` sobre el
  mensaje del propio prospecto, así que `In-Reply-To` y `References` son correctos. Si
  ese mensaje se eliminó, la respuesta sale como un email nuevo.
- **Tu bandeja de entrada no se toca.** En cada ciclo, Harvey lee los últimos 7 días de
  la bandeja de entrada, empezando por lo más reciente, todo (página a página), y omite tu propio correo. Nunca marca nada como
  leído, ni lo mueve ni lo elimina. Mantiene su propio registro de lo que ha
  gestionado.
- **Solo actúa como el buzón correcto.** Si el buzón con el que se ha iniciado sesión no es
  `persona.email`, cada lectura y cada envío se rechaza con un mensaje que lo indica.
  Así se evita el error común de iniciar sesión como el administrador que aprobó
  la aplicación.
- **Los fallos detienen el envío.** Si no se puede leer la bandeja de entrada (sesión caducada,
  caída de Graph, limitación de peticiones), el ciclo no envía nada. Una respuesta que nadie leyó
  no puede haber detenido sus seguimientos. La limitación de Graph (429/503 con un `Retry-After`
  corto) se reintenta una vez. Una lectura que falla a mitad cuenta
  como lectura fallida: Harvey nunca actúa sobre una parte de la bandeja de entrada.
- **Los borradores no enviados se limpian.** Si un envío falla, su borrador se elimina
  para que no se quede en tu carpeta de Borradores.
- **El nombre del remitente es el del buzón.** El correo sale con el nombre visible
  del buzón en Microsoft 365, no con `persona.name`.

## Solución de problemas

| Síntoma | Solución |
|---|---|
| `Timed out waiting for the browser round-trip` | El navegador nunca volvió a `localhost:8766`. Comprueba que nada más use el puerto y que el URI de redirección sea `http://localhost:8766` en *Mobile and desktop applications* (no en *Web*). |
| `AADSTS50011` (redirect URI mismatch) | Igual que arriba: el URI y su plataforma deben coincidir exactamente. |
| `Need admin approval` | Consulta [Si ves "Need admin approval"](#si-ves-need-admin-approval). |
| `signed in as X, but persona.email is Y` | Ejecuta `harvey microsoft auth` de nuevo y elige la cuenta correcta. Usa "Use another account" si el navegador ya tiene la sesión iniciada con otra persona. |
| `token refresh rejected` | La sesión caducó (90 días sin uso) o se revocó. Ejecuta `harvey microsoft auth` de nuevo. |

Para revocar el acceso de Harvey, ve a
[myaccount.microsoft.com](https://myaccount.microsoft.com) → **Apps**, o
elimina el registro de la aplicación. Después elimina `data/m365_token.json`.

## Notas sobre entregabilidad

- **Activa DKIM** para tu dominio en Microsoft Defender (Email
  authentication → DKIM). Sin él, el correo de Exchange Online no se firma
  con tu dominio.
- **Ten en cuenta el tenant.** Exchange Online vigila el spam saliente de todo el
  tenant. Si lo compartes con una organización, su reputación de envío
  depende de la tuya: mantén `max_daily_sends` bajo y `require_approval: true`.

## Para desarrolladores

| Archivo | Qué es |
|---|---|
| `harvey/integrations/microsoft.py` | `MicrosoftProvider` (un `MailProvider`) y `run_auth_flow` |
| `harvey/integrations/mail_provider.py` | Registra `microsoft` en `NATIVE_PROVIDERS` y `get_mail_provider` |
| `harvey/cli.py` | `harvey microsoft auth\|test` |
| `tests/test_microsoft.py` | Graph y el inicio de sesión simulados con `httpx.MockTransport`; sin red |

`get_replies` **lanza** `GraphError` cuando no se puede leer la bandeja de entrada, en vez de
devolver `[]`. El handler lo convierte en una lectura fallida, y el
heartbeat detiene el envío. Devuelve toda la ventana de 7 días o nada:

- **Todas las páginas.** `limit` es solo el tamaño de página (`$top`). Harvey sigue
  `@odata.nextLink` hasta que Graph deja de enviarlo, usando el enlace exactamente
  como viene, sin volver a añadir los parámetros de la primera petición ni tocar
  `$skip`, como pide Microsoft. Los mensajes repetidos entre páginas (el correo nuevo
  desplaza `$skip` a mitad de la lectura) se devuelven una sola vez.
- **Los enlaces se comprueban antes de adjuntar el token.** Un `nextLink` debe ser
  `https://graph.microsoft.com` (puerto por defecto), con la ruta
  `/v1.0/me/mailFolders/inbox/messages`, con una query, y sin credenciales,
  fragmento, barra invertida ni caracteres de control. Un enlace que repite una
  página anterior es un bucle. En ambos casos la lectura falla sin enviar la petición.
- **Acotado.** Más de `MAX_INBOX_PAGES` (40) páginas, es decir, 2.000 mensajes
  en una semana con el tamaño de página por defecto, hace fallar la lectura en vez de truncarla.
- **Los datos malformados fallan.** Toda respuesta de Graph debe ser un objeto JSON; solo
  `202`/`204` (envío, borrado) pueden estar vacías. Una página cuyo `value` falte
  o no sea una lista, o un mensaje con una forma incorrecta (sin `id`, `from` o
  `body` que no sean un objeto, campos que no sean cadenas, cabeceras que no sean una lista) lanza una excepción. Un
  mensaje sin dirección de remitente se omite, como antes.

Limitaciones: un buzón con más de 2.000 mensajes en la bandeja de entrada en 7 días detiene
el envío en cada ciclo hasta que baje el volumen (sube `MAX_INBOX_PAGES` o el
tamaño de página). Si Graph llegara a devolver un `nextLink` con otra forma (por ejemplo
`/users/{id}/...`), las lecturas fallan de forma segura hasta que se amplíe la comprobación. El correo que
llega mientras se leen las páginas puede desplazar `$skip` y hacer que se pierda un mensaje
ese ciclo; el siguiente ciclo lo lee, ya que la ventana es de 7 días.

El servidor de callback de loopback escucha tanto en `127.0.0.1` como en `::1`, porque
`localhost` se resuelve a ambos y los navegadores difieren en cuál prueban.
