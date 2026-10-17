def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["app"] in {"Seoul", "RankLens"}
    assert body["serp_provider"] in {"serper", "duckduckgo"}


def test_health_never_leaks_keys(client):
    assert "key" not in client.get("/api/health").text.lower()


def test_docs_available(client):
    assert client.get("/api/docs").status_code == 200
