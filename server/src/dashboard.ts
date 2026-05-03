import type { StatsResult } from './stats.ts';

const escape = (s: string | null | undefined): string =>
  String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

const fmtDate = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toISOString().slice(0, 16).replace('T', ' ');
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

export function renderDashboard(s: StatsResult): string {
  const byType = Object.entries(s.by_type)
    .sort(([, a], [, b]) => b - a)
    .map(([t, n]) => `<span class="tag">${escape(t)}<b>${n}</b></span>`)
    .join('');

  const topReadsRows = s.top_pages_by_reads.length === 0
    ? `<tr><td colspan="3" class="empty">no reads yet — instrument by browsing the wiki</td></tr>`
    : s.top_pages_by_reads.map(r =>
        `<tr><td><code>${escape(r.path)}</code></td><td class="num">${r.reads}</td><td class="dim">${ago(r.last_read)}</td></tr>`
      ).join('');

  const recentlyAddedRows = s.recently_added.map(r =>
    `<tr><td><code>${escape(r.path)}</code></td><td><span class="tag">${escape(r.type ?? '?')}</span></td><td class="dim">${ago(r.created_at)}</td></tr>`
  ).join('');

  const recentlyUpdatedRows = s.recently_updated.map(r =>
    `<tr><td><code>${escape(r.path)}</code></td><td><span class="tag">${escape(r.type ?? '?')}</span></td><td class="dim">${ago(r.updated_at)}</td></tr>`
  ).join('');

  const recentSearchesRows = s.recent_searches.length === 0
    ? `<tr><td colspan="3" class="empty">no searches yet</td></tr>`
    : s.recent_searches.map(r =>
        `<tr><td>${escape(r.query)}</td><td class="num">${r.result_count ?? '—'}</td><td class="dim">${ago(r.ts)}</td></tr>`
      ).join('');

  const staleRows = s.stale.length === 0
    ? `<tr><td colspan="3" class="empty">no stale pages — wiki is fresh</td></tr>`
    : s.stale.map(r =>
        `<tr><td><code>${escape(r.path)}</code></td><td class="dim">${fmtDate(r.updated_at)}</td><td class="dim">${ago(r.last_read)}</td></tr>`
      ).join('');

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>scriptorium — ${escape(s.collection)}</title>
<style>
  :root {
    --bg: #0e0e10; --fg: #e9e9ec; --muted: #8a8a93; --line: #232327;
    --accent: #ffb454; --pill: #1a1a1d; --emp: #5b5b62;
  }
  * { box-sizing: border-box; }
  body { font: 14px/1.55 -apple-system, system-ui, "Segoe UI", monospace; background: var(--bg); color: var(--fg); margin: 0; padding: 32px; }
  .wrap { max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }
  h1 small { color: var(--muted); font-weight: 400; margin-left: 12px; font-size: 14px; }
  .meta { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
  h2 { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--accent); margin: 32px 0 8px; }
  .totals { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 8px; }
  .stat { background: var(--pill); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
  .stat .n { font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
  .stat .l { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px; }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .tag { background: var(--pill); border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; font-size: 12px; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }
  .tag b { color: var(--fg); font-weight: 600; }
  table { width: 100%; border-collapse: collapse; background: var(--pill); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; background: #141417; }
  tr:last-child td { border-bottom: 0; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; color: var(--accent); }
  td.dim { color: var(--muted); }
  td.empty { text-align: center; color: var(--emp); font-style: italic; padding: 18px; }
  code { font: 13px ui-monospace, "SF Mono", Menlo, monospace; color: #d8d8de; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 800px) {
    body { padding: 16px; }
    .totals { grid-template-columns: repeat(2, 1fr); }
    .grid2 { grid-template-columns: 1fr; }
  }
  footer { color: var(--emp); font-size: 11px; margin-top: 40px; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>${escape(s.collection)}<small>scriptorium dashboard · ${s.window_days}-day window</small></h1>
  <div class="meta">generated ${new Date().toISOString().slice(0, 19).replace('T', ' ')} UTC</div>

  <div class="totals">
    <div class="stat"><div class="n">${s.totals.pages}</div><div class="l">pages</div></div>
    <div class="stat"><div class="n">${s.totals.raw_sources}</div><div class="l">raw sources</div></div>
    <div class="stat"><div class="n">${s.totals.ingests}</div><div class="l">ingests (${s.window_days}d)</div></div>
    <div class="stat"><div class="n">${s.totals.page_reads}</div><div class="l">reads (${s.window_days}d)</div></div>
    <div class="stat"><div class="n">${s.totals.searches}</div><div class="l">searches (${s.window_days}d)</div></div>
  </div>

  <h2>By type</h2>
  <div class="tags">${byType || '<span class="tag">(empty)</span>'}</div>

  <h2>Top pages by reads</h2>
  <table><thead><tr><th>path</th><th>reads</th><th>last read</th></tr></thead><tbody>${topReadsRows}</tbody></table>

  <div class="grid2">
    <div>
      <h2>Recently added</h2>
      <table><thead><tr><th>path</th><th>type</th><th>added</th></tr></thead><tbody>${recentlyAddedRows}</tbody></table>
    </div>
    <div>
      <h2>Recently updated</h2>
      <table><thead><tr><th>path</th><th>type</th><th>updated</th></tr></thead><tbody>${recentlyUpdatedRows}</tbody></table>
    </div>
  </div>

  <h2>Recent searches</h2>
  <table><thead><tr><th>query</th><th>results</th><th>when</th></tr></thead><tbody>${recentSearchesRows}</tbody></table>

  <h2>Stale (>180d, low traffic)</h2>
  <table><thead><tr><th>path</th><th>updated</th><th>last read</th></tr></thead><tbody>${staleRows}</tbody></table>

  <footer>scriptorium · the scribes don't sleep · refresh for live data</footer>
</div>
</body>
</html>`;
}
