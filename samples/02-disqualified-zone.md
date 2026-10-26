# Disqualified: city not covered, then the talent-pool opt-in

Mérida is outside the service area. Leo asks once more, and the chat shows the service cities as tap options (they come from the state, so the transcript does not hold them). Leo then closes as zone_not_covered and asks whether to tell the candidate if Grupo Sazón opens there. The yes stores a consent that expires in 12 months.

Real run on 2026-10-25 with Claude Haiku 5.5 via OpenRouter, through `sazon.turn.start` and `turn`. The candidate's messages were scripted and are fictional; the transcript, fields and summary below are what the app stored.

## Transcript

As stored, after redaction.

> **Leo:** ¡Hola! Soy Leo, el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas sobre tu solicitud de repartidor: unos 2 minutos. Privacidad: https://gruposazon.example/privacidad. ¿Empezamos?

> **Candidate:** Sí, claro

> **Leo:** ¿Tienes carné o licencia de conducir?

> **Candidate:** Sí, tengo licencia

> **Leo:** Perfecto, carné anotado. ¿En qué ciudad o pueblo vives?

> **Candidate:** Vivo en Mérida, Yucatán

> **Leo:** Mérida todavía no está en nuestra zona de reparto. ¿Vives en alguna de nuestras ciudades de servicio o cerca de una? Elige una de la lista de abajo o escribe otra ciudad.

> **Candidate:** No, sigo en Mérida y ninguna me queda cerca

> **Leo:** Gracias por tu interés. De momento no repartimos en tu ciudad, así que no podemos seguir. Si es un error, dínoslo aquí. ¿Quieres que te avisemos si abrimos en tu ciudad?

> **Candidate:** Sí, avísenme por favor

> **Leo:** ¡Hecho! Te avisaremos si abrimos en tu ciudad.

## Extracted fields

The validated screening fields. The zone stays as written; code resolves the service city, shown in the summary.

```json
{
  "full_name": null,
  "has_license": true,
  "zone": "Mérida",
  "availability": null,
  "preferred_schedule": null,
  "prior_delivery_experience": null,
  "start_date": null
}
```

## Talent-pool consent

```json
{
  "at": "2026-10-25T17:46:11.329955Z",
  "expires_on": "2027-10-25",
  "city": "Mérida"
}
```

## Summary

Rendered by code from the screening state:

```text
Outcome: disqualified (zone_not_covered)
Full name: not given
Driving licence: yes
Zone: Mérida → not covered
Availability: not given
Preferred schedule: not given
Delivery experience: not given
Start date: not given
Flagged fields: none
Answers naming an uncovered city: 2
```

AI-generated note: The candidate wrote that they live in Mérida, Yucatán, and that none of the service cities is close to them.
