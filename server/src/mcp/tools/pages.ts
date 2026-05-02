import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query, withTransaction } from '../../db/client.ts';
import { canWrite, type AuthContext } from '../../auth/middleware.ts';
import { validateFrontmatter } from '../../schema/frontmatter.ts';
import { ok, err, getCollectionIdBySlug } from '../util.ts';

export function registerPages(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'get_page',
    {
      title: 'Get page',
      description: 'Read a single wiki page including frontmatter and version.',
      inputSchema: { collection: z.string(), path: z.string() },
    },
    async ({ collection, path }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const r = await query(
        `SELECT path, content, frontmatter, version, updated_at
         FROM pages WHERE collection_id = $1 AND path = $2 AND deleted_at IS NULL`,
        [cid, path]
      );
      if (r.rows.length === 0) return err(`page not found: ${path}`);
      return ok(r.rows[0]);
    }
  );

  server.registerTool(
    'list_pages',
    {
      title: 'List pages',
      description: 'List page paths in a collection. Supports filtering by frontmatter type.',
      inputSchema: {
        collection: z.string(),
        type: z.string().optional(),
        limit: z.number().int().positive().max(500).default(100),
      },
    },
    async ({ collection, type, limit }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const params: any[] = [cid];
      let where = 'collection_id = $1 AND deleted_at IS NULL';
      if (type) {
        params.push(type);
        where += ` AND frontmatter->>'type' = $${params.length}`;
      }
      params.push(limit);
      const r = await query(
        `SELECT path, frontmatter->>'title' AS title, frontmatter->>'type' AS type, updated_at
         FROM pages WHERE ${where} ORDER BY path LIMIT $${params.length}`,
        params
      );
      return ok(r.rows);
    }
  );

  server.registerTool(
    'create_page',
    {
      title: 'Create page',
      description: 'Create a new wiki page. Frontmatter is validated against the collection schema.',
      inputSchema: {
        collection: z.string(),
        path: z.string(),
        content: z.string(),
        frontmatter: z.record(z.any()),
      },
    },
    async ({ collection, path, content, frontmatter }) => {
      if (!canWrite(auth)) return err('write scope required');
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');

      const v = validateFrontmatter(frontmatter);
      if (!v.ok) return err(`frontmatter invalid: ${v.errors.join('; ')}`);

      try {
        const result = await withTransaction(async client => {
          const r = await client.query<{ id: number; version: number }>(
            `INSERT INTO pages (collection_id, path, content, frontmatter)
             VALUES ($1, $2, $3, $4) RETURNING id, version`,
            [cid, path, content, v.value]
          );
          const page = r.rows[0]!;
          await client.query(
            'INSERT INTO page_versions (page_id, version, content, frontmatter, author) VALUES ($1, $2, $3, $4, $5)',
            [page.id, page.version, content, v.value, auth.tokenName]
          );
          return page;
        });
        return ok({ path, version: result.version });
      } catch (e: any) {
        if (e.code === '23505') return err(`page already exists: ${path}`);
        throw e;
      }
    }
  );

  server.registerTool(
    'update_page',
    {
      title: 'Update page',
      description: 'Update a wiki page using compare-and-swap on the version number.',
      inputSchema: {
        collection: z.string(),
        path: z.string(),
        content: z.string(),
        frontmatter: z.record(z.any()),
        base_version: z.number().int().positive(),
      },
    },
    async ({ collection, path, content, frontmatter, base_version }) => {
      if (!canWrite(auth)) return err('write scope required');
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');

      const v = validateFrontmatter(frontmatter);
      if (!v.ok) return err(`frontmatter invalid: ${v.errors.join('; ')}`);

      const result = await withTransaction(async client => {
        const upd = await client.query<{ id: number; version: number }>(
          `UPDATE pages SET content = $1, frontmatter = $2, version = version + 1, updated_at = now()
           WHERE collection_id = $3 AND path = $4 AND version = $5 AND deleted_at IS NULL
           RETURNING id, version`,
          [content, v.value, cid, path, base_version]
        );
        if (upd.rows.length === 0) return null;
        const page = upd.rows[0]!;
        await client.query(
          'INSERT INTO page_versions (page_id, version, content, frontmatter, author) VALUES ($1, $2, $3, $4, $5)',
          [page.id, page.version, content, v.value, auth.tokenName]
        );
        return page;
      });

      if (!result) {
        const cur = await query<{ version: number }>(
          'SELECT version FROM pages WHERE collection_id = $1 AND path = $2 AND deleted_at IS NULL',
          [cid, path]
        );
        return err(`version conflict; current version is ${cur.rows[0]?.version ?? 'missing'}`);
      }
      return ok({ path, version: result.version });
    }
  );

  server.registerTool(
    'delete_page',
    {
      title: 'Delete page',
      description: 'Soft-delete a page (sets deleted_at). Use with care.',
      inputSchema: { collection: z.string(), path: z.string(), reason: z.string().min(1) },
    },
    async ({ collection, path, reason }) => {
      if (!canWrite(auth)) return err('write scope required');
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const r = await query(
        `UPDATE pages SET deleted_at = now() WHERE collection_id = $1 AND path = $2 AND deleted_at IS NULL`,
        [cid, path]
      );
      if (r.rowCount === 0) return err(`page not found: ${path}`);
      await query(
        'INSERT INTO logs (collection_id, kind, actor, payload) VALUES ($1, $2, $3, $4)',
        [cid, 'delete_page', auth.tokenName, { path, reason }]
      );
      return ok({ deleted: path });
    }
  );
}
