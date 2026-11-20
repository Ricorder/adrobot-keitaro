from app.db.models import Base


def test_healthz_reports_database_reachable(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "reachable"
    assert body["tables"] == len(Base.metadata.tables)


def test_meta_exposes_config_without_the_key(client) -> None:
    body = client.get("/api/meta").json()
    assert set(body) == {
        "keitaro_base_url",
        "keitaro_prefix",
        "keitaro_key_configured",
        "google_redirect_url",
    }
    assert isinstance(body["keitaro_key_configured"], bool)
    assert body["keitaro_prefix"].endswith("-")
