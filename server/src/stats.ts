import { query } from './db/client.ts';

export interface StatsResult {
  collection: string;
  window_days: number;
  totals: {
    pages: number;
    raw_sources: number;
    page_reads: number;
    searches: number;
    ingests: number;
  };
  by_type: Record<string, number>;
  top_pages_by_reads: Array<{ path: string; reads: number; last_read: string }>;
  recently_updated: Array<{ path: string; type: string | null; updated_at: string }>;
  recently_added: Array<{ path: string; type: string | null; created_at: string }>;
  recent_searches: Array<{ query: string; ts: string; result_count: number | null }>;
  stale: Array<{ path: string; updated_at: string; last_read: string | null }>;
}

export async function computeStats(slug: string, days: number): Promise<StatsResult | null> {
  const c = await query<{ id: string }>('SELECT id FROM collections WHERE slug = $1', [slug]);
  const cid = c.rows[0]?.id;
  if (!cid) return null;

  const interval = `${days} days`;

  const [pagesCount, rawCount, logCounts, byType, topReads, recentlyUpdated, recentlyAdded, recentSearches, stalePages] = await Promise.all([
    query<{ count: string }>(
      `SELECT COUNT(*)::text AS count FROM pages WHERE collection_id = $1 AND deleted_at IS NULL`,
      [cid]
    ),
    query<{ count: string }>(
      `SELECT COUNT(*)::text AS count FROM raw_sources WHERE collection_id = $1`,
      [cid]
    ),
    query<{ kind: string; count: string }>(
      `SELECT kind, COUNT(*)::text AS count FROM logs
       WHERE collection_id = $1 AND ts > now() - $2::interval
       GROUP BY kind`,
      [cid, interval]
    ),
    query<{ type: string | null; count: string }>(
      `SELECT frontmatter->>'type' AS type, COUNT(*)::text AS count
       FROM pages WHERE collection_id = $1 AND deleted_at IS NULL
       GROUP BY frontmatter->>'type'
       ORDER BY count DESC`,
      [cid]
    ),
    query<{ path: string; reads: string; last_read: Date }>(
      `SELECT payload->>'path' AS path, COUNT(*)::text AS reads, MAX(ts) AS last_read
       FROM logs
       WHERE collection_id = $1 AND kind = 'page_read' AND ts > now() - $2::interval
         AND payload ? 'path'
       GROUP BY payload->>'path'
       ORDER BY COUNT(*) DESC
       LIMIT 20`,
      [cid, interval]
    ),
    query<{ path: string; type: string | null; updated_at: Date }>(
      `SELECT path, frontmatter->>'type' AS type, updated_at
       FROM pages WHERE collection_id = $1 AND deleted_at IS NULL
       ORDER BY updated_at DESC LIMIT 10`,
      [cid]
    ),
    query<{ path: string; type: string | null; created_at: Date }>(
      `SELECT path, frontmatter->>'type' AS type, created_at
       FROM pages WHERE collection_id = $1 AND deleted_at IS NULL
       ORDER BY created_at DESC LIMIT 10`,
      [cid]
    ),
    query<{ query: string | null; ts: Date; result_count: number | null }>(
      `SELECT payload->>'query' AS query, ts, (payload->>'result_count')::int AS result_count
       FROM logs
       WHERE collection_id = $1 AND kind = 'search'
       ORDER BY ts DESC LIMIT 10`,
      [cid]
    ),
    query<{ path: string; updated_at: Date; last_read: Date | null }>(
      `SELECT p.path, p.updated_at,
              (SELECT MAX(l.ts) FROM logs l
               WHERE l.collection_id = p.collection_id
                 AND l.kind = 'page_read'
                 AND l.payload->>'path' = p.path) AS last_read
       FROM pages p
       WHERE p.collection_id = $1 AND p.deleted_at IS NULL
         AND p.updated_at < now() - interval '180 days'
       ORDER BY p.updated_at ASC LIMIT 10`,
      [cid]
    ),
  ]);

  const counts: Record<string, number> = {};
  for (const r of logCounts.rows) counts[r.kind] = Number(r.count);

  const byTypeMap: Record<string, number> = {};
  for (const r of byType.rows) byTypeMap[r.type ?? '(untyped)'] = Number(r.count);

  return {
    collection: slug,
    window_days: days,
    totals: {
      pages: Number(pagesCount.rows[0]?.count ?? 0),
      raw_sources: Number(rawCount.rows[0]?.count ?? 0),
      page_reads: counts['page_read'] ?? 0,
      searches: counts['search'] ?? 0,
      ingests: counts['ingest'] ?? 0,
    },
    by_type: byTypeMap,
    top_pages_by_reads: topReads.rows.map(r => ({
      path: r.path,
      reads: Number(r.reads),
      last_read: r.last_read.toISOString(),
    })),
    recently_updated: recentlyUpdated.rows.map(r => ({
      path: r.path,
      type: r.type,
      updated_at: r.updated_at.toISOString(),
    })),
    recently_added: recentlyAdded.rows.map(r => ({
      path: r.path,
      type: r.type,
      created_at: r.created_at.toISOString(),
    })),
    recent_searches: recentSearches.rows
      .filter(r => r.query !== null)
      .map(r => ({ query: r.query!, ts: r.ts.toISOString(), result_count: r.result_count })),
    stale: stalePages.rows.map(r => ({
      path: r.path,
      updated_at: r.updated_at.toISOString(),
      last_read: r.last_read?.toISOString() ?? null,
    })),
  };
}
