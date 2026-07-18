-- Visitor network (Track 2): site-wide chat message history + admin
-- feedback inbox. Not hypertables - low-volume operational tables, not
-- time-series metrics like the other modules' data.
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0005_chat_and_feedback.sql

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username    TEXT         NOT NULL,
    role        TEXT         NOT NULL,
    text        TEXT         NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback_messages (
    id          INTEGER      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username    TEXT         NOT NULL,
    role        TEXT         NOT NULL,
    text        TEXT         NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
