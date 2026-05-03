import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpServer } from './mcp/server.ts';
import { verifyBearer, canAccessCollection, type AuthContext } from './auth/middleware.ts';
import { query } from './db/client.ts';
import { computeStats } from './stats.ts';
import { renderDashboard } from './dashboard.ts';

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

async function handleDashboard(req: http.IncomingMessage, res: http.ServerResponse) {
  const url = new URL(req.url!, `http://${req.headers.host ?? 'localhost'}`);
  // auth: prefer Bearer header; fall back to ?token= query (browser convenience).
  let authHeader = req.headers.authorization;
  const queryToken = url.searchParams.get('token');
  if (!authHeader && queryToken) authHeader = `Bearer ${queryToken}`;
  const auth = await verifyBearer(authHeader);
  if (!auth) {
    res.writeHead(401, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Unauthorized — pass Bearer header or ?token=<token>');
    return;
  }

  const collection = url.searchParams.get('collection');
  const days = Math.max(1, Math.min(365, Number(url.searchParams.get('days') ?? '7') || 7));

  if (!collection) {
    const r = await query<{ slug: string; name: string }>('SELECT slug, name FROM collections ORDER BY slug');
    const visible = r.rows.filter(c => canAccessCollection(auth, c.slug));
    const list = visible.map(c =>
      `<li><a href="/dashboard?collection=${encodeURIComponent(c.slug)}${queryToken ? `&token=${encodeURIComponent(queryToken)}` : ''}">${c.name} <span style="color:#888">(${c.slug})</span></a></li>`
    ).join('');
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!doctype html><meta charset="utf-8"><title>scriptorium</title>
<body style="font:14px/1.6 -apple-system,system-ui,monospace;background:#0e0e10;color:#e9e9ec;padding:32px">
<h1 style="font-weight:600">scriptorium · pick a collection</h1>
<ul>${list || '<li style="color:#888">(no collections)</li>'}</ul>
</body>`);
    return;
  }

  if (!canAccessCollection(auth, collection)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('forbidden — this token cannot access that collection');
    return;
  }

  const stats = await computeStats(collection, days);
  if (!stats) {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`collection not found: ${collection}`);
    return;
  }

  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(renderDashboard(stats));
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
      if (url.startsWith('/dashboard') && req.method === 'GET') return await handleDashboard(req, res);
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
