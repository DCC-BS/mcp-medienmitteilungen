import pytest
from mcp.server.mcpserver.exceptions import ToolError

SEARCH_RESPONSE = {
    "took": 12,
    "total": 25,
    "totalPages": 3,
    "params": {
        "size": 10,
        "page": 0,
        "filter": {"text": ""},
        "langcode": "de",
        "locale": "de-CH",
        "facets": [],
    },
    "facets": [
        {
            "id": "organization",
            "terms": [
                {
                    "count": 3144,
                    "value": "310",
                    "label": "Bau- und Verkehrsdepartement",
                },
                {
                    "count": 1203,
                    "value": "139",
                    "label": "Departement für Wirtschaft, Soziales und Umwelt",
                },
                {
                    "count": 53,
                    "value": "14",
                    "label": "Bevölkerungsdienste und Migration",
                },
            ],
        }
    ],
    "filters": [
        {
            "type": "dateRange",
            "id": "date",
            "min": "1994-12-06",
            "max": "2026-10-26",
        }
    ],
    "hits": [
        {
            "id": "entity:node/43944:de",
            "url": "/medienmitteilungen/jsd/2026-volle-motorfahrzeugsteuer-fuer-elektroautos",
            "title": "Volle <em>Motorfahrzeugsteuer</em> f&uuml;r Elektroautos",
            "text": "Im November erfolgt der Versand.<br>Der Rabatt f&auml;llt weg.",
            "organization": "Justiz- und Sicherheitsdepartement",
            "date": "26.10.2026 – 10:00 Uhr",
            "group": "Oktober 2026",
        },
        {
            "id": "entity:node/43943:de",
            "url": "/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-steigt-2027-auf-2250-franken-pro-stunde",
            "title": "Kantonaler Mindestlohn steigt 2027 auf 22.50 Franken pro Stunde",
            "text": "Der kantonale Mindestlohn in Basel-Stadt steigt per 1. Januar 2027.",
            "organization": "Departement für Wirtschaft, Soziales und Umwelt",
            "date": "26.10.2026 – 09:30 Uhr",
            "group": "Oktober 2026",
        },
    ],
}


DETAIL_RESPONSE = {
    "data": {
        "route": {
            "__typename": "EntityCanonicalUrl",
            "path": "/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-steigt-2027-auf-2250-franken-pro-stunde",
            "drupalRouteEntity": {
                "uuid": "abc-123",
                "entityBundle": "press_release",
                "entityTypeId": "node",
                "id": "43943",
            },
            "entity": {
                "__typename": "NodePressRelease",
                "title": "Kantonaler Mindestlohn steigt 2027 auf 22.50 Franken pro Stunde",
                "isCallForWitnesses": False,
                "lead": "Der kantonale Mindestlohn in Basel-Stadt steigt per 1. Januar 2027.",
                "senderInfo": None,
                "date": {
                    "first": {
                        "dateShort": "26.10.2026",
                        "readableDateWithTime": "Montag, 26. Oktober 2026 - 09:30",
                        "dateWithTime": "26.10.2026 - 09:30",
                        "html": "2026-10-26T09:30:00+0100",
                    }
                },
                "paragraphs": [
                    {
                        "uuid": "p1",
                        "bundle": "text",
                        "isVisible": True,
                        "props": {
                            "text": (
                                "<p>Erster Absatz mit &amp; Sonderzeichen.</p>"
                                '<p>Zweiter Absatz mit <a href="https://grosserrat.bs.ch/123">Motion</a>.</p>'
                            )
                        },
                    }
                ],
                "attachments": [
                    {
                        "title": "Merkblatt Mindestlohn",
                        "file": {
                            "entity": {
                                "uri": {
                                    "first": {
                                        "url": "https://media.bs.ch/dynamic/noop/1/merkblatt.pdf"
                                    }
                                }
                            }
                        },
                        "originalFileUrl": "https://media.bs.ch/original_file/1/merkblatt.pdf",
                    }
                ],
                "links": [
                    {
                        "title": "Weitere Informationen zum kantonalen Mindestlohn",
                        "uri": {
                            "url": "https://www.bs.ch/wsu/awa/arbeitsbeziehungen/loehne/mindestlohn"
                        },
                    }
                ],
                "fieldOrganization": {
                    "label": "Departement für Wirtschaft, Soziales und Umwelt",
                },
                "paragraphsContact": [
                    {
                        "bundle": "government_contact",
                        "isVisible": True,
                        "props": {
                            "person": {
                                "firstName": "Michael",
                                "lastName": "Mauerhofer",
                                "mail": "michael.mauerhofer@bs.ch",
                                "role": "Bereichsleitung Arbeitsbedingungen",
                                "fieldPhoneNumber": {
                                    "first": {"parsed": {"international": "+41 61 267 87 78"}}
                                },
                            }
                        },
                    },
                    {
                        "bundle": "external_contact",
                        "isVisible": True,
                        "props": {
                            "name": "Thomas Heimberg",
                            "role": "Leiter Friedhöfe Basel",
                            "mail": "thomas.heimberg@bs.ch",
                            "phoneNumber": {
                                "first": {"parsed": {"international": "+41 61 267 20 05"}}
                            },
                        },
                    },
                ],
            },
        }
    }
}


