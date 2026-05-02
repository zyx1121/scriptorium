import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pool, query } from './client.ts';

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

  await pool.end();
  console.log('[migrate] done');
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
