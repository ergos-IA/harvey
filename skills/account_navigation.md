# Navegación de cuentas: trabajar varios contactos en una misma empresa

## Empresas y contactos

Una empresa es una cuenta. Un contacto es una persona de esa empresa. Una empresa puede tener muchos contactos. Harvey debe crear siempre primero el perfil de la empresa y después asociarle los contactos.

## Perfiles de empresa

Toda empresa que Harvey investigue debe tener:
- **Name**: el nombre real de la empresa
- **Domain**: el dominio de su web (p. ej., acme.com)
- **Website**: la URL completa
- **Description**: qué hace la empresa (1-2 frases)
- **Industry**: sector principal
- **Company size**: rango de empleados
- **Location**: ciudad/región de la sede
- **Source**: cómo la encontró Harvey (google, linkedin, website scrape)
- **Source URL**: la URL exacta donde Harvey encontró la información

Harvey debe sacar esto de la web de la empresa, de su página de empresa en LinkedIn o de los resultados de Google. No adivines. Si no puedes verificar un campo, déjalo en blanco.

## Perfiles de contacto

Todo contacto debe tener como mínimo:
- **First name**: obligatorio. Real y verificado.
- **Last name**: obligatorio. Real y verificado.
- **Title**: obligatorio. Debe ser su cargo actual real.
- **Company**: vinculada al perfil de la empresa.

Campos opcionales (rellénalos solo si son verificables):
- **Email**: inclúyelo solo si está verificado mediante comprobación MX/SMTP o aparece en la web de la empresa. Marca email_verified = true solo si está confirmado.
- **Phone**: muy difícil de encontrar. Inclúyelo solo si figura públicamente (web de la empresa, perfil de LinkedIn). Marca phone_verified = true solo si está confirmado. NO inventes números de teléfono.
- **LinkedIn URL**: inclúyela si la encuentras.
- **Seniority**: c_suite, vp, director, manager, individual. Dedúcelo del cargo.
- **Department**: Sales, marketing, engineering, operations, etc. Dedúcelo del cargo.

### Reglas de calidad de datos
1. Nunca inventes datos de contacto. Si no puedes verificarlos, no los incluyas.
2. Los patrones de email (nombre.apellido@dominio.com) solo son válidos tras una verificación SMTP.
3. Un contacto sin email verificado puede seguir siendo valioso para LinkedIn.
4. Registra siempre dónde encontraste cada dato (source + source_url).

## A quién contactar en una empresa

### La matriz del punto de entrada

No todos los contactos valen lo mismo. A quién escribes primero depende del tipo de operación:

| Tipo de operación | Primer contacto | Segundo contacto | Evitar al principio |
|-------------------|-----------------|------------------|---------------------|
| **Compra pequeña** (<500 $/mes) | Usuario final / responsable | Su jefe | C-suite (demasiado alto) |
| **Mid-market** (500-5.000 $/mes) | Director / VP | Responsable que lo usaría | Contribuidores individuales |
| **Enterprise** (5.000+ $/mes) | VP / C-suite | Champion (responsable que lo defenderá) | Personal junior |

### Multi-threading: trabajar varios contactos

Cuando Harvey encuentra varios contactos en una empresa:

1. **Empieza por uno.** Nunca escribas a varias personas de la misma empresa a la vez. Parece spam y comparan notas.

2. **Empieza al nivel adecuado.** Elige a la persona con más probabilidades de:
   - Sentir el problema que resuelve tu producto
   - Tener autoridad para evaluar soluciones
   - Leer y responder realmente al email

3. **Sube o baja según la respuesta:**
   - ¿Sin respuesta del responsable? Prueba con el VP.
   - ¿El VP dice "habla con mi equipo"? Escribe al responsable y menciona al VP.
   - ¿El responsable está interesado? Pregúntale si quiere incluir a su jefe.

4. **Espera entre contactos.** Si escribes a la persona A de Acme, espera al menos 5 días laborables antes de escribir a la persona B de Acme. Trata la empresa como una sola cuenta, no como contactos sueltos.

5. **Comparte el contexto entre contactos.** Si la persona A respondió, Harvey debe saberlo al escribir a la persona B. "Tu compañera Sara comentó que está evaluando opciones" tiene mucho peso.

### Detección de seniority

Deduce la seniority a partir del cargo:

- **C-Suite**: CEO, CTO, CFO, CMO, COO, CRO, "Chief __", director general, consejero delegado
- **VP**: VP, Vice President, SVP, EVP, "Head of __", director de área
- **Director**: Director, Senior Director, "Director of __", director/a de departamento
- **Manager**: Manager, Senior Manager, Team Lead, "Manager of __", responsable, jefe de equipo
- **Individual**: Analyst, Specialist, Coordinator, Associate, Engineer, analista, técnico, especialista

### Cuándo parar

Deja de contactar con una empresa si:
- Has escrito a 3 contactos distintos sin respuesta
- Cualquier contacto dice explícitamente "no me interesa" o "dejad de escribirme"
- La empresa no encaja con el ICP tras investigar más

## Verificación con una muestra

Antes de añadir prospectos al pipeline real, Harvey debe crear un lote de muestra de 5-10 perfiles de empresa y contacto y presentárselo al usuario para que lo revise. Así se asegura que:

1. La segmentación del ICP es correcta (sectores y tamaños de empresa adecuados)
2. Los cargos de los contactos coinciden con lo que quiere el usuario
3. La calidad de los datos cumple las expectativas
4. Las fuentes de investigación son legítimas

### Flujo de la muestra
1. Harvey investiga 5-10 empresas y sus contactos
2. Las presenta como muestra: "Aquí tienes 8 empresas que he encontrado. Cada una tiene 1-2 contactos. Échales un vistazo y dime si son el tipo de objetivo correcto."
3. El usuario revisa y da su opinión ("demasiado pequeñas", "sector equivocado", "perfecto", "ya trabajamos con ellos")
4. Harvey ajusta la segmentación según el feedback
5. Tras la aprobación, Harvey continúa con la prospección completa

Este paso de muestra solo ocurre una vez al principio (o cuando cambia el ICP). Una vez que el usuario aprueba la muestra, Harvey prospecta de forma autónoma.
