import type { StatsResult, TeamActivityResult } from './stats.ts';

const escape = (s: string | null | undefined): string =>
  String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

const fmtDate = (iso: string | null): string => {
  if (!iso) return '—';
  return new Date(iso).toISOString().slice(0, 16).replace('T', ' ');
};

const ago = (iso: string | null): string => {
  if (!iso) return 'never';
  const ms = Date.now() - new Date(iso).getTime();
  const d = Math.floor(ms / 86400000);
  if (d > 0) return `${d}d ago`;
  const h = Math.floor(ms / 3600000);
  if (h > 0) return `${h}h ago`;
  const m = Math.floor(ms / 60000);
  if (m > 0) return `${m}m ago`;
  return 'just now';
};

const STYLE = `
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #000; color: #fff; }
body {
  font-family: ui-monospace, "SF Mono", "Menlo", "DejaVu Sans Mono", monospace;
  font-size: 13px;
  line-height: 1.5;
  min-height: 100vh;
  padding: 16px 24px 32px;
}
a { color: #fff; text-decoration: underline; text-underline-offset: 2px; }
a:hover { background: #fff; color: #000; text-decoration: none; }
h1 {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
h1 .sep { color: #666; }
h1 .meta { color: #888; font-weight: 400; text-transform: none; letter-spacing: 0; }
h2 {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin: 24px 0 6px;
  border-bottom: 1px solid #fff;
  padding-bottom: 2px;
}
.bar { color: #666; user-select: none; }
.totals { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid #fff; }
.stat { padding: 10px 14px; border-right: 1px solid #fff; }
.stat:last-child { border-right: 0; }
.stat .n { font-size: 22px; font-weight: 700; line-height: 1.1; }
.stat .l { color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 4px; }
.tags { display: flex; flex-wrap: wrap; gap: 0; border: 1px solid #fff; }
.tag { padding: 4px 10px; border-right: 1px solid #fff; color: #888; font-size: 11px; }
.tag:last-child { border-right: 0; }
.tag b { color: #fff; font-weight: 700; }
table { width: 100%; border-collapse: collapse; border: 1px solid #fff; }
th, td { padding: 4px 10px; border-bottom: 1px solid #fff; text-align: left; vertical-align: top; font-weight: 400; }
th { background: #fff; color: #000; text-transform: uppercase; font-size: 10px; letter-spacing: 0.1em; font-weight: 700; }
tr:last-child td { border-bottom: 0; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.dim { color: #888; }
td.empty { text-align: center; color: #666; padding: 12px; }
code { font-family: inherit; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.crumbs { color: #888; font-size: 11px; margin-bottom: 16px; }
.crumbs a { color: #888; }
pre.body {
  border: 1px solid #fff;
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  margin: 0;
}
.kv { width: 100%; }
.kv th { width: 18ch; }
@media (max-width: 760px) {
  body { padding: 12px; font-size: 12px; }
  .totals { grid-template-columns: repeat(2, 1fr); }
  .stat { border-bottom: 1px solid #fff; }
  .grid2 { grid-template-columns: 1fr; }
}
`;

function shell(title: string, body: string): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escape(title)}</title>
<style>${STYLE}</style>
</head>
<body>${body}</body>
</html>`;
}

export interface DashboardOpts {
  /** raw token to thread through links so navigation stays authenticated in the browser. */
  token?: string;
}

function withToken(href: string, token?: string): string {
  if (!token) return href;
  const sep = href.includes('?') ? '&' : '?';
  return `${href}${sep}token=${encodeURIComponent(token)}`;
}

export function renderDashboard(s: StatsResult, opts: DashboardOpts = {}): string {
  const t = opts.token;
  const pageHref = (path: string) =>
    withToken(`/dashboard?collection=${encodeURIComponent(s.collection)}&path=${encodeURIComponent(path)}`, t);

  const byType = Object.entries(s.by_type)
    .sort(([, a], [, b]) => b - a)
    .map(([k, n]) => `<span class="tag">${escape(k)} <b>${n}</b></span>`)
    .join('');

  const topReadsRows = s.top_pages_by_reads.length === 0
    ? `<tr><td colspan="3" class="empty">no reads recorded yet</td></tr>`
    : s.top_pages_by_reads.map(r =>
        `<tr><td><a href="${escape(pageHref(r.path))}">${escape(r.path)}</a></td><td class="num">${r.reads}</td><td class="dim">${ago(r.last_read)}</td></tr>`
      ).join('');

  const recentlyAddedRows = s.recently_added.map(r =>
    `<tr><td><a href="${escape(pageHref(r.path))}">${escape(r.path)}</a></td><td>${escape(r.type ?? '?')}</td><td class="dim">${ago(r.created_at)}</td></tr>`
  ).join('');

  const recentlyUpdatedRows = s.recently_updated.map(r =>
    `<tr><td><a href="${escape(pageHref(r.path))}">${escape(r.path)}</a></td><td>${escape(r.type ?? '?')}</td><td class="dim">${ago(r.updated_at)}</td></tr>`
  ).join('');

  const recentSearchesRows = s.recent_searches.length === 0
    ? `<tr><td colspan="3" class="empty">no searches recorded yet</td></tr>`
    : s.recent_searches.map(r =>
        `<tr><td>${escape(r.query)}</td><td class="num">${r.result_count ?? '—'}</td><td class="dim">${ago(r.ts)}</td></tr>`
      ).join('');

  const byUserRows = s.top_users_by_activity.length === 0
    ? `<tr><td colspan="6" class="empty">no team activity recorded</td></tr>`
    : s.top_users_by_activity.map(u =>
        `<tr><td>${escape(u.display)}${u.user_email && u.user_name ? ` <span class="dim">(${escape(u.user_name)})</span>` : ''}${u.user_email ? '' : ' <span class="dim">(unassigned)</span>'}</td><td class="num">${u.ingests}</td><td class="num">${u.searches}</td><td class="num">${u.page_reads}</td><td class="num">${u.total}</td><td class="dim">${ago(u.last_active)}</td></tr>`
      ).join('');

  const staleRows = s.stale.length === 0
    ? `<tr><td colspan="3" class="empty">no stale pages</td></tr>`
    : s.stale.map(r =>
        `<tr><td><a href="${escape(pageHref(r.path))}">${escape(r.path)}</a></td><td class="dim">${escape(fmtDate(r.updated_at))}</td><td class="dim">${ago(r.last_read)}</td></tr>`
      ).join('');

  const indexHref = withToken('/dashboard', t);
  const collHref = withToken(`/dashboard?collection=${encodeURIComponent(s.collection)}`, t);
  const generated = new Date().toISOString().replace('T', ' ').slice(0, 19);

  const body = `
