"""
Output guardrail, OpenAI wrapper costs, and the typed-name cache.
"""
import asyncio

import pytest

from services import metrics_service, nutrition_service, openai_client, ood_service
from services.guardrail_service import NotFoodPhoto, check_per_100g, check_plate, FoodGate


def _item(**overrides):
    item = {"food": "dal", "weight_grams": 200, "calories": 230, "protein": 12, "carbs": 30, "fat": 6}
    item.update(overrides)
    return item


# ── check_plate ───────────────────────────────────────────────────────────
def test_clean_plate_passes_untouched():
    plate, flags = check_plate({"items": [_item()], "total_calories": 230, "primary_food": "dal"})
    assert flags == []
    assert plate["total_calories"] == 230
    assert plate["primary_food"] == "dal"


def test_totals_are_rebuilt_from_items():
    data = {"items": [_item(), _item(food="rice", calories=260, protein=5, carbs=57, fat=0.5)],
            "total_calories": 900}
    plate, flags = check_plate(data)
    assert plate["total_calories"] == 490
    assert "totals_recomputed" in flags


def test_not_food_answer_raises():
    with pytest.raises(NotFoodPhoto):
        check_plate({"is_food": False, "items": []})


def test_negative_numbers_are_clamped():
    plate, flags = check_plate({"items": [_item(fat=-5)]})
    assert plate["items"][0]["fat"] == 0
    assert "negative_value" in flags


def test_impossible_density_item_is_dropped():
    data = {"items": [_item(), _item(food="salad", weight_grams=50, calories=2000, protein=1, carbs=2, fat=1)]}
    plate, flags = check_plate(data)
    assert [i["food"] for i in plate["items"]] == ["dal"]
    assert "impossible_density" in flags


def test_calories_below_macros_are_raised_to_match():
    plate, flags = check_plate({"items": [_item(calories=50, protein=20, carbs=40, fat=10)]})
    assert plate["items"][0]["calories"] == 330
    assert "calories_below_macros" in flags


def test_huge_plate_is_rejected():
    data = {"items": [_item(weight_grams=2000, calories=5000, protein=100, carbs=600, fat=200),
                      _item(weight_grams=2000, calories=5000, protein=100, carbs=600, fat=200)]}
    plate, flags = check_plate(data)
    assert plate is None
    assert "plate_too_large" in flags


def test_strings_and_html_are_cleaned():
    plate, _ = check_plate({"items": [_item(food="<b>paneer</b> tikka", calories="300")]})
    assert plate["items"][0]["food"] == "paneer tikka"
    assert plate["items"][0]["calories"] == 300


def test_garbage_returns_none():
    assert check_plate(None)[0] is None
    assert check_plate({"items": "lots"})[0] is None
    assert check_plate({"items": [{"food": "x"}]})[0] is None


def test_per_100g_checks():
    assert check_per_100g(89, 1.1, 22.8, 0.3) == []
    assert "impossible_density" in check_per_100g(1200, 0, 0, 100)
    assert "macros_over_100g" in check_per_100g(500, 60, 60, 10)


def test_food_gate_fails_open_when_not_loaded():
    gate = FoodGate()
    assert gate.check(b"anything") == (True, None)


# ── OpenAI wrapper records cost ───────────────────────────────────────────
class _FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def _fake_openai(monkeypatch, status=200, content='{"ok": true}', usage=None):
    calls = []

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            calls.append(json)
            body = {"choices": [{"message": {"content": content}}],
                    "usage": usage or {"prompt_tokens": 1000, "completion_tokens": 200}}
            return _FakeResponse(status, body)

    monkeypatch.setattr(openai_client.httpx, "AsyncClient", FakeClient)
    return calls


def test_wrapper_prices_each_call(monkeypatch):
    _fake_openai(monkeypatch)
    asyncio.run(openai_client.chat_completion({"model": "gpt-4o"}, feature="scan"))
    asyncio.run(openai_client.chat_completion({"model": "gpt-4o-mini"}, feature="scan"))
    summary = metrics_service.summary(None)
    assert summary["by_model"]["gpt-4o"]["cost_usd"] == pytest.approx(0.0045, abs=1e-4)
    assert summary["by_model"]["gpt-4o-mini"]["cost_usd"] == pytest.approx(0.00027, abs=1e-4)


def test_wrapper_returns_none_on_api_error(monkeypatch):
    _fake_openai(monkeypatch, status=500)
    assert asyncio.run(openai_client.chat_completion({"model": "gpt-4o"}, feature="scan")) is None
    assert metrics_service.summary(None)["by_model"]["gpt-4o"]["errors"] == 1


def test_detect_all_foods_runs_output_guardrail(monkeypatch):
    content = '```json\n{"is_food": true, "primary_food": "dal", "hint_correct": true, ' \
              '"items": [{"food": "dal", "weight_grams": 200, "calories": 230, "protein": 12, "carbs": 30, "fat": 6}], ' \
              '"total_calories": 999}\n```'
    calls = _fake_openai(monkeypatch, content=content)
    plate, flags = asyncio.run(ood_service.detect_all_foods(b"img", "dal", model="gpt-4o-mini", detail="low"))
    assert plate["total_calories"] == 230
    assert "totals_recomputed" in flags
    assert calls[0]["model"] == "gpt-4o-mini"
    assert calls[0]["messages"][0]["content"][0]["image_url"]["detail"] == "low"


# ── Typed-name cache ──────────────────────────────────────────────────────
def test_name_lookup_is_cached(monkeypatch):
    calls = _fake_openai(monkeypatch, content='{"is_food": true, "food_name": "banana", '
                                              '"calories": 89, "protein": 1.1, "carbs": 22.8, "fat": 0.3}')
    first = asyncio.run(nutrition_service.get_nutrition("Banana"))
    second = asyncio.run(nutrition_service.get_nutrition("  banana "))
    assert first == second
    assert len(calls) == 1
    assert metrics_service.summary(None)["name_cache_hits"] == 1


def test_not_food_names_are_cached(monkeypatch):
    calls = _fake_openai(monkeypatch, content='{"is_food": false}')
    for _ in range(2):
        with pytest.raises(nutrition_service.NotAFoodError):
            asyncio.run(nutrition_service.get_nutrition("asdfgh"))
    assert len(calls) == 1


def test_impossible_lookup_is_not_cached(monkeypatch):
    calls = _fake_openai(monkeypatch, content='{"is_food": true, "calories": 2000, "protein": 0, "carbs": 0, "fat": 0}')
    assert asyncio.run(nutrition_service.get_nutrition("butter")) is None
    assert asyncio.run(nutrition_service.get_nutrition("butter")) is None
    assert len(calls) == 2
