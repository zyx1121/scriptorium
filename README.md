![scriptorium](assets/banner.jpg)

# scriptorium

Persistent, compounding knowledge base for teams. The LLM scribes don't sleep.

A scriptorium was a medieval room where monks copied and illuminated manuscripts. Here, the LLM is the scribe, you curate the sources, and the wiki is the manuscript that compounds over time. Based on Andrej Karpathy's [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — but server-backed so a team, not just one laptop, can share one brain.

## Why scriptorium

Most LLM-assisted knowledge tools are RAG systems — every query rediscovers facts from raw chunks. Scriptorium flips it: **synthesis happens once at ingest time** and is baked into a structured, interlinked wiki. Subsequent queries read the already-compiled pages.

|  | RAG | Scriptorium |
|---|---|---|
| When does synthesis happen | Per query | Once at ingest |
| Cross-document linking | Re-derived each time | Wikilinks materialised |
| Where contradictions surface | Buried in chunks | Flagged on the page |
| Source of truth | Embeddings (opaque) | Markdown (human-readable, auditable) |
| Sweet spot | Any size | < ~100K-token wikis (then layer RAG on top) |

Knowledge compounds because every ingest **updates** existing pages instead of dumping new chunks. The maintenance toil that kills personal wikis — cross-references, dedup, stale detection, conflict resolution — is exactly the kind of bookkeeping LLMs are good at and humans are not.

## Architecture

```
        ┌──────────────────────────────────────────┐
        │  Scriptorium server (one per wiki)       │
        │  PostgreSQL + MCP-over-HTTP at /mcp      │
        │  https://wiki.<your-team>.tld            │
        └──────────────────────┬───────────────────┘
                               │  Bearer token (per member)
                               │  streamable HTTP
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
 Loki's Claude Code     Teammate's Claude Code   Researcher's Claude Code
   (this plugin)          (this plugin)             (this plugin)
```

Two halves in one repo:

- **`/server`** — Postgres + an MCP server speaking streamable HTTP at `/mcp`. One instance per wiki. Deploy with the included `docker-compose.yml`.
- **`/` (root)** — a Claude Code plugin. Its `.mcp.json` declares an HTTP MCP server pointed at `${SCRIPTORIUM_API_URL}/mcp` with a Bearer token. No local shim, no bundled binary — Claude Code calls the remote MCP directly.

## Mental model

Every collection has three layers. These are load-bearing — don't break them.

| Layer | Owner | Mutability |
|---|---|---|
| **Raw sources** | Humans curate | Immutable. The LLM reads, never modifies. |
| **Wiki pages** | LLM scribes write & maintain | Mutable. Updated on every ingest. |
| **Schema** (`SCHEMA.md`) | Co-evolved | Versioned via `schema_version`. Edit intentionally. |

Each page declares one **`type`** in its YAML frontmatter. Eleven types ship by default — pick what fits the topic, no presets to choose:

`concept` · `entity` · `source-summary` · `comparison` · `synthesis` · `decision` · `paper` · `experiment` · `hypothesis` · `playbook` · `incident`

`entity` covers `entity_kind: person / org / project / paper / model / tool / code-symbol / library / dataset / endpoint / concept-ref` — codebases are a first-class case, not a workaround. Don't like a type? Don't use it. Want a new one? `scriptorium.update_schema()` evolves the collection's schema, audited.

Full spec: [`server/templates/SCHEMA.md.tpl`](server/templates/SCHEMA.md.tpl).

## Lifecycle

The wiki has four loops. Each is invokable as a slash command, and Claude is steered to auto-trigger them on appropriate prompts:

- **Ingest** — `/scriptorium:ingest <source>`. A single source typically touches **5–15 pages**: a `source-summary`, new `entity`/`concept` pages, edits to existing pages, plus an `index.md` entry and a `log` entry. **Always discussed with the human first** — silent ingests cause schema drift.
- **Query** — `/scriptorium:query <question>`. PostgreSQL `ts_rank` finds top candidates → Claude reads them → answers with **inline citations** `[path/to/page.md]`. Novel cross-source synthesis is offered for save-back.
- **Lint** — `/scriptorium:lint`. The wiki's immune system: dead wikilinks, orphans, stale claims (>180d), schema violations, confidence inflation. Surfaced top-N for human approval. Never auto-fixed.
- **Recap** — `/scriptorium:recap`. Save the durable insights from a session before the conversation evaporates: decisions, comparisons, novel entities, multi-source synthesis.

## Quick start

### As a server admin (host a new wiki)

