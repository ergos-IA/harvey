# Estrategia de ofertas y mecánica de cierre

## Regla base: gánate el derecho a pedir

Nunca empieces con una oferta. Nunca vendas en un email en frío. El primer contacto existe para iniciar una conversación, no para cerrar una venta.

Las ofertas solo se presentan cuando el prospecto ha mostrado un interés genuino:
- Ha respondido en positivo
- Ha hecho una pregunta sobre el producto
- Ha expresado un problema que puedes resolver
- Ha preguntado por el precio o los siguientes pasos

Si no ha pasado nada de esto, sigues en la fase de "ganar atención". Quédate ahí.

## La escalera de ofertas

No todos los prospectos interesados reciben la misma oferta. Ajusta la oferta a su nivel de implicación:

| Nivel de implicación | Señal | Oferta |
|----------------------|-------|--------|
| **Curious** (curioso) | Hizo una pregunta, hizo clic en un enlace | Responde a su pregunta + CTA suave ("Encantado de explicártelo si te sirve") |
| **Interested** (interesado) | Expresó un problema, preguntó por funcionalidades | Comparte un recurso o caso de éxito relevante + propón una llamada breve |
| **Ready** (listo) | Preguntó por precio, plazos o siguientes pasos | Presenta la oferta concreta con un siguiente paso claro |
| **Urgent** (urgente) | Tiene una fecha límite, perdió a su proveedor actual, está contratando | Actúa rápido: presenta la oferta de inmediato con un encuadre de urgencia |

## Construir ofertas a partir del conocimiento del producto

Cuando Harvey conoce un producto (mediante rastreo de la web o entrenamiento manual), debe identificar:

1. **Oferta principal**: ¿qué es lo principal que vendemos? (p. ej., suscripción de software, servicio, auditoría/evaluación)
2. **Ofertas de entrada**: formas de empezar con menos compromiso (p. ej., prueba gratuita, programa piloto, auditoría gratuita, sesión de estrategia)
3. **Ofertas de prueba**: formas de demostrar valor antes de pedir dinero (p. ej., informe de muestra, evaluación gratuita, calculadora de ROI)

### Marco para construir la oferta

Para cada producto, determina:
- **Qué obtienen**: entregable o acceso concreto (no un "valor" vago)
- **Qué cuesta**: precio, dedicación de tiempo o "gratis"
- **Qué arriesgan**: nada (prueba gratuita), garantía de devolución o mes a mes
- **Qué ocurre después**: la mecánica exacta: hacer clic en un enlace, responder con horarios, rellenar un formulario

### Ejemplos de estructuras de oferta

**Producto SaaS:**
- Entrada: "Tenemos una prueba gratuita de 14 días, sin tarjeta de crédito. ¿Quieres que te prepare una?"
- Principal: "Los planes empiezan en X $/mes. ¿Quieres que te explique qué plan tiene más sentido para tu equipo?"

**Servicio/Agencia:**
- Entrada: "Solemos empezar con una auditoría gratuita de 30 minutos de vuestra configuración actual. ¿Te interesa?"
- Principal: "Nuestro servicio habitual empieza en X $/mes. Puedo preparar un alcance a medida si me cuentas más sobre vuestra situación."

**Consultoría:**
- Entrada: "He preparado un análisis rápido de [su situación concreta]. ¿Quieres que te lo mande?"
- Principal: "Lo hacemos como un proyecto [cerrado/con iguala]. ¿Hacemos una llamada de 20 minutos para ver si tiene sentido?"

## Mecánica de cierre: cómo reservar

La forma de pedir el siguiente paso importa. Confirma siempre con el usuario qué mecánica usar:

### Opción 1: enlace de calendario
Mejor cuando: hay mucho volumen, se busca un aire de autoservicio y el usuario tiene una herramienta de agenda.
```
"Aquí tienes mi calendario por si quieres reservar 15 minutos: [LINK]"
```
- Úsalo cuando la configuración del producto incluya un `booking_url`
- Especifica siempre la duración ("15 minutos", "llamada rápida de 20 min")
- Nunca digas "reserva una demo": di "reserva un hueco" o "hacemos una llamada"

### Opción 2: proponer horas concretas
Mejor cuando: se busca un trato más personal, una venta de más contacto y no hay herramienta de agenda.
```
"¿Te viene bien el jueves a las 14:00 o el viernes por la mañana para una llamada rápida?"
```
- Ofrece exactamente 2-3 opciones
- Incluye siempre día + hora
- Mantén la ventana estrecha (la misma semana)

### Opción 3: preguntar por su preferencia
Mejor cuando: son prospectos enterprise, hay que respetar su agenda o son decisores de alto nivel.
```
"¿Cómo tienes la agenda esta semana para 15 minutos rápidos?"
```
- Deferente pero con tiempo acotado
- Bueno para C-suite, donde no quieres parecer presuntuoso

### Opción 4: siguiente paso sin llamada
Mejor cuando: el producto se vende solo y el prospecto solo necesita acceso.
```
"¿Quieres que te cree una cuenta de prueba? Son 2 minutos."
```
- Para productos de autoservicio con prueba gratuita
- Sáltate la llamada si el producto habla por sí mismo

## Qué debe confirmar Harvey con el usuario

Durante la configuración o el entrenamiento, Harvey necesita saber:

1. **¿Cuál es la oferta principal?** (suscripción, servicio, prueba, auditoría, etc.)
2. **¿Hay una oferta de entrada?** (prueba gratuita, auditoría gratuita, muestra, etc.)
3. **¿Cuál es el objetivo de la prospección?** (reservar una llamada, empezar una prueba, conseguir una respuesta, etc.)
4. **¿Cómo deben reservarse las reuniones?**
   - Enlace de calendario (proporcionar la URL)
   - Proponer horas
   - Preguntar por su preferencia
5. **¿Quién atiende la reunión?** (el usuario, alguien del equipo comercial, Harvey reserva y otra persona acude)
6. **¿Hay alguna cualificación antes de reservar?** (tamaño de empresa, presupuesto, necesidad concreta)

Estas respuestas van a `harvey.yaml`, en la configuración del producto, e influyen en cómo Harvey redacta los emails y gestiona las respuestas.

## Momento de la oferta en la secuencia

### Secuencia de email en frío (3 emails)
- **Email 1**: sin oferta. Inicia una conversación. Haz una pregunta. Comparte una idea.
- **Email 2**: mención suave solo si es relevante. "Ayudamos a equipos como el tuyo a [hacer tal cosa]. ¿Hablamos?"
- **Email 3**: email de despedida. Algo más directo, pero sin venta dura. "Si ahora no es prioridad, sin problema. Pero si [punto de dolor] surge, aquí estoy."

### Gestión de respuestas (tras mostrar interés)
- **Primera respuesta con interés**: reconoce, responde a su pregunta y luego presenta la oferta de entrada o propón una llamada.
- **Seguimiento tras el interés**: si se quedaron callados después de mostrar interés, un solo recordatorio amable. Nunca más de uno.
- **Listo para reservar**: presenta la mecánica de cierre concreta. Sé directo. "Vamos a poner algo en la agenda."

## Reglas de lenguaje

**Sí di:**
- "¿Hablamos un momento?"
- "Encantado de explicártelo"
- "¿Tendría sentido que reserváramos 15 minutos?"
- "¿Quieres que te mande [cosa concreta]?"

**Nunca digas:**
- "Reserva una demo" (suena a discurso comercial)
- "Agenda una llamada con nuestro equipo" (impersonal)
- "Me encantaría enseñártelo" (enfoque egocéntrico)
- "Avísame si te interesa" (pasivo, sin siguiente paso claro)
- "¿Cuándo estás libre?" (demasiado abierto)

## Cómo gestionar "¿cuánto cuesta?"

Cuando un prospecto pregunta por el precio antes de haberlo cualificado:

1. Da una respuesta real: nunca esquives la pregunta
2. Enmárcala con contexto: "Los planes empiezan en X $/mes, según [variable]. La mayoría de los equipos de tu tamaño están en el plan [nivel]."
3. Pivota hacia la cualificación: "Para darte una cifra exacta, me ayudaría saber [pregunta concreta sobre sus necesidades]."
4. Si hay una oferta de entrada gratuita, empieza por ella: "Hay una prueba gratuita para que veas si encaja antes de comprometerte con nada."
