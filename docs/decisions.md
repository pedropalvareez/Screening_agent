# Decisions

Where the brief is silent or offers a choice, this file rules. Bonus features not listed here are out of scope.

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

## 002. LLM client

- Decision: OpenRouter through its OpenAI-compatible API. Model choice still open, to be recorded here.
- Alternative: a single provider's SDK.
- Trade-off: swapping models is a config change, at the cost of an extra hop and a third party in the data path.

## 003. Bonus: voice agent

- Decision: browser voice via ElevenLabs, calling an endpoint on the same FastAPI app so it runs the same screening flow.
- Alternative: no voice; another voice provider.
- Trade-off: covers the brief's "Great" tier; adds a paid external dependency and latency to every turn.
