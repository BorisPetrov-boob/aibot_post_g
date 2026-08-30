def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_source_crud(client):
    r = client.post(
        "/api/sources/",
        json={"type": "site", "name": "Example RSS", "url": "https://example.com/rss"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    assert client.get("/api/sources/").status_code == 200
    assert client.get(f"/api/sources/{sid}").json()["name"] == "Example RSS"

    r = client.patch(f"/api/sources/{sid}", json={"enabled": False})
    assert r.json()["enabled"] is False

    # duplicate type+url -> 409
    r = client.post(
        "/api/sources/",
        json={"type": "site", "name": "dup", "url": "https://example.com/rss"},
    )
    assert r.status_code == 409

    assert client.delete(f"/api/sources/{sid}").json()["detail"] == "deleted"


def test_keyword_crud(client):
    r = client.post("/api/keywords/", json={"word": "AI"})
    assert r.status_code == 201
    kid = r.json()["id"]
    assert r.json()["word"] == "ai"
    assert any(k["id"] == kid for k in client.get("/api/keywords/").json())
    assert client.delete(f"/api/keywords/{kid}").status_code == 200


def test_manual_generate_offline_stub(client):
    r = client.post(
        "/api/generate/",
        json={
            "title": "Учёные открыли новый вид глубоководных рыб",
            "summary": "Экспедиция обнаружила рыбу на глубине 8000 метров.",
            "url": "https://example.com/fish",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["used_offline_stub"] is True
    assert "рыб" in body["generated_text"].lower()
    assert body["post_id"] is None


def test_manual_generate_persist(client):
    r = client.post(
        "/api/generate/",
        json={"title": "Тест", "summary": "Тестовое содержимое", "persist": True},
    )
    assert r.status_code == 200
    post_id = r.json()["post_id"]
    assert post_id
    assert client.get(f"/api/posts/{post_id}").json()["status"] == "generated"


def test_generate_requires_content(client):
    r = client.post("/api/generate/", json={})
    assert r.status_code == 422
