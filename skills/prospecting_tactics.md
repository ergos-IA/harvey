# Tácticas de prospección DIY

El playbook de Harvey para encontrar leads sin herramientas caras como Apollo, ZoomInfo o Clearbit.

---

## Estrategia 1: Google dorking

### Encontrar perfiles de LinkedIn
```
site:linkedin.com/in "VP Marketing" "SaaS" "Madrid"
site:linkedin.com/in "Head of Growth" "agencia de marketing"
site:linkedin.com/in "{{title}}" "{{industry}}" "{{location}}"
```

### Encontrar páginas de equipo de una empresa
```
site:{{domain}} "equipo" OR "quiénes somos" OR "team" OR "about"
"{{company name}}" "equipo" "{{title}}"
```

### Encontrar empresas de un sector
```
"{{industry}}" "Series A" OR "Series B" site:crunchbase.com
"{{industry}}" empresa "{{location}}" "empleados" site:linkedin.com/company
```

### Encontrar patrones de email
```
"@{{domain}}" email
site:{{domain}} "contacto" OR "email" OR "@"
"{{first_name}} {{last_name}}" "{{company}}" email
```

---

## Estrategia 2: búsqueda en LinkedIn

### Operadores de búsqueda de personas
- **Cargo**: busca "VP Marketing" para encontrar coincidencias exactas de cargo
- **Empresa**: filtra por empresa actual
- **Ubicación**: filtra por región geográfica
- **Sector**: filtra por las categorías de sector de LinkedIn
- **Conexiones**: las conexiones de segundo grado tienen mayor tasa de aceptación

### Sales Navigator (si está disponible)
- Búsqueda booleana: "VP Marketing" AND "SaaS" NOT "consultant"
- Búsquedas guardadas con alertas de nuevas coincidencias
- Listas de leads para una prospección ordenada

### Sin Sales Navigator
- Usa la búsqueda básica de LinkedIn con combinaciones de palabras clave
- Explora "Otras personas también vieron" en perfiles relevantes
- Revisa las páginas de empresa, pestaña "Personas", para ver empleados
- Busca dentro de grupos de LinkedIn relevantes

---

## Estrategia 3: rastreo de la web de la empresa

### Páginas de equipo / quiénes somos
La mayoría de las empresas publican su equipo directivo en páginas como /team, /about, /about-us, /our-team, /people, /leadership (o /equipo, /quienes-somos).

**Extrae:**
- Nombre + cargo de las fichas del equipo
- A veces el email o los enlaces de LinkedIn aparecen directamente
- Un indicador del tamaño de la empresa según el número de miembros del equipo

### Ofertas de empleo
- Las empresas que contratan para roles que tu producto apoya = prospectos de alta intención
- Revisa las páginas /careers, /jobs (o /empleo, /trabaja-con-nosotros)
- Revisa también portales de empleo: Indeed, LinkedIn Jobs, InfoJobs, Wellfound (para startups)

### Descubrimiento del stack tecnológico
- **BuiltWith/Wappalyzer**: identifica las herramientas que usan
- Útil para: "Veo que usáis {{competitor}}, así es como nos comparamos"
- Hay extensiones de navegador gratuitas

---

## Estrategia 4: descubrimiento de patrones de email

### Formatos de email habituales (por orden de frecuencia)
1. `first.last@domain.com` (el más común)
2. `first@domain.com`
3. `firstlast@domain.com`
4. `flast@domain.com` (inicial del nombre + apellido)
5. `firstl@domain.com`
6. `f.last@domain.com`
7. `last.first@domain.com`
8. `first_last@domain.com`
9. `first-last@domain.com`

### Métodos de verificación (gratuitos)
1. **Comprobación de registro MX**: verifica que el dominio acepta correo (consulta DNS)
2. **SMTP RCPT TO**: pregunta al servidor de correo si la dirección existe
3. **Plan gratuito de Hunter.io**: 25 búsquedas/mes + 50 verificaciones/mes
4. **Formato a partir de direcciones conocidas**: si conoces el email de una persona de la empresa, el patrón se aplica a todos

### Dominios catch-all
Algunos dominios aceptan todas las direcciones (catch-all). La verificación SMTP no funciona en ellos. Apóyate en el patrón + la verificación del dominio.

---

## Estrategia 5: eventos desencadenantes (trigger events)

Señales de momento de alto valor que indican que un prospecto puede estar listo para comprar:

1. **Nueva incorporación en un rol relevante**: están construyendo la función que tú apoyas
2. **Financiación reciente**: tienen presupuesto para gastar
3. **Lanzamiento de un producto nuevo**: necesitan apoyo de marketing/crecimiento
4. **Oferta de empleo en el ámbito de tu producto**: están invirtiendo en esa área
5. **Un competidor usa tu producto**: ángulo de prueba social
6. **Expansión de la empresa**: los equipos que crecen necesitan herramientas nuevas
7. **Cambio de liderazgo**: los nuevos líderes traen herramientas nuevas
8. **Cambio de stack tecnológico**: están evaluando alternativas

### Dónde encontrar eventos desencadenantes (gratis)
- Alertas de Google Noticias para las empresas objetivo
- LinkedIn: sigue a las empresas objetivo para ver sus novedades
- Crunchbase (plan gratuito): anuncios de financiación
- Blogs de empresa y páginas de notas de prensa
- Portales de empleo: ofertas nuevas en los departamentos relevantes

---

## Estrategia 6: minería de referidos

Cuando un prospecto dice "no soy la persona adecuada":
1. Pregunta quién ES la persona adecuada (nombre + cargo)
2. Pregunta si estaría dispuesto a hacer una presentación
3. Si no hay presentación, usa su nombre como prueba social: "{{name}}, de tu equipo, me sugirió que te escribiera..."

Cuando se cierra una venta:
1. Pide referidos de empresas parecidas
2. Pregunta si conocen a colegas de otras empresas con retos similares
3. LinkedIn: revisa sus conexiones en busca de coincidencias con el ICP

---

## Cuotas diarias de prospección

Para construir un pipeline sostenible:
- **Investigación**: 20-30 empresas al día
- **Nuevos prospectos identificados**: 10-15 al día
- **Emails verificados**: 10-15 al día
- **Total de prospectos añadidos a la base de datos**: 10-15 al día
- **Control de calidad**: puntúa a cada prospecto antes de añadirlo a la prospección
