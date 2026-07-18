-- Visitor network v2: per-browser chat identity (display name + avatar)
-- since the viewer/operator demo logins are shared credentials (multiple
-- real people can be signed in as the same `username`) - display_name/
-- avatar/client_id let the chat UI tell them apart, LINE-style. Nullable:
-- older rows (written before this migration) simply fall back to the raw
-- username/a default avatar in application code.
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0006_chat_profile_and_history.sql

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS avatar TEXT;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS client_id TEXT;
