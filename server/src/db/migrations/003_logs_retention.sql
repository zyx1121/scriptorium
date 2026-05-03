-- 003_logs_retention.sql
-- Helper function for log retention.
-- High-value events (init / schema_update / ingest / lint / recap / delete_page) are kept forever.
-- Low-value, high-volume events (page_read / search) are subject to retention.

CREATE OR REPLACE FUNCTION prune_logs(retention_days INT) RETURNS INT AS $$
DECLARE
  deleted_count INT;
BEGIN
  WITH deleted AS (
    DELETE FROM logs
    WHERE kind IN ('page_read', 'search')
      AND ts < now() - (retention_days || ' days')::interval
    RETURNING 1
  )
  SELECT count(*) INTO deleted_count FROM deleted;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION prune_logs(INT) IS
  'Delete page_read and search log entries older than N days. Returns deleted row count. Run via cron / pg_cron / external scheduler.';
