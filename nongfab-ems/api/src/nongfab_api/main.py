"""Scaffold entrypoint - just enough for `docker compose up` to bring up a
healthy container. Real endpoints (/forecast/{horizon}, /simulate,
/performance, /assets, /ws/live, auth) land in a later step, not this one.
"""

from fastapi import FastAPI

app = FastAPI(title="Nong Fab EMS API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
