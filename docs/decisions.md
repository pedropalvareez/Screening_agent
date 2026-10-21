# Decisions

Where the brief is silent or offers a choice, this file rules. Bonus features not listed here are out of scope.

Entries marked (provisional) come from the Phase 1 design and product sessions and may change.

Template:

```
## NNN. Title
- Decision:
- Alternative:
- Trade-off:
```

## 001. Stack

- Decision: Python, FastAPI, plain HTML/JS (no framework), SQLite, one Docker container.
- Alternative: a JS framework for the panel; Postgres; separate services.
- Trade-off: fewest moving parts for a demo-sized load; SQLite and a single process cap write concurrency, revisit before multi-instance deployment.

## 002. LLM client and model (provisional)

- Decision: OpenRouter through its OpenAI-compatible API. Model: Claude Haiku 5.5 at low effort for every call, confirmed by the scripted conversations in evals/ (#10) on per-field extraction accuracy, invalid-JSON rate, p50/p95 latency and the tone rules. Gemini 3.8 Flash is compared only where Haiku fails the bar below.
- Alternative: a single provider's SDK; Gemini 3.8 Flash; Haiku to extract plus Sonnet 5.5 to phrase.
- Trade-off: swapping models is a config change, at the cost of an extra hop and a third party in the data path. Haiku 5.5 is the cheapest fast option (about $7/week at 1K candidates), so cost does not decide at this scale; quality and latency do.
- Verified (spike, #6): model id `anthropic/claude-haiku-5.5`, called with `reasoning.effort: low`. json_schema is honoured only by the providers that enforce it (Anthropic, Azure, Google Vertex; not Amazon Bedrock or Claude Platform on AWS), so every request sets `provider.require_parameters`. The schema is the one Pydantic generates from schema.py minus the full-name regex: with the regex, OpenRouter answers "Schema is too complex" after about 200 s. parse_extraction still enforces it. One extraction takes 1.7–2.7 s through Anthropic or Azure and 7.6–8.6 s through Vertex; the first call with a new schema adds about 2.5 s. Requests therefore ask for Anthropic, then Azure, and keep the rest as fallbacks: about 1.1 s per extraction on a reused connection.
- Verified (#7): with only intent and language required, the model skipped keys the message gave ("el lunes que viene" 0/6, "media jornada" 1/3). The schema sent now requires every property, and a missing field is null: 15/15 on the same cases. A turn took 1.9–4.8 s with its two calls, and the recap turn 7.5–9.2 s.
- Verified (#10): `uv run --env-file .env pytest evals -m live` runs 11 scripted conversations 3 times each through turn(), with Haiku 5.5 as the app calls it and Sonnet 5.5 judging tone and notes: 24 min and under $1 a run. Bar, set before the first run: Haiku fails if an extraction stays invalid after the retry, a field is under 90% accurate, the p95 turn takes over 10 s, or a tone or notes rule fails in over 10% of cases after prompt fixes. Final run, 273 turns: 33/33 conversations end as scripted, 0 invalid JSON, every field 100% except intent at 99% ("Carmen, ya te lo he dicho" read as off_topic, 2/3), turn p50/p95 2.8/4.6 s. confirmed is scored where the engine reads it, the recap and the pool question; elsewhere the model set it 20 more times, on a yes to "¿Empezamos?" or a correction. Of 237 replies the LLM worded, by the code checks and the judge: none over 300 characters, in the wrong language, greeting, thanking for bad news or contradicting the directive; 4 promise or state a company fact (3 describe the screening after the duration answer, 1 calls own_fleet "our own fleet"); 1 has two question marks (an options list). Before the prompt fixes: 6 greetings or restarts ("Para empezar" after a job question, 3/3), "no experience is fine" after 6/6 zero-experience answers, and the English zone re-ask thanked them 1/3.
- Verified (#10, notes): of 33 closings, notes that name the candidate or use a gendered pronoun fell from 18 to 1, and Spanish notes from 9 to 0; 1 assesses the candidate. 11/33 (33%) state something the chat does not show, so Haiku fails the notes bar. Gemini 3.8 Flash, on the same transcripts and prompt, misstated facts in 17/66, wrote vaguer notes that left out both injection attempts, and took 11.5 s at p95: not adopted. #23 builds the notes' facts in code instead. The judge was checked against hand labels from Claude Code (not a human, and partly not blind: the run's report had listed the flagged items) on 30 replies and 16 notes. Agreement per reply rule: 26/30 to 30/30. On unsupported notes: 11/16 (4 both, 3 judge only, 2 labeller only), and extrapolated over all 33 the labels put the rate near the same third.

## 003. Bonus: voice agent (provisional)

- Decision: push-to-talk in the browser: recorded audio goes to ElevenLabs speech-to-text, the transcript runs through the same turn endpoint, and the reply comes back as ElevenLabs text-to-speech. Built last, first to cut if time runs short.
- Alternative: ElevenLabs Agents with a custom LLM pointing at our endpoint; no voice; another voice provider.
- Trade-off: covers the brief's "Great" tier with the same engine and no public tunnel during the demo; not real-time and no barge-in. Adds a paid external dependency and latency to every turn.

## 004. Channel (provisional)

- Decision: a web chat styled as messaging for the demo, built on a channel-agnostic core with one entry point, turn(conversation, message) → reply. WhatsApp is designed as a production adapter, not built. The agent sends the first message.
- Alternative: real WhatsApp through Twilio or Meta Cloud API; a Telegram bot.
- Trade-off: no new dependency and a reliable live demo; it is not the channel candidates actually use, so the jump to WhatsApp has to be explained. The QUALIFIED closing says a recruiter will message the candidate in the chat, but the demo panel cannot write into it: in production the recruiter replies through WhatsApp, which is not built.

## 005. Stage order and derived stage (provisional)

- Decision: GREETING (AI and privacy notice) → LICENSE → ZONE → NAME → AVAILABILITY → SCHEDULE → EXPERIENCE → START_DATE → CONFIRM. Knockout questions come first. One message may fill several fields. The stage is not stored; it is the first unmet requirement in that fixed order.
- Alternative: the brief's order with the name first; free slot-filling chosen by the LLM.
- Trade-off: unqualified candidates exit in two turns without giving personal data, and there is no stored stage to fall out of sync; the first two questions feel impersonal.

## 006. Turn pipeline (provisional)

- Decision: an extraction call returns every field present plus intent, language, the topic of any question and a yes/no to a confirmation (the CONFIRM recap or the 018 opt-in); Pydantic strict checks format; engine.py applies business rules and picks the next stage; code hands the LLM a closed directive to phrase. Closing messages, approved answers and the abuse warning are code templates in ES and EN, sent word for word. On LLM failure: one retry, then a template reply with state unchanged. Each call sees only what it needs: extraction sees the pending question, the agent's last message and the new message (with the full history it could re-extract stale values and undo a correction); phrasing sees the directive and no candidate text; the summary notes see the transcript. Storage keeps the full history.
- Alternative: one call returning fields and reply together; extraction plus fixed templates for every message.
- Trade-off: two calls per turn cost latency and money, in exchange for the LLM never deciding. Templated closings read less naturally but cannot promise anything the business did not approve.

## 007. Service zones (provisional)

- Decision: a fictional list of 12 cities holding the 45 locations; coverage is checked per city. ES: Madrid, Barcelona, Valencia, Sevilla, Málaga, Bilbao, Zaragoza. MX: Ciudad de México, Guadalajara, Monterrey, Puebla, Querétaro. The LLM extracts the city as written; code resolves it with a metro-area alias table and difflib. One re-ask before disqualifying; the re-ask shows the 12 cities as tap options grouped by country, plus "other city" to type one.
- Alternative: the LLM maps to the enum directly; a city dropdown from the first question; city plus neighbourhood mapped to one of the 45 locations; postcode to distance from the nearest location.
- Trade-off: only code decides coverage; the alias table is maintained by hand, and an unlisted suburb can be wrongly rejected, which the re-ask (the candidate taps the city the suburb belongs to) and recruiter review mitigate. Tap options cannot catch a wrong fuzzy match (Palencia read as Valencia), which only CONFIRM shows back. A dropdown first would cost the natural dialogue and leave uncovered towns without an option. City granularity also accepts candidates far from any location; postcode distance is the production fix, and it needs a postcode-to-coordinates table or a geocoder.

## 008. Field rules (provisional)

- Decision: full name has at least two words. Any motor-vehicle licence counts, and "in progress", "expired" or "suspended" count as no. Availability and preferred schedule are one enum value each, and two or more named slots become flexible. Prior delivery experience is one nested object, as in the brief: years as a float from 0 to 50 (0 does not disqualify and is flagged) and platforms as an enum plus other with the raw text, normalized by the LLM, required when years > 0 and empty when years = 0, a rule validated inside the submodel. Start date is an ISO date in [today, today + 365 days]; the LLM resolves relative dates and CONFIRM shows the result. Today is the candidate's date: Europe/Madrid or America/Mexico_City from the resolved zone, Spain until the zone is known.
- Alternative: 0 years disqualifies; start-date buckets; free-text platforms.
- Trade-off: no knockout the client did not ask for. The LLM normalizes only fields that no decision depends on.

## 009. Invalid answers and silence (provisional)

- Decision: first invalid answer → re-ask with an example; second → offer closed options; third → flag the field and move on, and the outcome becomes NEEDS_REVIEW. Ambiguity never disqualifies. Corrections are accepted until the conversation closes. A silent candidate resumes where they left off. ABANDONED is computed on read after 72 h of inactivity. Nudges are designed but not sent: at most two per conversation, at +8 h and +22 h after the candidate's last message, none at night.
- Alternative: disqualify after N failures; immediate human handoff; scheduler-driven nudges.
- Trade-off: some candidates reach recruiters incomplete, and no background process is needed.

## 010. Persona and tone (provisional)

- Decision: "Leo, Grupo Sazón's virtual assistant", disclosed as an AI. Informal "tú" in Spain and Mexico. One question per message, at most about 300 characters, country-specific wording once the zone is known, 0–1 emoji and none in rejections. Enforced by evals, not by truncation.
- Alternative: an unnamed assistant; "usted" in Mexico.
- Trade-off: warmer and easier to remember; length is a guideline checked offline, not a runtime guarantee.

## 011. Outcomes (provisional)

- Decision: QUALIFIED → "a recruiter will message you here". DISQUALIFIED → a clear reason plus "tell us here if this is a mistake"; anything written after close is flagged for human review. Also NEEDS_REVIEW, WITHDRAWN (including abusive) and ABANDONED.
- Alternative: "a recruiter will call you"; a generic rejection with no reason.
- Trade-off: the best candidates stay on the async channel. Stating the reason lets someone learn the passing answer, but every answer is self-declared anyway and the licence is checked at onboarding.

## 012. Recruiter panel (provisional)

- Decision: a work queue (QUALIFIED and NEEDS_REVIEW) with filters by outcome and zone; a detail view with summary, JSON, transcript and the candidate's questions; recruiter_status (pending, contacted, hired, rejected, showed_up, no_show; the last two measure 017's first shift) kept separate from the screening outcome; recruiters can reopen a DISQUALIFIED candidate, which moves it to NEEDS_REVIEW and keeps the screening's outcome for 017's guardrail. The panel is in English, like the summary. Basic auth from .env with fastapi.security.HTTPBasic and secrets.compare_digest.
- Alternative: a read-only panel; a kanban board; per-user accounts.
- Trade-off: real tracking for one enum and one endpoint; one shared credential, so there is no per-recruiter audit trail. The queue is not paginated and the server loads every record per request: fine for the demo, but at about 1,000 applications a week it grows every week, so before production store outcome and city in indexed columns and paginate.

## 013. Summary (provisional)

- Decision: the key-data block is rendered by code from validated fields, followed by 2–3 LLM notes labelled as AI-generated. Generated when a conversation reaches a terminal state.
- Alternative: a template only; an LLM-only summary.
- Trade-off: one extra call per closed conversation; the summary cannot contradict the fields.

## 014. Privacy (provisional)

- Decision: knockout questions before personal data. Regex redaction of DNI/NIE, CURP, phone, email and card numbers before every LLM call and before storage. OpenRouter set to exclude providers that train on inputs. EU routing and a retention period for disqualified candidates are designed, not enforced in the demo.
- Alternative: no redaction; enforce EU routing now.
- Trade-off: regexes miss cases but reduce what reaches a third party; EU routing may require a paid OpenRouter plan.

## 015. Bonus scope (provisional)

- Decision: in scope: multi-language (ES/EN), guardrails, tests and evals, minimal analytics (completion rate, drop-off stage, average duration) and voice (003). Possible but not in scope until decided: interview scheduling, FAQ answers by classification, sent re-engagement nudges.
- Alternative: many shallow bonus features.
- Trade-off: the rubric rewards depth; most chosen bonuses fall out of the core design.

## 016. Product direction (provisional)

- Decision: build the triage queue with business rules in code; that is the answer to "why not buy Paradox or Fountain": decisions are tested, auditable and immune to prompt injection. Designed but not built: auto-scheduling of onboarding when volume outgrows 13 recruiters (about 4,000 qualified a week at 10K applications), first-shift confirmation 48 h ahead, and inbound phone voice as another channel adapter. Languages stay ES/EN; each new language is one template set, chosen from candidate data.
- Alternative: build interview scheduling with fictional slots; an FAQ-first "sell, then screen" agent; real phone voice; ES/EN/PT/FR.
- Trade-off: everything built uses data the brief provides; the alternatives need client data we do not have, so they stay as designed phases.

## 017. Product metrics (provisional)

- Decision: two layers. Agent metric, owned by the agent and estimated in the demo: recruiter minutes per qualified candidate. Baseline from the brief: 80% of recruiter time goes to unqualified candidates, so each qualified candidate costs about 5 calls of recruiter time today [assumption: individual calls vary, but over time calls with qualified and unqualified candidates average the same length; unanswered attempts come on top]. With the agent, recruiters spend time only on QUALIFIED and NEEDS_REVIEW, so the cost falls toward one call per qualified plus the NEEDS_REVIEW load. Business outcome, influenced but not controlled by the agent: drivers who complete their first shift per week, measured in production through recruiter_status values showed_up and no_show. Supporting input: response rate (applied → started screening). Guardrails: rate of DISQUALIFIED reopened by a recruiter, and NEEDS_REVIEW share with a target below 10% [assumption], broken down by flagged field and by language. Diagnostics as in 015. That async messaging fixes the 60% is presented as a hypothesis, tested by a two-week 50/50 split between calls and chat.
- Alternative: first shift as the only north star; time from application to the recruiter queue; completion rate as headline; hires per week.
- Trade-off: the commitment is something the agent controls and the demo shows; whether it moves first shifts is a bet tested in production.

## 018. Talent pool for uncovered zones (provisional)

- Decision: a zone_not_covered closing asks "shall we tell you if we open in your city?". A yes stores consent, an expiry date 12 months out and the raw city. A no stores nothing; an unclear reply is flagged like any message after close. Reactivation is designed, not sent. Only worth it if Grupo Sazón plans to expand.
- Alternative: a pool for every rejection; design only.
- Trade-off: one boolean, one date and one template line keep an already-acquired candidate; it extends retention of personal data, so it needs explicit consent and an expiry.

## 019. Candidate questions (provisional)

- Decision: the agent answers process questions (duration, next steps, data use) from code-approved text. Job questions (pay, vehicle, insurance) get "a recruiter will confirm that" and are logged for the recruiter, until the client provides an FAQ. The extraction tags each question with a topic (duration, next_steps, data_use, other) and code picks the text; any other topic goes to a recruiter. This is the narrow case of 015's "FAQ answers by classification": three approved process answers, no job facts.
- Alternative: a fictional full FAQ; log everything.
- Trade-off: the agent never states a company fact the business did not approve; candidates asking about pay wait for a person.

## 020. First message (provisional)

- Decision: one sentence of AI disclosure, "about 2 minutes", a privacy link and a yes/no question, as a code template. Variants for A/B tests are assigned by hash(conversation_id) % 2 and stored in SQLite.
- Alternative: full privacy notice up front; disclosure in the second message. PostHog for flags and funnels is a possible production dependency, not added.
- Trade-off: the first message decides the response rate, so it stays short; disclosure is never deferred.

## 021. Bias checks (provisional)

- Decision: AI notes in the summary describe facts (questions asked, hesitations) and never assess the candidate, checked by evals. The NEEDS_REVIEW guardrail is broken down by language.
- Alternative: hide the zero-experience flag; mention bias only in the presentation.
- Trade-off: two cheap checks on the least visible bias, weaker Spanish leading to more flagged fields; the zero-experience flag stays and the breakdown shows whether it hurts.

## 022. Eval consistency metric

- Decision: the evals report no per-scenario pass@k or pass^k. Each scenario runs 3 times as separate tests, so the suite is green only when every run ends as scripted: pass^3 is enforced, not printed. The report gives the pooled rate over all conversations and lists each failed run by label, which shows which scenario failed and how often.
- Alternative: group runs by scenario in metrics() and print c/3 per scenario plus pass^3 as one headline number (about 6 lines, no extra calls). pass@k was ruled out: a candidate gets one conversation and no retries.
- Trade-off: comparing prompt changes means counting failure lines by hand. With 3 runs, 3/3 does not prove a scenario reliable; a meaningful pass^k needs about 10 runs, roughly three times the eval cost. Worth adding if prompts keep changing between eval runs.

## Open questions

For Orbio:
- The RAG bonus mentions a provided FAQ: does it exist, and where (019)?
- Is the demo live or recorded, and does the evaluator run the code locally?
- Should the docs and presentation be in English or Spanish?

For the client:
- Which job FAQ answers may the agent give (019)?
- Expansion plans to new cities (018)?
- Who provides the vehicle, and are drivers employees or self-employed?
- Who records the first-shift date and the show-up?
- Are minimum age or work permit requirements, and so knockouts?
- How do candidates apply today, and do we get their phone number?
- Average screening call length, and does the 80% figure include unanswered calls (017)?
- Is there an ATS to export candidates to?
- Are recruiters split by country?

To verify:
- Paradox, Fountain and Workstream feature claims.
- AI Act transparency article and dates; Ley Rider scope.
- ElevenLabs Agents telephony.
- PostHog EU hosting.

Pending:
- Demo story.
