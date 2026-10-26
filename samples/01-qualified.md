# Qualified, in Spanish (Spain)

One message gives both availability and schedule, so Leo skips the schedule question. Alcorcón resolves to the Madrid service city.

Real run on 2026-10-25 with Claude Haiku 5.5 via OpenRouter, through `sazon.turn.start` and `turn`. The candidate's messages were scripted and are fictional; the transcript, fields and summary below are what the app stored.

## Transcript

As stored, after redaction.

> **Leo:** ¡Hola! Soy Leo, el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas sobre tu solicitud de repartidor: unos 2 minutos. Privacidad: https://gruposazon.example/privacidad. ¿Empezamos?

> **Candidate:** ¡Hola! Sí, vamos

> **Leo:** ¿Tienes carné o licencia de conducir?

> **Candidate:** Sí, tengo el carné B

> **Leo:** Perfecto, carné anotado. ¿En qué ciudad o pueblo vives?

> **Candidate:** Vivo en Alcorcón

> **Leo:** Alcorcón, anotado. Ahora, ¿cuál es tu nombre completo, con apellido?

> **Candidate:** Elena Ruiz Navas

> **Leo:** Gracias, Elena. ¿Qué disponibilidad tienes: jornada completa, media jornada o solo fines de semana?

> **Candidate:** Jornada completa, y prefiero tardes

> **Leo:** Perfecto, jornada completa por la tarde. ¿Cuánto tiempo llevas haciendo reparto y en qué plataformas?

> **Candidate:** Dos años en Glovo

> **Leo:** Perfecto, dos años en Glovo. ¿A partir de qué fecha podrías empezar?

> **Candidate:** Dentro de una semana

> **Leo:** Anotado, empiezas el 1 de noviembre de 2026. Este es tu resumen:
>
> - Nombre: Elena Ruiz Navas
> - Carné de conducir: sí
> - Zona: Alcorcón → Madrid
> - Disponibilidad: jornada completa
> - Horario preferido: tarde
> - Experiencia: 2 años en Glovo
> - Fecha de inicio: 1 de noviembre de 2026
>
> ¿Está todo bien o hay algo que quieras cambiar?

> **Candidate:** Sí, todo correcto

> **Leo:** ¡Listo, gracias! Un reclutador te escribirá por aquí. 🙌

## Extracted fields

The validated screening fields. The zone stays as written; code resolves the service city, shown in the summary.

```json
{
  "full_name": "Elena Ruiz Navas",
  "has_license": true,
  "zone": "Alcorcón",
  "availability": "full_time",
  "preferred_schedule": "afternoon",
  "prior_delivery_experience": {
    "years": 2.0,
    "platforms": [
      "glovo"
    ],
    "other_platform": null
  },
  "start_date": "2026-11-01"
}
```

## Summary

Rendered by code from the screening state:

```text
Outcome: qualified
Full name: Elena Ruiz Navas
Driving licence: yes
Zone: Alcorcón → Madrid (ES)
Availability: full_time
Preferred schedule: afternoon
Delivery experience: 2 years on glovo
Start date: 2026-11-01
Flagged fields: none
```

AI-generated note: none (the model answered NONE).
