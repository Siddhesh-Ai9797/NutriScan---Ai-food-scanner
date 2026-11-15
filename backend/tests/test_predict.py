"""
Scan pipeline: router, caching, guardrails and monitoring on /predict.
The vision model and CLIP are stubbed; no network calls are made.
"""
import io

import pytest
from PIL import Image

from routers import predict as predict_router
from services import metrics_service
from services.guardrail_service import NotFoodPhoto, food_gate

PLATE = {
    "items": [{"food": "chicken biryani", "weight_grams": 350, "calories": 600,
               "protein": 30, "carbs": 70, "fat": 20}],
    "primary_food": "chicken biryani",
    "total_calories": 600,
    "total_protein": 30,
    "total_carbs": 70,
    "total_fat": 20,
}


def _jpeg_bytes(colour="orange") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def pipeline(monkeypatch):
    """
    Stubs EfficientNet and the vision model. `answers` maps model name to what
    that model returns: a hint_correct value, "not_food", or "fail".
    Every call is recorded in `calls`.
    """
    state = {"calls": [], "answers": {}}

    def setup(model_guess, confidence, is_ood, answers):
        predict_router.classifier.predict.return_value = (model_guess, confidence, is_ood)
        predict_router.classifier.top5_predictions.return_value = []
        state["answers"] = answers

    async def fake_detect(image_bytes, primary_food=None, model="gpt-4o", detail="auto"):
        state["calls"].append({"model": model, "detail": detail, "hint": primary_food})
        answer = state["answers"].get(model, True)
        if answer == "not_food":
            raise NotFoodPhoto()
        if answer == "fail":
            return None, ["llm_failed"]
        return {**PLATE, "hint_correct": answer}, []

    monkeypatch.setattr(predict_router, "detect_all_foods", fake_detect)
    monkeypatch.setattr(predict_router, "upload_food_photo", lambda **kw: "https://example.com/photo.jpg")
    setup.calls = state["calls"]
    return setup


def _post_photo(client, headers, colour="orange"):
    files = {"file": ("plate.jpg", _jpeg_bytes(colour), "image/jpeg")}
    return client.post("/predict", files=files, headers=headers)


# ── Router ────────────────────────────────────────────────────────────────
def test_confident_scan_uses_cheap_model(client, user_headers, pipeline):
    pipeline("chicken_biryani", 0.97, False, {"gpt-4o-mini": True})
    body = _post_photo(client, user_headers).json()
    assert body["route"] == "fast"
    assert body["source"] == "efficientnet"
    assert body["food"] == "chicken biryani"
    assert body["confidence"] == 97.0
    assert [c["model"] for c in pipeline.calls] == ["gpt-4o-mini"]
    assert pipeline.calls[0]["detail"] == "low"


def test_cheap_model_dispute_escalates_to_full_model(client, user_headers, pipeline):
    pipeline("fried_rice", 0.97, False, {"gpt-4o-mini": False, "gpt-4o": False})
    body = _post_photo(client, user_headers).json()
    assert body["route"] == "escalated"
    assert [c["model"] for c in pipeline.calls] == ["gpt-4o-mini", "gpt-4o"]
    assert body["source"] == "gpt4o"
    assert body["food"] == "chicken biryani"
    assert body["model_guess"] == "fried rice"


def test_cheap_model_failure_escalates(client, user_headers, pipeline):
    pipeline("pizza", 0.99, False, {"gpt-4o-mini": "fail", "gpt-4o": True})
    body = _post_photo(client, user_headers).json()
    assert body["route"] == "escalated"
    assert body["calories"] == 600


def test_cheap_model_not_food_escalates_instead_of_blocking(client, user_headers, pipeline):
    pipeline("pizza", 0.99, False, {"gpt-4o-mini": "not_food", "gpt-4o": True})
    body = _post_photo(client, user_headers).json()
    assert body["route"] == "escalated"


def test_mid_confidence_goes_straight_to_full_model(client, user_headers, pipeline):
    pipeline("chicken_biryani", 0.90, False, {"gpt-4o": True})
    body = _post_photo(client, user_headers).json()
    assert body["route"] == "full"
    assert body["source"] == "efficientnet"
    assert [c["model"] for c in pipeline.calls] == ["gpt-4o"]


