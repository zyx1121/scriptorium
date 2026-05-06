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
  entity_kind: z.enum([
    'person', 'org', 'project', 'paper', 'model', 'tool',
    'code-symbol', 'library', 'dataset', 'endpoint', 'concept-ref',
  ]),
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

export const PaperSchema = z.object({
  ...baseFields,
  type: z.literal('paper'),
  authors: z.array(z.string()).default([]),
  year: z.number().int().optional(),
  venue: z.string().optional(),
  arxiv_id: z.string().optional(),
  doi: z.string().optional(),
  abstract_summary: z.string().optional(),
  key_claims: z.array(z.string()).default([]),
  limitations: z.array(z.string()).default([]),
});

export const ExperimentSchema = z.object({
  ...baseFields,
  type: z.literal('experiment'),
  hypothesis_ref: z.string().optional(),
  setup: z.string(),
  result: z.string(),
  takeaway: z.string(),
  ran_at: isoDate,
});

export const HypothesisSchema = z.object({
  ...baseFields,
  type: z.literal('hypothesis'),
  status: z.enum(['open', 'supported', 'refuted', 'inconclusive']).default('open'),
  evidence_for: z.array(wikilink).default([]),
  evidence_against: z.array(wikilink).default([]),
  last_evaluated: isoDate.optional(),
});

export const PlaybookSchema = z.object({
  ...baseFields,
  type: z.literal('playbook'),
  trigger: z.string(),
  prerequisites: z.array(z.string()).default([]),
  steps: z.array(z.string()).min(1),
  last_verified: isoDate.optional(),
});

export const IncidentSchema = z.object({
  ...baseFields,
  type: z.literal('incident'),
  status: z.enum(['open', 'resolved']).default('open'),
  severity: z.enum(['P0', 'P1', 'P2', 'P3']),
  detected_at: z.string().datetime({ offset: true, message: 'must be ISO 8601 datetime, e.g. 2026-05-04T14:32:00Z' }),
  resolved_at: z.string().datetime({ offset: true, message: 'must be ISO 8601 datetime' }).optional(),
  timeline: z.array(z.string()).default([]),
  root_cause: z.string().optional(),
  lessons: z.array(z.string()).default([]),
  related_decisions: z.array(wikilink).default([]),
});

export const FrontmatterSchema = z.discriminatedUnion('type', [
  ConceptSchema,
  EntitySchema,
  SourceSummarySchema,
  ComparisonSchema,
  SynthesisSchema,
  DecisionSchema,
  PaperSchema,
  ExperimentSchema,
  HypothesisSchema,
  PlaybookSchema,
  IncidentSchema,
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
