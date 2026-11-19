"""Helpers that turn GSMArena's free-text spec strings into numbers."""
import re

Specs = dict[str, dict[str, str]]


def _get(specs: Specs, category: str, key: str) -> str:
    return specs.get(category, {}).get(key, "") or ""


def battery_mah(specs: Specs) -> int | None:
    m = re.search(r"(\d{3,5})\s*mAh", _get(specs, "Battery", "Type"), re.I)
    return int(m.group(1)) if m else None


def display_inches(specs: Specs) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*inches", _get(specs, "Display", "Size"), re.I)
    return float(m.group(1)) if m else None


def ram_gb(specs: Specs) -> int | None:
    values = re.findall(r"(\d+)\s*GB RAM", _get(specs, "Memory", "Internal"), re.I)
    return max(map(int, values)) if values else None


def price(specs: Specs) -> tuple[float, str, str] | None:
    """Return (amount, currency, raw) from the Misc > Price row, or None."""
    raw = _get(specs, "Misc", "Price")
    m = re.search(r"(\$|€|£)\s*([\d,]+(?:\.\d+)?)", raw)
    if m:
        cur = {"$": "USD", "€": "EUR", "£": "GBP"}[m.group(1)]
        return float(m.group(2).replace(",", "")), cur, raw
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(USD|EUR|GBP|INR)", raw)
    if m:
        return float(m.group(1).replace(",", "")), m.group(2), raw
    return None


def announced(specs: Specs) -> str | None:
    return _get(specs, "Launch", "Announced") or None
