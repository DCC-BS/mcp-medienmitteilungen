import pytest


@pytest.fixture
def mock_fetch(monkeypatch):
    """Replace main.fetch with a stub that serves canned bodies per endpoint and
    records the calls. A body may be a callable taking the query params. Also
    resets the in-memory organization cache."""
    import main

    monkeypatch.setitem(main._org_cache, "data", {})
    monkeypatch.setitem(main._org_cache, "loaded_at", {})

    def _install(bodies: dict):
        calls = []

        async def fake_fetch(endpoint, params=None, **kwargs):
            calls.append({"endpoint": endpoint, "params": params or {}})
            key = (endpoint, (params or {}).get("path"))
            if key in bodies:
                body = bodies[key]
            else:
                body = bodies[endpoint]
            return body(params or {}) if callable(body) else body

        monkeypatch.setattr("main.fetch", fake_fetch)
        return calls

    return _install
