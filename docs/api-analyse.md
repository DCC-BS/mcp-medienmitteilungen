# API-Analyse www.bs.ch Medienmitteilungen für den MCP-Server

Stand: 2026-10-26. Grundlage: Nuxt-Frontend `www.bs.ch/medien/medienmitteilungen`,
Live-Abfragen gegen `www.bs.ch`.

## Fazit

Die erste Version des MCP-Servers benötigt keinen eigenen Index und keine Datenbank.
Die bestehenden öffentlichen JSON-Endpunkte von `www.bs.ch` decken Volltextsuche,
Filterung nach Absenderorganisation und Zeitraum, Paginierung sowie den Abruf des
vollständigen Medienmitteilungstexts inkl. Anhängen, Links und Kontakten ab.

## Vorhandene Endpunkte

| Endpunkt | Inhalt | Nutzung im MCP |
|---|---|---|
| `GET /api/search/press-releases` | Volltextsuche, Facetten (61 Organisationen mit Anzahl), Datumsfilter (`date:min`, `date:max`), Paginierung (`page`, `size`), Sprachwahl (`langcode`) | `search_press_releases`, `get_organizations` |
| `GET /api/graphql/query/routeNodePressRelease?path={pfad}` | Vollständige Medienmitteilung (Titel, Lead, Absätze als HTML, Organisation, Anhänge, weiterführende Links, Medienkontakte) | `get_press_release` |

## Beobachtungen

1. **Organisationsfilter erwartet numerische Drupal-Taxonomie-IDs.**
   `/api/search/press-releases` akzeptiert im Parameter `organization` nur IDs wie
   `310` (Bau- und Verkehrsdepartement) oder mehrere mit Doppelpunkt getrennte IDs
   (`310:139`). Damit Sprachmodelle nicht zwingend vorher `get_organizations`
   aufrufen müssen, hält der MCP-Server die Facettenliste 1 Stunde im Speicher und
   löst auch deutsche Namen oder Teilbegriffe (`"Verkehr"`, `"Grosser Rat"`)
   automatisch in die passende ID auf.
2. **Suchtreffer liefern nur den Lead-Text.**
   In `hits[].text` steht lediglich der Lead (Vorspann). Der eigentliche Artikeltext
   befindet sich in `paragraphs` der GraphQL-Antwort von `routeNodePressRelease`.
3. **Auflösung von Node-IDs über Redirect-Routen.**
   Suchtreffer tragen eine ID der Form `entity:node/43944:de`. Ein Aufruf von
   `routeNodePressRelease?path=/node/43944` liefert `__typename: "RedirectUrl"` mit
   dem kanonischen Pfad `/medienmitteilungen/...`. Der MCP-Server folgt diesem
   Redirect automatisch, sodass `get_press_release` sowohl Pfade/URLs als auch
   numerische Node-IDs akzeptiert.
4. **GraphQL-Persistenz-Hash (`__gqlh`) ist optional.**
   Das Nuxt-Frontend sendet `__gqlh=6KWLft7eOh`, der Server beantwortet
   `GET /api/graphql/query/routeNodePressRelease?path=...` jedoch auch ohne Hash.
   Dadurch übersteht der MCP-Server Frontend-Rebuilds auf `www.bs.ch`.

## Ausblick: Option 2 (Semantische Suche und Graph-Suche)

Die aktuelle Suche auf `www.bs.ch` ist rein lexikalisch. Für komplexe thematische
Fragen oder Zusammenhänge über lange Zeiträume (Archiv ab 1994, knapp 18'000
Medienmitteilungen) bietet sich analog zu `grossrat-bs-mcp` eine zweite Ausbaustufe an:

- Periodischer Harvest aller Medienmitteilungen in eine lokale Datenbank (SQLite/DuckDB + Vektorindex).
- Hybride Suche (BM25 + Embeddings) über Titel, Lead und Volltext.
- Verknüpfung von Entitäten (Departemente, Grossratsgeschäfte in Links, Orte, Themen) für Graph-Abfragen.
