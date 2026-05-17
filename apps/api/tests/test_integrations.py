async def test_create_webhook_integration(client):
    resp = await client.post(
        "/api/v1/integrations/bitrix24/webhook",
        json={
            "label": "Test portal",
            "webhook_url": "https://test.bitrix24.ru/rest/1/abcdef123456/",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "webhook"
    assert body["status"] == "connected"
    assert body["domain"] == "test.bitrix24.ru"


async def test_list_and_delete(client):
    create = await client.post(
        "/api/v1/integrations/bitrix24/webhook",
        json={
            "label": "Test 2",
            "webhook_url": "https://x.bitrix24.ru/rest/1/aaaaaaaaaaaaaaaa/",
        },
    )
    assert create.status_code == 201, create.text
    integration_id = create.json()["id"]

    list_resp = await client.get("/api/v1/integrations")
    assert list_resp.status_code == 200
    assert any(i["id"] == integration_id for i in list_resp.json())

    del_resp = await client.delete(f"/api/v1/integrations/{integration_id}")
    assert del_resp.status_code == 204

    list2 = await client.get("/api/v1/integrations")
    assert all(i["id"] != integration_id for i in list2.json())


def test_portal_from_client_endpoint():
    from app.api.v1.integrations import _portal_from_client_endpoint

    assert (
        _portal_from_client_endpoint("https://acme.bitrix24.ru/rest/")
        == "acme.bitrix24.ru"
    )
    assert (
        _portal_from_client_endpoint("https://b24-xyz.bitrix24.com/rest/")
        == "b24-xyz.bitrix24.com"
    )
    assert _portal_from_client_endpoint(None) is None
    assert _portal_from_client_endpoint("") is None
    assert _portal_from_client_endpoint("not a url") is None


async def test_create_oauth_returns_authorize_url(client):
    resp = await client.post(
        "/api/v1/integrations/bitrix24/oauth",
        json={
            "label": "Portal A",
            "domain": "company.bitrix24.ru",
            "client_id": "app.abc123def456",
            "client_secret": "secret123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["integration"]["status"] == "pending"
    assert "company.bitrix24.ru/oauth/authorize/" in body["authorize_url"]
    assert "client_id=app.abc123def456" in body["authorize_url"]
