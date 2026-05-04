import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query } from '../../db/client.ts';
import type { AuthContext } from '../../auth/middleware.ts';
import { ok, err, getCollectionIdBySlug } from '../util.ts';

export function registerSearch(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'search',
    {
      title: 'Search wiki',
      description: 'Full-text search over wiki pages using PostgreSQL ts_rank. Returns ranked candidates with snippets.',
      inputSchema: {
        collection: z.string(),
        query: z.string().min(1),
        top_k: z.number().int().positive().max(50).default(10),
        filter_type: z.array(z.string()).optional(),
      },
    },
    async ({ collection, query: q, top_k, filter_type }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');

      const params: any[] = [cid, q];
      let where = 'collection_id = $1 AND deleted_at IS NULL AND search_vector @@ plainto_tsquery(\'simple\', $2)';
      if (filter_type && filter_type.length > 0) {
        params.push(filter_type);
        where += ` AND frontmatter->>'type' = ANY($${params.length})`;
      }
      params.push(top_k);

      const r = await query<{ path: string; title: string | null; type: string | null; score: number; snippet: string }>(
        `SELECT path,
                frontmatter->>'title' AS title,
                frontmatter->>'type' AS type,
                ts_rank(search_vector, plainto_tsquery('simple', $2)) AS score,
                ts_headline('simple', content, plainto_tsquery('simple', $2),
                  'MaxWords=30, MinWords=10, ShortWord=2, MaxFragments=2') AS snippet
         FROM pages
         WHERE ${where}
         ORDER BY score DESC
         LIMIT $${params.length}`,
        params
      );
      // fire-and-forget search log
      query(
        'INSERT INTO logs (collection_id, kind, actor, actor_user_id, payload) VALUES ($1, $2, $3, $4, $5)',
        [cid, 'search', auth.tokenName, auth.userId, {
          query: q,
          result_count: r.rows.length,
          top_paths: r.rows.slice(0, 5).map(row => row.path),
        }]
      ).catch(e => console.error('[stats] search log failed:', e));
      return ok(r.rows);
    }
  );
}
