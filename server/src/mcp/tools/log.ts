import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query } from '../../db/client.ts';
import { canWrite, type AuthContext } from '../../auth/middleware.ts';
import { ok, err, getCollectionIdBySlug } from '../util.ts';

export function registerLog(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'append_log',
    {
      title: 'Append to log',
      description: 'Append an audit entry to the collection log (immutable).',
      inputSchema: {
        collection: z.string(),
        kind: z.string().min(1),
        payload: z.record(z.any()).default({}),
      },
    },
    async ({ collection, kind, payload }) => {
      if (!canWrite(auth)) return err('write scope required');
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      await query(
        'INSERT INTO logs (collection_id, kind, actor, actor_user_id, payload) VALUES ($1, $2, $3, $4, $5)',
        [cid, kind, auth.tokenName, auth.userId, payload]
      );
      return ok({ logged: true, kind });
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
