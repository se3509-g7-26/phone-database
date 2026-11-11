# M4 verification and team handoff

The executed notebook, report, SQL queries, six SVG figures and README changes
are prepared locally. Member review/attribution, individual commits, feedback
confirmation, the `m4` tag, push and course submission are still team actions.
No member is claimed to have performed work they have not reviewed.

## Reproduce

```sh
python src/load.py
python src/clean.py
python src/validate.py
python scripts/run_m4_eda.py
python -m unittest discover -s tests -q
```

The notebook uses ordinary Python and runs through either the dependency-free
runner above or Jupyter/nbconvert. `PHONE_M4_DB` selects a different database;
the runner also accepts `--db PATH`. Run from the repository root. Plotting
uses deterministic SVG output, with no extra packages or network requests.
The original ingestion dependencies in `requirements.txt` remain necessary
for rebuilding M2.

## Evidence

- `results.json`: aggregate summaries, all annual denominators, six pooled
  brand-pair looks, correlation sensitivities, paired year comparison and seeds.
- `notebook-verification.json`: database hashes before/after notebook execution
  and the six generated figure filenames.
- `fresh-build-verification.json`: fresh M2/M3 equality with the working
  database, repeatable notebook outputs and unchanged database bytes.
- `validate.txt`: full-data validation; WARNs describe existing evidence limits.
- `tests.txt`: offline regression suite, including tied ranks, undefined
  correlations, percentile interpolation, coverage denominators and bootstrap.

`python scripts/verify_m4.py --db tmp/m4-fresh/phones.db` verifies an already
rebuilt comparison database against `data/phones.db` and reruns the notebook.
To reproduce the fresh database used for that check:

```sh
python src/load.py --db tmp/m4-fresh/phones.db
python src/clean.py --db tmp/m4-fresh/phones.db
python src/validate.py --db tmp/m4-fresh/phones.db
python scripts/verify_m4.py --db tmp/m4-fresh/phones.db
```

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
