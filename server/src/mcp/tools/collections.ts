import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query, withTransaction } from '../../db/client.ts';
import { canAccessCollection, canWrite, type AuthContext } from '../../auth/middleware.ts';
import { ok, err } from '../util.ts';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATES_DIR = join(__dirname, '..', '..', '..', 'templates');

const SLUG_RE = /^[a-z][a-z0-9-]{2,39}$/;

function readTemplate(name: string): string {
  return readFileSync(join(TEMPLATES_DIR, name), 'utf8');
}

export function registerCollections(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'list_collections',
    {
      title: 'List collections',
      description: 'List all collections this bearer token can access.',
      inputSchema: {},
    },
    async () => {
      const r = await query<{ slug: string; name: string; schema_version: number }>(
        'SELECT slug, name, schema_version FROM collections ORDER BY slug'
      );
      return ok(r.rows.filter(c => canAccessCollection(auth, c.slug)));
    }
  );

  server.registerTool(
    'create_collection',
    {
      title: 'Create collection',
      description: 'Create a new wiki collection seeded with a schema template (default | research | team-knowledge).',
      inputSchema: {
        slug: z.string(),
        name: z.string().min(1),
        schema_template: z.enum(['default', 'research', 'team-knowledge']).default('default'),
      },
    },
    async ({ slug, name, schema_template }) => {
      if (!canWrite(auth)) return err('write scope required');
      if (!SLUG_RE.test(slug)) return err('slug must be lowercase kebab-case, 3-40 chars, start with a letter');
      if (!canAccessCollection(auth, slug)) return err('this token cannot access that slug');

      const schemaMd = readTemplate(`SCHEMA-${schema_template}.md.tpl`).replace(/{{slug}}/g, slug).replace(/{{name}}/g, name);
      const indexMd = readTemplate('index.md.tpl').replace(/{{name}}/g, name);
      const today = new Date().toISOString().slice(0, 10);

      try {
        const result = await withTransaction(async client => {
          const c = await client.query<{ id: string }>(
            'INSERT INTO collections (slug, name, schema_md) VALUES ($1, $2, $3) RETURNING id',
            [slug, name, schemaMd]
          );
          const cid = c.rows[0]!.id;

          const indexFm = { title: 'Index', type: 'concept', sources: [], related: [], created: today, updated: today, confidence: 'high' };
          await client.query(
            'INSERT INTO pages (collection_id, path, content, frontmatter) VALUES ($1, $2, $3, $4)',
            [cid, 'index.md', indexMd, indexFm]
          );

          await client.query(
            'INSERT INTO logs (collection_id, kind, actor, payload) VALUES ($1, $2, $3, $4)',
            [cid, 'init', auth.tokenName, { template: schema_template }]
          );

          return cid;
        });
        return ok({ collection_id: result, slug, name });
      } catch (e: any) {
        if (e.code === '23505') return err(`slug already exists: ${slug}`);
        throw e;
      }
    }
  );

  server.registerTool(
    'get_schema',
    {
      title: 'Get schema',
      description: 'Read the SCHEMA.md (CLAUDE.md) of a collection.',
      inputSchema: { collection: z.string() },
    },
    async ({ collection }) => {
      if (!canAccessCollection(auth, collection)) return err('not accessible');
      const r = await query<{ schema_md: string; schema_version: number }>(
        'SELECT schema_md, schema_version FROM collections WHERE slug = $1',
        [collection]
      );
      const row = r.rows[0];
      if (!row) return err(`collection not found: ${collection}`);
      return ok({ collection, schema_version: row.schema_version, schema_md: row.schema_md });
    }
  );

  server.registerTool(
    'update_schema',
    {
      title: 'Update schema',
      description: 'Replace the SCHEMA.md of a collection. Bumps schema_version.',
      inputSchema: { collection: z.string(), schema_md: z.string() },
    },
    async ({ collection, schema_md }) => {
      if (!canWrite(auth)) return err('write scope required');
      if (!canAccessCollection(auth, collection)) return err('not accessible');
      const r = await query<{ schema_version: number }>(
        `UPDATE collections SET schema_md = $1, schema_version = schema_version + 1, updated_at = now()
         WHERE slug = $2 RETURNING schema_version`,
        [schema_md, collection]
      );
      if (r.rows.length === 0) return err(`collection not found: ${collection}`);
      await query(
        'INSERT INTO logs (collection_id, kind, actor, payload) SELECT id, $1, $2, $3 FROM collections WHERE slug = $4',
        ['schema_update', auth.tokenName, { schema_version: r.rows[0]!.schema_version }, collection]
      );
      return ok({ collection, schema_version: r.rows[0]!.schema_version });
    }
  );
}
