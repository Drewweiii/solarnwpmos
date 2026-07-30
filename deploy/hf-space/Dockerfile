# Hugging Face Space (Docker SDK) image for the Nong Fab EMS API.
#
# WHY THIS FILE EXISTS SEPARATELY from nongfab-ems/api/Dockerfile: a Docker
# Space requires a file named exactly `Dockerfile` at the ROOT of the Space
# repo - the path is not configurable - and its build context is that root,
# which holds the whole monorepo. So every COPY here is prefixed
# `nongfab-ems/`, unlike the api/ Dockerfile whose context is `nongfab-ems/`
# itself. `deploy/hf-space/push.sh` is what puts this at the Space root.
#
# Three HF-specific constraints this is built around (docs: Docker Spaces):
#   1. The container runs as uid 1000. Create that user BEFORE any COPY and
#      always `COPY --chown=user`, or the app cannot read its own files.
#   2. Port 7860 by default (README.md's `app_port` must agree).
#   3. Disk is NOT persistent - anything written is lost on restart/sleep,
#      and `/data` exists only with a paid Storage Bucket attached. That costs
#      this app almost nothing, because API_REAL_DATA_DB_PATH already defaults
#      to an in-memory store and the auth tables are recreated on startup.
#      See STATE_DIR below for what we still keep per-session.
FROM python:3.11-slim

# HF runs the container as uid 1000; set the user up first so every COPY can
# hand ownership straight over (a recursive chown afterwards would duplicate
# every file into a new layer and balloon the image).
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# CPU-ONLY TORCH, INSTALLED FIRST AND DELIBERATELY.
# forecast/ depends on neuralforecast and neuralprophet, which both pull torch.
# From the default index that resolves to the CUDA build: roughly 2.5 GB of
# NVIDIA libraries this Space can never use, since free HF hardware is CPU-only
# (2 vCPU / 16 GB RAM). Pinning the CPU wheel from PyTorch's own index cuts that
# to a couple of hundred MB, which is the difference between a build that
# finishes comfortably and one that crawls or trips a size limit.
#
# It must come BEFORE the monorepo install: pip then sees torch already
# satisfied and will not go fetch the CUDA wheel to satisfy the same
# constraint.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

# Same single-pip-command rule as nongfab-ems/api/Dockerfile, for the same
# reason: installing these one at a time lets a later package downgrade a
# shared compiled dep (numpy) after an earlier one already installed wheels
# built against the previous version, producing an env that installs cleanly
# then dies at import with "numpy._core.multiarray failed to import". One
# resolver pass picks one numpy for everybody.
COPY --chown=user nongfab-ems/libs/nongfab_common/pyproject.toml ./libs/nongfab_common/pyproject.toml
COPY --chown=user nongfab-ems/libs/nongfab_common/src ./libs/nongfab_common/src
COPY --chown=user nongfab-ems/features/pyproject.toml ./features/pyproject.toml
COPY --chown=user nongfab-ems/features/src ./features/src
COPY --chown=user nongfab-ems/forecast/pyproject.toml ./forecast/pyproject.toml
COPY --chown=user nongfab-ems/forecast/src ./forecast/src
COPY --chown=user nongfab-ems/simulation/pyproject.toml ./simulation/pyproject.toml
COPY --chown=user nongfab-ems/simulation/src ./simulation/src
COPY --chown=user nongfab-ems/financial/pyproject.toml ./financial/pyproject.toml
COPY --chown=user nongfab-ems/financial/src ./financial/src
COPY --chown=user nongfab-ems/ingestion/nwp/pyproject.toml ./ingestion/nwp/pyproject.toml
COPY --chown=user nongfab-ems/ingestion/nwp/src ./ingestion/nwp/src
COPY --chown=user nongfab-ems/ingestion/himawari/pyproject.toml ./ingestion/himawari/pyproject.toml
COPY --chown=user nongfab-ems/ingestion/himawari/src ./ingestion/himawari/src
COPY --chown=user nongfab-ems/ingestion/nasa_power/pyproject.toml ./ingestion/nasa_power/pyproject.toml
COPY --chown=user nongfab-ems/ingestion/nasa_power/src ./ingestion/nasa_power/src
COPY --chown=user nongfab-ems/ingestion/pvgis/pyproject.toml ./ingestion/pvgis/pyproject.toml
COPY --chown=user nongfab-ems/ingestion/pvgis/src ./ingestion/pvgis/src
COPY --chown=user nongfab-ems/api/pyproject.toml ./api/pyproject.toml
COPY --chown=user nongfab-ems/api/src ./api/src
RUN pip install --no-cache-dir \
      ./libs/nongfab_common ./features ./forecast ./simulation ./financial \
      ./ingestion/nwp ./ingestion/himawari ./ingestion/nasa_power ./ingestion/pvgis \
      ./api

# load_assets() otherwise guesses a repo-relative path from its own installed
# __file__, which is fragile across install modes - point at this copy.
COPY --chown=user nongfab-ems/config/assets.yaml ./config/assets.yaml
ENV NONGFAB_ASSETS_PATH=/home/user/app/config/assets.yaml

# Per-session scratch, replacing the api/ Dockerfile's `cd /data`. registry.py's
# MLflow tracking URI and any sqlite file are resolved relative to the
# process's cwd at startup, so the entrypoint cds here to keep them together
# and out of the source tree. This is NOT persistent on a free Space - it is
# only about not scattering writes; anything here is gone after a restart.
ENV STATE_DIR=/home/user/app/state
RUN mkdir -p "$STATE_DIR"

# HF's default exposed port. README.md's `app_port` must match this.
ENV PORT=7860
EXPOSE 7860

# Shell form so ${PORT} expands. --proxy-headers so the app trusts HF's
# X-Forwarded-* headers and builds correct absolute URLs behind their TLS
# proxy (same reason as the Railway image).
CMD cd "$STATE_DIR" && uvicorn nongfab_api.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers
