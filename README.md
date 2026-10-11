# Cellphone Launch Prices and Specifications

## The question

This project aims to explore the connection between smartphones’ original launch prices (MSRP) and their technical specifications, as well as how this connection has evolved over the years. By combining pricing data with hardware specifications, we will compare features such as RAM and storage capacity relative to launch prices across different years and manufacturers. We will also investigate which hardware characteristics have the strongest relationship with MSRP and assess their ability to predict launch prices. To ensure fair comparisons, we will consider the original currency, market, and storage configuration of each device.

## Sources

- GSMArena phone catalog — model and specification source, one page per model.
- Wikipedia articles — release history and supporting information.
- Wikidata entities — structured identities and links between the other sources.

See [source cards](docs/sources.md) for provenance, access notes and known issues. Raw responses are excluded from Git because GSMArena's terms restrict redistribution; running the ingestion regenerates them.

Attribution:

- Phone specifications are from [GSMArena.com](https://www.gsmarena.com/), copyright Arena Kom OOD.
- Wikipedia text is by Wikipedia contributors, available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- [Wikidata](https://www.wikidata.org/) data is available under CC0 1.0.

## Setup and run

Requires Python 3.10 or later. From the repository root:

```sh
python -m venv venv
# PowerShell: use the interpreter directly; activation is optional.
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

On Linux or macOS the interpreter is `venv/bin/python`.

Set `PHONE_DATA_USER_AGENT` to a descriptive value with a real contact address as shown in `.env.example` (for example, in PowerShell: `$env:PHONE_DATA_USER_AGENT = 'PhoneLaunchPricesStudentProject/0.1 (contact: name@example.com)'`). Copy `.env.example` to `.env` and replace the placeholder contact; the script refuses to start with the placeholder. The script automatically loads `.env` from the repository root; existing process environment variables take precedence. No API key is needed for any source. Then run from the repository root:

```sh
.\venv\Scripts\python.exe src/ingest.py --max-brands 1 --max-models 2 --max-wikidata-pages 1 --wikidata-page-size 5 --max-wikipedia-articles 2
```

This trial enumerates one brand, downloads details for two models, samples five Wikidata rows and requests at most two Wikipedia articles. It takes about a minute and ends with a summary:

```
Fetched 2 GSMArena model details
Discovered 5 Wikidata entities; requested 2 Wikipedia articles
Raw responses saved: gsmarena=6, wikidata=1, wikipedia=1
```

Inspect the run summary and raw responses, then run `python src/ingest.py` for the full collection. GSMArena serves about 7.5 pages a minute to one address, so its 15,000 pages take about 34 hours; Wikidata and Wikipedia take a few minutes. The discovered URLs are checkpointed in `data/discovery/`, separate from raw source responses. `PHONE_DATA_DELAY_SECONDS`, `PHONE_DATA_TIMEOUT_SECONDS` and `PHONE_DATA_RETRIES` are optional environment settings. Each source pipeline stops on an error and is listed on a `FAILED:` line; the other pipeline is still attempted and reports how many original responses were saved; each later run adds files rather than overwriting them.

Each response is saved unchanged as `data/raw/<source>/<UTC timestamp>_<number>.html` or `.json`, next to a `.meta.json` file with the address, the retrieval time and the size.

To retry GSMArena after a partial run, use `--sources gsmarena --resume`.
This reuses saved catalog and model responses, including mobile redirects, and
fetches missing pages. Server messages requesting a slowdown are never reused;
they trigger a 60-second wait and retry, even when returned with HTTP 200.
Keep `PHONE_DATA_DELAY_SECONDS=8`, as in `.env.example`: a shorter delay only
triggers the slowdown message. When Wikidata results are already saved
(`--sources wikidata`), the models they link to are fetched first.

On Linux, `scripts/crawl_gsmarena.sh` repeats the resume command after a rate-limit stop, and `scripts/crawl_status.py` shows how far a crawl is.

GSMArena's terms restrict redistribution, so never commit `data/raw/`. Read the terms before a full run: they allow personal, informational, non-commercial use only. The code keeps to the pace the site allows and does not bypass access controls. The model catalog includes tablets and watches; classification belongs in later milestones.

To run the tests:

```sh
.\venv\Scripts\python.exe -m unittest discover -s tests
```

## Structure

- `src/ingest.py` — ingestion entry point.
- `tests/test_ingest.py` — tests of the ingestion script; they make no network requests.
- `scripts/` — helpers for the long GSMArena crawl.
- `data/raw/` — timestamped original responses, kept locally.
- `data/discovery/` — local model URL inventories from catalog traversal.
- `docs/sources.md` — data source and licence cards.
- `requirements.txt` — packages the script imports.
- `.env.example` — configuration template; `.env` is ignored.
- `data.pyproj`, `data.slnx` — Visual Studio project files.

## Status

M1 — ingestion complete

## Team

- Oğuzhan Karacan — [NevermindExpress](https://github.com/NevermindExpress)
- Osman Yiğit Doğan — [se-230717001](https://github.com/se-230717001)
- Onur Atıcı — [se-240717002](https://github.com/se-240717002)
