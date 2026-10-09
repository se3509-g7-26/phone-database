#!/usr/bin/env python3
"""Show GSMArena crawl progress: pages saved, recent pace, ETA and log health.

Uses only the standard library, so the system python3 can run it.
"""

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WINDOW = 600  # seconds of recent saves used for the pace estimate

inventory = max((ROOT / "data" / "discovery").glob("*_gsmarena_model_urls.txt"))
wanted = set(inventory.read_text(encoding="utf-8").split())
saved, recent, now = set(), 0, time.time()
for meta in (ROOT / "data" / "raw" / "gsmarena").glob("*.meta.json"):
    url = json.loads(meta.read_text(encoding="utf-8"))["url"]
    url = url.replace("://m.gsmarena.com/", "://www.gsmarena.com/", 1)
    if url in wanted and url not in saved:
        saved.add(url)
        recent += now - meta.stat().st_mtime < WINDOW

log = max((ROOT / "logs").glob("crawl-*.log"), default=None)
text = log.read_text(encoding="utf-8", errors="replace") if log else ""
lines = text.splitlines()
# Anchored: the tmux server's own command line also names the script.
running = subprocess.run(["pgrep", "-f", r"^bash \./crawl_gsmarena\.sh"],
                         capture_output=True).returncode == 0

if "ingest.py exited 0" in text:
    state = "FINISHED"
elif running:
    state = "running (watch it live: tmux attach -t phone-crawl, leave with Ctrl+B then D)"
else:
    state = "STOPPED - check the log below; it resumes where it left off when restarted"
done, total = len(saved), len(wanted)
print(f"Crawl:       {state}")
if state.startswith("STOPPED"):
    print("Restart:     cd ~/projects/phone-database && tmux new-session -d -s phone-crawl "
          "\"PYTHONUNBUFFERED=1 ./crawl_gsmarena.sh 2>&1 | tee -a logs/crawl-$(date -u +%Y%m%dT%H%M%SZ).log\"")
print(f"Phone pages: {done:,} / {total:,} ({100 * done / total:.1f}%)")
if running and recent:
    pace = recent / (WINDOW / 60)
    left = (total - done) / pace * 60
    finish = time.strftime("%a %d %b %H:%M", time.localtime(now + left))
    print(f"Pace:        {pace:.1f} pages/min over the last {WINDOW // 60} min; "
          f"about {left / 3600:.1f} h left, done around {finish}")
if log:
    print(f"Log:         {log.relative_to(ROOT)}: {text.count('slowdown')} slow-downs, "
          f"{text.count('FAILED')} failures, {text.count('ingest.py exited')} restarts")
    print(f"Last line:   {lines[-1] if lines else '(empty)'}")
