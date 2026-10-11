#!/usr/bin/env python3
"""Show GSMArena crawl progress: pages saved, recent pace, ETA and log health.

Uses only the standard library, so the system python3 can run it.
"""

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
WINDOW = 600  # seconds of recent saves used for the pace estimate

inventory = max((ROOT / "data" / "discovery").glob("*_gsmarena_model_urls.txt"))
wanted = set(inventory.read_text(encoding="utf-8").split())
saved, recent, now = set(), 0, time.time()
for meta in (RAW / "gsmarena").glob("*.meta.json"):
    url = json.loads(meta.read_text(encoding="utf-8"))["url"]
    url = url.replace("://m.gsmarena.com/", "://www.gsmarena.com/", 1)
    if url in wanted and url not in saved:
        saved.add(url)
        recent += now - meta.stat().st_mtime < WINDOW

# ingest.py fetches the phones that Wikidata links to (P4723) first.
linked = set()
for path in (RAW / "wikidata").glob("*.json"):
    if not path.name.endswith(".meta.json"):
        linked.update(row["gsmId"]["value"]
                      for row in json.loads(path.read_bytes())["results"]["bindings"])
first = {url for url in wanted if url.rsplit("-", 1)[1].removesuffix(".php") in linked}

log = max((ROOT / "logs").glob("crawl-*.log"), default=None)
text = log.read_text(encoding="utf-8", errors="replace") if log else ""
lines = text.splitlines()
# Anchored: the tmux server's own command line also names the script.
running = subprocess.run(["pgrep", "-f", r"^bash \S*crawl_gsmarena\.sh"],
                         capture_output=True).returncode == 0

if "ingest.py exited 0" in text:
    state = "FINISHED"
elif running:
    state = "running (watch it live: tmux attach -t phone-crawl, leave with Ctrl+B then D)"
else:
    state = "STOPPED - check the log below; it resumes where it left off when restarted"
pace = recent / (WINDOW / 60) if running and recent else 0


def progress(label: str, done: int, total: int) -> None:
    line = f"{label:<20}{done:,} / {total:,} ({100 * done / total:.1f}%)"
    if pace and done < total:
        seconds = (total - done) / pace * 60
        finish = time.strftime("%a %d %b %H:%M", time.localtime(now + seconds))
        line += f"; about {seconds / 3600:.1f} h left, done around {finish}"
    print(line)


print(f"{'Crawl:':<20}{state}")
if state.startswith("STOPPED"):
    print(f"{'Restart:':<20}cd {ROOT} && mkdir -p logs && tmux new-session -d -s phone-crawl "
          "\"PYTHONUNBUFFERED=1 scripts/crawl_gsmarena.sh 2>&1 "
          "| tee -a logs/crawl-$(date -u +%Y%m%dT%H%M%SZ).log\"")
progress("Wikidata-linked:", len(saved & first), len(first))
progress("All phone pages:", len(saved), len(wanted))
if pace:
    print(f"{'Pace:':<20}{pace:.1f} pages/min over the last {WINDOW // 60} min")
if log:
    print(f"{'Log:':<20}{log.relative_to(ROOT)}: {text.count('slowdown')} slow-downs, "
          f"{text.count('FAILED')} failures, {text.count('ingest.py exited')} restarts")
    print(f"{'Last line:':<20}{lines[-1] if lines else '(empty)'}")
