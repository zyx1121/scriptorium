import { randomBytes, timingSafeEqual } from 'node:crypto';
import { pool, query } from '../db/client.ts';
import { hashToken } from '../auth/middleware.ts';

function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(1);
}

let adminVerified = false;

async function requireAdmin() {
  if (adminVerified) return;
  const raw = process.env.ADMIN_TOKEN?.trim();
  if (!raw) fail('ADMIN_TOKEN env var must be set to run the CLI');
  const got = hashToken(raw);
  const r = await query<{ value: string }>(
    `SELECT value FROM server_config WHERE key = 'admin_token_hash'`
  );
  const stored = r.rows[0]?.value;
  if (!stored) {
    fail('admin_token_hash is not seeded — run `bun run migrate` with ADMIN_TOKEN set first');
  }
  // Length is fixed (hex sha256) so length-leak doesn't matter, but use timing-safe regardless.
  const a = Buffer.from(got, 'utf8');
  const b = Buffer.from(stored, 'utf8');
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    fail('ADMIN_TOKEN does not match the seeded hash — see OPERATIONS.md to rotate');
  }
  adminVerified = true;
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

// ----- users -----

async function userCreate(flags: Record<string, string | string[]>) {
  await requireAdmin();
  const email = flags.email as string | undefined;
  const name = flags.name as string | undefined;
  const role = (flags.role as string | undefined) ?? 'member';
  if (!email) fail('--email <user-email> required');
  if (!['admin', 'member', 'viewer'].includes(role)) {
    fail(`invalid role: ${role} (use admin | member | viewer)`);
  }
  try {
    const r = await query<{ id: number }>(
      'INSERT INTO users (email, name, role) VALUES ($1, $2, $3) RETURNING id',
      [email, name ?? null, role]
    );
    console.log(`User created: id=${r.rows[0]!.id} email=${email} role=${role}`);
  } catch (e: any) {
    if (e.code === '23505') fail(`email already exists: ${email}`);
    throw e;
  }
}

async function userList() {
  await requireAdmin();
  const r = await query<{
    id: number; email: string; name: string | null; role: string; created_at: Date;
    token_count: string; last_active: Date | null;
  }>(
    `SELECT u.id, u.email, u.name, u.role, u.created_at,
            (SELECT COUNT(*) FROM tokens t WHERE t.user_id = u.id AND t.revoked_at IS NULL)::text AS token_count,
            (SELECT MAX(ts) FROM logs l WHERE l.actor_user_id = u.id) AS last_active
     FROM users u ORDER BY u.id`
  );
  console.table(r.rows.map(u => ({
    id: u.id,
    email: u.email,
    name: u.name ?? '-',
    role: u.role,
    tokens: u.token_count,
    last_active: u.last_active?.toISOString().slice(0, 19).replace('T', ' ') ?? '-',
  })));
}

async function userDelete(flags: Record<string, string | string[]>) {
  await requireAdmin();
  const email = flags.email as string | undefined;
  if (!email) fail('--email <user-email> required');
  const u = await query<{ id: number }>('SELECT id FROM users WHERE email = $1', [email]);
  if (u.rows.length === 0) fail(`no user with email: ${email}`);
  const userId = u.rows[0]!.id;
  // revoke all their active tokens
  const tokensR = await query('UPDATE tokens SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL', [userId]);
  // delete the user (logs/tokens have ON DELETE SET NULL, so they stay but become orphaned)
  await query('DELETE FROM users WHERE id = $1', [userId]);
  console.log(`User ${email} deleted, ${tokensR.rowCount ?? 0} active token(s) revoked.`);
}

// ----- tokens -----

