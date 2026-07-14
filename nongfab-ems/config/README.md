# Config — single source of truth for plant geometry

`assets.yaml` (Step 2, not yet created — pending real zone/equipment specs
from the architecture doc) will hold the 3 zones (GIS 50kW, ISB 150kW, Jetty
200→600kW) with corner coordinates, centroids, and the Jetty's panel/inverter
layout (Trina 715W panels, SUN2000-50KTL-M3×4, sub-arrays 01A.L..05A.R, EL
points). `ingestion/himawari/src/himawari_ingestion/geolocation.py`'s
hardcoded `NONG_FAB_BBOX` will be replaced with a value derived from this
file once it exists.
