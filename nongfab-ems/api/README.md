# Module 6 — Backend API (scaffold)

Not implemented yet — this is just enough for `docker compose up` to bring
up a healthy container per Step 1. Only route: `GET /healthz`.

Planned (later step, not this one): `GET /forecast/{horizon}`, `POST
/simulate`, `GET /performance`, `GET /assets`, `WS /ws/live`, OAuth2+JWT+RBAC
(admin/operator/viewer), auto-generated OpenAPI docs.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
uvicorn nongfab_api.main:app --reload
```
