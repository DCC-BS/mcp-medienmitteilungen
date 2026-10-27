# medienmitteilungen-bs-mcp

MCP server for the press releases (Medienmitteilungen) of the canton of Basel-Stadt
([www.bs.ch/medien/medienmitteilungen](https://www.bs.ch/medien/medienmitteilungen)).
It gives chatbots and agents access to all ~18,000 official press releases published
since 1994: full-text search, filtering by sender department/office and date range,
full article text, PDF attachments, related links and media contacts.

It uses the public JSON endpoints of the `www.bs.ch` Nuxt/Drupal platform
(`/api/search/press-releases` and `/api/graphql/query/routeNodePressRelease`).
No authentication.

It runs in two modes:

- **stdio** for local MCP clients (opencode, Cursor, Claude Desktop).
- **streamable HTTP** hosted as a container, so it can be wired into ChatGPT
  connectors, OpenWebUI, and `dcc-mcp-facade`. Also ships a **skill** as a
  no-server alternative.

Sister projects: [mcp-data-bs](https://github.com/DCC-BS/mcp-data-bs) (`data.bs.ch`)
and [mcp-statistikportal](https://github.com/DCC-BS/mcp-statistikportal) (`statistik.bs.ch`).

## Installation

The toolchain (`uv` only; Python version comes from `pyproject.toml`) and the task
runner are managed by [mise](https://mise.jdx.dev/). Enter the project and trust
the config once:

```bash
mise trust
mise install            # provisions uv, runs the postinstall hook
```

Then set up the virtual environment and dependencies:

```bash
mise run install        # alias: i (uv sync --locked)
```

## Tasks

| Task                 | Alias | Description                                       |
|----------------------|-------|---------------------------------------------------|
| `mise run install`   | `i`   | Create venv and install deps (`uv sync --locked`) |
| `mise run dev`       | `d`   | MCP server over stdio (local clients)             |
| `mise run dev:http`  | `dh`  | Streamable HTTP on `:8000` for local testing      |
| `mise run check`     | `c`   | Verify lockfile, format, and lint (ruff)          |
| `mise run test:unit` | `t`   | Run the unit test suite (pytest)                  |

## Configuration

Read from the environment first, else a local `.env` next to `main.py`
(`cp .env.example .env`). All settings are optional.

| Variable            | Default              | Meaning                                              |
|---------------------|----------------------|------------------------------------------------------|
| `BS_DOMAIN`         | `www.bs.ch`          | Portal serving `/api/*`                              |
| `BS_API_URL`        | `https://<domain>`   | Where the server fetches from; links in results stay `https://<domain>` |
| `ORG_CACHE_TTL`     | `3600`               | Seconds the organization facet list is kept in memory |
| `MCP_ALLOWED_HOSTS` | empty                | Allowed `Host` headers, e.g. `mcp-medienmitteilungen.statistik.bs.ch` |

## Hosting (streamable HTTP)

```bash
docker build -f Dockerfile -t mcp-medienmitteilungen .
docker run --rm -p 8000:8000 mcp-medienmitteilungen
```

The MCP endpoint is mounted at `/mcp` (streamable HTTP).

Healthcheck: `GET /healthz -> {"status":"ok"}`.

### API reference

The HTTP server exposes an OpenAPI description of the MCP endpoint with a
rendered Swagger UI:

- `GET /docs` serves the interactive reference (Swagger UI). Each tool appears as a
  `tools/call` request schema with a working example you can execute against
  the server via *Try it out*.
- `GET /openapi.json` serves the raw OpenAPI 3.1 spec.

## Connecting clients

**Claude Desktop / Cursor** in `claude_desktop_config.json` or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "medienmitteilungen-bs": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/DCC-BS/mcp-medienmitteilungen", "medienmitteilungen-bs-mcp"]
    }
  }
}
```

**OpenWebUI / ChatGPT** via streamable HTTP endpoint `https://<hosted-domain>/mcp` (no auth).

## Tools

### `search_press_releases`
Full-text search over press releases on `www.bs.ch`, with optional filters for
`organization` (accepts either a numeric taxonomy ID like `"310"` or a German
name/substring like `"Verkehr"` or `"Grosser Rat"`), `date_from` (`YYYY-MM-DD`),
`date_to` (`YYYY-MM-DD`), `limit` (default 10, max 50), `page` (0-based), and
`lang` (`de`, `en`, `fr`, `it`).

Each hit returns `id`, `title`, `lead`, `organization`, `date`, `url`, and
`citation_label`.

```
search_press_releases(search="Mindestlohn")
search_press_releases(search="Veloring", organization="Verkehr", date_from="2025-01-01")
```

### `get_press_release`
Full content of one press release by `url`, path (`"/medienmitteilungen/..."`), or
node ID (`43943` or `"entity:node/43943:de"`). Automatically follows `/node/{id}`
redirects to the canonical URL. Returns `id`, `title`, `lead`, `published` (ISO 8601),
`date`, `organization`, `is_call_for_witnesses`, `url`, `citation_label`, `body`
(plain text converted from HTML paragraphs, capped at 12,000 characters),
`attachments` (PDFs/files with download URLs), `links`, and `contacts`.

```
get_press_release(press_release="/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-steigt-2027-auf-2250-franken-pro-stunde")
get_press_release(press_release=43943)
```

### `get_organizations`
Lists the sender departments, offices, and authorities (`id`, `name`, `count`,
`url`, `citation_label`) sorted by number of press releases descending, optionally
filtered by a `search` substring.

```
get_organizations()
get_organizations(search="Gesundheit")
```

## Skills (no MCP needed)

See `skills/medienmitteilungen-bs/SKILL.md` for calling the public endpoints
directly with plain HTTP.

## Architecture & API notes

See [docs/api-analyse.md](docs/api-analyse.md).
