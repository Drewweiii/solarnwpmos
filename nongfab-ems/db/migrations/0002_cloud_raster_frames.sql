-- Module 1 (Himawari ingestion): hypertable for cloud-tile frame metadata.
-- The pixel arrays themselves are stored in MinIO as .npz (raster_object_key
-- points to the object); this table is a lightweight, queryable index over
-- them plus the single-point sample already used by cloud_obs.
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0002_cloud_raster_frames.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS cloud_raster_frames (
    time                        TIMESTAMPTZ      NOT NULL,
    source                      TEXT             NOT NULL,
    lat_min                     DOUBLE PRECISION NOT NULL,
    lat_max                     DOUBLE PRECISION NOT NULL,
    lon_min                     DOUBLE PRECISION NOT NULL,
    lon_max                     DOUBLE PRECISION NOT NULL,
    rows                        INTEGER          NOT NULL CHECK (rows > 0),
    cols                        INTEGER          NOT NULL CHECK (cols > 0),
    nong_fab_cloud_opacity_pct  DOUBLE PRECISION NOT NULL CHECK (nong_fab_cloud_opacity_pct BETWEEN 0 AND 100),
    nong_fab_cloud_index        DOUBLE PRECISION NOT NULL CHECK (nong_fab_cloud_index BETWEEN -0.2 AND 1.5),
    motion_speed_kmh            DOUBLE PRECISION,
    motion_direction_deg        DOUBLE PRECISION CHECK (motion_direction_deg IS NULL OR motion_direction_deg BETWEEN 0 AND 360),
    raster_object_key           TEXT,
    ingested_at                 TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (time, source)
);

SELECT create_hypertable('cloud_raster_frames', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_cloud_raster_frames_time ON cloud_raster_frames (time DESC);
