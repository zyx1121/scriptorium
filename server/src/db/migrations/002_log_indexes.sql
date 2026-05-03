-- 002_log_indexes.sql
-- Indexes for observability queries on the logs table.

-- Fast lookup by kind (page_read / search / ingest / lint / ...)
CREATE INDEX IF NOT EXISTS logs_kind_ts_idx ON logs (kind, ts DESC);

-- Fast lookup by path inside payload (page_read records)
CREATE INDEX IF NOT EXISTS logs_payload_path_idx ON logs ((payload->>'path'));

-- General-purpose JSONB containment / key probes
CREATE INDEX IF NOT EXISTS logs_payload_gin_idx ON logs USING GIN (payload);
