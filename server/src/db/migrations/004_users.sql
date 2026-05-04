-- 004_users.sql
-- Add users abstraction so a single human can own multiple tokens
-- (e.g. mac + laptop + phone) and activity aggregates per person.

CREATE TABLE IF NOT EXISTS users (
  id          BIGSERIAL PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  name        TEXT,
  role        TEXT NOT NULL DEFAULT 'member',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (role IN ('admin', 'member', 'viewer'))
);

ALTER TABLE tokens
  ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS tokens_user_idx ON tokens (user_id) WHERE revoked_at IS NULL;

ALTER TABLE logs
  ADD COLUMN IF NOT EXISTS actor_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS logs_actor_user_idx ON logs (actor_user_id, ts DESC);

-- Backfill: create an initial admin user from the existing 'loki-*' tokens.
-- This is a one-time migration of the bootstrapped data; new servers won't
-- have any 'loki-*' rows so these statements are no-ops there.
INSERT INTO users (email, name, role)
  VALUES ('loki@winlab.tw', 'Loki', 'admin')
  ON CONFLICT (email) DO NOTHING;

UPDATE tokens
   SET user_id = (SELECT id FROM users WHERE email = 'loki@winlab.tw')
 WHERE user_id IS NULL AND name LIKE 'loki%';

UPDATE logs
   SET actor_user_id = (SELECT id FROM users WHERE email = 'loki@winlab.tw')
 WHERE actor_user_id IS NULL AND actor LIKE 'loki%';
