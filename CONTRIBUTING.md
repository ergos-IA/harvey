# Contribuir a Harvey

Para quien modifique este repositorio y abra pull requests, y sobre todo
para los agentes de programación (Claude Code, Codex, Cursor, Aider). `CLAUDE.md` es distinto:
guía a quien *usa* Harvey. Este archivo trata de cómo contribuir a Harvey.

## Ningún dato de contacto real, en ningún sitio que se publique

Este repositorio es público. El trabajo de Harvey consiste en encontrar a personas reales en negocios reales,
así que al probarlo aparecen nombres, direcciones y teléfonos reales. Esos datos se quedan en
tu máquina. Una vez, un pull request enumeró las direcciones de trabajo de trece personas reales,
con sus nombres y empleadores, en su descripción y en sus fixtures de test, y
limpiarlo supuso reescribir la rama.

**No incluyas nunca nada de esto en un commit, test, fixture, comentario, docstring, documento,
entrada del changelog, mensaje de commit, título de PR, descripción de PR, comentario de PR, revisión o
issue:**

- el nombre, la dirección de email, el teléfono o la dirección postal de una persona real;
- un negocio real encontrado durante las pruebas: su nombre, dominio, URL del sitio web o
  ubicación, incluido el HTML copiado de su sitio;
- cualquier cosa sacada de `data/harvey.db`, de la exportación de un usuario, de un elemento del Outbox, de una respuesta
  o de una ejecución de prueba en vivo.

**Haz esto en su lugar:**

- Escribe los fixtures a mano con negocios y personas ficticios. Usa los nombres
  reservados allí donde el código los acepte: `example.com`, `example.net`,
  `example.org`, y los dominios de primer nivel `.example`, `.test` y `.invalid`. Los
  marcadores de posición del estilo `acme.com` están bien. A las personas inventadas
  ponles nombres inventados y genéricos.
- Cuando un test necesite marcado que falló en un sitio real, reconstruye la estructura que
  falló (un `<br>` dentro de un span, la forma de una frase, un bloque schema.org) con
  contenido ficticio. No recortes una copia de la página real.
- Informa de las comprobaciones en vivo solo como recuentos y tipos: "encontré al decisor en 17
  de 19 sitios de pequeños negocios (tejadistas, dentistas, bufetes de abogados)". No una tabla
  por sitio, ni las direcciones encontradas, ni los dominios probados. Guarda los resultados
  detallados en tu directorio temporal local.
- Se puede nombrar a proveedores e infraestructura, porque no son contactos:
  Google, Cloudflare, Hunter, Instantly, DataForSEO, Greenhouse, etc.
  También se puede nombrar a empresas citadas solo por datos públicos de producto (de quién era el formato
  de bolsa de empleo que se probó). Su personal, no.

**Antes de hacer push o abrir un PR**, revisa el diff y la descripción que vas
a publicar en busca de direcciones:

```bash
git diff origin/main | grep '^+' | grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}' | sort -u
```

Todo resultado debe ser un marcador de posición. Si alguno no lo es, corrígelo antes de hacer push. Una vez
que algo se sube a un repositorio público, borrarlo después no lo elimina:
los commits antiguos siguen accesibles por su hash y las descripciones de los PR conservan un
historial de ediciones.

## Email de prueba y de verificación

Todo email de prueba o de verificación va a una dirección que sea tuya, creada
para ese fin. Nunca a una dirección de una base de datos, una exportación, una respuesta o un fixture.
Los tests nunca envían email real: usa los proveedores falsos de `tests/`.
