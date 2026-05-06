import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query } from '../../db/client.ts';
import type { AuthContext } from '../../auth/middleware.ts';
import { ok, err, getCollectionIdBySlug } from '../util.ts';

interface LintIssue {
  severity: 'error' | 'warning' | 'info';
  rule: string;
  path: string;
  detail: string;
}

const STALE_DAYS = 180;

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

export function registerLint(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'lint',
    {
      title: 'Lint wiki',
      description: 'Run health checks: dead wikilinks, orphan pages, missing concepts, stale claims, schema violations.',
      inputSchema: {
        collection: z.string(),
        scope: z.enum(['all', 'touched_pages']).default('all'),
        paths: z.array(z.string()).optional(),
      },
    },
    async ({ collection, scope, paths }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');

      let pageQuery = `SELECT path, content, frontmatter, updated_at FROM pages
                       WHERE collection_id = $1 AND deleted_at IS NULL`;
      const params: any[] = [cid];
      if (scope === 'touched_pages' && paths && paths.length > 0) {
        params.push(paths);
        pageQuery += ` AND path = ANY($${params.length})`;
      }

      const r = await query<{ path: string; content: string; frontmatter: any; updated_at: Date }>(pageQuery, params);

      // Resolve a wikilink target to a full page path. Two accepted forms:
      //   [[notes/foo]]  → matches page path "notes/foo.md"
      //   [[foo]]        → matches any page whose basename is "foo" (unique only)
      // Same-named files in different folders disambiguate by full path.
      const fullPathIndex = new Map<string, string>();   // "notes/foo" -> "notes/foo.md"
      const basenameIndex = new Map<string, string[]>(); // "foo" -> ["notes/foo.md", "refs/foo.md"]
      for (const p of r.rows) {
        const noExt = p.path.replace(/\.md$/, '');
        fullPathIndex.set(noExt, p.path);
        const base = noExt.split('/').pop()!;
        const bucket = basenameIndex.get(base) ?? [];
        bucket.push(p.path);
        basenameIndex.set(base, bucket);
      }

      function resolveLink(link: string): { resolved: string | null; ambiguous: boolean } {
        const stripped = link.replace(/\.md$/, '');
        const full = fullPathIndex.get(stripped);
        if (full) return { resolved: full, ambiguous: false };
        const matches = basenameIndex.get(stripped) ?? [];
        if (matches.length === 1) return { resolved: matches[0]!, ambiguous: false };
        if (matches.length > 1) return { resolved: null, ambiguous: true };
        return { resolved: null, ambiguous: false };
      }

      const issues: LintIssue[] = [];
      const incomingLinks = new Map<string, Set<string>>(); // target path -> set of pages linking in

      for (const page of r.rows) {
        const links = [...page.content.matchAll(WIKILINK_RE)].map(m => m[1]!);
        for (const link of links) {
          const { resolved, ambiguous } = resolveLink(link);
          if (resolved) {
            const inc = incomingLinks.get(resolved) ?? new Set<string>();
            inc.add(page.path);
            incomingLinks.set(resolved, inc);
          } else if (ambiguous) {
            issues.push({ severity: 'warning', rule: 'ambiguous_wikilink', path: page.path,
              detail: `[[${link}]] matches multiple pages by basename — use the full path to disambiguate` });
          } else {
            issues.push({ severity: 'error', rule: 'dead_wikilink', path: page.path, detail: `[[${link}]] does not resolve` });
          }
        }

        // schema sanity
        if (!page.frontmatter?.title) {
          issues.push({ severity: 'error', rule: 'schema', path: page.path, detail: 'missing frontmatter.title' });
        }
        if (!page.frontmatter?.type) {
          issues.push({ severity: 'error', rule: 'schema', path: page.path, detail: 'missing frontmatter.type' });
        }
        if (page.frontmatter?.confidence === 'high' && (page.frontmatter.sources?.length ?? 0) < 2) {
          issues.push({ severity: 'warning', rule: 'confidence_inflation', path: page.path, detail: 'high confidence with <2 sources' });
        }

        // stale
        const updated = new Date(page.frontmatter?.updated ?? page.updated_at);
        const days = (Date.now() - updated.getTime()) / (1000 * 60 * 60 * 24);
        if (days > STALE_DAYS) {
          issues.push({ severity: 'info', rule: 'stale', path: page.path, detail: `updated ${days.toFixed(0)} days ago` });
        }
      }

      // orphans: pages with no incoming wikilinks (excluding index).
      for (const page of r.rows) {
        if (page.path === 'index.md') continue;
        if (!incomingLinks.has(page.path)) {
          issues.push({ severity: 'warning', rule: 'orphan', path: page.path, detail: 'no incoming wikilinks' });
        }
      }

      const errors = issues.filter(i => i.severity === 'error');
      const warnings = issues.filter(i => i.severity === 'warning');
      const info = issues.filter(i => i.severity === 'info');

      return ok({ counts: { errors: errors.length, warnings: warnings.length, info: info.length }, errors, warnings, info });
    }
  );
}
