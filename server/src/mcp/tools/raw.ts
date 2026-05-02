import { createHash } from 'node:crypto';
import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { query } from '../../db/client.ts';
import { canWrite, type AuthContext } from '../../auth/middleware.ts';
import { ok, err, getCollectionIdBySlug } from '../util.ts';

export function registerRaw(server: McpServer, auth: AuthContext) {
  server.registerTool(
    'upload_raw',
    {
      title: 'Upload raw source',
      description: 'Upload an immutable raw source (paper / article / URL snapshot).',
      inputSchema: {
        collection: z.string(),
        slug: z.string().min(1),
        kind: z.enum(['article', 'paper', 'url', 'note', 'transcript']),
        content: z.string(),
        metadata: z.record(z.any()).default({}),
      },
    },
    async ({ collection, slug, kind, content, metadata }) => {
      if (!canWrite(auth)) return err('write scope required');
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const sha = createHash('sha256').update(content).digest('hex');
      try {
        const r = await query<{ id: number }>(
          `INSERT INTO raw_sources (collection_id, slug, kind, content, sha256, metadata)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING id`,
          [cid, slug, kind, content, sha, metadata]
        );
        return ok({ raw_id: r.rows[0]!.id, sha256: sha });
      } catch (e: any) {
        if (e.code === '23505') return err(`raw source slug already exists: ${slug}`);
        throw e;
      }
    }
  );

  server.registerTool(
    'get_raw',
    {
      title: 'Get raw source',
      description: 'Read a raw source by slug.',
      inputSchema: { collection: z.string(), slug: z.string() },
    },
    async ({ collection, slug }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const r = await query(
        `SELECT slug, kind, content, sha256, metadata, ingested_at
         FROM raw_sources WHERE collection_id = $1 AND slug = $2`,
        [cid, slug]
      );
      if (r.rows.length === 0) return err(`raw source not found: ${slug}`);
      return ok(r.rows[0]);
    }
  );

  server.registerTool(
    'list_raw',
    {
      title: 'List raw sources',
      description: 'List raw sources in a collection.',
      inputSchema: { collection: z.string() },
    },
    async ({ collection }) => {
      const cid = await getCollectionIdBySlug(auth, collection);
      if (!cid) return err('collection not found or not accessible');
      const r = await query(
        `SELECT slug, kind, sha256, ingested_at FROM raw_sources
         WHERE collection_id = $1 ORDER BY ingested_at DESC`,
        [cid]
      );
      return ok(r.rows);
    }
  );
}
