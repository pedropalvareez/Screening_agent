# Grupo Sazón screening agent

A conversational agent that screens delivery-driver applicants for Grupo Sazón, and a web panel where recruiters follow each candidate.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
cp .env.example .env        # fill in the API keys
uv sync
uv run uvicorn sazon.api:app --app-dir src --reload
```

Checks (the same ones CI runs):

```sh
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```

Docker:

```sh
docker build -t sazon .
docker run --rm -p 8000:8000 --env-file .env sazon
```

## Architecture

TBD.

## Design decisions

See [docs/decisions.md](docs/decisions.md).

## Improvements

TBD.
