from fastapi import FastAPI

app = FastAPI(title="Grupo Sazón screening")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
