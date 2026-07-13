-- Module 1 (Himawari ingestion): hypertable for parsed cloud observations.
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0001_cloud_obs.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS cloud_obs (
    time              TIMESTAMPTZ      NOT NULL,
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    cloud_opacity_pct DOUBLE PRECISION NOT NULL CHECK (cloud_opacity_pct BETWEEN 0 AND 100),
    cloud_index       DOUBLE PRECISION NOT NULL CHECK (cloud_index BETWEEN -0.2 AND 1.5),
    source            TEXT             NOT NULL,
    raw_object_key    TEXT,
    ingested_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (time, source)
);

SELECT create_hypertable('cloud_obs', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_cloud_obs_time ON cloud_obs (time DESC);