def test_unsure_model_goes_to_full_model_without_hint(client, user_headers, pipeline):
    pipeline("hamburger", 0.40, True, {"gpt-4o": None})
    body = _post_photo(client, user_headers).json()
    assert body["source"] == "gpt4o"
    assert body["is_ood"] is True
    assert body["calories"] == 600
    assert pipeline.calls[0]["hint"] is None


def test_router_can_be_switched_off(client, user_headers, pipeline, monkeypatch):
    monkeypatch.setattr(predict_router, "ROUTER_ON", False)
    pipeline("pizza", 0.99, False, {"gpt-4o": True})
    body = _post_photo(client, user_headers).json()
    assert body["route"] == "full"


# ── Caching ───────────────────────────────────────────────────────────────
def test_same_photo_twice_is_served_from_cache(client, user_headers, pipeline):
    pipeline("pizza", 0.99, False, {"gpt-4o-mini": True})
    first = _post_photo(client, user_headers).json()
    second = _post_photo(client, user_headers).json()
    assert first["route"] == "fast"
    assert second["route"] == "cache"
    assert second["calories"] == first["calories"]
    assert len(pipeline.calls) == 1


def test_different_photo_is_not_a_cache_hit(client, user_headers, pipeline):
    pipeline("pizza", 0.99, False, {"gpt-4o-mini": True})
    _post_photo(client, user_headers, "orange")
    second = _post_photo(client, user_headers, "green").json()
    assert second["route"] == "fast"
    assert len(pipeline.calls) == 2


def test_failed_scans_are_not_cached(client, user_headers, pipeline):
    pipeline("pizza", 0.40, True, {"gpt-4o": "fail"})
    assert _post_photo(client, user_headers).json()["status"] == "unknown"
    assert _post_photo(client, user_headers).json()["status"] == "unknown"
    assert len(pipeline.calls) == 2


# ── Input guardrails ──────────────────────────────────────────────────────
def test_clip_blocks_non_food_before_any_paid_call(client, user_headers, pipeline, monkeypatch):
    monkeypatch.setattr(food_gate, "check", lambda image: (False, 0.04))
    pipeline("pizza", 0.99, False, {})
    response = _post_photo(client, user_headers)
    assert response.status_code == 422
    assert "doesn't look like food" in response.json()["detail"]
    assert pipeline.calls == []
    predict_router.classifier.predict.assert_not_called()


def test_full_model_not_food_answer_blocks(client, user_headers, pipeline):
    pipeline("pizza", 0.40, True, {"gpt-4o": "not_food"})
    response = _post_photo(client, user_headers)
    assert response.status_code == 422


def test_blocked_photo_is_cached_too(client, user_headers, pipeline, monkeypatch):
    calls = []
    monkeypatch.setattr(food_gate, "check", lambda image: calls.append(1) or (False, 0.04))
    pipeline("pizza", 0.99, False, {})
    assert _post_photo(client, user_headers).status_code == 422
    assert _post_photo(client, user_headers).status_code == 422
    assert len(calls) == 1


@pytest.fixture(autouse=True)
def _fresh_classifier():
    predict_router.classifier.reset_mock()
    yield


# ── Monitoring ────────────────────────────────────────────────────────────
def test_every_scan_is_recorded(client, user_headers, pipeline, monkeypatch):
    pipeline("pizza", 0.99, False, {"gpt-4o-mini": True})
    _post_photo(client, user_headers)
    _post_photo(client, user_headers)
    monkeypatch.setattr(food_gate, "check", lambda image: (False, 0.02))
    _post_photo(client, user_headers, "blue")

    summary = metrics_service.summary(None)
    assert summary["scans"] == 3
    assert summary["routes"] == {"fast": 1, "cache": 1, "blocked": 1}
    assert summary["cache_hit_pct"] == 33.3
    assert summary["guardrails"]["clip_not_food"] == 1
    assert summary["latency_ms"]["p50"] is not None


def test_admin_metrics_needs_admin(client, user_headers, admin_headers):
    assert client.get("/admin/metrics", headers=user_headers).status_code == 403
    body = client.get("/admin/metrics", headers=admin_headers).json()
    assert {"window", "all_time", "caches", "food_gate"} <= body.keys()
