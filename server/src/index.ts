import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpServer } from './mcp/server.ts';
import { verifyBearer, canAccessCollection, type AuthContext } from './auth/middleware.ts';
import { query } from './db/client.ts';
import { computeStats, computeTeamActivity } from './stats.ts';
import { renderDashboard, renderCollectionPicker, renderPageDetail, renderTeamPage } from './dashboard.ts';
import { rateLimit } from './rate-limit.ts';
import { VERSION } from './version.ts';

const PORT = Number(process.env.PORT ?? 8787);

interface SessionEntry {
  transport: StreamableHTTPServerTransport;
  tokenId: number;
  lastUsed: number;
}

const sessions = new Map<string, SessionEntry>();

// 8 hr covers a normal Claude Code working session — long-idle (think → batch)
// patterns won't lose their session and trip "Server not initialized". Upper
// bound is also the worst-case lag for a revoked token to stop working via an
// already-open session, so don't push this much higher without rotating it.
const SESSION_IDLE_MS = 8 * 60 * 60_000;
const SESSION_SWEEP_MS = 5 * 60_000;
setInterval(() => {
  const now = Date.now();
  for (const [sid, entry] of sessions) {
    if (now - entry.lastUsed > SESSION_IDLE_MS) {
      try { entry.transport.close(); } catch { /* transport already gone */ }
      sessions.delete(sid);
    }
  }
}, SESSION_SWEEP_MS).unref();

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

const DASH_COOKIE = 'scriptorium_dash';
const DASH_COOKIE_MAX_AGE = 12 * 60 * 60; // 12h

function parseCookies(header: string | undefined): Record<string, string> {
  if (!header) return {};
  const out: Record<string, string> = {};
  for (const part of header.split(';')) {
    const eq = part.indexOf('=');
    if (eq < 0) continue;
    const k = part.slice(0, eq).trim();
    const v = part.slice(eq + 1).trim();
    if (k) {
      try { out[k] = decodeURIComponent(v); } catch { out[k] = v; }
    }
  }
  return out;
}

function isHttps(req: http.IncomingMessage): boolean {
  if (req.headers['x-forwarded-proto'] === 'https') return true;
  return (req.socket as { encrypted?: boolean }).encrypted === true;
}

function dashCookieValue(token: string, secure: boolean): string {
  const parts = [
    `${DASH_COOKIE}=${encodeURIComponent(token)}`,
    'Path=/dashboard',
    'HttpOnly',
    'SameSite=Strict',
    `Max-Age=${DASH_COOKIE_MAX_AGE}`,
  ];
  if (secure) parts.push('Secure');
  return parts.join('; ');
}

function clearDashCookie(secure: boolean): string {
  const parts = [
    `${DASH_COOKIE}=`,
    'Path=/dashboard',
    'HttpOnly',
    'SameSite=Strict',
    'Max-Age=0',
  ];
  if (secure) parts.push('Secure');
  return parts.join('; ');
}

