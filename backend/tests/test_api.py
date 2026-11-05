import main
from routers.label import clean_food_name
from routers.predict import _folder_name
from services.nutrition_service import NotAFoodError

PER_100G = {
    "food": "banana",
    "calories": 89,
    "protein": 1.1,
    "carbs": 22.8,
    "fat": 0.3,
    "serving": "per 100g",
    "source": "gpt4o",
}


def _nutrition_returns(monkeypatch, value=None, error=None):
    async def fake(food):
        if error:
            raise error
        return dict(value) if value else None
    monkeypatch.setattr(main, "_get_nutrition", fake)


def test_health_needs_no_sign_in(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_nutrition_requires_sign_in(client):
    assert client.get("/nutrition", params={"food": "banana"}).status_code == 401


def test_nutrition_rejects_bad_token(client):
    headers = {"Authorization": "Bearer expired"}
    assert client.get("/nutrition", params={"food": "banana"}, headers=headers).status_code == 401


def test_nutrition_per_100g(client, user_headers, monkeypatch):
    _nutrition_returns(monkeypatch, PER_100G)
    body = client.get("/nutrition", params={"food": "banana"}, headers=user_headers).json()
    assert body["calories"] == 89
    assert body["serving"] == "per 100g"


def test_nutrition_scales_to_portion(client, user_headers, monkeypatch):
    _nutrition_returns(monkeypatch, PER_100G)
    body = client.get("/nutrition", params={"food": "banana", "grams": 200}, headers=user_headers).json()
    assert body["calories"] == 178
    assert body["carbs"] == 45.6
    assert body["serving"] == "200g"


def test_nutrition_rejects_non_food(client, user_headers, monkeypatch):
    _nutrition_returns(monkeypatch, error=NotAFoodError("nope"))
    response = client.get("/nutrition", params={"food": "asdfgh"}, headers=user_headers)
    assert response.status_code == 400
    assert "asdfgh" in response.json()["detail"]


def test_nutrition_reports_outage(client, user_headers, monkeypatch):
    _nutrition_returns(monkeypatch, None)
    assert client.get("/nutrition", params={"food": "banana"}, headers=user_headers).status_code == 503


def test_nutrition_rejects_huge_portion(client, user_headers, monkeypatch):
    _nutrition_returns(monkeypatch, PER_100G)
    response = client.get("/nutrition", params={"food": "banana", "grams": 5000}, headers=user_headers)
    assert response.status_code == 422


def test_rate_limit_blocks_after_60_calls(client, user_headers, monkeypatch):
    _nutrition_returns(monkeypatch, PER_100G)
    for _ in range(60):
        assert client.get("/nutrition", params={"food": "banana"}, headers=user_headers).status_code == 200
    assert client.get("/nutrition", params={"food": "banana"}, headers=user_headers).status_code == 429


def test_admin_route_blocks_normal_users(client, user_headers):
    assert client.get("/admin/me", headers=user_headers).status_code == 403


def test_admin_route_allows_admin(client, admin_headers):
    assert client.get("/admin/me", headers=admin_headers).json() == {"admin": True}


def test_predict_rejects_non_image_upload(client, user_headers):
    files = {"file": ("notes.txt", b"hello", "text/plain")}
    assert client.post("/predict", files=files, headers=user_headers).status_code == 400


def test_clean_food_name_strips_html_and_symbols():
    assert clean_food_name("<b>Chicken</b>   Biryani!!") == "chicken biryani"
    assert clean_food_name("Pav Bhaji 🍛") == "pav bhaji"


def test_folder_name():
    assert _folder_name("Chicken Biryani") == "chicken_biryani"
    assert _folder_name("  ???  ") == "unknown"
