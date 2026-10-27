import asyncio
import html
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

import api_docs

# The mcp SDK logs INFO chatter on every streamable-HTTP request: with
# stateless_http=True each request gets a throwaway transport that the session
# manager tears down afterwards, logging "Terminating session: None".
logging.getLogger("mcp").setLevel(logging.WARNING)


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_ENV_FILE = _read_env_file(Path(__file__).parent / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return _ENV_FILE.get(name, "").strip() or default


DOMAIN = _env("BS_DOMAIN", "www.bs.ch").removeprefix("https://").removeprefix("http://").strip("/")
BASE_URL = f"https://{DOMAIN}"
API_URL = _env("BS_API_URL", BASE_URL).rstrip("/")
SEARCH_PATH = "/api/search/press-releases"
GRAPHQL_PRESS_RELEASE_PATH = "/api/graphql/query/routeNodePressRelease"
ORG_CACHE_TTL = int(_env("ORG_CACHE_TTL", "3600"))
BODY_MAX_CHARS = 12000


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection for the HTTP endpoint. FastMCP auto-enables
    Host-header validation limited to localhost when no host is given, which
    would reject real deployment hosts with 421. Configure the allowed hosts
    via MCP_ALLOWED_HOSTS (comma-separated, e.g. "mcp-medienmitteilungen.statistik.bs.ch");
    when unset, protection is disabled so the server is reachable on any Host header."""
    allowed = [h.strip() for h in _env("MCP_ALLOWED_HOSTS").split(",") if h.strip()]
    if not allowed:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed,
    )


class RelaxedAcceptHeaderMiddleware(BaseHTTPMiddleware):
    """Tolerate JSON-RPC clients that send incomplete Accept headers.

    The streamable HTTP transport rejects POST requests without an Accept
    header listing both application/json and text/event-stream (406), which
    plain JSON-RPC clients routinely omit. Rewrite those Accept headers to
    what the transport requires before the request reaches it."""

    async def dispatch(self, request, call_next):
        if request.method == "POST":
            accept = request.headers.get("accept", "")
            if "text/event-stream" not in accept or "application/json" not in accept:
                request.scope["headers"] = [
                    (k, v) for k, v in request.scope["headers"] if k.lower() != b"accept"
                ] + [(b"accept", b"application/json, text/event-stream")]
        return await call_next(request)


mcp = MCPServer(
    DOMAIN,
    instructions=(
        f"Press releases (Medienmitteilungen) of the canton of Basel-Stadt ({DOMAIN}) since 1994. "
        "Find press releases by German keywords, sender organization or date range with "
        "search_press_releases (returns title, lead, date, organization and url). "
        "Read the full article text, attachments, links and media contacts with get_press_release. "
        "List available sender departments and offices with get_organizations."
    ),
)

MCP_HTTP_SETTINGS = {
    "streamable_http_path": "/mcp",
    "stateless_http": True,
    "transport_security": _transport_security(),
}


async def fetch(
    endpoint: str,
    params: dict[str, str | int] | None = None,
    not_found_hint: str = "find press releases with search_press_releases",
) -> dict:
    """GET JSON from www.bs.ch. Failures are raised as ToolError with a reason the
    calling model can act on."""
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
            response = await client.get(endpoint, params=params)
    except httpx.TimeoutException as exc:
        raise ToolError(f"{DOMAIN} did not answer within 30 s") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"{DOMAIN} is not reachable: {type(exc).__name__}") from exc
    if response.status_code == 404:
        raise ToolError(f"not found on {DOMAIN}: {endpoint} ({not_found_hint})")
    if response.status_code >= 400:
        raise ToolError(f"{DOMAIN} answered {response.status_code} for {endpoint}")
    try:
        return response.json()
    except ValueError as exc:
        raise ToolError(f"{DOMAIN} returned no JSON for {endpoint}") from exc


# --- Text and HTML helpers --------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_P_END_RE = re.compile(r"</(?:p|div|h[1-6]|li|blockquote)>", re.IGNORECASE)
_SUP_RE = re.compile(r"<sup>\s*([23])\s*</sup>", re.IGNORECASE)
_SUPERSCRIPT = {"2": "²", "3": "³"}
_UMLAUT_DIGRAPHS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENTITY_NODE_RE = re.compile(r"^entity:node/(\d+)(?::[a-z]+)?$", re.IGNORECASE)


def _clean_html(value) -> str:
    """Plain text from HTML: paragraph and line breaks preserved, tags dropped, entities decoded."""
    if not value:
        return ""
    text = _SUP_RE.sub(lambda m: _SUPERSCRIPT[m.group(1)], str(value))
    text = _P_END_RE.sub("\n\n", text)
    text = _BR_RE.sub("\n", text)
    cleaned = html.unescape(_TAG_RE.sub("", text)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _clean_inline(value) -> str:
    """Single-line plain text (titles, labels, lead snippets)."""
    return " ".join(_clean_html(value).split())


def _normalize(value) -> str:
    """Casefolded text with umlauts written as ae/oe/ue."""
    return " ".join(str(value or "").casefold().translate(_UMLAUT_DIGRAPHS).split())


def _fold(value) -> str:
    """Casefolded text with umlauts reduced to the bare vowel."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold().replace("ß", "ss"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def citation_label(title) -> str | None:
    """Short name of a result for a client's citation list: portal and press release title."""
    title = _clean_inline(title)
    return f"{DOMAIN} · {title}" if title else None


def _full_url(path_or_url: str | None) -> str | None:
    if not path_or_url:
        return None
    val = str(path_or_url).strip()
    if val.startswith(("http://", "https://")):
        return val
    return f"{BASE_URL}/{val.lstrip('/')}"


def _extract_node_id(raw_id: str | None) -> str | None:
    if not raw_id:
        return None
    text = str(raw_id).strip()
    match = _ENTITY_NODE_RE.match(text)
    if match:
        return match.group(1)
    return text


# --- Organization facet cache -----------------------------------------------

_org_cache: dict[str, dict] = {"data": {}, "loaded_at": {}}
_org_lock = asyncio.Lock()


def _parse_org_terms(data: dict) -> list[dict]:
    for facet in data.get("facets") or []:
        if isinstance(facet, dict) and facet.get("id") == "organization":
            terms = [
                {
                    "id": str(t.get("value")),
                    "name": _clean_inline(t.get("label")),
                    "count": int(t.get("count") or 0),
                    "url": f"{BASE_URL}/medien/medienmitteilungen?organization={quote(str(t.get('value')), safe='')}",
                    "citation_label": f"{DOMAIN} · Medienmitteilungen: {_clean_inline(t.get('label'))}",
                }
                for t in (facet.get("terms") or [])
                if isinstance(t, dict) and t.get("value") and t.get("label")
            ]
            return sorted(terms, key=lambda item: (-item["count"], item["name"]))
    return []


async def _load_organizations(lang: str = "de") -> list[dict]:
    """Load and cache the sender organizations facet for the given language."""
    async with _org_lock:
        loaded_at = _org_cache["loaded_at"].get(lang, 0.0)
        fresh = time.monotonic() - loaded_at < ORG_CACHE_TTL
        if lang not in _org_cache["data"] or not fresh:
            data = await fetch(SEARCH_PATH, {"langcode": lang, "size": 1})
            _org_cache["data"][lang] = _parse_org_terms(data)
            _org_cache["loaded_at"][lang] = time.monotonic()
        return _org_cache["data"][lang]


async def _resolve_organization(organization: str, lang: str = "de") -> str:
    """Resolve an organization filter (numeric ID, colon-separated IDs, or German name/substring)
    to the numeric taxonomy IDs expected by /api/search/press-releases."""
    parts = [p.strip() for p in organization.split(":") if p.strip()]
    if not parts:
        raise ToolError("organization filter must not be empty")
    if all(p.isdigit() for p in parts):
        return ":".join(parts)

    orgs = await _load_organizations(lang)
    resolved: list[str] = []
    for part in parts:
        if part.isdigit():
            resolved.append(part)
            continue
        norm_q = _normalize(part)
        fold_q = _fold(part)
        exact = [
            o["id"] for o in orgs if _normalize(o["name"]) == norm_q or _fold(o["name"]) == fold_q
        ]
        if exact:
            resolved.append(exact[0])
            continue
        matches = [
            o["id"] for o in orgs if norm_q in _normalize(o["name"]) or fold_q in _fold(o["name"])
        ]
        if not matches:
            sample = ", ".join(f"{o['name']} ({o['id']})" for o in orgs[:5])
            raise ToolError(
                f"Unknown organization {part!r}. Call get_organizations to list valid senders "
                f"(e.g. {sample})."
            )
        resolved.append(matches[0])
    return ":".join(resolved)


def _validate_date(value: str | None, param_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _DATE_RE.match(cleaned):
        raise ToolError(f"{param_name} must be YYYY-MM-DD (e.g. '2026-01-01'), got {value!r}")
    return cleaned


def _simplify_hit(hit: dict) -> dict:
    title = _clean_inline(hit.get("title"))
    return {
        "id": _extract_node_id(hit.get("id")),
        "title": title,
        "lead": _clean_inline(hit.get("text")),
        "organization": _clean_inline(hit.get("organization")) or None,
        "date": _clean_inline(hit.get("date")) or None,
        "url": _full_url(hit.get("url")),
        "citation_label": citation_label(title),
    }


# --- MCP tools --------------------------------------------------------------


@mcp.tool(
    title="Search Press Releases",
    description=(
        f"Search press releases (Medienmitteilungen) on {DOMAIN} by German keywords, sender "
        "organization (name or id) and date range. Returns hits with id, title, lead, "
        "organization, date and url; pass url or id to get_press_release for the full article."
    ),
)
async def search_press_releases(
    search: str | None = None,
    organization: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
    page: int = 0,
    lang: str = "de",
) -> dict:
    """
    Args:
        search: Search terms (German works best). Omit to list the newest press releases.
        organization: Sender department/office name, substring (e.g. "Verkehr", "Grosser Rat")
            or numeric ID (e.g. "310", see get_organizations).
        date_from: Start date inclusive in YYYY-MM-DD format (e.g. "2025-01-01").
        date_to: End date inclusive in YYYY-MM-DD format (e.g. "2026-10-26").
        limit: Hits per page (default 10, max 50).
        page: Zero-based page index (default 0; pass next_page from the previous response).
        lang: Language code ("de", "en", "fr", "it"; default "de").
    """
    lang_clean = (lang or "de").strip().lower()
    size = max(1, min(limit, 50))
    page_num = max(0, page)
    params: dict[str, str | int] = {
        "langcode": lang_clean,
        "size": size,
        "page": page_num,
    }
    if search and search.strip():
        params["text"] = " ".join(search.split())
    if organization and organization.strip():
        params["organization"] = await _resolve_organization(organization.strip(), lang_clean)
    min_date = _validate_date(date_from, "date_from")
    max_date = _validate_date(date_to, "date_to")
    if min_date:
        params["date:min"] = min_date
    if max_date:
        params["date:max"] = max_date

    data = await fetch(SEARCH_PATH, params)
    # Seed the organization cache when an unfiltered query already includes the full facet.
    if (
        "text" not in params
        and "organization" not in params
        and "date:min" not in params
        and "date:max" not in params
    ):
        terms = _parse_org_terms(data)
        if terms:
            _org_cache["data"][lang_clean] = terms
            _org_cache["loaded_at"][lang_clean] = time.monotonic()

    hits = [_simplify_hit(h) for h in (data.get("hits") or []) if isinstance(h, dict)]
    total = data.get("total")
    total_pages = data.get("totalPages")
    next_page = (
        page_num + 1
        if isinstance(total_pages, int) and page_num + 1 < total_pages and hits
        else None
    )
    return {
        "total_count": total,
        "page": page_num,
        "total_pages": total_pages,
        "next_page": next_page,
        "results": hits,
    }


def _normalize_press_release_path(press_release: str | int) -> str:
    if isinstance(press_release, bool) or press_release is None:
        raise ToolError(
            "press_release must be a URL/path ('/medienmitteilungen/...') or a node id "
            "('43944') from search_press_releases."
        )
    text = str(press_release).strip()
    if not text:
        raise ToolError(
            "press_release must not be empty. Pass the url or id from search_press_releases."
        )
    entity_match = _ENTITY_NODE_RE.match(text)
    if entity_match:
        return f"/node/{entity_match.group(1)}"
    if text.isdigit():
        return f"/node/{text}"
    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        text = parsed.path or "/"
    if not text.startswith("/"):
        text = "/" + text
    return text


def _extract_body(paragraphs: list) -> str:
    blocks: list[str] = []
    for para in paragraphs or []:
        if not isinstance(para, dict) or para.get("isVisible") is False:
            continue
        props = para.get("props") or {}
        if not isinstance(props, dict):
            continue
        text = _clean_html(props.get("text") or props.get("title"))
        if text:
            blocks.append(text)
    return "\n\n".join(blocks)


def _extract_attachments(attachments: list) -> list[dict]:
    items: list[dict] = []
    for att in attachments or []:
        if not isinstance(att, dict):
            continue
        url = att.get("originalFileUrl") or (
            (((att.get("file") or {}).get("entity") or {}).get("uri") or {}).get("first") or {}
        ).get("url")
        if url:
            items.append(
                {
                    "title": _clean_inline(att.get("title")) or url.rsplit("/", 1)[-1],
                    "url": url,
                }
            )
    return items


def _extract_links(links: list) -> list[dict]:
    items: list[dict] = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        url = (link.get("uri") or {}).get("url")
        if url:
            items.append(
                {
                    "title": _clean_inline(link.get("title")) or url,
                    "url": _full_url(url),
                }
            )
    return items


def _extract_contacts(contacts: list) -> list[dict]:
    items: list[dict] = []
    for contact in contacts or []:
        if not isinstance(contact, dict) or contact.get("isVisible") is False:
            continue
        props = contact.get("props") or {}
        if not isinstance(props, dict):
            continue
        person = props.get("person")
        if isinstance(person, dict):
            first = _clean_inline(person.get("firstName"))
            last = _clean_inline(person.get("lastName"))
            name = " ".join(p for p in (first, last) if p)
            phone = (
                ((person.get("fieldPhoneNumber") or {}).get("first") or {}).get("parsed") or {}
            ).get("international")
            entry = {
                "name": name or None,
                "role": _clean_inline(person.get("role")) or None,
                "mail": person.get("mail") or None,
                "phone": phone or None,
            }
        else:
            phone = (((props.get("phoneNumber") or {}).get("first") or {}).get("parsed") or {}).get(
                "international"
            )
            entry = {
                "name": _clean_inline(props.get("name")) or None,
                "role": _clean_inline(props.get("role")) or None,
                "mail": props.get("mail") or None,
                "phone": phone or None,
            }
        entry = {k: v for k, v in entry.items() if v}
        if entry:
            items.append(entry)
    return items


@mcp.tool(
    title="Get Press Release",
    description=(
        "Get the full content of one press release by url, path ('/medienmitteilungen/...') "
        "or id ('43944') from search_press_releases: title, lead, full body text, published "
        "timestamp, sender organization, attachments (PDFs), related links and media contacts."
    ),
)
async def get_press_release(press_release: str | int) -> dict:
    """
    Args:
        press_release: Press release URL, path (e.g. "/medienmitteilungen/jsd/...") or node ID
            (e.g. 43944 or "entity:node/43944:de") from search_press_releases.
    """
    path = _normalize_press_release_path(press_release)
    data = await fetch(GRAPHQL_PRESS_RELEASE_PATH, {"path": path})
    route = (data.get("data") or {}).get("route") if isinstance(data, dict) else None
    if isinstance(route, dict) and route.get("__typename") == "RedirectUrl" and route.get("path"):
        path = route["path"]
        data = await fetch(GRAPHQL_PRESS_RELEASE_PATH, {"path": path})
        route = (data.get("data") or {}).get("route") if isinstance(data, dict) else None

    if not isinstance(route, dict) or not isinstance(route.get("entity"), dict):
        raise ToolError(
            f"Press release not found on {DOMAIN} for {press_release!r}. "
            "Find valid URLs or IDs with search_press_releases."
        )

    entity = route["entity"]
    canonical_path = route.get("path") or path
    drupal_entity = route.get("drupalRouteEntity") or {}
    date_first = (entity.get("date") or {}).get("first") or {}
    org_field = entity.get("fieldOrganization") or {}
    title = _clean_inline(entity.get("title"))
    body = _extract_body(entity.get("paragraphs") or [])
    truncated = False
    if len(body) > BODY_MAX_CHARS:
        body = body[: BODY_MAX_CHARS - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        truncated = True

    result: dict = {
        "id": str(drupal_entity.get("id")) if drupal_entity.get("id") else None,
        "title": title,
        "lead": _clean_html(entity.get("lead")) or None,
        "published": date_first.get("html"),
        "date": date_first.get("dateWithTime") or date_first.get("readableDateWithTime"),
        "organization": _clean_inline(org_field.get("label"))
        or _clean_inline(entity.get("senderInfo"))
        or None,
        "is_call_for_witnesses": bool(entity.get("isCallForWitnesses")),
        "url": _full_url(canonical_path),
        "citation_label": citation_label(title),
        "body": body,
        "attachments": _extract_attachments(entity.get("attachments") or []),
        "links": _extract_links(entity.get("links") or []),
        "contacts": _extract_contacts(entity.get("paragraphsContact") or []),
        "truncated": truncated,
    }
    if truncated:
        result["hint"] = (
            f"Body text was truncated to {BODY_MAX_CHARS} characters; open url for the full page."
        )
    return result


@mcp.tool(
    title="Get Sender Organizations",
    description=(
        "List the departments, offices and authorities that publish press releases on "
        f"{DOMAIN}, with their id and press release count. Use to browse senders or find "
        "an organization filter for search_press_releases."
    ),
)
async def get_organizations(search: str | None = None, lang: str = "de") -> dict:
    """
    Args:
        search: Optional substring to filter organization names (e.g. "Verkehr", "Gesundheit").
        lang: Language code ("de", "en", "fr", "it"; default "de").
    """
    lang_clean = (lang or "de").strip().lower()
    orgs = await _load_organizations(lang_clean)
    if search and search.strip():
        norm_q = _normalize(search)
        fold_q = _fold(search)
        orgs = [o for o in orgs if norm_q in _normalize(o["name"]) or fold_q in _fold(o["name"])]
    return {
        "total_count": len(orgs),
        "organizations": orgs,
    }


# --- HTTP app ---------------------------------------------------------------


def _healthz(request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _index(request) -> JSONResponse:
    return JSONResponse(
        {
            "server": DOMAIN,
            "status": "ok",
            "transport": "mcp-streamable-http",
            "endpoints": {
                "mcp": "/mcp",
                "health": "/healthz",
                "openapi": "/openapi.json",
                "docs": "/docs",
            },
        }
    )


def _openapi(request) -> JSONResponse:
    return JSONResponse(api_docs.build_openapi(DOMAIN, mcp._tool_manager.list_tools()))


def _docs(request) -> HTMLResponse:
    return HTMLResponse(api_docs.docs_page(DOMAIN))


def create_http_app():
    """Build a fresh ASGI app. Call once per process; tests create one per case
    because the underlying session manager may run only once per instance."""
    app = mcp.streamable_http_app(**MCP_HTTP_SETTINGS)
    app.add_middleware(RelaxedAcceptHeaderMiddleware)
    app.router.routes.insert(0, Route("/", _index))
    app.router.routes.insert(0, Route("/healthz", _healthz))
    app.router.routes.insert(0, Route("/openapi.json", _openapi))
    app.router.routes.insert(0, Route("/docs", _docs))
    return app


http_app = create_http_app()


def main():
    mcp.run(transport="stdio")


def main_http():
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(http_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
