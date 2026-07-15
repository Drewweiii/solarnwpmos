# Build context is the repo root (see docker-compose.yml: `context: .`,
# `dockerfile: api/Dockerfile`), not api/ itself. nongfab-api's pyproject.toml
# depends on bare package names (nongfab-common, nongfab-features,
# nongfab-forecast, nongfab-simulation) that are only published inside this
# monorepo, not on PyPI - so every sibling has to be copied in and installed,
# in dependency order, before `pip install ./api` so those names already
# resolve locally when pip reaches them instead of trying (and failing) to
# fetch them from the index.
FROM python:3.11-slim

WORKDIR /app

COPY libs/nongfab_common/pyproject.toml ./libs/nongfab_common/pyproject.toml
COPY libs/nongfab_common/src ./libs/nongfab_common/src
RUN pip install --no-cache-dir ./libs/nongfab_common

COPY features/pyproject.toml ./features/pyproject.toml
COPY features/src ./features/src
RUN pip install --no-cache-dir ./features

COPY forecast/pyproject.toml ./forecast/pyproject.toml
COPY forecast/src ./forecast/src
RUN pip install --no-cache-dir ./forecast

COPY simulation/pyproject.toml ./simulation/pyproject.toml
COPY simulation/src ./simulation/src
RUN pip install --no-cache-dir ./simulation

COPY api/pyproject.toml ./api/pyproject.toml
COPY api/src ./api/src
RUN pip install --no-cache-dir ./api

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
CMD uvicorn nongfab_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers
