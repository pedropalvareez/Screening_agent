# Needs review: no single availability option (Mexico)

Three availability answers name no single option. After the third, code flags the field and moves on, and the screening ends in NEEDS_REVIEW for a recruiter. Zapopan resolves to Guadalajara, so Leo uses Mexico's wording.

Real run on 2026-10-25 with Claude Haiku 5.5 via OpenRouter, through `sazon.turn.start` and `turn`. The candidate's messages were scripted and are fictional; everything below is what the app stored.

## Transcript

As stored, after redaction.

> **Leo:** ¡Hola! Soy Leo, el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas sobre tu solicitud de repartidor: unos 2 minutos. Privacidad: https://gruposazon.example/privacidad. ¿Empezamos?

> **Candidate:** Hola, sí

> **Leo:** ¿Tienes carné o licencia de conducir?

> **Candidate:** Sí, tengo licencia de manejo

> **Leo:** Perfecto, carné anotado. ¿En qué ciudad o pueblo vives?

> **Candidate:** Vivo en Zapopan

> **Leo:** Perfecto, Zapopan anotado. ¿Me compartes tu nombre completo, con apellido?

> **Candidate:** Rocío Mendoza Paredes

> **Leo:** Gracias, Rocío. ¿Qué disponibilidad tienes: tiempo completo, medio tiempo o solo fines de semana?

> **Candidate:** Depende de la semana, entre semana o los fines

> **Leo:** Entiendo, no se pudo registrar. ¿Qué disponibilidad tienes: tiempo completo, medio tiempo o solo fines de semana? Por ejemplo: "medio tiempo".

> **Candidate:** Es que cambia cada semana, no sabría decirte

> **Leo:** ¿Cuál es tu disponibilidad: tiempo completo, medio tiempo o solo fines de semana?

> **Candidate:** Un poco de todo: unas semanas tiempo completo y otras solo fines

> **Leo:** ¿En qué horario prefieres trabajar: mañana, tarde, noche o cualquier horario?

> **Candidate:** Por las mañanas

> **Leo:** Perfecto, mañana anotado. ¿Cuánto tiempo llevas haciendo reparto y en qué plataformas?

> **Candidate:** Un año en DiDi Food

> **Leo:** Anotado, un año con Didi Food. ¿Desde qué fecha podrías empezar?

> **Candidate:** El 1 de noviembre

> **Leo:** Anotado, 1 de noviembre de 2026. Este es tu resumen:
>
> - Nombre: Rocío Mendoza Paredes
> - Licencia de manejo: sí
> - Zona: Zapopan → Guadalajara (MX)
> - Disponibilidad: sin indicar
> - Horario preferido: mañana
> - Experiencia: 1 año en didi_food
> - Fecha de inicio: 1 de noviembre de 2026
>
> ¿Está todo bien así?

> **Candidate:** Sí, correcto

> **Leo:** ¡Gracias! Una persona revisará tu solicitud.

## Extracted fields

The validated screening fields. The zone stays as written; code resolves the service city, shown in the summary.

```json
{
  "full_name": "Rocío Mendoza Paredes",
  "has_license": true,
  "zone": "Zapopan",
  "availability": null,
  "preferred_schedule": "morning",
  "prior_delivery_experience": {
    "years": 1.0,
    "platforms": [
      "didi_food"
    ],
    "other_platform": null
  },
  "start_date": "2026-11-01"
}
```

## Summary

Rendered by code from the screening state:

```text
Outcome: needs_review
Full name: Rocío Mendoza Paredes
Driving licence: yes
Zone: Zapopan → Guadalajara (MX)
Availability: not given
Preferred schedule: morning
Delivery experience: 1 years on didi_food
Start date: 2026-11-01
Flagged fields: availability
Invalid answers: availability 3
```

AI-generated note: The candidate says availability changes weekly, sometimes full-time and sometimes weekends only, which the key data's "not given" availability does not capture.
