# nongfab-common

Shared library: loads and Pydantic-validates `config/assets.yaml` — the
single source of truth for Nong Fab plant geometry (3 zones: GIS, ISB,
Jetty). Every module that needs zone coordinates, capacity, or equipment
specs should depend on this rather than duplicating numbers.

```python
from nongfab_common.assets import load_assets, target_bbox

registry = load_assets()  # resolves config/assets.yaml relative to the repo root
gis = registry.zone("GIS")
lat_min, lat_max, lon_min, lon_max = target_bbox(registry)  # union of all zones + buffer
```

Path resolution for `load_assets()`: explicit argument > `NONGFAB_ASSETS_PATH`
env var > repo-relative default (`config/assets.yaml`).

## Install (editable, from a consuming module's venv)

```bash
pip install -e ../../libs/nongfab_common
```

No workspace tool (uv/pdm) wired up yet for this monorepo, so this is a
manual step for now — each consuming module's README says so.

## Run tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```
