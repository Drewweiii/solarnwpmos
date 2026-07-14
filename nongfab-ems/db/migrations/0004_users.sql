-- Module 6 (Backend API): users table for JWT/RBAC auth.
-- Not a hypertable (users aren't a time series) - a plain table on the same
-- shared Postgres database the other modules' hypertables live in.
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0004_users.sql

CREATE TABLE IF NOT EXISTS users (
    id                INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username          TEXT         NOT NULL UNIQUE,
    hashed_password   TEXT         NOT NULL,
    role              TEXT         NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
