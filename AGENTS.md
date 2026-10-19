# AGENTS.md

Screening agent for Grupo Sazón delivery drivers + recruiter panel. Python, FastAPI, SQLite, OpenRouter, ElevenLabs.

- docs/assignment.md is the client brief. Its core requirements and deliverables are mandatory; never contradict them. It is gitignored: if it is missing, ask for it before continuing.
- Where the brief is silent or offers a choice (LLM, stack, which bonus features), docs/decisions.md rules. Bonus features not listed there are out of scope. docs/process-design.md (pending) will be the conversation contract. Create no other docs.
- If a task or decision seems to conflict with the brief, stop and ask. Do not resolve it yourself.
- The LLM converses, code decides: disqualification, service zones, allowed values and stage transitions live in schema.py and engine.py, never in prompts or in code that handles LLM output.
- One Pydantic schema is the single source of truth for screening fields and JSON output. Validate at every boundary with models using `ConfigDict(strict=True, extra="forbid")`. Never duplicate a type.
- No `cast`, `Any`, `type: ignore` or `noqa` to silence errors, and no defaults that hide failures. Fix the cause of a lint or type error.
- Never disable, skip or loosen a check to get green: never edit config, tests, lockfile, CI, thresholds or timeouts to make a change pass. Unsure about a test, config or dependency: ask. Ask before adding any dependency.
- Tests check behavior through contracts, not implementation details. Always state whether a result was verified with the fake LLM or a real model.
- Privacy: only fictional personal data in tests, evals and samples/. Secrets only in .env. Never simplify away requested privacy measures.
- Report honestly: what you ran, with its real output, vs. what you did not run or are assuming. Never claim something ran when it did not.
- Branches `type/short-topic`, commits `type(scope): outcome` (Conventional Commits types: feat, fix, docs, test, refactor, chore). No merge or deploy without the repo owner's approval.
- Ponytail applies to all code. emilkowalski/skills apply ONLY to src/sazon/web/: no stock photos, no landing-page heroes.
- Skill locations: `.agents/skills/` holds agent-agnostic skills linked from this file; `.claude/skills/` holds skills Claude Code auto-loads. Do not move or symlink between them: Claude Code reads only `.claude/skills/`, and symlinks break on Windows clones.
- Code and docs in English.

## Scope and Ponytail

- Before implementing a code change, read and use [Ponytail](.agents/skills/ponytail/SKILL.md). Use its default `full` mode unless the user specifies another mode. Let it guide reuse, dependencies, abstractions, and the smallest correct solution.
- Before finalizing a code change or requesting review, use [Ponytail Review](.agents/skills/ponytail-review/SKILL.md) on the complete task diff. It covers bugs, security, load, missing tests, and unnecessary complexity; also review accessibility and behavior.
- Stay within the requested objective. Do not include unrelated linting, formatting, refactoring, or import changes. A Ponytail finding does not authorize a repository-wide cleanup.
- Preserve user-owned changes. Report unrelated findings without fixing them or creating issues automatically.
- Challenge unnecessary complexity with a concrete alternative. Do not simplify away explicitly requested behavior, validation, security, accessibility, or error handling.

## Checks

All must pass: `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest`
