# Language switch to English, with a phone number redacted

The candidate's first reply asks to go on in English, and Leo switches. The phone number in the name message is replaced with [phone] before the LLM call and before storage, so neither OpenRouter nor the database sees it.

Real run on 2026-10-25 with Claude Haiku 5.5 via OpenRouter, through `sazon.turn.start` and `turn`. The candidate's messages were scripted and are fictional; everything below is what the app stored.

## Transcript

As stored, after redaction.

> **Leo:** ¡Hola! Soy Leo, el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas sobre tu solicitud de repartidor: unos 2 minutos. Privacidad: https://gruposazon.example/privacidad. ¿Empezamos?

> **Candidate:** Sorry, can we do this in English?

> **Leo:** Just to confirm, do you want to start the application now?

> **Candidate:** Yes, let's start

> **Leo:** Do you hold a valid driving licence?

> **Candidate:** Yes, I have a full driving licence

> **Leo:** Thanks, got your driving licence. Which city or town do you live in?

> **Candidate:** I live in Seville

> **Leo:** Thanks, Seville noted. What's your full name, first name and surname?

> **Candidate:** Sam Taylor Ruiz. You can also call me on [phone]

> **Leo:** Thanks, Sam. What's your availability: full-time, part-time, or weekends only?

> **Candidate:** Part time

> **Leo:** Got it, part-time. What schedule works best for you: morning, afternoon, evening, or flexible?

> **Candidate:** Mornings, ideally

> **Leo:** Got it, mornings work for you. How long have you done delivery work, and on which platforms?

> **Candidate:** About six months with Uber Eats

> **Leo:** Thanks, got it: about six months on Uber Eats. When could you realistically start?

> **Candidate:** In two weeks

> **Leo:** Thanks, noted: you can start on 8 November 2026. Here's your recap:
>
> - Full name: Sam Taylor Ruiz
> - Driving licence: yes
> - Zone: Sevilla (ES)
> - Availability: part-time
> - Preferred schedule: morning
> - Delivery experience: 0.5 years on Uber Eats
> - Start date: 8 November 2026
>
> Is this all correct?

> **Candidate:** Yes, that's right

> **Leo:** All done, thanks! A recruiter will message you here. 🙌

## Extracted fields

The validated screening fields. The zone stays as written; code resolves the service city, shown in the summary.

```json
{
  "full_name": "Sam Taylor Ruiz",
  "has_license": true,
  "zone": "Seville",
  "availability": "part_time",
  "preferred_schedule": "morning",
  "prior_delivery_experience": {
    "years": 0.5,
    "platforms": [
      "uber_eats"
    ],
    "other_platform": null
  },
  "start_date": "2026-11-08"
}
```

## Summary

Rendered by code from the screening state:

```text
Outcome: qualified
Full name: Sam Taylor Ruiz
Driving licence: yes
Zone: Seville → Sevilla (ES)
Availability: part_time
Preferred schedule: morning
Delivery experience: 0.5 years on uber_eats
Start date: 2026-11-08
Flagged fields: none
```

AI-generated note: none (the model answered NONE).
