import { z } from 'zod';

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'must be YYYY-MM-DD');
const wikilink = z.string().regex(/^\[\[[^\]]+\]\]$/, 'must be [[wikilink]]');
const confidence = z.enum(['high', 'medium', 'low']);

const baseFields = {
  title: z.string().min(1),
  sources: z.array(z.string()).default([]),
  related: z.array(wikilink).default([]),
  created: isoDate,
  updated: isoDate,
  confidence: confidence.default('medium'),
};

export const ConceptSchema = z.object({
  ...baseFields,
  type: z.literal('concept'),
  domain: z.string().optional(),
});

export const EntitySchema = z.object({
  ...baseFields,
  type: z.literal('entity'),
  entity_kind: z.enum(['person', 'org', 'project', 'paper', 'model', 'tool']),
  canonical_url: z.string().url().optional(),
});

export const SourceSummarySchema = z.object({
  ...baseFields,
  type: z.literal('source-summary'),
  sources: z.array(z.string()).length(1, 'source-summary must cite exactly 1 source'),
  length_tokens: z.number().int().nonnegative().optional(),
});

export const ComparisonSchema = z.object({
  ...baseFields,
  type: z.literal('comparison'),
  items: z.array(wikilink).min(2, 'comparison needs >=2 items'),
});

export const SynthesisSchema = z.object({
  ...baseFields,
  type: z.literal('synthesis'),
  sources: z.array(z.string()).min(2, 'synthesis needs >=2 sources'),
});

export const DecisionSchema = z.object({
  ...baseFields,
  type: z.literal('decision'),
  status: z.enum(['active', 'superseded', 'reversed']).default('active'),
  alternatives_considered: z.array(z.string()).default([]),
  superseded_by: z.string().optional(),
});

export const FrontmatterSchema = z.discriminatedUnion('type', [
  ConceptSchema,
  EntitySchema,
  SourceSummarySchema,
  ComparisonSchema,
  SynthesisSchema,
  DecisionSchema,
]);

export type Frontmatter = z.infer<typeof FrontmatterSchema>;

export function validateFrontmatter(input: unknown): { ok: true; value: Frontmatter } | { ok: false; errors: string[] } {
  const r = FrontmatterSchema.safeParse(input);
  if (r.success) {
    if (r.data.created > r.data.updated) {
      return { ok: false, errors: ['created must be <= updated'] };
    }
    if (r.data.confidence === 'high' && r.data.sources.length < 2) {
      return { ok: false, errors: ['confidence: high requires >= 2 sources'] };
    }
    return { ok: true, value: r.data };
  }
  return { ok: false, errors: r.error.issues.map(i => `${i.path.join('.')}: ${i.message}`) };
}
