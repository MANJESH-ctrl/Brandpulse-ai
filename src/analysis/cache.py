# src/analysis/cache.py
from datetime import date
from typing import Optional


_cache: dict[str, dict] = {}


def _key(brand_name: str) -> str:
    return f"{brand_name.lower().strip()}:{date.today().isoformat()}"


def get_cached(brand_name: str) -> Optional[dict]:
    return _cache.get(_key(brand_name))


def set_cached(brand_name: str, result: dict) -> None:
    _cache[_key(brand_name)] = result


def clear_cache() -> None:
    _cache.clear()