async function tokenIssue(flags: Record<string, string | string[]>) {
  await requireAdmin();
  const name = flags.name as string | undefined;
  if (!name) fail('--name <token-name> required (a device label, e.g. alice-mac)');

  const scopesArg = flags.scope;
  const scopes = Array.isArray(scopesArg) ? scopesArg : scopesArg ? [scopesArg as string] : ['rw'];
  for (const s of scopes) {
    if (!['r', 'rw', 'admin'].includes(s)) fail(`invalid scope: ${s} (use r | rw | admin)`);
  }

  const colsArg = flags.collection;
  // Wildcard semantics live in `canAccessCollection` (length===0 → all).
  // Strip literal '*' so `--collection '*'` is the same as omitting the flag.
  const collections = (Array.isArray(colsArg) ? colsArg : colsArg ? [colsArg as string] : [])
    .filter((s: string) => s !== '*');

  const expiresDays = flags['expires-days'];
  const expiresAt = expiresDays ? new Date(Date.now() + Number(expiresDays) * 86_400_000) : null;

  // resolve --user <email> → user_id (optional but encouraged)
  const userEmail = flags.user as string | undefined;
  let userId: number | null = null;
  let userName: string | null = null;
  if (userEmail) {
    const u = await query<{ id: number; name: string | null }>(
      'SELECT id, name FROM users WHERE email = $1',
      [userEmail]
    );
    if (u.rows.length === 0) fail(`no user with email: ${userEmail} — create one first with: cli user create --email ${userEmail}`);
    userId = u.rows[0]!.id;
    userName = u.rows[0]!.name;
  }

  const raw = randomBytes(32).toString('base64url');
  const hash = hashToken(raw);

  await query(
    `INSERT INTO tokens (name, token_hash, scopes, collection_slugs, expires_at, user_id)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [name, hash, scopes, collections, expiresAt, userId]
  );

  console.log('Token issued. Save this — it will not be shown again:\n');
  console.log(`  ${raw}\n`);
  console.log(`Name:        ${name}`);
  console.log(`User:        ${userEmail ? `${userEmail}${userName ? ` (${userName})` : ''}` : '(unassigned)'}`);
  console.log(`Scopes:      ${scopes.join(', ')}`);
  console.log(`Collections: ${collections.length === 0 ? '*' : collections.join(', ')}`);
  if (expiresAt) console.log(`Expires:     ${expiresAt.toISOString()}`);
}

async function tokenList() {
  await requireAdmin();
  const r = await query<{
    id: number; name: string; scopes: string[]; collection_slugs: string[];
    created_at: Date; expires_at: Date | null; revoked_at: Date | null;
    user_email: string | null;
  }>(
    `SELECT t.id, t.name, t.scopes, t.collection_slugs, t.created_at, t.expires_at, t.revoked_at,
            u.email AS user_email
     FROM tokens t LEFT JOIN users u ON u.id = t.user_id ORDER BY t.id`
  );
  console.table(r.rows.map(t => ({
    id: t.id,
    name: t.name,
    user: t.user_email ?? '(unassigned)',
    scopes: t.scopes.join(','),
    collections: t.collection_slugs.length === 0 ? '*' : t.collection_slugs.join(','),
    expires: t.expires_at?.toISOString() ?? '-',
    status: t.revoked_at ? 'revoked' : t.expires_at && t.expires_at < new Date() ? 'expired' : 'active',
  })));
}

async function tokenRevoke(flags: Record<string, string | string[]>) {
  await requireAdmin();
  const id = flags.id as string | undefined;
  if (!id) fail('--id <token-id> required');
  const r = await query('UPDATE tokens SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL', [Number(id)]);
  if (r.rowCount === 0) fail('no active token with that id');
  console.log(`Token ${id} revoked`);
}

// ----- main -----

async function main() {
  const [, , cmd, sub, ...rest] = process.argv;
  const flags = parseFlags(rest);

  try {
    if (cmd === 'user' && sub === 'create') await userCreate(flags);
    else if (cmd === 'user' && sub === 'list') await userList();
    else if (cmd === 'user' && sub === 'delete') await userDelete(flags);
    else if (cmd === 'token' && sub === 'issue') await tokenIssue(flags);
    else if (cmd === 'token' && sub === 'list') await tokenList();
    else if (cmd === 'token' && sub === 'revoke') await tokenRevoke(flags);
    else {
      console.log(`Usage:
  bun run cli user create  --email <email> [--name <name>] [--role admin|member|viewer]
  bun run cli user list
  bun run cli user delete  --email <email>     # revokes all active tokens for the user

  bun run cli token issue  --name <device-label> [--user <email>] [--scope rw] [--collection <slug>] [--expires-days N]
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
