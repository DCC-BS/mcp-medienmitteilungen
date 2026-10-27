# Medienmitteilungen MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `mcp-medienmitteilungen` MCP server for `www.bs.ch/medien/medienmitteilungen` and integrate it into `dcc-mcp-facade`.

**Architecture:** Stateless Python MCP server using `MCPServer`, `httpx`, and `uvicorn`/`starlette`, wrapping `GET /api/search/press-releases` and `GET /api/graphql/query/routeNodePressRelease`.

**Tech Stack:** Python >= 3.13, `mcp[cli]>=2.3.0`, `httpx>=0.28.1`, `uvicorn>=0.54.0`, `pytest`, `ruff`, Docker, Traefik (`dcc-mcp-facade`).

## Global Constraints
- Python `>=3.13`, line length 100 (`ruff`), identical Docker/mise/CI structure to `mcp-statistikportal`.
- Hostname in `dcc-mcp-facade`: `mcp-medienmitteilungen.statistik.bs.ch`.

---

### Task 1: Project scaffolding and configuration
- Create `pyproject.toml`, `mise.toml`, `.env.example`, `.gitignore`, `renovate.json`, `Dockerfile`, `compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/publish.yml`.

### Task 2: TDD for MCP tools and HTTP server
- Create `tests/conftest.py`, `tests/test_tools.py`, `tests/test_http.py`.
- Run `pytest` to confirm failure (RED).
- Implement `api_docs.py` and `main.py`.
- Run `pytest` to confirm all tests pass (GREEN).

### Task 3: Skill, README, and Facade integration
- Create `skills/medienmitteilungen-bs/SKILL.md` and `README.md`.
- Update `dcc-mcp-facade/compose.yml`, `dcc-mcp-facade/nginx-example.conf`, and `dcc-mcp-facade/README.md`.
- Run `mise run check` and `mise run test:unit`.
