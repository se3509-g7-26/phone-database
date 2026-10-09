"""Fetch unmodified responses from GSMArena, Wikidata and Wikipedia.

Run from the repository root with ``python ingest.py``. A trial run can use
``--max-models 10``; the default fetches every discovered model detail page.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
GSM = "https://www.gsmarena.com/"
WDQS = "https://query.wikidata.org/sparql"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
BRAND = re.compile(r"^[a-z0-9_-]+-phones-(\d+)\.php$", re.I)
PAGE = re.compile(r"^[a-z0-9_-]+-phones-f-(\d+)-0-p\d+\.php$", re.I)
MODEL = re.compile(r"^[a-z0-9_-]+-(\d+)\.php$", re.I)


class IngestError(RuntimeError):
    pass


def anchors(html: bytes, base: str, selector: str) -> set[str]:
    result = set()
    for anchor in BeautifulSoup(html, "html.parser").select(selector):
        if anchor.get("href"):
            url = urljoin(base, anchor["href"])
            if urlparse(url).netloc == "www.gsmarena.com":
                result.add(url)
    return result


class Collector:
    def __init__(self, agent: str, delay: float, timeout: float, retries: int,
                 resume: bool = False):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = agent
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.last_request = 0.0
        self.counts: Counter[str] = Counter()
        self.failures: list[str] = []
        self.cached: dict[str, Path] = {}
        self.reused = 0
        if resume:
            for meta in sorted((RAW / "gsmarena").glob("*.meta.json")):
                try:
                    info = json.loads(meta.read_text(encoding="utf-8"))
                    path = meta.with_name(meta.name.replace(".meta.json", ".html"))
                    if path.is_file() and path.stat().st_size == info["bytes"]:
                        self.cached[info["url"]] = path
                        parsed = urlparse(info["url"])
                        if parsed.netloc == "m.gsmarena.com":
                            self.cached[parsed._replace(netloc="www.gsmarena.com").geturl()] = path
                except (OSError, ValueError, KeyError, TypeError):
                    continue

    def fetch(self, source: str, url: str, *, params: dict | None = None,
              kind: str = "html") -> bytes:
        if source == "gsmarena":
            # www answers non-browser clients with a 302 to the mobile site;
            # asking m.gsmarena.com directly halves the rate-limited requests.
            url = url.replace("://www.gsmarena.com/", "://m.gsmarena.com/", 1)
        request_url = requests.Request("GET", url, params=params).prepare().url
        if source == "gsmarena" and request_url in self.cached:
            body = self.cached[request_url].read_bytes()
            if b"<" in body and b"please slow down" not in body.lower():
                self.reused += 1
                print(f"[gsmarena] Reusing {request_url}", flush=True)
                return body
        for attempt in range(self.retries + 1):
            remaining = self.delay - (time.monotonic() - self.last_request)
            if remaining > 0:
                time.sleep(remaining)
            print(f"[{source} #{self.counts[source] + 1}] GET {request_url} "
                  f"(attempt {attempt + 1}/{self.retries + 1})", flush=True)
            try:
                self.last_request = time.monotonic()
                response = self.session.get(
                    url, params=params, timeout=self.timeout,
                    headers={"Accept": "application/sparql-results+json"}
                    if source == "wikidata" else None)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == self.retries:
                    raise IngestError(f"{source}: network failure: {url}: {exc}") from exc
                pause = min(60, 2 ** attempt)
                print(f"[{source}] {type(exc).__name__}; retrying in {pause}s", flush=True)
                time.sleep(pause)
                continue
            if response.status_code in (401, 403):
                raise IngestError(f"{source}: HTTP {response.status_code}: {response.url}; stopping without retry")
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt == self.retries:
                    raise IngestError(f"{source}: HTTP {response.status_code} after {attempt + 1} attempts: {response.url}")
                retry_after = response.headers.get("Retry-After", "")
                pause = int(retry_after) if retry_after.isdigit() else 2 ** attempt
                pause = min(120, pause)
                print(f"[{source}] HTTP {response.status_code}; retrying in {pause}s", flush=True)
                time.sleep(pause)
                continue
            if not response.ok:
                raise IngestError(f"{source}: HTTP {response.status_code}: {response.url}")
            body = response.content
            if source == "gsmarena" and b"please slow down" in body.lower():
                if attempt == self.retries:
                    raise IngestError(f"GSMArena: rate limit after {attempt + 1} attempts: {response.url}")
                print("[gsmarena] Server requested a slowdown; retrying in 60s", flush=True)
                time.sleep(60)
                continue
            content_type = response.headers.get("Content-Type", "").lower()
            if not body.strip():
                raise IngestError(f"{source}: empty response: {response.url}")
            if kind == "json" and "json" not in content_type:
                raise IngestError(f"{source}: expected JSON, got {content_type}: {response.url}")
            if kind == "html" and "html" not in content_type:
                raise IngestError(f"{source}: expected HTML, got {content_type}: {response.url}")
            self.save(source, response.url, body, kind)
            print(f"[{source} #{self.counts[source]}] Saved {len(body):,} bytes "
                  f"to {RAW / source}", flush=True)
            return body
        raise AssertionError("unreachable retry state")

    def save(self, source: str, url: str, body: bytes, kind: str) -> None:
        folder = RAW / source
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        stem = f"{stamp}_{self.counts[source] + 1:06d}"
        # Exclusive creation prevents accidental replacement on later runs.
        with (folder / f"{stem}.{kind}").open("xb") as file:
            file.write(body)
        with (folder / f"{stem}.meta.json").open("x", encoding="utf-8") as file:
            json.dump({"source": source, "url": url, "retrieved_at_utc": stamp,
                       "bytes": len(body)}, file, indent=2)
        self.counts[source] += 1


def ingest_gsm(c: Collector, max_models: int | None,
               max_brands: int | None) -> int:
    index = c.fetch("gsmarena", urljoin(GSM, "makers.php3"))
    brands = sorted(u for u in anchors(index, GSM, "a[href]")
                    if BRAND.fullmatch(Path(urlparse(u).path).name))
    if not brands:
        raise IngestError("GSMArena: brand index has no recognizable brand links")
    print(f"GSMArena: {len(brands)} brands discovered", flush=True)
    if max_brands:
        brands = brands[:max_brands]
    models: set[str] = set()
    for brand in brands:
        brand_path = Path(urlparse(brand).path).name
        brand_id = BRAND.fullmatch(brand_path).group(1)
        pending = [brand]
        visited: set[str] = set()
        while pending:
            url = pending.pop(0)
            if url in visited:
                continue
            visited.add(url)
            html = c.fetch("gsmarena", url)
            # Some brand pages no longer place model anchors under .makers.
            # Accept all model-shaped links, including subbrands such as Acerone.
            found = {u for u in anchors(html, url, "a[href]")
                     if (path := Path(urlparse(u).path).name)
                     and MODEL.fullmatch(path)
                     and not BRAND.fullmatch(path)
                     and not PAGE.fullmatch(path)
                     and not any(tag in path for tag in ("-review-", "-news-", "-opinions-"))}
            if not found:
                raise IngestError(f"GSMArena: no phone links on {url}; inspect saved HTML")
            models.update(found)
            pages = {u for u in anchors(html, url, "a[href]")
                     if (m := PAGE.fullmatch(Path(urlparse(u).path).name))
                     and m.group(1) == brand_id}
            pending.extend(sorted(pages - visited - set(pending)))
        print(f"GSMArena: {len(visited)} pages for {brand}; {len(models)} distinct models so far", flush=True)
    # A URL inventory is an ingestion checkpoint; it is not a cleaned phone table.
    inventory = ROOT / "data" / "discovery"
    inventory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with (inventory / f"{stamp}_gsmarena_model_urls.txt").open("x", encoding="utf-8") as file:
        file.write("\n".join(sorted(models)) + "\n")
    chosen = sorted(models)[:max_models] if max_models else sorted(models)
    for number, url in enumerate(chosen, 1):
        html = c.fetch("gsmarena", url)
        soup = BeautifulSoup(html, "html.parser")
        if not soup.select_one("h1") or not soup.select_one("[data-spec]"):
            raise IngestError(f"GSMArena: unexpected model page: {url}")
        if number % 100 == 0:
            print(f"GSMArena: fetched {number}/{len(chosen)} model details", flush=True)
    return len(chosen)


def ingest_wikimedia(c: Collector, max_pages: int | None,
                     page_size: int = 500, max_articles: int | None = None) -> tuple[int, int]:
    # Wikidata P4723 is the GSMArena phone ID; QIDs link to Wikipedia pages.
    entities: set[str] = set()
    articles: set[str] = set()
    offset = 0
    while True:
        query = ("SELECT ?phone ?gsmId ?article WHERE { ?phone wdt:P4723 ?gsmId. "
                 "OPTIONAL { ?article schema:about ?phone; "
                 "schema:isPartOf <https://en.wikipedia.org/>. } } "
                 f"ORDER BY ?phone LIMIT {page_size} OFFSET {offset}")
        body = c.fetch("wikidata", WDQS, params={"query": query, "format": "json"}, kind="json")
        try:
            rows = json.loads(body)["results"]["bindings"]
            if not isinstance(rows, list):
                raise TypeError("bindings is not a list")
            for row in rows:
                entities.add(row["phone"]["value"])
                if "article" in row:
                    articles.add(row["article"]["value"])
        except (ValueError, KeyError, TypeError) as exc:
            raise IngestError(f"Wikidata: unexpected result at offset {offset}") from exc
        if len(rows) < page_size:
            break
        offset += page_size
        if max_pages is not None and offset // page_size >= max_pages:
            break
    if not entities:
        raise IngestError("Wikidata: no entities with GSMArena IDs")
    titles = sorted({unquote(urlparse(url).path.removeprefix("/wiki/")).replace("_", " ")
                     for url in articles if urlparse(url).netloc == "en.wikipedia.org"})
    if max_articles is not None:
        titles = titles[:max_articles]
    for start in range(0, len(titles), 25):
        body = c.fetch("wikipedia", WIKIPEDIA, params={
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "revisions|pageprops", "rvprop": "timestamp|content",
            "rvslots": "main", "titles": "|".join(titles[start:start + 25])}, kind="json")
        try:
            pages = json.loads(body)["query"]["pages"]
            if not pages:
                raise ValueError("no pages")
        except (ValueError, KeyError, TypeError) as exc:
            raise IngestError("Wikipedia: empty or unexpected page response") from exc
    return len(entities), len(titles)


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-models", type=int, help="Fetch only N model details for a trial run")
    parser.add_argument("--max-brands", type=int, help="Discover only N brands for a trial run")
    parser.add_argument("--max-wikidata-pages", type=int, help="Fetch only N SPARQL pages for a trial run")
    parser.add_argument("--wikidata-page-size", type=int, default=500)
    parser.add_argument("--max-wikipedia-articles", type=int)
    parser.add_argument("--resume", action="store_true",
                        help="Reuse locally saved GSMArena responses")
    parser.add_argument("--sources", nargs="+", choices=("gsmarena", "wikidata"),
                        default=["gsmarena", "wikidata"],
                        help="Wikidata also fetches linked Wikipedia articles")
    args = parser.parse_args()
    if any(x is not None and x < 1 for x in
           (args.max_models, args.max_brands, args.max_wikidata_pages,
            args.wikidata_page_size, args.max_wikipedia_articles)):
        parser.error("trial limits must be positive")
    if args.wikidata_page_size > 500:
        parser.error("Wikidata page size must be at most 500")
    agent = os.environ.get("PHONE_DATA_USER_AGENT", "").strip()
    if not agent or "your-email@example.com" in agent.lower() or "YOUR_EMAIL" in agent:
        print("Set PHONE_DATA_USER_AGENT with your real contact address; see .env.example.", file=sys.stderr)
        return 2
    try:
        delay = float(os.environ.get("PHONE_DATA_DELAY_SECONDS", "1"))
        timeout = float(os.environ.get("PHONE_DATA_TIMEOUT_SECONDS", "20"))
        retries = int(os.environ.get("PHONE_DATA_RETRIES", "4"))
        if not math.isfinite(delay) or not math.isfinite(timeout) or delay < 0 or timeout <= 0 or not 0 <= retries <= 10:
            raise ValueError("out of range")
    except ValueError:
        print("Invalid delay, timeout or retry setting.", file=sys.stderr)
        return 2
    c = Collector(agent, delay, timeout, retries, resume=args.resume)
    for source in dict.fromkeys(args.sources):
        try:
            if source == "gsmarena":
                models = ingest_gsm(c, args.max_models, args.max_brands)
                print(f"Fetched {models} GSMArena model details", flush=True)
            else:
                entities, articles = ingest_wikimedia(
                    c, args.max_wikidata_pages, args.wikidata_page_size,
                    args.max_wikipedia_articles)
                print(f"Discovered {entities} Wikidata entities; requested {articles} Wikipedia articles", flush=True)
        except (IngestError, requests.RequestException) as exc:
            c.failures.append(str(exc))
    c.session.close()
    print("Raw responses saved: " + ", ".join(
        f"{name}={c.counts[name]}" for name in ("gsmarena", "wikidata", "wikipedia")))
    if args.resume:
        print(f"GSMArena responses reused: {c.reused}")
    for failure in c.failures:
        print(f"FAILED: {failure}", file=sys.stderr)
    return 1 if c.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
