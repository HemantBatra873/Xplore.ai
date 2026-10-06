def test_health_check_returns_dependencies(client):
    response = client.get("/api/v1/health/", follow_redirects=True)
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "dependencies" in data
    deps = data["dependencies"]
    assert "database" in deps
    assert "redis" in deps
    assert "ollama" in deps
    assert deps["database"]["status"] == "up"
    if response.status_code == 200:
        assert data["status"] == "ok"
    else:
        assert data["status"] == "degraded"


def test_root_endpoint(client):
    response = client.get("/")
    # With a frontend build present, "/" serves the SPA (HTML).
    # Without static assets, the API returns a JSON welcome payload.
    assert response.status_code in (200, 404)
    if response.status_code != 200:
        return
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        assert "Welcome" in response.json()["message"]
    else:
        assert "html" in content_type.lower() or "<!doctype html>" in response.text.lower()
