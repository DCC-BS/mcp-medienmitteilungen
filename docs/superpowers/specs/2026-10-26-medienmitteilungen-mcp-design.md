# Design Spec: mcp-medienmitteilungen

## Goal
Build a stateless Python MCP server (`mcp-medienmitteilungen`) that wraps the public `www.bs.ch` press release search and GraphQL detail endpoints, matching the architecture of `mcp-data-bs` and `mcp-statistikportal`, and wire it into `dcc-mcp-facade` under `mcp-medienmitteilungen.statistik.bs.ch`.

## Architecture
- **Server framework:** `mcp.server.mcpserver.MCPServer` with stdio (`main`) and streamable HTTP (`main_http`, `create_http_app`) entrypoints.
- **HTTP routes:** `/mcp`, `/healthz`, `/`, `/openapi.json`, `/docs`, protected by `TransportSecuritySettings` (`MCP_ALLOWED_HOSTS`) and `RelaxedAcceptHeaderMiddleware`.
- **Upstream endpoints on `www.bs.ch`:**
  - `GET /api/search/press-releases` for full-text search, date range filtering (`date:min`, `date:max`), organization filtering (`organization`), and organization facet counts.
  - `GET /api/graphql/query/routeNodePressRelease?path=...` for full article text, attachments, related links, and media contacts.
- **In-memory cache:** Organization facets from `/api/search/press-releases` cached for `ORG_CACHE_TTL` seconds (default 3600) so `search_press_releases` can resolve organization names or substrings (`"Verkehr"`, `"Grosser Rat"`) to numeric taxonomy IDs (`"310"`, `"603"`).

## Tools
1. `search_press_releases(search=None, organization=None, date_from=None, date_to=None, limit=10, page=0, lang="de")`
2. `get_press_release(press_release)`
3. `get_organizations(search=None, lang="de")`
