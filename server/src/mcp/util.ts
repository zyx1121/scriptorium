import { query } from '../db/client.ts';
import { canAccessCollection, type AuthContext } from '../auth/middleware.ts';

export function ok(obj: unknown) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(obj, null, 2) }],
  };
}

export function err(message: string) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify({ error: message }) }],
    isError: true,
  };
}

export async function getCollectionIdBySlug(auth: AuthContext, slug: string): Promise<string | null> {
  if (!canAccessCollection(auth, slug)) return null;
  const r = await query<{ id: string }>('SELECT id FROM collections WHERE slug = $1', [slug]);
  return r.rows[0]?.id ?? null;
}
