# M2 evidence

The database is rebuilt from the local M1 responses retrieved between
2026-10-09 and 2026-10-11 (UTC). It is stored at `data/phones.db` and is not
committed. None of these commands fetch data.

Both full loads completed. The second load added zero rows to every table.
All six required checks plus the foreign-key and STRICT-table checks passed;
the idempotence and atomicity checks compared complete contents as well as
counts. All 26 regression tests passed.

| File | Evidence |
| --- | --- |
| `key-audit.json` | Proposed identifiers and references tested directly against raw files |
| `load-first.txt` | Full database build from an empty database |
| `load-second.txt` | Second full load, including per-table row-count changes |
| `checks.txt` | Required constraint, idempotence and atomicity checks on a temporary database copy |
| `tests.txt` | 26 offline regression tests covering ingestion and M2 |
| `parser-check.txt` | Independent comparison against BeautifulSoup: 100 model pages and 4,118 specification cells |
| `price-coverage.txt` | Output of `sql/queries/price_coverage.sql` |

Rebuild and capture the required submission output from the repository root:

```powershell
.\.venv\Scripts\python.exe src/profile_keys.py > docs/m2/key-audit.json
.\.venv\Scripts\python.exe src/load.py > docs/m2/load-first.txt 2>&1
.\.venv\Scripts\python.exe src/load.py > docs/m2/load-second.txt 2>&1
.\.venv\Scripts\python.exe src/checks.py > docs/m2/checks.txt 2>&1
.\.venv\Scripts\python.exe src/report.py > docs/m2/price-coverage.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -q > docs/m2/tests.txt 2>&1
```

For a first-build log, use a new `--db` path when a derived database already
exists. Run reporting after loading finishes: a loader holds a write transaction
until the complete batch commits. Checks back up the source with a read-only
connection and perform all mutations on a temporary copy.

First-build totals: 15,565 files, 14,877 models, 14,881 model snapshots,
598,283 specification cells, 2,539 Wikidata items, 2,566 model-item links,
1,806 articles and 1,806 article revisions. Quarantine contains the legacy
slowdown response and ten unresolved Wikidata phone references. The 12,045
empty specification cells become NULL. One HTML page has three invalid UTF-8
bytes outside the modeled fields; its valid model data is retained unchanged.
