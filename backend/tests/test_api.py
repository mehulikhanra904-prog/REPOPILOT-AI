from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint_reports_local_analysis_mode():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "ai_provider" in response.json()


def test_analyze_rejects_non_github_url_before_network_call():
    response = TestClient(app).post("/api/analyze", json={"repo_url": "https://example.com/not-github"})
    assert response.status_code == 422
    assert "github.com" in response.json()["detail"]