@pytest.mark.anyio
async def test_search_press_releases_returns_citable_hits_and_paging(mock_fetch):
    import main

    calls = mock_fetch({main.SEARCH_PATH: SEARCH_RESPONSE})

    result = await main.search_press_releases(search="Mindestlohn", limit=10, page=0)

    assert calls[0]["params"] == {"langcode": "de", "size": 10, "page": 0, "text": "Mindestlohn"}
    assert result["total_count"] == 25
    assert result["page"] == 0
    assert result["total_pages"] == 3
    assert result["next_page"] == 1
    hit = result["results"][0]
    assert hit["id"] == "43944"
    assert hit["title"] == "Volle Motorfahrzeugsteuer für Elektroautos"
    assert hit["lead"] == "Im November erfolgt der Versand. Der Rabatt fällt weg."
    assert hit["organization"] == "Justiz- und Sicherheitsdepartement"
    assert hit["date"] == "26.10.2026 – 10:00 Uhr"
    assert hit["url"] == (
        "https://www.bs.ch/medienmitteilungen/jsd/2026-volle-motorfahrzeugsteuer-fuer-elektroautos"
    )
    assert hit["citation_label"] == (f"{main.DOMAIN} · Volle Motorfahrzeugsteuer für Elektroautos")


@pytest.mark.anyio
async def test_search_resolves_organization_by_name_and_id(mock_fetch):
    import main

    calls = mock_fetch({main.SEARCH_PATH: SEARCH_RESPONSE})

    await main.search_press_releases(organization="310")
    assert calls[-1]["params"]["organization"] == "310"

    await main.search_press_releases(organization="bevoelkerungsdienste")
    assert calls[-1]["params"]["organization"] == "14"

    await main.search_press_releases(organization="Wirtschaft")
    assert calls[-1]["params"]["organization"] == "139"


@pytest.mark.anyio
async def test_search_rejects_unknown_organization(mock_fetch):
    import main

    mock_fetch({main.SEARCH_PATH: SEARCH_RESPONSE})

    with pytest.raises(ToolError, match="get_organizations"):
        await main.search_press_releases(organization="Weltraumbehörde")


@pytest.mark.anyio
async def test_search_validates_and_passes_date_filters(mock_fetch):
    import main

    calls = mock_fetch({main.SEARCH_PATH: SEARCH_RESPONSE})

    await main.search_press_releases(date_from="2025-01-01", date_to="2026-10-26")
    assert calls[-1]["params"]["date:min"] == "2025-01-01"
    assert calls[-1]["params"]["date:max"] == "2026-10-26"

    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        await main.search_press_releases(date_from="26.10.2026")


@pytest.mark.anyio
async def test_get_organizations_sorts_by_count_and_filters(mock_fetch):
    import main

    calls = mock_fetch({main.SEARCH_PATH: SEARCH_RESPONSE})

    all_orgs = await main.get_organizations()
    assert [o["id"] for o in all_orgs["organizations"]] == ["310", "139", "14"]
    assert all_orgs["organizations"][0]["url"] == (
        "https://www.bs.ch/medien/medienmitteilungen?organization=310"
    )

    filtered = await main.get_organizations(search="bevoelkerung")
    assert [o["id"] for o in filtered["organizations"]] == ["14"]
    # Cached: second call did not hit upstream again
    assert len(calls) == 1


