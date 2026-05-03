![scriptorium](assets/banner.jpg)

# scriptorium

Persistent, compounding knowledge base for teams. The LLM scribes don't sleep.

A scriptorium was a medieval room where monks copied and illuminated manuscripts. Here, the LLM is the scribe, you curate the sources, and the wiki is the manuscript that compounds over time. Based on Andrej Karpathy's [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), but server-backed so a team — not just one laptop — can keep a single brain.

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
- **`/` (root)** — a Claude Code plugin. Its `.mcp.json` declares an HTTP MCP server pointed at `${SCRIPTORIUM_API_URL}/mcp` with a Bearer token. No local shim, no bundled binary — Claude Code just calls the remote MCP directly.

## Quick start

### As a server admin (host a new wiki)

```bash
# Use this template on GitHub → creates your-team/your-wiki
gh repo create your-team/your-wiki --template zyx1121/scriptorium --public

# Deploy
cd your-wiki/server
cp .env.example .env  # fill in POSTGRES_URL + ADMIN_TOKEN
docker compose up -d

# Mint a token for your team
docker compose exec server bun run cli token issue --collection my-wiki --scope rw
```

### As a Claude Code user (use a wiki someone hosted)

```bash
# In any Claude Code session
/plugin install zyx1121/scriptorium
/scriptorium:connect https://wiki.your-team.tld
/scriptorium:init my-research        # first time
/scriptorium:ingest ~/papers/karpathy-llm-wiki.md
/scriptorium:query "what's the difference between LLM Wiki and RAG?"
/scriptorium:lint
```

## Tech stack

- **Server**: TypeScript on Bun, raw `node:http`, [@modelcontextprotocol/sdk](https://github.com/modelcontextprotocol/typescript-sdk) streamable-HTTP transport, PostgreSQL 16 (`tsvector` + `GIN` for FTS)
- **Plugin**: vanilla Claude Code plugin — Skill + commands + hooks + remote `.mcp.json`
- **Schema**: YAML frontmatter, validated server-side with Zod
- **Auth**: bearer tokens, collection-scoped, sha256-hashed at rest
- **Deploy**: `docker-compose.yml` (server + Postgres). TLS terminates at your reverse proxy

## Components

| Path | What |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `.mcp.json` | Plugin's MCP config — HTTP transport pointed at the server |
| `skills/scriptorium/` | Workflow Skill — `SKILL.md` + `reference/*` |
| `commands/*.md` | Slash commands (`/scriptorium:connect` etc.) |
| `hooks/` | UserPromptSubmit + Stop nudges for save-back |
| `server/` | The wiki server (Postgres + MCP-over-HTTP) |

## Slash commands

| Command | Purpose |
|---|---|
| `/scriptorium:connect <url>` | Bind this session to a server |
| `/scriptorium:init <slug>` | Create a new wiki collection |
| `/scriptorium:ingest <path\|url>` | Turn a source into 5–15 wiki pages |
| `/scriptorium:query <question>` | Search + cite + synthesise |
| `/scriptorium:lint` | Find rot (orphans, dead links, stale claims) |
| `/scriptorium:recap` | Save durable insights from this session |

## Use this template

This repo is set up as a GitHub Template. Click **Use this template** on the GitHub page to create your own wiki repo. Each wiki = one fresh repo = one server instance + (optionally) one customised plugin. See `docs/use-this-template.md`.

## What it isn't

- **Not** a Notion/Confluence replacement — it's optimised for LLM-assisted curation, not human page-editing.
- **Not** a RAG system — RAG re-derives knowledge per query; Scriptorium compounds it at ingest. Below ~100K-token wikis it wins; above, you'd layer RAG on top.
- **Not** a streaming/live data tool. Sources are immutable snapshots.

## License

[MIT](LICENSE.md) — copy this scriptorium, let your scribes illuminate freely.
