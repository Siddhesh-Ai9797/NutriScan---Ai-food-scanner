import io

import pytest
from PIL import Image

from routers import predict as predict_router

GPT_RESULT = {
    "items": [{"name": "chicken biryani", "weight_grams": 350}],
    "primary_food": "chicken biryani",
    "total_calories": 600,
    "total_protein": 30,
    "total_carbs": 70,
    "total_fat": 20,
}


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "orange").save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def stub_pipeline(monkeypatch):
    def setup(model_guess, confidence, is_ood, hint_correct):
        predict_router.classifier.predict.return_value = (model_guess, confidence, is_ood)
        predict_router.classifier.top5_predictions.return_value = []

        async def fake_detect(image_bytes, primary_food=None):
            return {**GPT_RESULT, "hint_correct": hint_correct}

        monkeypatch.setattr(predict_router, "detect_all_foods", fake_detect)
        monkeypatch.setattr(predict_router, "upload_food_photo", lambda **kw: "https://example.com/photo.jpg")
    return setup


def _post_photo(client, headers):
    files = {"file": ("plate.jpg", _jpeg_bytes(), "image/jpeg")}
    return client.post("/predict", files=files, headers=headers)


def test_confident_model_answer_is_kept(client, user_headers, stub_pipeline):
    stub_pipeline("chicken_biryani", 0.95, False, True)
    body = _post_photo(client, user_headers).json()
    assert body["source"] == "efficientnet"
    assert body["food"] == "chicken biryani"
    assert body["confidence"] == 95.0
    assert body["model_guess"] is None


def test_gpt_overrules_wrong_confident_model(client, user_headers, stub_pipeline):
    stub_pipeline("fried_rice", 0.94, False, False)
    body = _post_photo(client, user_headers).json()
    assert body["source"] == "gpt4o"
    assert body["food"] == "chicken biryani"
    assert body["model_guess"] == "fried rice"
    assert body["confidence"] is None


def test_unsure_model_falls_back_to_gpt(client, user_headers, stub_pipeline):
    stub_pipeline("hamburger", 0.40, True, None)
    body = _post_photo(client, user_headers).json()
    assert body["source"] == "gpt4o"
    assert body["is_ood"] is True
    assert body["calories"] == 600
