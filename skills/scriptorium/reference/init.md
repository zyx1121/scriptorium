# `/scriptorium:init <name>` flow

## Purpose

Create a new wiki collection on the connected server.

## Steps

1. **Validate name**
   - Lowercase, kebab-case, 3–40 chars. Reject otherwise with explanation.

2. **Confirm with user**
   - Show: collection slug, default schema template, server URL.
   - AskUserQuestion: "Create collection `<slug>` on `<server>`? (y/N)"

3. **Server call**
   - `scriptorium.create_collection({ slug, name, schema_template: "default" })`
   - Server seeds: `CLAUDE.md` (schema), `wiki/index.md`, `log.md`, default page-type templates.

4. **Log**
   - `scriptorium.append_log({ collection: slug, kind: "init", actor: "claude", payload: { template: "default" } })`

5. **Print next-step hint**
   ```
   ✓ Created collection `<slug>` (id: <uuid>)
   
   Next:
     /scriptorium:ingest <path-to-first-source>
   
   Schema: <server>/collections/<slug>/schema
   ```

## Schema template options

| Template | Purpose |
|---|---|
| `default` | Karpathy-style: concept/entity/source-summary/comparison/synthesis |
| `research` | Adds `paper`, `experiment`, `hypothesis` types |
| `team-knowledge` | Adds `decision`, `playbook`, `incident` types |

User can override later via `scriptorium.update_schema()`.

## Failure modes

- Slug taken → suggest alternative.
- Token missing collection-create scope → tell user to ask the admin for a higher-scope token.
