-- Visitor network v3: private 1:1 messaging instead of one public/open
-- shared room (2026-07-18, at the user's explicit request - broadcasting
-- every message to every connected visitor was a real privacy problem, not
-- just a UX one). `recipient_client_id` is who a message is addressed to;
-- an index on (client_id, recipient_client_id) supports the conversation-
-- scoped lookups GET /chat/history now does (both directions of a pair, so
-- also index the reverse column order).
-- Apply with: psql "$TIMESCALE_DSN" -f db/migrations/0007_chat_direct_messages.sql

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS recipient_client_id TEXT;

CREATE INDEX IF NOT EXISTS idx_chat_messages_sender_recipient ON chat_messages (client_id, recipient_client_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_recipient_sender ON chat_messages (recipient_client_id, client_id);
