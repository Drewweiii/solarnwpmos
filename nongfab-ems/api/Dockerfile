# Build context is the repo root (see docker-compose.yml: `context: .`,
# `dockerfile: api/Dockerfile`), not api/ itself. nongfab-api's pyproject.toml
# depends on bare package names (nongfab-common, nongfab-features,
# nongfab-forecast, nongfab-simulation) that are only published inside this
# monorepo, not on PyPI - so every sibling is copied in and they're all
# installed together in ONE pip command below.
#
# One command, not one-per-package: a per-package sequential install lets a
# later package (forecast's heavy ML stack) downgrade a shared compiled dep
# (numpy) *after* an earlier package (features) already installed pandas/pvlib
# wheels built against the previous numpy - a resolver split that installs
# cleanly but leaves an ABI-inconsistent env that crashes at import
# ("numpy._core.multiarray failed to import"). A single resolver pass picks
# one numpy that satisfies every package and installs all compiled wheels
# against it consistently. pip still resolves the bare nongfab-* names to the
# local paths given as args (same run), so nothing is fetched from the index.
FROM python:3.11-slim

WORKDIR /app

COPY libs/nongfab_common/pyproject.toml ./libs/nongfab_common/pyproject.toml
COPY libs/nongfab_common/src ./libs/nongfab_common/src
COPY features/pyproject.toml ./features/pyproject.toml
COPY features/src ./features/src
COPY forecast/pyproject.toml ./forecast/pyproject.toml
COPY forecast/src ./forecast/src
COPY simulation/pyproject.toml ./simulation/pyproject.toml
COPY simulation/src ./simulation/src
COPY api/pyproject.toml ./api/pyproject.toml
COPY api/src ./api/src
RUN pip install --no-cache-dir ./libs/nongfab_common ./features ./forecast ./simulation ./api

# libs/nongfab_common's load_assets() falls back to a repo-relative path
# derived from its own installed __file__ location, which is fragile across
# install modes - point it at the copy below explicitly instead.
COPY config/assets.yaml ./config/assets.yaml
ENV NONGFAB_ASSETS_PATH=/app/config/assets.yaml

EXPOSE 8000
# Shell form (not exec form) so ${PORT} expands: platforms like Railway inject
# a PORT env var the app must bind to, while docker-compose leaves it unset and
# falls back to 8000. --proxy-headers so the app trusts the platform's
# X-Forwarded-* headers (correct scheme/host behind Railway's TLS proxy).
#
# `cd /data` first (silently no-op if it doesn't exist, e.g. docker-compose
# local dev with no volume attached): registry.py's MLflow tracking URI and
# API_TIMESCALE_DSN's sqlite file are resolved relative to the process's cwd
# at startup, not relative to each other - verified empirically that
# mlflow.pyfunc.log_model()'s artifact ("mlruns/") lands under cwd regardless
# of the sqlite DB's own path. Without this, both the auth DB and every
# trained model would be wiped on every redeploy/restart (Railway containers
# have no persistent disk outside an attached Volume).
CMD cd /data 2>/dev/null; uvicorn nongfab_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers
