# {{name}} — Wiki Schema (team-knowledge)

Same as the `default` schema, plus three team-knowledge page types for engineering / ops teams.

## Additional page types

| Type | When to use |
|---|---|
| `playbook` | A step-by-step procedure for a recurring task. |
| `incident` | A post-mortem of an outage / bug / mistake, with timeline and lessons. |
| (the `decision` type from default is heavily used here) |

## Type-specific fields

### playbook
```yaml
type: playbook
trigger: <string, when to run this>
prerequisites: [...]
steps: [...]
last_verified: YYYY-MM-DD
```

### incident
```yaml
type: incident
status: open | resolved
severity: P0 | P1 | P2 | P3
detected_at: YYYY-MM-DD HH:MM
resolved_at: YYYY-MM-DD HH:MM | null
timeline: [...]
root_cause: <string>
lessons: [...]
related_decisions: ["[[decision-slug]]", ...]
```

## Directory additions

```
playbooks/
incidents/
decisions/
```

(See `SCHEMA-default.md.tpl` for the rest.)
