import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { canAccessCollection, type AuthContext } from '../../auth/middleware.ts';
import { computeStats } from '../../stats.ts';
import { ok, err } from '../util.ts';

export function registerStats(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'stats',
    {
      title: 'Wiki stats',
      description: 'Dashboard data: page counts, top reads, recent activity, stale pages, recent searches. Use to give the user a quick health snapshot of a collection.',
      inputSchema: {
        collection: z.string(),
        days: z.number().int().positive().max(365).default(7),
      },
    },
    async ({ collection, days }) => {
      if (!canAccessCollection(auth, collection)) return err('not accessible');
      const stats = await computeStats(collection, days);
      if (!stats) return err(`collection not found: ${collection}`);
      return ok(stats);
    }
  );
}
