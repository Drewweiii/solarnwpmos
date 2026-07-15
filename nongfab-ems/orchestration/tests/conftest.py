"""himawari_ingestion.geolocation resolves config/assets.yaml at *import*
time (`_ASSETS = load_assets()` at module level), via nongfab_common.assets'
`__file__`-relative fallback path - which only lines up with the real repo
root for an editable (`pip install -e`) install. A regular install (e.g.
this package installed non-editably, matching how a real deployment would
build it) copies the package elsewhere, breaking that fallback - exactly
the scenario api/Dockerfile already works around with the same env var. Set
here, before pytest imports any test module (and transitively
nongfab_orchestration -> himawari_ingestion), so `import nongfab_orchestration`
doesn't require an editable install to succeed.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("NONGFAB_ASSETS_PATH", str(Path(__file__).resolve().parents[2] / "config" / "assets.yaml"))
