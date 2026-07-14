-- Module 2 (NCEP/NOAA NWP ingestion): hypertable for GFS forecast points.
-- Keyed on (issue_time, valid_time, source), not just (valid_time, source):
-- successive GFS cycles overlap in valid_time, and Module 4's training needs to
-- reconstruct "what was known as of issue_time X", not just the latest overwrite.
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0003_nwp_forecast.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS nwp_forecast (
    issue_time              TIMESTAMPTZ      NOT NULL,
    valid_time               TIMESTAMPTZ      NOT NULL,
    source                    TEXT             NOT NULL,
    latitude                  DOUBLE PRECISION NOT NULL,
    longitude                 DOUBLE PRECISION NOT NULL,
    ssrd_w_m2                 DOUBLE PRECISION NOT NULL CHECK (ssrd_w_m2 BETWEEN 0 AND 1500),
    temp2m_c                  DOUBLE PRECISION NOT NULL CHECK (temp2m_c BETWEEN -30 AND 60),
    wind10m_u_ms               DOUBLE PRECISION NOT NULL,
    wind10m_v_ms               DOUBLE PRECISION NOT NULL,
    relative_humidity_pct      DOUBLE PRECISION NOT NULL CHECK (relative_humidity_pct BETWEEN 0 AND 105),
    raw_object_key             TEXT,
    ingested_at                TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (issue_time, valid_time, source)
);

-- Hypertable partitioned on valid_time (not issue_time): most consumers query
-- "what forecast values are valid around time T", which valid_time answers directly.
SELECT create_hypertable('nwp_forecast', 'valid_time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_nwp_forecast_valid_time ON nwp_forecast (valid_time DESC);
CREATE INDEX IF NOT EXISTS idx_nwp_forecast_issue_time ON nwp_forecast (issue_time DESC);