<h1>scriptorium <span class="sep">/</span> ${escape(s.collection)} <span class="meta">— ${s.window_days}d window</span></h1>
<div class="crumbs"><a href="${escape(indexHref)}">collections</a> <span class="bar">/</span> <a href="${escape(collHref)}">${escape(s.collection)}</a> <span class="bar">/</span> dashboard <span style="float:right">generated ${escape(generated)} UTC</span></div>

<div class="totals">
  <div class="stat"><div class="n">${s.totals.pages}</div><div class="l">pages</div></div>
  <div class="stat"><div class="n">${s.totals.raw_sources}</div><div class="l">raw sources</div></div>
  <div class="stat"><div class="n">${s.totals.ingests}</div><div class="l">ingests · ${s.window_days}d</div></div>
  <div class="stat"><div class="n">${s.totals.page_reads}</div><div class="l">reads · ${s.window_days}d</div></div>
  <div class="stat"><div class="n">${s.totals.searches}</div><div class="l">searches · ${s.window_days}d</div></div>
</div>

<h2>by type</h2>
<div class="tags">${byType || '<span class="tag">(empty)</span>'}</div>

<h2>top pages by reads</h2>
<table><thead><tr><th>path</th><th>reads</th><th>last read</th></tr></thead><tbody>${topReadsRows}</tbody></table>

<div class="grid2">
  <div>
    <h2>recently added</h2>
    <table><thead><tr><th>path</th><th>type</th><th>added</th></tr></thead><tbody>${recentlyAddedRows}</tbody></table>
  </div>
  <div>
    <h2>recently updated</h2>
    <table><thead><tr><th>path</th><th>type</th><th>updated</th></tr></thead><tbody>${recentlyUpdatedRows}</tbody></table>
  </div>
</div>

<h2>recent searches</h2>
<table><thead><tr><th>query</th><th>results</th><th>when</th></tr></thead><tbody>${recentSearchesRows}</tbody></table>

<h2>by user (${s.window_days}d)</h2>
<table><thead><tr><th>user</th><th>ingests</th><th>searches</th><th>reads</th><th>total</th><th>last active</th></tr></thead><tbody>${byUserRows}</tbody></table>

<h2>stale (>180d, low traffic)</h2>
<table><thead><tr><th>path</th><th>updated</th><th>last read</th></tr></thead><tbody>${staleRows}</tbody></table>
`;

  return shell(`scriptorium · ${s.collection}`, body);
}

export function renderCollectionPicker(opts: { collections: { slug: string; name: string }[]; token?: string }): string {
  const t = opts.token;
  const items = opts.collections.length === 0
    ? `<tr><td class="empty">(no collections accessible to this token)</td></tr>`
    : opts.collections.map(c =>
        `<tr><td><a href="${escape(withToken(`/dashboard?collection=${encodeURIComponent(c.slug)}`, t))}">${escape(c.name)}</a> <span class="dim">(${escape(c.slug)})</span></td></tr>`
      ).join('');

  const teamHref = withToken('/dashboard?view=team', t);
  const body = `
<h1>scriptorium <span class="sep">/</span> collections</h1>
<div class="crumbs">pick a collection · or <a href="${escape(teamHref)}">team activity</a></div>
<table><thead><tr><th>name</th></tr></thead><tbody>${items}</tbody></table>
`;
  return shell('scriptorium', body);
}

export function renderTeamPage(t: TeamActivityResult, opts: DashboardOpts = {}): string {
  const tk = opts.token;
  const indexHref = withToken('/dashboard', tk);

  const userRows = t.users.length === 0
    ? `<tr><td colspan="7" class="empty">no users registered</td></tr>`
    : t.users.map(u =>
        `<tr><td>${escape(u.email ?? '?')}${u.name ? ` <span class="dim">(${escape(u.name)})</span>` : ''}</td><td>${escape(u.role ?? '-')}</td><td class="num">${u.active_tokens}</td><td class="num">${u.ingests}</td><td class="num">${u.searches}</td><td class="num">${u.page_reads}</td><td class="dim">${ago(u.last_active)}</td></tr>`
      ).join('');

  const unassignedRows = t.unassigned_actors.length === 0
    ? `<tr><td colspan="3" class="empty">no unassigned actors</td></tr>`
    : t.unassigned_actors.map(a =>
        `<tr><td>${escape(a.actor)}</td><td class="num">${a.total}</td><td class="dim">${ago(a.last_active)}</td></tr>`
      ).join('');

  const actionRows = t.recent_actions.length === 0
    ? `<tr><td colspan="5" class="empty">no recent actions</td></tr>`
    : t.recent_actions.map(a => {
        const collHref = a.collection ? withToken(`/dashboard?collection=${encodeURIComponent(a.collection)}`, tk) : null;
        const summary = JSON.stringify(a.payload).slice(0, 80);
        return `<tr><td class="dim">${escape(fmtDate(a.ts))}</td><td>${escape(a.kind)}</td><td>${escape(a.user_email ?? a.actor)}</td><td>${collHref ? `<a href="${escape(collHref)}">${escape(a.collection!)}</a>` : '<span class="dim">-</span>'}</td><td class="dim">${escape(summary)}</td></tr>`;
      }).join('');

  const body = `
<h1>scriptorium <span class="sep">/</span> team <span class="meta">— ${t.window_days}d window · scope: ${escape(t.scope)}</span></h1>
<div class="crumbs"><a href="${escape(indexHref)}">collections</a> <span class="bar">/</span> team</div>

<h2>users</h2>
<table><thead><tr><th>user</th><th>role</th><th>tokens</th><th>ingests</th><th>searches</th><th>reads</th><th>last active</th></tr></thead><tbody>${userRows}</tbody></table>

<h2>unassigned actors (legacy tokens without a user)</h2>
<table><thead><tr><th>actor (token name)</th><th>total actions</th><th>last active</th></tr></thead><tbody>${unassignedRows}</tbody></table>

<h2>recent actions (last 30, ${t.window_days}d)</h2>
<table><thead><tr><th>when</th><th>kind</th><th>by</th><th>collection</th><th>payload</th></tr></thead><tbody>${actionRows}</tbody></table>
`;
  return shell('scriptorium · team', body);
}

export interface PageDetailData {
  collection: string;
  path: string;
  content: string;
  frontmatter: Record<string, unknown>;
  version: number;
  updated_at: string;
  recent_reads: Array<{ ts: string; actor: string }>;
}

export function renderPageDetail(p: PageDetailData, opts: DashboardOpts = {}): string {
  const t = opts.token;
  const indexHref = withToken('/dashboard', t);
  const collHref = withToken(`/dashboard?collection=${encodeURIComponent(p.collection)}`, t);

  const fmRows = Object.entries(p.frontmatter)
    .map(([k, v]) => `<tr><th>${escape(k)}</th><td>${escape(typeof v === 'string' ? v : JSON.stringify(v))}</td></tr>`)
    .join('');

  const readsRows = p.recent_reads.length === 0
    ? `<tr><td colspan="2" class="empty">no recent reads</td></tr>`
    : p.recent_reads.map(r =>
        `<tr><td class="dim">${escape(fmtDate(r.ts))}</td><td>${escape(r.actor)}</td></tr>`
      ).join('');

  const body = `
<h1>scriptorium <span class="sep">/</span> ${escape(p.collection)} <span class="sep">/</span> ${escape(p.path)} <span class="meta">— v${p.version}</span></h1>
<div class="crumbs"><a href="${escape(indexHref)}">collections</a> <span class="bar">/</span> <a href="${escape(collHref)}">${escape(p.collection)}</a> <span class="bar">/</span> ${escape(p.path)} <span style="float:right">updated ${escape(fmtDate(p.updated_at))} UTC</span></div>

<h2>frontmatter</h2>
<table class="kv"><tbody>${fmRows}</tbody></table>

<h2>content</h2>
<pre class="body">${escape(p.content)}</pre>

<h2>recent reads (last 10)</h2>
<table><thead><tr><th>ts</th><th>actor</th></tr></thead><tbody>${readsRows}</tbody></table>
`;

  return shell(`${p.collection} / ${p.path}`, body);
}
