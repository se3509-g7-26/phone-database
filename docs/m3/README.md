# M3 evidence and group handoff

The implementation is uncommitted so the group can review and split its own work.
The report's investigator names and M2-feedback account are intentionally pending.
No commits, tag, push, or course submission have been performed.

Suggested review/commit work packages (assign members yourselves):

1. Investigation: `src/profile_m3.py`, `notebooks/m3_profile.ipynb`, notebook runner,
   aggregate findings, and mapping CSV review.
2. Cleaning: `sql/clean_schema.sql`, `src/clean_config.py`, `src/clean.py`,
   mapping decisions and resolved views.
3. Validation and integration: `src/validate.py`, regression tests, verification
   helper and saved outputs, report, README, and project-file integration.

Dependencies cross those boundaries: field rules feed profiling and cleaning;
the report quotes final outputs. Re-run integration after the group reviews changes.

## Reproduction

From the repository root with landed M1 responses and installed requirements:

```powershell
.\.venv\Scripts\python.exe src/load.py
.\.venv\Scripts\python.exe scripts/run_m3_profile.py
.\.venv\Scripts\python.exe scripts/verify_m3.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Or run `src/clean.py` twice and `src/validate.py` directly. Every tool accepts
`--db` except the notebook runner, which reads the optional `PHONE_M3_DB`
environment variable. The profile does not require a previously cleaned DB.
The notebook uses ordinary Python cells and also runs normally in Jupyter.
M3 adds no third-party runtime dependencies.

`clean-first.txt`, `clean-second.txt`, `validate.txt`, `verification.json`, and
`tests.txt` are saved evidence. `fresh-build-check.json` and `notebook-check.txt`
record the fresh M2 rebuild comparison and notebook execution.
`verification.json` includes full row-content
hashes, not just counts. Detailed CSVs and `profile.json` are local generated
source-derived extracts excluded from Git; the notebook recreates them. The
notebook retains aggregate outputs and a small number of representative examples.

The local database remains `data/phones.db`, excluded from Git. Submit that built
database and the required raw-data zip through the course system after the group
finishes its review, attribution, commits, and exact-state tag.
