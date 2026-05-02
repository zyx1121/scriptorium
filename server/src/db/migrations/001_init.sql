-- 001_init.sql
-- Initial schema for Scriptorium.

CREATE TABLE IF NOT EXISTS collections (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  schema_version  INTEGER NOT NULL DEFAULT 1,
  schema_md       TEXT NOT NULL DEFAULT '',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pages (
  id              BIGSERIAL PRIMARY KEY,
  collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  path            TEXT NOT NULL,
  content         TEXT NOT NULL,
  frontmatter     JSONB NOT NULL DEFAULT '{}'::jsonb,
  version         INTEGER NOT NULL DEFAULT 1,
  deleted_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  search_vector   tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(frontmatter->>'title', '')), 'A') ||
    setweight(to_tsvector('simple', content), 'B')
  ) STORED,
  UNIQUE (collection_id, path)
);
CREATE INDEX IF NOT EXISTS pages_search_idx ON pages USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS pages_frontmatter_idx ON pages USING GIN (frontmatter);
CREATE INDEX IF NOT EXISTS pages_collection_path_idx ON pages (collection_id, path) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS page_versions (
  id              BIGSERIAL PRIMARY KEY,
  page_id         BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  version         INTEGER NOT NULL,
  content         TEXT NOT NULL,
  frontmatter     JSONB NOT NULL,
  author          TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (page_id, version)
);

CREATE TABLE IF NOT EXISTS raw_sources (
  id              BIGSERIAL PRIMARY KEY,
  collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  kind            TEXT NOT NULL,
  content         TEXT NOT NULL,
  sha256          TEXT NOT NULL,
  metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
  ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (collection_id, slug)
);

CREATE TABLE IF NOT EXISTS logs (
  id              BIGSERIAL PRIMARY KEY,
  collection_id   UUID REFERENCES collections(id) ON DELETE CASCADE,
  ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind            TEXT NOT NULL,
  actor           TEXT NOT NULL,
  payload         JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS logs_collection_ts_idx ON logs (collection_id, ts DESC);

-- Tokens. The `token_hash` is sha256 of the raw token; raw token is shown ONCE on issuance.
CREATE TABLE IF NOT EXISTS tokens (
  id              BIGSERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  token_hash      TEXT NOT NULL UNIQUE,
  scopes          TEXT[] NOT NULL DEFAULT ARRAY['r']::text[],
  collection_slugs TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ,
  revoked_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS tokens_hash_idx ON tokens (token_hash) WHERE revoked_at IS NULL;

-- Migration tracking.
CREATE TABLE IF NOT EXISTS migrations (
  filename        TEXT PRIMARY KEY,
  applied_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
