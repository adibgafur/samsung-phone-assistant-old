"""Step 1 - scrape Samsung phone specs from GSMArena with requests + BeautifulSoup.

Usage:
    python -m scraper.gsmarena --out data/scraped_phones.json

GSMArena rate-limits aggressively (HTTP 429). The scraper sleeps between requests
and backs off on 429. If you get blocked, wait ~30 min or run from another network.
"""
import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.gsmarena.com/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_PHONES = [
    "Samsung Galaxy S21",
    "Samsung Galaxy S21 Ultra",
    "Samsung Galaxy S22",
    "Samsung Galaxy S22 Ultra",
    "Samsung Galaxy S23",
    "Samsung Galaxy S23 Ultra",
    "Samsung Galaxy S24",
    "Samsung Galaxy S24 Ultra",
    "Samsung Galaxy A54",
    "Samsung Galaxy A34",
    "Samsung Galaxy Z Fold5",
    "Samsung Galaxy Z Flip5",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+ ]", " ", text.lower())).strip()


class GSMArenaScraper:
    def __init__(self, delay: float = 4.0, retries: int = 4):
        self.delay = delay
        self.retries = retries
        self.http = requests.Session()
        self.http.headers.update(HEADERS)

    def _get(self, url: str, params: dict | None = None) -> str:
        for attempt in range(1, self.retries + 1):
            resp = self.http.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                time.sleep(self.delay)  # be polite
                return resp.text
            if resp.status_code == 429:
                wait = 30 * attempt
                print(f"  429 rate-limited, sleeping {wait}s (attempt {attempt}/{self.retries})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"Gave up fetching {url}")

    def find_phone_url(self, name: str) -> str | None:
        """Search GSMArena and return the page URL of the best-matching phone."""
        html = self._get(BASE + "res.php3", params={"sSearch": name})
        soup = BeautifulSoup(html, "lxml")
        results = soup.select("div.makers li a")
        if not results:
            return None
        target = _norm(name)
        for a in results:
            if _norm(a.get_text(" ")) == target:
                return BASE + a["href"]
        return BASE + results[0]["href"]  # fall back to top hit

    @staticmethod
    def parse_phone(html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        title = soup.select_one("h1.specs-phone-name-title")
        if title is None:
            raise ValueError("Phone title not found - page layout changed or request blocked")
        img = soup.select_one(".specs-photo-main img")

        specs: dict[str, dict[str, str]] = {}
        for table in soup.select("#specs-list table"):
            th = table.select_one("th")
            if th is None:
                continue
            category = th.get_text(strip=True)
            rows: dict[str, str] = specs.setdefault(category, {})
            last_key = None
            for tr in table.select("tr"):
                ttl, nfo = tr.select_one("td.ttl"), tr.select_one("td.nfo")
                if nfo is None:
                    continue
                key = ttl.get_text(" ", strip=True) if ttl else ""
                value = nfo.get_text(" ", strip=True)
                if not key and last_key:  # continuation row of the previous key
                    rows[last_key] += "; " + value
                else:
                    key = key or "Info"
                    rows[key] = rows[key] + "; " + value if key in rows else value
                    last_key = key
        return {
            "name": title.get_text(strip=True),
            "url": url,
            "image_url": img["src"] if img else None,
            "specs": specs,
        }

    def scrape(self, names: list[str]) -> list[dict]:
        phones = []
        for name in names:
            print(f"Scraping {name} ...")
            try:
                url = self.find_phone_url(name)
                if not url:
                    print("  not found, skipping")
                    continue
                phones.append(self.parse_phone(self._get(url), url))
            except Exception as exc:  # keep going if one phone fails
                print(f"  failed: {exc}")
        return phones


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/scraped_phones.json")
    ap.add_argument("--phones", nargs="*", default=DEFAULT_PHONES)
    ap.add_argument("--delay", type=float, default=4.0)
    args = ap.parse_args()

    phones = GSMArenaScraper(delay=args.delay).scrape(args.phones)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(phones, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(phones)} phones to {out}")


if __name__ == "__main__":
    main()
