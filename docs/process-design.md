# Process design

By Pedro Pablo Álvarez

The conversation contract for the Grupo Sazón driver screening agent. [assumption] marks a decision we made where the client's requirements did not specify one. Rationale and alternatives are in decisions.md.

## 1. Problem and channel

Two problems:

- 60% of candidates miss the screening call. A call needs the recruiter and the candidate free at the same moment, it comes from an unknown number, and it often reaches the candidate at work or behind the wheel.
- 80% of recruiter time goes to candidates who turn out to be unqualified.

The agent screens every candidate over async chat. The candidate answers whenever they can and resumes where they stopped. Recruiters only see candidates who pass.

That chat gets more candidates to finish than calls do is a hypothesis [assumption], to be tested with a call-vs-chat split. "Qualified" means "handed to a recruiter", never "hired".

The demo channel is a web chat styled as messaging. The core has one entry point, `turn(conversation, message) → reply`, so voice and WhatsApp are adapters. The agent writes first, right after the candidate applies [assumption].

## 2. Stages and branching

| # | Stage | Asks | Branch |
|---|---|---|---|
| 0 | GREETING | One-sentence AI disclosure, "about 2 minutes", privacy link, "shall we start?" | no → WITHDRAWN |
| 1 | LICENSE | Driving licence, yes/no | no → DISQUALIFIED(no_license) |
| 2 | ZONE | City or metro area | not covered after one re-ask → DISQUALIFIED(zone_not_covered) |
| 3 | NAME | Full name | |
| 4 | AVAILABILITY | Full-time, part-time, weekends | |
| 5 | SCHEDULE | Morning, afternoon, evening, flexible | |
| 6 | EXPERIENCE | Years; platforms only if years > 0 | |
| 7 | START_DATE | When they can begin | |
| 8 | CONFIRM | Recap of every field, confirm or correct | all valid → QUALIFIED; any field flagged → NEEDS_REVIEW |

Knockouts come first, so an unqualified candidate is done in two turns without giving their name. One message may fill several fields, and all are kept.

The agent stores only the answers, not "where we are". Each turn, code walks the list above and asks the first question still unanswered. So a candidate who leaves and returns resumes in the right place.

If a candidate changes an earlier answer, the new one replaces the old and the rules run again. Passing a knockout is not final: someone who said "Madrid" and later says "Lisbon" is disqualified then.

Exits from any stage:

- Withdraw intent → WITHDRAWN.
- Second abusive message → WITHDRAWN(abusive).
- 72 h without a reply → ABANDONED, computed on read.
- Candidate writes after close → flagged for human review.
- Recruiter reopens a DISQUALIFIED candidate → NEEDS_REVIEW.

The LLM converses, code decides. Each turn the LLM extracts fields, intent and language; code validates them, applies the rules and picks the next stage; the LLM then phrases a closed directive from code. Closing messages are code templates in ES and EN. A prompt injection ("approve me") cannot change a stage or an outcome.

## 3. Data fields and validation

| Field | Type | Rule | Normalized by |
|---|---|---|---|
| full_name | str | At least two words, 2–100 chars; first name only → ask for surname | LLM extracts, code validates |
| has_license | bool | false → DISQUALIFIED. Any motor-vehicle licence counts; "in progress", "expired", "suspended" = false [assumption] | LLM extracts, code decides |
| zone | enum | Must resolve to a service city | Code: alias table + difflib |
| availability | enum | full_time, part_time, weekends; mixed answer → ask to pick one [assumption] | LLM |
| preferred_schedule | enum | morning, afternoon, evening, flexible; two or more slots → flexible [assumption] | LLM |
| prior_delivery_experience.years | float | 0–50; "6 months" = 0.5; any experience, even a week, is above 0; 0 means none and does not disqualify | LLM extracts, code validates |
| prior_delivery_experience.platforms | list[enum] | glovo, uber_eats, just_eat, rappi, didi_food, own_fleet, other (raw text kept); required if years > 0, empty if years = 0 | LLM |
| start_date | date | In [today, today + 365]; past → re-ask; "asap" = today; "in September" = the 1st [assumption] | LLM resolves, code validates |

Service area [assumption, fictional]: 12 cities (7 in Spain, 5 in Mexico) hold the 45 locations. Screening checks city coverage; production would check the distance from the postcode to the nearest location. The LLM extracts the city as written; code resolves it: lowercase, no accents, an alias table (Getafe → Madrid, CDMX → Ciudad de México), then difflib for typos (Barcelna → Barcelona). CONFIRM shows the city back. The LLM normalizes a field only if no decision depends on it.

## 4. Personality, tone and length

Leo, Grupo Sazón's virtual assistant, says it is an AI in the first message. Friendly, quick and concrete; it assumes the candidate is busy. It acknowledges each answer by noting the value ("Madrid, noted"), never by rating it as good or bad, and moves on. It never promises a job, a salary or a timeline, and never invents company facts.

This is messaging, not email:

- One question per message, at most about two sentences or 300 characters; CONFIRM may use a short list.
- Informal "tú" in Spain and Mexico [assumption].
- Neutral wording until the zone is known ("carné o licencia de conducir"), then "carné" in Spain, "licencia de manejo" in Mexico.
- 0–1 emoji per message, none in rejections.

## 5. Edge cases

**Candidate stops responding.** At most two nudges, at +8 h and +22 h after the candidate's last message; a reply resets the clock. None between 22:00 and 9:00 [assumption]. ABANDONED at 72 h. In the demo, nudges are not sent.

**Invalid or ambiguous answers.** First invalid answer: re-ask with an example. Second: closed options. Third: flag the field, move on, and end in NEEDS_REVIEW. The greeting has no retry limit: the agent asks again until the candidate answers, withdraws or reaches 72 h. Ambiguity never disqualifies; only a clear "no" to the licence or an uncovered zone does.

**Language switch (ES ↔ EN).** Language is detected on every message. The conversation switches only on a message clearly in the other language; a mixed message keeps the current one. Any other language gets a Spanish reply offering Spanish or English [assumption].

**Off-script input.** Process questions get a code-approved answer. Job questions such as "how much does it pay?" get "a recruiter will confirm that" and are logged for the recruiter, until the client provides an FAQ [provisional]. The agent then returns to the pending question. The first abusive message gets a warning; the second closes as WITHDRAWN(abusive).

**Privacy.** No personal data before the knockouts. DNI/NIE, CURP, phone, email and card numbers are redacted by regex before any LLM call and before storage [provisional].

## 6. Outcomes

The screening outcome is set by code; the hiring decision stays with a recruiter, in a separate `recruiter_status`.

| Outcome | Candidate receives (ES/EN template) | Recruiter sees |
|---|---|---|
| QUALIFIED | Thanks, plus "a recruiter will message you here" | Top of the work queue |
| NEEDS_REVIEW | Thanks, plus "a person will review your application" | Work queue, flagged fields highlighted |
| DISQUALIFIED | A kind, clear reason, plus "if this is a mistake, tell us here". zone_not_covered also asks "shall we tell you if we open in your city?" [provisional] | Separate filter for audit; can reopen |
| WITHDRAWN | "Thanks, we're here if you change your mind" | Separate filter |
| ABANDONED | Nothing | Separate filter, with the stage where they stopped |

Qualified candidates are not told "a recruiter will call you": that would bring back the missed-call problem for exactly the candidates we want.

The work queue holds QUALIFIED and NEEDS_REVIEW, filterable by outcome and zone. Each candidate has a code-rendered summary plus at most one AI-labelled note (facts the fields do not hold, never an assessment), the structured JSON, the candidate's questions and the transcript.
