---
name: medienmitteilungen-bs
description: >
  Query the press releases (Medienmitteilungen) of the canton of Basel-Stadt
  (www.bs.ch/medien/medienmitteilungen). Use to search official announcements,
  government council decisions, police witness calls, and department news since
  1994, filter by sender department or date range, and read full articles,
  attachments, and media contacts via plain HTTP. No MCP server needed.
---

# Medienmitteilungen Basel-Stadt (www.bs.ch)

Public JSON endpoints of the canton of Basel-Stadt (`www.bs.ch`). No auth, no SDK.

## Base URL

```
https://www.bs.ch
```

## 1. Search press releases and list organizations

`GET /api/search/press-releases`

Parameters:
- `langcode`: `de` (default), `en`, `fr`, `it`
- `text`: Full-text search query (German terms work best)
- `organization`: Numeric Drupal taxonomy ID of the sender organization (e.g. `310` for Bau- und Verkehrsdepartement, `139` for Departement für Wirtschaft, Soziales und Umwelt; multiple separated by `:`)
- `date:min`: Start date (`YYYY-MM-DD`)
- `date:max`: End date (`YYYY-MM-DD`)
- `size`: Results per page (default 24)
- `page`: Zero-based page number (`0`, `1`, ...)

```bash
# Search press releases by keyword and date range
curl -s "https://www.bs.ch/api/search/press-releases?langcode=de&text=Mindestlohn&date:min=2025-01-01&size=5" \
  | jq '{total, hits: [.hits[] | {id, date, organization, title, url, text}]}'

# List all sender organizations with their numeric ID and count
curl -s "https://www.bs.ch/api/search/press-releases?langcode=de&size=1" \
  | jq '.facets[] | select(.id == "organization") | .terms'
```

Each hit in `hits` contains:
- `id`: e.g. `"entity:node/43943:de"`
- `url`: Relative path, e.g. `"/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-..."`
- `title`: Title (may contain HTML entities or `<em>` tags)
- `text`: Lead / summary paragraph
- `organization`: Sender department or office label
- `date`: Formatted publication date and time

## 2. Read the full press release

`GET /api/graphql/query/routeNodePressRelease?path={url_path}`

Pass the `url` path from a search hit (or `/node/{id}`, which returns a `RedirectUrl` with the canonical `path`).

```bash
curl -s "https://www.bs.ch/api/graphql/query/routeNodePressRelease?path=/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-steigt-2027-auf-2250-franken-pro-stunde" \
  | jq '.data.route.entity | {
      title,
      lead,
      published: .date.first.html,
      organization: .fieldOrganization.label,
      paragraphs: [.paragraphs[]? | .props.text],
      attachments: [.attachments[]? | {title, url: .originalFileUrl}],
      links: [.links[]? | {title, url: .uri.url}]
    }'
```

## 3. Link the user to the press release

`https://www.bs.ch{url}` — public web page of the press release.

## Suggested workflow

1. Search `/api/search/press-releases` with German keywords and optional `date:min` / `date:max`.
2. If filtering by department or office, look up its numeric ID in `.facets[] | select(.id == "organization")`.
3. Fetch the full text, PDF attachments, and links of relevant hits via `/api/graphql/query/routeNodePressRelease?path=...`.
4. Cite the title, publication date, sender organization, and `https://www.bs.ch/medienmitteilungen/...` URL.
