import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query } from '../../db/client.ts';
import { canWrite, type AuthContext } from '../../auth/middleware.ts';
import { ok, err, getCollectionIdBySlug } from '../util.ts';

// Kinds the skill is documented to emit. These show up in stats / dashboard
// counters and are aggregated cross-collection in team_activity.
const ALLOWED_WORKFLOW_KINDS = ['ingest', 'recap', 'query', 'lint'] as const;

// Kinds the server writes itself. Clients MUST NOT forge these — the audit
// log is the source of truth for who did what, and a `rw` token forging
// `page_read`/`search`/`init`/`schema_update`/`delete_page` would let an
// attacker poison stats and cover their tracks.
const RESERVED_SYSTEM_KINDS = new Set([
  'page_read', 'search', 'init', 'schema_update', 'delete_page',
]);

function validateKind(kind: string): { ok: true; value: string } | { ok: false; reason: string } {
  if ((ALLOWED_WORKFLOW_KINDS as readonly string[]).includes(kind)) return { ok: true, value: kind };
  if (kind.startsWith('client:') && kind.length > 'client:'.length) return { ok: true, value: kind };
  if (RESERVED_SYSTEM_KINDS.has(kind)) {
    return { ok: false, reason: `kind '${kind}' is reserved for the server; use 'client:${kind}' if you really need it` };
  }
  return { ok: false, reason: `kind must be one of [${ALLOWED_WORKFLOW_KINDS.join(', ')}] or prefixed with 'client:'` };
}

export function registerLog(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'append_log',
    {
      title: 'Append to log',
      description: 'Append an audit entry to the collection log (immutable). kind must be one of [ingest, recap, query, lint] or start with "client:".',
      inputSchema: {
        collection: z.string(),
        kind: z.string().min(1),
        payload: z.record(z.any()).default({}),
      },
    },
    async ({ collection, kind, payload }) => {
      if (!canWrite(auth)) return err('write scope required');
      const v = validateKind(kind);
      if (!v.ok) return err(v.reason);
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      await query(
        'INSERT INTO logs (collection_id, kind, actor, actor_user_id, payload) VALUES ($1, $2, $3, $4, $5)',
        [cid, v.value, auth.tokenName, auth.userId, payload]
      );
      return ok({ logged: true, kind: v.value });
    }
  );

  server.registerTool(
    'get_recent',
    {
      title: 'Get recent log',
      description: 'Get the most recent N audit log entries for a collection.',
      inputSchema: {
        collection: z.string(),
        n: z.number().int().positive().max(200).default(20),
      },
    },
    async ({ collection, n }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const r = await query(
        `SELECT ts, kind, actor, payload FROM logs
         WHERE collection_id = $1 ORDER BY ts DESC LIMIT $2`,
        [cid, n]
      );
      return ok(r.rows);
    }
  );
}
