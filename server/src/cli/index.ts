import { randomBytes } from 'node:crypto';
import { pool, query } from '../db/client.ts';
import { hashToken } from '../auth/middleware.ts';

const ADMIN_TOKEN = process.env.ADMIN_TOKEN;

function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(1);
}

function requireAdmin() {
  if (!ADMIN_TOKEN) fail('ADMIN_TOKEN env var must be set to run the CLI');
}

function parseFlags(argv: string[]): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    if (a.startsWith('--')) {
      const k = a.slice(2);
      const v = argv[i + 1];
      if (v && !v.startsWith('--')) {
        if (k === 'collection' || k === 'scope') {
          const cur = out[k];
          if (Array.isArray(cur)) cur.push(v);
          else if (typeof cur === 'string') out[k] = [cur, v];
          else out[k] = v;
        } else {
          out[k] = v;
        }
        i++;
      } else {
        out[k] = '';
      }
    }
  }
  return out;
}

async function tokenIssue(flags: Record<string, string | string[]>) {
  requireAdmin();
  const name = flags.name as string | undefined;
  if (!name) fail('--name <token-name> required');

  const scopesArg = flags.scope;
  const scopes = Array.isArray(scopesArg) ? scopesArg : scopesArg ? [scopesArg as string] : ['rw'];
  for (const s of scopes) {
    if (!['r', 'rw', 'admin'].includes(s)) fail(`invalid scope: ${s} (use r | rw | admin)`);
  }

  const colsArg = flags.collection;
  const collections = Array.isArray(colsArg) ? colsArg : colsArg ? [colsArg as string] : [];

  const expiresDays = flags['expires-days'];
  const expiresAt = expiresDays ? new Date(Date.now() + Number(expiresDays) * 86_400_000) : null;

  const raw = randomBytes(32).toString('base64url');
  const hash = hashToken(raw);

  await query(
    `INSERT INTO tokens (name, token_hash, scopes, collection_slugs, expires_at)
     VALUES ($1, $2, $3, $4, $5)`,
    [name, hash, scopes, collections, expiresAt]
  );

  console.log('Token issued. Save this — it will not be shown again:\n');
  console.log(`  ${raw}\n`);
  console.log(`Name:        ${name}`);
  console.log(`Scopes:      ${scopes.join(', ')}`);
  console.log(`Collections: ${collections.length === 0 ? '*' : collections.join(', ')}`);
  if (expiresAt) console.log(`Expires:     ${expiresAt.toISOString()}`);
}

async function tokenList() {
  requireAdmin();
  const r = await query<{ id: number; name: string; scopes: string[]; collection_slugs: string[]; created_at: Date; expires_at: Date | null; revoked_at: Date | null }>(
    'SELECT id, name, scopes, collection_slugs, created_at, expires_at, revoked_at FROM tokens ORDER BY id'
  );
  console.table(r.rows.map(t => ({
    id: t.id,
    name: t.name,
    scopes: t.scopes.join(','),
    collections: t.collection_slugs.length === 0 ? '*' : t.collection_slugs.join(','),
    expires: t.expires_at?.toISOString() ?? '-',
    status: t.revoked_at ? 'revoked' : t.expires_at && t.expires_at < new Date() ? 'expired' : 'active',
  })));
}

async function tokenRevoke(flags: Record<string, string | string[]>) {
  requireAdmin();
  const id = flags.id as string | undefined;
  if (!id) fail('--id <token-id> required');
  const r = await query('UPDATE tokens SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL', [Number(id)]);
  if (r.rowCount === 0) fail('no active token with that id');
  console.log(`Token ${id} revoked`);
}

async function main() {
  const [, , cmd, sub, ...rest] = process.argv;
  const flags = parseFlags(rest);

  try {
    if (cmd === 'token' && sub === 'issue') await tokenIssue(flags);
    else if (cmd === 'token' && sub === 'list') await tokenList();
    else if (cmd === 'token' && sub === 'revoke') await tokenRevoke(flags);
    else {
      console.log(`Usage:
  bun run cli token issue --name <name> [--scope rw] [--collection <slug>] [--expires-days N]
  bun run cli token list
  bun run cli token revoke --id <token-id>
`);
      process.exit(cmd ? 1 : 0);
    }
  } finally {
    await pool.end();
  }
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
