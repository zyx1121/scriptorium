-- 005_server_config.sql
-- A tiny key-value table for server-managed secrets that need to outlive
-- a single env-var read. Today: the admin token hash, so the CLI can
-- timing-safely verify ADMIN_TOKEN instead of trusting "is it set".
--
-- Rotating the admin token: DELETE the row, change ADMIN_TOKEN in .env,
-- re-run `bun run migrate`. (Documented in OPERATIONS.md.)

CREATE TABLE IF NOT EXISTS server_config (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
