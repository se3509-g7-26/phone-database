# M4 verification and team handoff

The executed notebook, report, SQL queries, seven SVG figures and README changes
are prepared locally. Member review/attribution, individual commits, feedback
confirmation, the `m4` tag, push and course submission are still team actions.
No member is claimed to have performed work they have not reviewed.

## Reproduce

```sh
python src/load.py
python src/clean.py
python src/validate.py
jupyter nbconvert --to notebook --execute --inplace notebooks/m4_eda.ipynb
python -m unittest discover -s tests -q
```

The notebook uses ordinary Python. The nbconvert step needs only
`pip install nbconvert ipykernel`; `python scripts/run_m4_eda.py` runs the same
cells without Jupyter and gives the same report, results and figures. Generated
files are written with LF line endings, so a Windows run reproduces the
committed bytes. `PHONE_M4_DB` selects a different database; the runner also
accepts `--db PATH`. Run from the repository root. Plotting
uses deterministic SVG output, with no extra packages or network requests.
The original ingestion dependencies in `requirements.txt` remain necessary
for rebuilding M2.

## Evidence

- `results.json`: aggregate summaries, all annual denominators, six pooled
  brand-pair looks, correlation sensitivities, the screen-size split, price by
  RAM level, paired year comparison and seeds.
- `notebook-verification.json`: database hashes before/after notebook execution
  and the generated figure filenames.
- `fresh-build-verification.json`: fresh M2/M3 equality with the working
  database, repeatable notebook outputs and unchanged database bytes.
- `validate.txt`: full-data validation; WARNs describe existing evidence limits.
- `tests.txt`: offline regression suite, including tied ranks, undefined
  correlations, percentile interpolation, coverage denominators and bootstrap.

`python scripts/verify_m4.py --db tmp/m4-fresh/phones.db` verifies an already
rebuilt comparison database against `data/phones.db` and reruns the notebook;
`--nbconvert` reruns it with the course command instead of the runner. To
reproduce the fresh database used for that check:

```sh
python src/load.py --db tmp/m4-fresh/phones.db
python src/clean.py --db tmp/m4-fresh/phones.db
python src/validate.py --db tmp/m4-fresh/phones.db
python scripts/verify_m4.py --db tmp/m4-fresh/phones.db --nbconvert
```

The committed evidence was produced this way except for the first step: the
Wikidata and Wikipedia responses are not on every member's machine, so the
fresh database started from a copy of the M2 submission database (built by
`load.py` from the full landed data; `load.py`, `db.py` and `sql/schema.sql`
are unchanged since tag `m2`). `clean.py` and `validate.py` then ran on it from
scratch, and the validation output matched `validate.txt` line for line.

The fresh database is temporary evidence; the submission database remains
`data/phones.db`. Raw files and databases stay outside Git. Submit the built
database and required raw zip through the course system after team review.

## Review before tagging

The findings table uses **Pending review: member name** to make the review
assignment explicit without inventing authorship. Each member should reproduce
their assigned analysis, check that they can explain it, replace the pending
label with truthful ownership, and commit their own reviewed work. The
instructor's requirement for meaningful commits from every member cannot be
satisfied by fabricated commits or attribution.

Confirm the M3 feedback with the group; no feedback text was available in the
repository and no resolution was invented. M4 established no additional
cleaning defect; issue I-13 records selection evidence and the existing MSRP
limitation. Catalog estimates should not be submitted as verified launch MSRP.

Only after the final reviewed state is committed and pushed should the team
create and push the `m4` tag; that tag is the graded state.
