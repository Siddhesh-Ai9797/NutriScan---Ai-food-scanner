"""
Monitoring for NutriScan.

Every OpenAI call and every scan leaves a small record: which path it took,
how long each step took, how many tokens it used, what it cost, and whether a
guardrail stepped in. Records go to three places:

1. A JSON line in the server log (Railway keeps these).
2. A rolling in-memory window that powers /admin/metrics.
3. A DynamoDB table, when METRICS_TABLE is set, so numbers survive redeploys.

No user id, photo, or food text is stored: only counts, timings and costs.
"""
import contextvars
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from decimal import Decimal

logger = logging.getLogger("nutriscan.metrics")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# US dollars per 1 million tokens. Check OpenAI's pricing page if these change.
PRICES = {
    "gpt-4o"     : {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

WINDOW_SIZE   = 5000
METRICS_TABLE = os.getenv("METRICS_TABLE", "").strip()
RECORD_TTL_DAYS = 400


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICES.get(model)
    if not price:
        return 0.0
    return (prompt_tokens * price["input"] + completion_tokens * price["output"]) / 1_000_000


@dataclass
class ScanTrace:
    """Everything that happened during one photo scan."""
    endpoint     : str = "predict"
    route        : str = "pending"      # cache, fast, escalated, full, blocked, failed
    models       : list = field(default_factory=list)
    llm_calls    : int = 0
    tokens_in    : int = 0
    tokens_out   : int = 0
    cost_usd     : float = 0.0
    stage_ms     : dict = field(default_factory=dict)
    guardrails   : list = field(default_factory=list)
    cache_hit    : bool = False
    errors       : list = field(default_factory=list)
    started      : float = field(default_factory=time.perf_counter)

    def stage(self, name: str, started: float):
        self.stage_ms[name] = round((time.perf_counter() - started) * 1000, 1)

    def flag(self, rule: str):
        if rule not in self.guardrails:
            self.guardrails.append(rule)


_current_trace: contextvars.ContextVar = contextvars.ContextVar("scan_trace", default=None)

_lock = threading.Lock()
_scans: deque = deque(maxlen=WINDOW_SIZE)
_llm_calls: deque = deque(maxlen=WINDOW_SIZE)
_events: deque = deque(maxlen=WINDOW_SIZE)
_started_at = time.time()


def start_trace(endpoint: str = "predict") -> ScanTrace:
    trace = ScanTrace(endpoint=endpoint)
    _current_trace.set(trace)
    return trace


def current_trace() -> ScanTrace | None:
    return _current_trace.get()


def finish_trace(trace: ScanTrace, status_code: int = 200):
    record = {
        "type"       : "scan",
        "ts"         : time.time(),
        "endpoint"   : trace.endpoint,
        "route"      : trace.route,
        "models"     : trace.models,
        "llm_calls"  : trace.llm_calls,
        "tokens_in"  : trace.tokens_in,
        "tokens_out" : trace.tokens_out,
        "cost_usd"   : round(trace.cost_usd, 6),
        "total_ms"   : round((time.perf_counter() - trace.started) * 1000, 1),
        "stage_ms"   : trace.stage_ms,
        "guardrails" : trace.guardrails,
        "cache_hit"  : trace.cache_hit,
        "errors"     : trace.errors,
        "status_code": status_code,
    }
    with _lock:
        _scans.append(record)
    _emit(record)
    _current_trace.set(None)
    return record


def record_llm_call(feature: str, model: str, latency_ms: float, prompt_tokens: int,
                    completion_tokens: int, ok: bool, status: int | None = None):
    cost = cost_usd(model, prompt_tokens, completion_tokens)
    record = {
        "type"      : "llm",
        "ts"        : time.time(),
        "feature"   : feature,
        "model"     : model,
        "latency_ms": round(latency_ms, 1),
        "tokens_in" : prompt_tokens,
        "tokens_out": completion_tokens,
        "cost_usd"  : round(cost, 6),
        "ok"        : ok,
        "status"    : status,
    }
    with _lock:
        _llm_calls.append(record)

    trace = current_trace()
    if trace is not None:
        trace.llm_calls += 1
        trace.tokens_in += prompt_tokens
        trace.tokens_out += completion_tokens
        trace.cost_usd += cost
        trace.models.append(model)
        if not ok:
            trace.errors.append(f"{model}:{status}")
    _emit(record)
    return record


def record_event(kind: str, **fields):
    """Small one-off events: cache hits on name lookups, guardrail blocks outside scans."""
    record = {"type": "event", "kind": kind, "ts": time.time(), **fields}
    with _lock:
        _events.append(record)
    _emit(record)


# ── Output ────────────────────────────────────────────────────────────────
def _emit(record: dict):
    logger.info(json.dumps(record, separators=(",", ":")))
    if METRICS_TABLE:
        threading.Thread(target=_store, args=(record,), daemon=True).start()


_table = None


def _store(record: dict):
    """Best effort write to DynamoDB. Monitoring must never break a scan."""
    global _table
    try:
        if _table is None:
            import boto3
            _table = boto3.resource(
                "dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")
            ).Table(METRICS_TABLE)
        item = json.loads(json.dumps(record), parse_float=Decimal)
        item["pk"] = f"{record['type']}#{time.strftime('%Y-%m-%d', time.gmtime(record['ts']))}"
        item["sk"] = f"{record['ts']:.6f}#{uuid.uuid4().hex[:8]}"
        item["expires_at"] = int(record["ts"]) + RECORD_TTL_DAYS * 86400
        _table.put_item(Item=item)
    except Exception as e:  # noqa: BLE001
        logger.info(json.dumps({"type": "metrics_store_error", "error": type(e).__name__}))


# ── Summary for the admin page ────────────────────────────────────────────
def _percentile(values: list, pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def summary(hours: float | None = None) -> dict:
    cutoff = time.time() - hours * 3600 if hours else 0
    with _lock:
        scans = [s for s in _scans if s["ts"] >= cutoff]
        calls = [c for c in _llm_calls if c["ts"] >= cutoff]
        events = [e for e in _events if e["ts"] >= cutoff]

    photo_scans = [s for s in scans if s["endpoint"] == "predict"]
    total = len(photo_scans)
    routes: dict = {}
    for s in photo_scans:
        routes[s["route"]] = routes.get(s["route"], 0) + 1

    guardrails: dict = {}
    for s in photo_scans:
        for rule in s["guardrails"]:
            guardrails[rule] = guardrails.get(rule, 0) + 1
    for e in events:
        if e["kind"] == "guardrail":
            rule = e.get("rule", "other")
            guardrails[rule] = guardrails.get(rule, 0) + 1

    latencies = [s["total_ms"] for s in photo_scans if s["route"] != "blocked"]
    by_model: dict = {}
    for c in calls:
        m = by_model.setdefault(c["model"], {"calls": 0, "errors": 0, "cost_usd": 0.0, "latency": []})
        m["calls"] += 1
        m["errors"] += 0 if c["ok"] else 1
        m["cost_usd"] += c["cost_usd"]
        m["latency"].append(c["latency_ms"])
    for m in by_model.values():
        m["cost_usd"] = round(m["cost_usd"], 4)
        m["p50_ms"] = _percentile(m["latency"], 50)
        m["p95_ms"] = _percentile(m["latency"], 95)
        del m["latency"]

    by_feature: dict = {}
    for c in calls:
        f = by_feature.setdefault(c["feature"], {"calls": 0, "cost_usd": 0.0})
        f["calls"] += 1
        f["cost_usd"] = round(f["cost_usd"] + c["cost_usd"], 4)

    scan_cost = sum(s["cost_usd"] for s in photo_scans)
    name_cache_hits = sum(1 for e in events if e["kind"] == "name_cache_hit")
    errors = sum(1 for s in photo_scans if s["status_code"] >= 500 or s["route"] == "failed")

    def share(n: int) -> float | None:
        return round(100 * n / total, 1) if total else None

    return {
        "window_hours"     : hours,
        "since"            : max(cutoff, _started_at),
        "scans"            : total,
        "routes"           : routes,
        "cache_hit_pct"    : share(routes.get("cache", 0)),
        "blocked_pct"      : share(routes.get("blocked", 0)),
        "fast_path_pct"    : share(routes.get("fast", 0)),
        "escalated_pct"    : share(routes.get("escalated", 0)),
        "error_pct"        : share(errors),
        "guardrails"       : guardrails,
        "latency_ms"       : {"p50": _percentile(latencies, 50), "p95": _percentile(latencies, 95)},
        "scan_cost_usd"    : round(scan_cost, 4),
        "avg_cost_per_scan": round(scan_cost / total, 5) if total else None,
        "total_llm_cost_usd": round(sum(c["cost_usd"] for c in calls), 4),
        "by_model"         : by_model,
        "by_feature"       : by_feature,
        "name_cache_hits"  : name_cache_hits,
    }


def reset():
    """Test helper."""
    with _lock:
        _scans.clear()
        _llm_calls.clear()
        _events.clear()


def as_dict(trace: ScanTrace) -> dict:
    return asdict(trace)
