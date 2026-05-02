import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpServer } from './mcp/server.ts';
import { verifyBearer, type AuthContext } from './auth/middleware.ts';
import { query } from './db/client.ts';

const PORT = Number(process.env.PORT ?? 8787);
const VERSION = '0.1.0';

interface SessionEntry {
  transport: StreamableHTTPServerTransport;
  tokenId: number;
}

const sessions = new Map<string, SessionEntry>();

function send(res: http.ServerResponse, status: number, body: unknown) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

async function readJsonBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw) return resolve(undefined);
      try { resolve(JSON.parse(raw)); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

async function handleHealth(_req: http.IncomingMessage, res: http.ServerResponse) {
  let dbOk = false;
  try { await query('SELECT 1'); dbOk = true; } catch { dbOk = false; }
  send(res, 200, { ok: true, db_ok: dbOk, version: VERSION });
}

async function handleWhoami(req: http.IncomingMessage, res: http.ServerResponse) {
  const auth = await verifyBearer(req.headers.authorization);
  if (!auth) return send(res, 401, { error: 'unauthorized' });
  send(res, 200, {
    token_name: auth.tokenName,
    scopes: auth.scopes,
    collections: auth.collectionSlugs.length === 0 ? '*' : auth.collectionSlugs,
  });
}

async function handleMcp(req: http.IncomingMessage, res: http.ServerResponse) {
  const auth = await verifyBearer(req.headers.authorization);
  if (!auth) return send(res, 401, { error: 'unauthorized' });

  const sessionId = (req.headers['mcp-session-id'] as string | undefined)?.trim();

  let entry: SessionEntry | undefined = sessionId ? sessions.get(sessionId) : undefined;

  if (entry && entry.tokenId !== auth.tokenId) {
    return send(res, 403, { error: 'session does not belong to this token' });
  }

  if (!entry) {
    if (req.method !== 'POST') {
      return send(res, 400, { error: 'no valid session; initialize with POST first' });
    }
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
      onsessioninitialized: (id: string) => {
        sessions.set(id, { transport, tokenId: auth.tokenId });
      },
    });
    transport.onclose = () => {
      const sid = transport.sessionId;
      if (sid) sessions.delete(sid);
    };
    const mcp = createMcpServer(auth);
    await mcp.connect(transport);
    entry = { transport, tokenId: auth.tokenId };
  }

  let body: unknown;
  if (req.method === 'POST') {
    try { body = await readJsonBody(req); }
    catch { return send(res, 400, { error: 'invalid JSON body' }); }
  }

  await entry.transport.handleRequest(req, res, body);
}

const server = http.createServer((req, res) => {
  const url = req.url ?? '/';
  (async () => {
    try {
      if (url === '/health' && req.method === 'GET') return await handleHealth(req, res);
      if (url === '/whoami' && req.method === 'GET') return await handleWhoami(req, res);
      if (url.startsWith('/mcp')) return await handleMcp(req, res);
      send(res, 404, { error: 'not found' });
    } catch (e: any) {
      console.error('[server] error:', e);
      if (!res.headersSent) send(res, 500, { error: e?.message ?? 'internal error' });
      else res.end();
    }
  })();
});

server.listen(PORT, () => {
  console.log(`[scriptorium] listening on :${PORT}`);
});

function shutdown(sig: string) {
  console.log(`[scriptorium] received ${sig}, shutting down`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5_000).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