async function handleDashboard(req: http.IncomingMessage, res: http.ServerResponse) {
  const ip = (req.socket.remoteAddress ?? 'unknown').replace(/^::ffff:/, '');
  if (!rateLimit(`dash:${ip}`, 20, 1 / 3)) {
    res.writeHead(429, { 'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '3' });
    res.end('rate limited (20 req/min per IP)');
    return;
  }

  const url = new URL(req.url!, `http://${req.headers.host ?? 'localhost'}`);
  const secure = isHttps(req);

  // Logout: clear cookie + redirect to bare /dashboard.
  if (url.pathname === '/dashboard/logout') {
    res.writeHead(303, { Location: '/dashboard', 'Set-Cookie': clearDashCookie(secure) });
    res.end();
    return;
  }

  // First-visit token swap: ?token=<raw> → set cookie, redirect to clean URL.
  // The token still appears once in proxy access logs on this single request,
  // but every subsequent navigation is cookie-only — no token in URL, history,
  // or Referer.
  const queryToken = url.searchParams.get('token');
  if (queryToken) {
    const probe = await verifyBearer(`Bearer ${queryToken}`);
    if (!probe) {
      res.writeHead(401, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('Unauthorized — token invalid or expired');
      return;
    }
    url.searchParams.delete('token');
    const cleanUrl = url.pathname + (url.searchParams.toString() ? `?${url.searchParams.toString()}` : '');
    res.writeHead(303, { Location: cleanUrl, 'Set-Cookie': dashCookieValue(queryToken, secure) });
    res.end();
    return;
  }

  let authHeader = req.headers.authorization;
  if (!authHeader) {
    const cookies = parseCookies(req.headers.cookie);
    const fromCookie = cookies[DASH_COOKIE];
    if (fromCookie) authHeader = `Bearer ${fromCookie}`;
  }
  const auth = await verifyBearer(authHeader);
  if (!auth) {
    res.writeHead(401, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Unauthorized — append ?token=<token> once to set a session cookie, or send Authorization: Bearer');
    return;
  }

  const view = url.searchParams.get('view');
  const collection = url.searchParams.get('collection');
  const path = url.searchParams.get('path');
  const days = Math.max(1, Math.min(365, Number(url.searchParams.get('days') ?? '7') || 7));

  if (view === 'team') {
    const teamCollection = collection && canAccessCollection(auth, collection) ? collection : undefined;
    const team = await computeTeamActivity({ collectionSlug: teamCollection, days });
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(renderTeamPage(team));
    return;
  }

  if (!collection) {
    const r = await query<{ slug: string; name: string }>('SELECT slug, name FROM collections ORDER BY slug');
    const visible = r.rows.filter(c => canAccessCollection(auth, c.slug));
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(renderCollectionPicker({ collections: visible }));
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
    }));
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

  // General throttle: 120 burst, 2 req/sec sustained — covers a normal MCP
  // turn (search → 3 get_pages → update → log) without thrashing.
  if (!rateLimit(`mcp:${auth.tokenId}`, 120, 2)) {
    res.writeHead(429, { 'Content-Type': 'application/json', 'Retry-After': '1' });
    res.end(JSON.stringify({ error: 'rate limited (120 burst, 2 req/sec sustained per token)' }));
    return;
  }

  const sessionId = (req.headers['mcp-session-id'] as string | undefined)?.trim();

  let entry: SessionEntry | undefined = sessionId ? sessions.get(sessionId) : undefined;

  if (entry && entry.tokenId !== auth.tokenId) {
    return send(res, 403, { error: 'session does not belong to this token' });
  }

  // Stale session-id (client kept it across an idle sweep). Per MCP spec, return
  // 404 so the client knows to drop the id and reinitialize — never silently
  // create a new transport here, because the new transport hasn't seen an
  // `initialize` request yet and will reject every subsequent tool call with
  // "Server not initialized".
  if (sessionId && !entry) {
    return send(res, 404, { error: 'session expired or unknown; reinitialize without mcp-session-id' });
  }

  if (!entry) {
    if (req.method !== 'POST') {
      return send(res, 400, { error: 'no valid session; initialize with POST first' });
    }
    // Session creation is heavy (instantiates the full MCP server, registers
    // every tool). Throttle it harder so a leaked token can't churn RAM by
    // spamming inits without ever sending DELETE.
    if (!rateLimit(`mcp:init:${auth.tokenId}`, 5, 5 / 60)) {
      res.writeHead(429, { 'Content-Type': 'application/json', 'Retry-After': '12' });
      res.end(JSON.stringify({ error: 'rate limited (session inits: 5 burst, 5 per minute sustained)' }));
      return;
    }
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
      onsessioninitialized: (id: string) => {
        sessions.set(id, { transport, tokenId: auth.tokenId, lastUsed: Date.now() });
      },
    });
    transport.onclose = () => {
      const sid = transport.sessionId;
      if (sid) sessions.delete(sid);
    };
    const mcp = createMcpServer(auth);
    await mcp.connect(transport);
    entry = { transport, tokenId: auth.tokenId, lastUsed: Date.now() };
  } else {
    entry.lastUsed = Date.now();
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
