import api as app_module
from src.config import FALLBACK_DOC_TYPE, MODEL, SUPPORTED_DOC_TYPES


class TestHealthEndpoints:
    async def test_root_redirects_to_docs(self, api_client):
        response = await api_client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"

    async def test_health_returns_200(self, api_client):
        response = await api_client.get("/health")
        assert response.status_code == 200

    async def test_health_status_ok(self, api_client):
        body = (await api_client.get("/health")).json()
        assert body["status"] == "ok"

    async def test_health_model(self, api_client):
        body = (await api_client.get("/health")).json()
        assert body["model"] == MODEL

    async def test_health_fallback_doc_type(self, api_client):
        body = (await api_client.get("/health")).json()
        assert body["fallback_doc_type"] == FALLBACK_DOC_TYPE

    async def test_health_supported_doc_types_sorted(self, api_client):
        body = (await api_client.get("/health")).json()
        assert body["supported_doc_types"] == sorted(SUPPORTED_DOC_TYPES)

    async def test_health_langfuse_enabled_matches_constant(self, api_client):
        body = (await api_client.get("/health")).json()
        assert body["langfuse_enabled"] == app_module._LANGFUSE_ENABLED
