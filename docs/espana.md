# Harvey para España: cuentas seleccionadas y señales locales

Este fork añade un flujo "por cuentas" (ABM): en lugar de descubrir miles de negocios en
mapas, importas una lista corta de empresas elegidas, Harvey las enriquece con señales
españolas, las puntúa con tus reglas y solo trabaja las que pasan el corte.

## Flujo

```bash
harvey accounts import cuentas.csv --batch lote-01 --segment industrial   # o --dry-run
harvey signals --confirm HIRING_FUNCTION,BORME_APPOINTMENT,BORME_CAPITAL,BORME_MERGER,NEWS_EXPANSION,NEWS_ACQUISITION,NEWS_INVESTOR,NEWS_LEADERSHIP
harvey accounts enrich --batch lote-01            # web, empleo, BORME y prensa
harvey accounts score --segment industrial         # ranking con las reglas que han sumado
harvey accounts cohort --min-score 60 --csv lote-01.csv
```

El bucle de Harvey vuelve a enriquecer las cuentas cada `accounts.enrich_every_days` días.

## CSV de cuentas

Cabeceras en español o inglés; separador `,`, `;` o tabulador; UTF-8 o Windows-1252.

| Columna | Obligatoria | Notas |
|---|:-:|---|
| `name` / `nombre` | sí | Nombre comercial |
| `domain` / `web` | sí | Se deduplica por dominio |
| `legal_name` / `razon_social` | no | Nombre registral: mejora el cruce con BORME e InfoJobs |
| `cif`, `segment`, `province`, `employees`, `revenue_eur`, `notes` | no | Admite "1.200", "12,5 M€" o "51-200" |

## Señales

| Señal | Fuente | Coste |
|---|---|---|
| `MULTILANG_SITE`, `EXPORTS`, `HELPDESK_TOOL`, `ECOMMERCE_PLATFORM`, `B2B_PORTAL`, `ERP_MENTION` | Su web (la portada que ya se descarga) | Gratis |
| `HIRING_FUNCTION` | Portal de empleo enlazado en su web (Personio, Teamtailor, Factorial, JOIN, SmartRecruiters, Workable…) y API de InfoJobs (`INFOJOBS_CLIENT_ID` / `INFOJOBS_CLIENT_SECRET`) | Gratis |
| `BORME_APPOINTMENT`, `BORME_CAPITAL`, `BORME_MERGER` | API de datos abiertos del BOE, sección A | Gratis |
| `NEWS_EXPANSION`, `NEWS_ACQUISITION`, `NEWS_INVESTOR`, `NEWS_LEADERSHIP` | RSS de Google News en español | Gratis (sus condiciones hablan de uso personal y no comercial: revísalas) |
| `ICP_SCORE` | Calculada con tus reglas de `scoring` | — |

## Puntuación

En `harvey.local.yaml` (no se sube al repo):

```yaml
scoring:
  threshold: 60
  segments:
    <segmento>:
      rules:
        - {signal: HIRING_FUNCTION, when: {older_than_days: 60}, points: 20}
        - {signal: EMPLOYEE_COUNT, when: {between: [50, 1000]}, points: 10}
        - {signal: BORME_APPOINTMENT, when: {within_months: 12}, points: 10}
```

Condiciones: `exists`, `min`, `max`, `between`, `older_than_days`, `within_days`,
`within_months`, `contains_any`, `contains_none`, `min_confidence`.

## Idioma y cumplimiento

- Los agentes escriben en español salvo que el prospecto use otro idioma.
- Bajas reconocidas sin modelo: "baja", "no gracias", "dadme de baja", "no me escribáis"…
- Escalan a una persona: abogado, denuncia, AEPD, RGPD, LOPD, LSSI, burofax…
- Zona horaria por destinatario: península `Europe/Madrid`, Canarias `Atlantic/Canary`.
- Revisa con tu asesor la LSSI (art. 21) antes de enviar correo comercial no solicitado.
