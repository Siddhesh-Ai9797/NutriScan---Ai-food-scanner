"""
Small in-memory caches so the same work is not paid for twice.

photo_cache: keyed by the SHA-256 of the cleaned photo. A re-upload, a double
tap, or a retry after a slow network gets the earlier result without another
GPT-4o call. Only the analysis is cached, never the user's S3 link.

name_cache: keyed by a normalised food name, for the typed nutrition lookup.

The app runs on one Railway replica, so process memory is enough. Entries
expire after a while and the oldest are dropped when a cache is full.
"""
import hashlib
import os
import re
import threading
import time
from collections import OrderedDict
from copy import deepcopy


class TTLCache:
    def __init__(self, max_items: int, ttl_seconds: float):
        self.max_items = max_items
        self.ttl = ttl_seconds
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        with self._lock:
            entry = self._data.get(key)
            if entry is None or entry[0] < time.time():
                if entry is not None:
                    del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return deepcopy(entry[1])

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = (time.time() + self.ttl, deepcopy(value))
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict:
        with self._lock:
            size = len(self._data)
        lookups = self.hits + self.misses
        return {
            "size"   : size,
            "hits"   : self.hits,
            "misses" : self.misses,
            "hit_pct": round(100 * self.hits / lookups, 1) if lookups else None,
        }


CACHE_ON = os.getenv("CACHE", "on").lower() != "off"

photo_cache = TTLCache(
    max_items   = int(os.getenv("PHOTO_CACHE_SIZE", "2000")),
    ttl_seconds = float(os.getenv("PHOTO_CACHE_TTL_HOURS", "24")) * 3600,
)
name_cache = TTLCache(
    max_items   = int(os.getenv("NAME_CACHE_SIZE", "5000")),
    ttl_seconds = float(os.getenv("NAME_CACHE_TTL_HOURS", "168")) * 3600,
)


def photo_key(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def name_key(food_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", food_name.lower()).strip()
