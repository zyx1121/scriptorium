import { createHash } from 'node:crypto';
import { query } from '../db/client.ts';

export interface AuthContext {
  tokenId: number;
  tokenName: string;
  scopes: string[];
  collectionSlugs: string[];
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
  }>(
    `SELECT id, name, scopes, collection_slugs, expires_at
     FROM tokens
     WHERE token_hash = $1 AND revoked_at IS NULL`,
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
  };
}

export function canAccessCollection(ctx: AuthContext, slug: string): boolean {
  if (ctx.scopes.includes('admin')) return true;
  if (ctx.collectionSlugs.length === 0) return true; // wildcard
  return ctx.collectionSlugs.includes(slug);
}

export function canWrite(ctx: AuthContext): boolean {
  return ctx.scopes.includes('rw') || ctx.scopes.includes('admin');
}
