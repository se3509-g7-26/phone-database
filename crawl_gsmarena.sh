#!/usr/bin/env bash
# Resume the GSMArena crawl until a run completes. ingest.py exits 1 when the
# rate limit outlasts its retries; wait and resume. Stop after three runs in a
# row that save nothing, so a persistent block or a bad page is not hammered.
set -u
cd "$(dirname "$0")"
python=${PYTHON:-.venv/bin/python}
cooldown=${COOLDOWN_SECONDS:-900}
idle=0
saved() { find data/raw/gsmarena -name '*.meta.json' 2>/dev/null | wc -l; }
while :; do
    before=$(saved)
    "$python" ingest.py --sources gsmarena --resume
    status=$?
    after=$(saved)
    echo "$(date -u +%FT%TZ) ingest.py exited $status; $((after - before)) new responses, $after in total"
    [ "$status" -eq 1 ] || exit "$status"
    if [ "$after" -gt "$before" ]; then idle=0; else idle=$((idle + 1)); fi
    if [ "$idle" -ge 3 ]; then
        echo "Three runs without progress; stopping. Check the FAILED lines above." >&2
        exit 1
    fi
    echo "Resuming in $((cooldown << idle)) seconds"
    sleep "$((cooldown << idle))"
done
