import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type { AuthContext } from '../auth/middleware.ts';
import { registerHealth } from './tools/health.ts';
import { registerCollections } from './tools/collections.ts';
import { registerPages } from './tools/pages.ts';
import { registerSearch } from './tools/search.ts';
import { registerLog } from './tools/log.ts';
import { registerRaw } from './tools/raw.ts';
import { registerLint } from './tools/lint.ts';
import { registerStats } from './tools/stats.ts';
import { registerTeam } from './tools/team.ts';
import { VERSION } from '../version.ts';

export function createMcpServer(auth: AuthContext): McpServer {
  const server = new McpServer({
    name: 'scriptorium',
    version: VERSION,
  });

  registerHealth(server, auth);
  registerCollections(server, auth);
  registerPages(server, auth);
  registerSearch(server, auth);
  registerLog(server, auth);
  registerRaw(server, auth);
  registerLint(server, auth);
  registerStats(server, auth);
  registerTeam(server, auth);

  return server;
}

export type { AuthContext };