@pytest.mark.anyio
async def test_get_press_release_by_path_and_url(mock_fetch):
    import main

    path = "/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-steigt-2027-auf-2250-franken-pro-stunde"
    mock_fetch({(main.GRAPHQL_PRESS_RELEASE_PATH, path): DETAIL_RESPONSE})

    result = await main.get_press_release(f"https://www.bs.ch{path}")

    assert result["id"] == "43943"
    assert result["title"] == "Kantonaler Mindestlohn steigt 2027 auf 22.50 Franken pro Stunde"
    assert result["published"] == "2026-10-26T09:30:00+0100"
    assert result["date"] == "26.10.2026 - 09:30"
    assert result["organization"] == "Departement für Wirtschaft, Soziales und Umwelt"
    assert "Erster Absatz mit & Sonderzeichen." in result["body"]
    assert "Zweiter Absatz mit Motion." in result["body"]
    assert result["attachments"] == [
        {
            "title": "Merkblatt Mindestlohn",
            "url": "https://media.bs.ch/original_file/1/merkblatt.pdf",
        }
    ]
    assert result["links"] == [
        {
            "title": "Weitere Informationen zum kantonalen Mindestlohn",
            "url": "https://www.bs.ch/wsu/awa/arbeitsbeziehungen/loehne/mindestlohn",
        }
    ]
    assert len(result["contacts"]) == 2
    assert result["contacts"][0]["name"] == "Michael Mauerhofer"
    assert result["contacts"][0]["phone"] == "+41 61 267 87 78"
    assert result["contacts"][1]["name"] == "Thomas Heimberg"
    assert result["url"] == f"https://www.bs.ch{path}"
    assert result["citation_label"] == (
        f"{main.DOMAIN} · Kantonaler Mindestlohn steigt 2027 auf 22.50 Franken pro Stunde"
    )


@pytest.mark.anyio
async def test_get_press_release_follows_node_id_redirect(mock_fetch):
    import main

    canonical = "/medienmitteilungen/wsu/2026-kantonaler-mindestlohn-steigt-2027-auf-2250-franken-pro-stunde"
    redirect_resp = {
        "data": {
            "route": {
                "__typename": "RedirectUrl",
                "path": canonical,
            }
        }
    }
    calls = mock_fetch(
        {
            (main.GRAPHQL_PRESS_RELEASE_PATH, "/node/43943"): redirect_resp,
            (main.GRAPHQL_PRESS_RELEASE_PATH, canonical): DETAIL_RESPONSE,
        }
    )

    result = await main.get_press_release("entity:node/43943:de")

    assert [c["params"]["path"] for c in calls] == ["/node/43943", canonical]
    assert result["id"] == "43943"
    assert result["url"] == f"https://www.bs.ch{canonical}"


@pytest.mark.anyio
async def test_get_press_release_truncates_long_body(mock_fetch):
    import copy

    import main

    path = "/medienmitteilungen/wsu/long"
    long_resp = copy.deepcopy(DETAIL_RESPONSE)
    long_resp["data"]["route"]["path"] = path
    long_resp["data"]["route"]["entity"]["paragraphs"] = [
        {"bundle": "text", "isVisible": True, "props": {"text": "<p>" + ("Wort " * 4000) + "</p>"}}
    ]
    mock_fetch({(main.GRAPHQL_PRESS_RELEASE_PATH, path): long_resp})

    result = await main.get_press_release(path)

    assert len(result["body"]) <= main.BODY_MAX_CHARS
    assert result["truncated"] is True
    assert "hint" in result


@pytest.mark.anyio
async def test_get_press_release_raises_on_missing_route(mock_fetch):
    import main

    mock_fetch(
        {
            (main.GRAPHQL_PRESS_RELEASE_PATH, "/medienmitteilungen/missing"): {
                "data": {"route": None}
            }
        }
    )

    with pytest.raises(ToolError, match="search_press_releases"):
        await main.get_press_release("/medienmitteilungen/missing")


def test_instructions_route_but_do_not_prescribe_a_citation_format():
    import main

    text = main.mcp.instructions
    assert "search_press_releases" in text and "get_press_release" in text
    assert "Always cite" not in text
