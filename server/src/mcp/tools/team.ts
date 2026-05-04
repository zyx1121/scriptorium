import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { canAccessCollection, type AuthContext } from '../../auth/middleware.ts';
import { computeTeamActivity } from '../../stats.ts';
import { ok, err } from '../util.ts';

export function registerTeam(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'team_activity',
    {
      title: 'Team activity',
      description: 'Per-user activity breakdown — ingests / searches / reads / last-active. Optionally scoped to a single collection. Use to answer "who has been active?", "who ingested most this week?", "show team activity".',
      inputSchema: {
        collection: z.string().optional(),
        days: z.number().int().positive().max(365).default(7),
      },
    },
    async ({ collection, days }) => {
      if (collection && !canAccessCollection(auth, collection)) return err('not accessible');
      const result = await computeTeamActivity({ collectionSlug: collection, days });
      return ok(result);
    }
  );
}
