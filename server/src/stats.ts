import { query } from './db/client.ts';

export interface UserActivity {
  user_email: string | null;
  user_name: string | null;
  display: string;
  ingests: number;
  searches: number;
  page_reads: number;
  total: number;
  last_active: string;
}

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
  top_users_by_activity: UserActivity[];
}

export async function computeStats(slug: string, days: number): Promise<StatsResult | null> {
  const c = await query<{ id: string }>('SELECT id FROM collections WHERE slug = $1', [slug]);
  const cid = c.rows[0]?.id;
  if (!cid) return null;

  const interval = `${days} days`;

  const [
    pagesCount, rawCount, logCounts, byType, topReads,
    recentlyUpdated, recentlyAdded, recentSearches, stalePages, topUsers,
  ] = await Promise.all([
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
    query<{
      user_email: string | null; user_name: string | null; actor: string;
      ingests: string; searches: string; reads: string; total: string; last_active: Date;
    }>(
      `SELECT u.email AS user_email, u.name AS user_name, l.actor,
              COUNT(*) FILTER (WHERE l.kind = 'ingest')::text AS ingests,
              COUNT(*) FILTER (WHERE l.kind = 'search')::text AS searches,
              COUNT(*) FILTER (WHERE l.kind = 'page_read')::text AS reads,
              COUNT(*)::text AS total,
              MAX(l.ts) AS last_active
       FROM logs l LEFT JOIN users u ON u.id = l.actor_user_id
       WHERE l.collection_id = $1 AND l.ts > now() - $2::interval
       GROUP BY u.email, u.name, l.actor
       ORDER BY COUNT(*) DESC
       LIMIT 10`,
      [cid, interval]
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
    top_users_by_activity: topUsers.rows.map(r => ({
      user_email: r.user_email,
      user_name: r.user_name,
      display: r.user_email ?? r.actor,
      ingests: Number(r.ingests),
      searches: Number(r.searches),
      page_reads: Number(r.reads),
      total: Number(r.total),
      last_active: r.last_active.toISOString(),
    })),
  };
}

// ----- cross-collection team stats -----

export interface TeamUserActivity {
  user_id: number | null;
  email: string | null;
  name: string | null;
  role: string | null;
  active_tokens: number;
  ingests: number;
  searches: number;
  page_reads: number;
  total: number;
  last_active: string | null;
}

export interface TeamActivityResult {
  window_days: number;
  scope: string;
  users: TeamUserActivity[];
  unassigned_actors: Array<{ actor: string; total: number; last_active: string }>;
  recent_actions: Array<{
    ts: string;
    kind: string;
    actor: string;
    user_email: string | null;
    collection: string | null;
    payload: Record<string, unknown>;
  }>;
}

export async function computeTeamActivity(opts: {
  collectionSlug?: string;
  days: number;
}): Promise<TeamActivityResult> {
  const interval = `${opts.days} days`;
  const collectionFilter = opts.collectionSlug
    ? `AND l.collection_id = (SELECT id FROM collections WHERE slug = $2)`
    : '';
  const params: unknown[] = [interval];
  if (opts.collectionSlug) params.push(opts.collectionSlug);

  const [usersR, unassignedR, recentR] = await Promise.all([
    query<{
      user_id: number | null; email: string | null; name: string | null; role: string | null;
      active_tokens: string;
      ingests: string; searches: string; reads: string; total: string; last_active: Date | null;
    }>(
      `SELECT u.id AS user_id, u.email, u.name, u.role,
              (SELECT COUNT(*) FROM tokens t WHERE t.user_id = u.id AND t.revoked_at IS NULL)::text AS active_tokens,
              COUNT(l.*) FILTER (WHERE l.kind = 'ingest')::text AS ingests,
              COUNT(l.*) FILTER (WHERE l.kind = 'search')::text AS searches,
              COUNT(l.*) FILTER (WHERE l.kind = 'page_read')::text AS reads,
              COUNT(l.*)::text AS total,
              MAX(l.ts) AS last_active
       FROM users u
       LEFT JOIN logs l
         ON l.actor_user_id = u.id
        AND l.ts > now() - $1::interval
        ${collectionFilter}
       GROUP BY u.id, u.email, u.name, u.role
       ORDER BY COUNT(l.*) DESC, u.email`,
      params
    ),
    query<{ actor: string; total: string; last_active: Date }>(
      `SELECT l.actor, COUNT(*)::text AS total, MAX(l.ts) AS last_active
       FROM logs l
       WHERE l.actor_user_id IS NULL AND l.ts > now() - $1::interval ${collectionFilter}
       GROUP BY l.actor
       ORDER BY COUNT(*) DESC LIMIT 20`,
      params
    ),
    query<{
      ts: Date; kind: string; actor: string; user_email: string | null;
      slug: string | null; payload: Record<string, unknown>;
    }>(
      `SELECT l.ts, l.kind, l.actor, u.email AS user_email,
              c.slug, l.payload
       FROM logs l
       LEFT JOIN users u ON u.id = l.actor_user_id
       LEFT JOIN collections c ON c.id = l.collection_id
       WHERE l.ts > now() - $1::interval ${collectionFilter}
       ORDER BY l.ts DESC LIMIT 30`,
      params
    ),
  ]);

  return {
    window_days: opts.days,
    scope: opts.collectionSlug ?? '*',
    users: usersR.rows.map(u => ({
      user_id: u.user_id,
      email: u.email,
      name: u.name,
      role: u.role,
      active_tokens: Number(u.active_tokens),
      ingests: Number(u.ingests),
      searches: Number(u.searches),
      page_reads: Number(u.reads),
      total: Number(u.total),
      last_active: u.last_active?.toISOString() ?? null,
    })),
    unassigned_actors: unassignedR.rows.map(r => ({
      actor: r.actor,
      total: Number(r.total),
      last_active: r.last_active.toISOString(),
    })),
    recent_actions: recentR.rows.map(r => ({
      ts: r.ts.toISOString(),
      kind: r.kind,
      actor: r.actor,
      user_email: r.user_email,
      collection: r.slug,
      payload: r.payload,
    })),
  };
}
