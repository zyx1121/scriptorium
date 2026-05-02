import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query } from '../../db/client.ts';
import { ok } from '../util.ts';
import type { AuthContext } from '../../auth/middleware.ts';

export function registerHealth(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'health',
    {
      title: 'Health',
      description: 'Check server health and database connectivity.',
      inputSchema: {},
    },
    async () => {
      let dbOk = false;
      try {
        await query('SELECT 1');
        dbOk = true;
      } catch {
        dbOk = false;
      }
      return ok({ ok: true, db_ok: dbOk, version: '0.1.0' });
    }
  );

  server.registerTool(
    'whoami',
    {
      title: 'Whoami',
      description: 'Return the current bearer token identity, scopes, and accessible collections.',
      inputSchema: {},
    },
    async () =>
      ok({
        token_name: auth.tokenName,
        scopes: auth.scopes,
        collections: auth.collectionSlugs.length === 0 ? '*' : auth.collectionSlugs,
      })
  );
}
