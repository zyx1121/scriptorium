import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pool, query } from './client.ts';
import { hashToken } from '../auth/middleware.ts';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MIGRATIONS_DIR = join(__dirname, 'migrations');

async function ensureTable() {
  await query(`
    CREATE TABLE IF NOT EXISTS migrations (
      filename TEXT PRIMARY KEY,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
  `);
}

async function applied(): Promise<Set<string>> {
  const r = await query<{ filename: string }>('SELECT filename FROM migrations');
  return new Set(r.rows.map(row => row.filename));
}

async function seedAdminTokenHash() {
  const raw = process.env.ADMIN_TOKEN?.trim();
  if (!raw) {
    console.warn('[migrate] ADMIN_TOKEN not set in env — admin CLI will refuse to run until it is.');
    return;
  }
  const hash = hashToken(raw);
  // Only seed once. Rotating is an explicit op (DELETE + re-migrate) — see OPERATIONS.md.
  const r = await query<{ key: string }>(
    `INSERT INTO server_config (key, value)
     VALUES ('admin_token_hash', $1)
     ON CONFLICT (key) DO NOTHING
     RETURNING key`,
    [hash]
  );
  if (r.rowCount && r.rowCount > 0) {
    console.log('[migrate] seeded admin_token_hash from ADMIN_TOKEN env');
  } else {
    console.log('[migrate] admin_token_hash already set; ignoring ADMIN_TOKEN env (rotate via OPERATIONS.md)');
  }
}

async function main() {
  await ensureTable();
  const done = await applied();
  const files = readdirSync(MIGRATIONS_DIR).filter(f => f.endsWith('.sql')).sort();

  for (const file of files) {
    if (done.has(file)) {
      console.log(`[migrate] skip ${file} (already applied)`);
      continue;
    }
    const sql = readFileSync(join(MIGRATIONS_DIR, file), 'utf8');
    console.log(`[migrate] applying ${file}`);
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      await client.query(sql);
      await client.query('INSERT INTO migrations (filename) VALUES ($1)', [file]);
      await client.query('COMMIT');
      console.log(`[migrate] ✓ ${file}`);
    } catch (e) {
      await client.query('ROLLBACK');
      console.error(`[migrate] ✗ ${file}:`, e);
      process.exit(1);
    } finally {
      client.release();
    }
  }

  await seedAdminTokenHash();

  await pool.end();
  console.log('[migrate] done');
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
