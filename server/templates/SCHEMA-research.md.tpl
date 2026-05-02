# {{name}} — Wiki Schema (research)

Same as the `default` schema, plus three research-oriented page types.

(Use the default schema as the base; the additions below extend `type` and frontmatter rules.)

## Additional page types

| Type | When to use |
|---|---|
| `paper` | A specific academic paper. Use `entity` if you only need the citation; use `paper` if you've read it and want a structured summary. |
| `experiment` | A run of an experiment, with hypothesis, setup, result, takeaway. |
| `hypothesis` | A claim under investigation, with evidence-for / evidence-against and current status. |

## Type-specific fields

### paper
```yaml
type: paper
authors: [...]
year: <int>
venue: <string, optional>
arxiv_id: <string, optional>
doi: <string, optional>
abstract_summary: <string, 2-4 sentences>
key_claims: [...]
limitations: [...]
```

### experiment
```yaml
type: experiment
hypothesis: "[[hypothesis-slug]]"
setup: <string>
result: <string>
takeaway: <string>
ran_at: YYYY-MM-DD
```

### hypothesis
```yaml
type: hypothesis
status: open | supported | refuted | inconclusive
evidence_for: [...]    # wikilinks to papers/experiments/sources
evidence_against: [...]
last_evaluated: YYYY-MM-DD
```

## Directory additions

```
papers/
experiments/
hypotheses/
```

(See `SCHEMA-default.md.tpl` for the rest.)
