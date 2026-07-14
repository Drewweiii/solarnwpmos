#!/bin/bash
# Runs automatically on first container start (docker-entrypoint-initdb.d).
# Creates the separate database MLflow's backend store uses, alongside the
# main app database (POSTGRES_DB). App tables (cloud_obs, cloud_raster_frames,
# ...) are NOT auto-applied here - see each module's README for its migration.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE mlflow;
EOSQL
