import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpServer } from './mcp/server.ts';
import { verifyBearer, canAccessCollection, type AuthContext } from './auth/middleware.ts';
import { query } from './db/client.ts';
import { computeStats } from './stats.ts';
import { renderDashboard, renderCollectionPicker, renderPageDetail } from './dashboard.ts';
import { rateLimit } from './rate-limit.ts';

const PORT = Number(process.env.PORT ?? 8787);
const VERSION = '0.3.0';

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
  const ip = (req.socket.remoteAddress ?? 'unknown').replace(/^::ffff:/, '');
  if (!rateLimit(`dash:${ip}`, 20, 1 / 3)) {
    res.writeHead(429, { 'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '3' });
    res.end('rate limited (20 req/min per IP)');
    return;
  }

  const url = new URL(req.url!, `http://${req.headers.host ?? 'localhost'}`);
  let authHeader = req.headers.authorization;
  const queryToken = url.searchParams.get('token') ?? undefined;
  if (!authHeader && queryToken) authHeader = `Bearer ${queryToken}`;
  const auth = await verifyBearer(authHeader);
  if (!auth) {
    res.writeHead(401, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Unauthorized — pass Bearer header or ?token=<token>');
    return;
  }

  const collection = url.searchParams.get('collection');
  const path = url.searchParams.get('path');
  const days = Math.max(1, Math.min(365, Number(url.searchParams.get('days') ?? '7') || 7));

  if (!collection) {
    const r = await query<{ slug: string; name: string }>('SELECT slug, name FROM collections ORDER BY slug');
    const visible = r.rows.filter(c => canAccessCollection(auth, c.slug));
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(renderCollectionPicker({ collections: visible, token: queryToken }));
    return;
  }

  if (!canAccessCollection(auth, collection)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('forbidden — this token cannot access that collection');
    return;
  }

  if (path) {
    const r = await query<{ id: number; content: string; frontmatter: Record<string, unknown>; version: number; updated_at: Date }>(
      `SELECT p.id, p.content, p.frontmatter, p.version, p.updated_at
       FROM pages p
       JOIN collections c ON c.id = p.collection_id
       WHERE c.slug = $1 AND p.path = $2 AND p.deleted_at IS NULL`,
      [collection, path]
    );
    const row = r.rows[0];
    if (!row) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end(`page not found: ${path}`);
      return;
    }
    const reads = await query<{ ts: Date; actor: string }>(
      `SELECT ts, actor FROM logs
       WHERE collection_id = (SELECT id FROM collections WHERE slug = $1)
         AND kind = 'page_read' AND payload->>'path' = $2
       ORDER BY ts DESC LIMIT 10`,
      [collection, path]
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(renderPageDetail({
      collection,
      path,
      content: row.content,
      frontmatter: row.frontmatter,
      version: row.version,
      updated_at: row.updated_at.toISOString(),
      recent_reads: reads.rows.map(r => ({ ts: r.ts.toISOString(), actor: r.actor })),
    }, { token: queryToken }));
    return;
  }

  const stats = await computeStats(collection, days);
  if (!stats) {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`collection not found: ${collection}`);
    return;
  }

  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(renderDashboard(stats, { token: queryToken }));
}

async function handleMcp(req: http.IncomingMessage, res: http.ServerResponse) {
  const auth = await verifyBearer(req.headers.authorization);
  if (!auth) return send(res, 401, { error: 'unauthorized' });

  if (!rateLimit(`mcp:${auth.tokenId}`, 60, 1)) {
    res.writeHead(429, { 'Content-Type': 'application/json', 'Retry-After': '1' });
    res.end(JSON.stringify({ error: 'rate limited (60 req/min per token)' }));
    return;
  }

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