```bash
# Use this template on GitHub → creates your-team/your-wiki
gh repo create your-team/your-wiki --template zyx1121/scriptorium --public --clone
cd your-wiki/server

# Configure
cp .env.example .env   # fill in DATABASE_URL + ADMIN_TOKEN (openssl rand -hex 32)

# Deploy
docker compose up -d --build

# Mint a token for yourself
docker compose exec -T server bun src/cli/index.ts token issue \
  --name admin --scope admin
```

### As a Claude Code user (use a wiki someone hosted)

```bash
# Set env vars (one-time, in shell profile)
export SCRIPTORIUM_API_URL=https://wiki.your-team.tld
export SCRIPTORIUM_TOKEN=<your-token>
```

```
# Inside Claude Code
/plugin marketplace add zyx1121/marketplace
/plugin install scriptorium@zyx1121
/scriptorium:status                                # verify
/scriptorium:init my-research                      # first time
/scriptorium:ingest ~/papers/karpathy-llm-wiki.md
/scriptorium:query "what's the difference between LLM Wiki and RAG?"
```

## Tech stack

- **Server**: TypeScript on Bun, raw `node:http`, [@modelcontextprotocol/sdk](https://github.com/modelcontextprotocol/typescript-sdk) streamable-HTTP transport, PostgreSQL 16 (`tsvector` + `GIN` for FTS).
- **Plugin**: vanilla Claude Code plugin — Skill + commands + hooks + remote `.mcp.json`.
- **Schema**: YAML frontmatter, validated server-side with Zod.
- **Auth**: Bearer tokens, collection-scoped, sha256-hashed at rest. In-memory token-bucket rate limit on `/mcp` (60 rpm/token) and `/dashboard` (20 rpm/IP).
- **Deploy**: `docker-compose.yml` (server + Postgres). TLS terminates at your reverse proxy.

## Components

| Path | What |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `.mcp.json` | Plugin's MCP config — HTTP transport pointed at the server |
| `skills/scriptorium/` | Workflow Skill — `SKILL.md` + `reference/*` |
| `commands/*.md` | Slash commands (`/scriptorium:connect` etc.) |
| `hooks/` | UserPromptSubmit + Stop nudges for save-back |
| `server/` | The wiki server (Postgres + MCP-over-HTTP) |
| `docs/` | Architecture, deploy, onboarding guides |

## Slash commands

| Command | Purpose |
|---|---|
| `/scriptorium:status` | One-screen view: server health, token, collections |
| `/scriptorium:connect <url>` | Print setup instructions for a new server |
| `/scriptorium:init <slug>` | Create a new wiki collection |
| `/scriptorium:ingest <path\|url>` | Turn a source into 5–15 wiki pages |
| `/scriptorium:query <question>` | Search + cite + synthesise |
| `/scriptorium:lint` | Find rot (orphans, dead links, stale claims) |
| `/scriptorium:recap` | Save durable insights from this session |

## Dashboard

Every Scriptorium server renders an HTML dashboard at `/dashboard?collection=<slug>` — totals, by-type breakdown, top-read pages, recently added/updated, stale pages, recent searches. Server-rendered, no JavaScript, monochrome bash aesthetic.

- **Collection picker**: `/dashboard` (no params)
- **Page detail**: `/dashboard?collection=<slug>&path=<page>` — frontmatter + content + recent reads

The same data is exposed as the `scriptorium.stats` MCP tool, so Claude can inspect a collection's health from within a session.

## Use this template

This repo is set up as a GitHub Template. Click **Use this template** on the GitHub page to create your own wiki repo. Each wiki = one fresh repo = one server instance + (optionally) one customised plugin. See [`docs/use-this-template.md`](docs/use-this-template.md).

Onboarding teammates: [`docs/onboarding-teammate.md`](docs/onboarding-teammate.md).

## What it isn't

- **Not** a Notion / Confluence replacement — built for LLM-assisted curation, not human page-editing.
- **Not** a streaming / live-data tool — sources are immutable snapshots.
- **Not** intended for >100K-token collections — at that scale, layer pgvector / RAG on top of the wiki, don't replace it.
- **Not** a multi-tenant SaaS — one server per wiki, per team.

## Inspiration

- **Andrej Karpathy** — [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (Apr 2026). The pattern Scriptorium implements: LLM as compiler, raw sources as input, wiki as compiled artifact, schema as the build spec.
- **Vannevar Bush** — *[As We May Think](https://www.theatlantic.com/magazine/archive/1945/07/as-we-may-think/303881/)* (1945). The original Memex: a personal, curated knowledge store with associative trails between documents. Bush couldn't solve the maintenance question. LLMs can.
- **ekadetov/llm-wiki** — single-laptop precursor (Obsidian + Claude Code, no server). Scriptorium borrowed the verb skeleton and stripped the local-filesystem assumptions.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Security reports: [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE.md) — copy this scriptorium, let your scribes illuminate freely.
