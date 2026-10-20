# Grupo Sazón screening agent

A conversational agent that screens delivery-driver applicants for Grupo Sazón, and a web panel where recruiters follow each candidate.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
cp .env.example .env        # fill in the API keys and the panel login
uv sync
uv run --env-file .env uvicorn sazon.api:app --app-dir src --reload
```

The candidate chat is at http://localhost:8000/ and the recruiter panel at http://localhost:8000/panel, behind `PANEL_USER` and `PANEL_PASSWORD`.

Conversations are stored in SQLite at `DB_PATH` (default `sazon.db` in the working directory). The record format is strict, so a database written by an older version may fail to load: delete it.

Checks (the same ones CI runs):

```sh
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```

Docker:

```sh
docker build -t sazon .
docker run --rm -p 8000:8000 --env-file .env -v sazon-data:/data sazon
```

The volume keeps the database between runs.

## Architecture

TBD.

## Design decisions

See [docs/decisions.md](docs/decisions.md).

## Improvements

TBD.
