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
   - `scriptorium.create_collection({ slug, name })`
   - Server seeds: `SCHEMA.md` (the universal schema doc), `index.md`, and an `init` log entry.

4. **Log**
   - `scriptorium.append_log({ collection: slug, kind: "init", actor: "claude", payload: { template: "default" } })`

5. **Print next-step hint**
   ```
   ✓ Created collection `<slug>` (id: <uuid>)
   
   Next:
     /scriptorium:ingest <path-to-first-source>
   
   Schema: <server>/collections/<slug>/schema
   ```

## Schema

Every collection is seeded with the same universal `SCHEMA.md` — eleven page types covering general knowledge, research, team ops, and codebases:

`concept`, `entity` (with broad `entity_kind` including `code-symbol`, `library`, `dataset`, `endpoint`), `source-summary`, `comparison`, `synthesis`, `decision`, `paper`, `experiment`, `hypothesis`, `playbook`, `incident`.

Don't like a type? Don't use it. Want to add one? `scriptorium.update_schema()` to evolve it per collection.

## Failure modes

- Slug taken → suggest alternative.
- Token missing collection-create scope → tell user to ask the admin for a higher-scope token.
