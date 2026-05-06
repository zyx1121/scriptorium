import { createHash } from 'node:crypto';
import { query } from '../db/client.ts';

export type UserRole = 'admin' | 'member' | 'viewer';

export interface AuthContext {
  tokenId: number;
  tokenName: string;
  scopes: string[];
  collectionSlugs: string[];
  userId: number | null;
  userEmail: string | null;
  userName: string | null;
  userRole: UserRole | null;
}

export function hashToken(raw: string): string {
  return createHash('sha256').update(raw).digest('hex');
}

export async function verifyBearer(authHeader: string | undefined): Promise<AuthContext | null> {
  if (!authHeader || !authHeader.startsWith('Bearer ')) return null;
  const raw = authHeader.slice('Bearer '.length).trim();
  if (!raw) return null;

  const hash = hashToken(raw);
  const r = await query<{
    id: number;
    name: string;
    scopes: string[];
    collection_slugs: string[];
    expires_at: Date | null;
    user_id: number | null;
    user_email: string | null;
    user_name: string | null;
    user_role: string | null;
  }>(
    `SELECT t.id, t.name, t.scopes, t.collection_slugs, t.expires_at,
            t.user_id,
            u.email AS user_email, u.name AS user_name, u.role AS user_role
     FROM tokens t
     LEFT JOIN users u ON u.id = t.user_id
     WHERE t.token_hash = $1 AND t.revoked_at IS NULL`,
    [hash]
  );
  const row = r.rows[0];
  if (!row) return null;
  if (row.expires_at && row.expires_at < new Date()) return null;

  return {
    tokenId: row.id,
    tokenName: row.name,
    scopes: row.scopes,
    collectionSlugs: row.collection_slugs,
    userId: row.user_id,
    userEmail: row.user_email,
    userName: row.user_name,
    userRole: (row.user_role as UserRole | null) ?? null,
  };
}

export function canAccessCollection(ctx: AuthContext, slug: string): boolean {
  if (ctx.scopes.includes('admin')) return true;
  // wildcard: empty array (canonical) or literal '*' (legacy / hand-rolled tokens)
  if (ctx.collectionSlugs.length === 0 || ctx.collectionSlugs.includes('*')) return true;
  return ctx.collectionSlugs.includes(slug);
}

export function canWrite(ctx: AuthContext): boolean {
  return ctx.scopes.includes('rw') || ctx.scopes.includes('admin');
}
