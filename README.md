# Cellphone Launch Prices and Specifications

This project aims to explore the connection between smartphones’ original launch prices (MSRP) and their technical specifications, as well as how this connection has evolved over the years. By combining pricing data with hardware specifications, we will compare features such as RAM and storage capacity relative to launch prices across different years and manufacturers. We will also investigate which hardware characteristics have the strongest relationship with MSRP and assess their ability to predict launch prices. To ensure fair comparisons, we will consider the original currency, market, and storage configuration of each device.

## Sources

- GSMArena phone catalog — proposed model/specification source; automated access is pending confirmation.
- Wikipedia articles — release history and supporting information.
- Wikidata entities — structured identities and links between the other sources.

See [source cards](sources.md) for provenance, access notes and attribution. Raw responses are excluded from Git while their redistribution rights are uncertain or restricted.

## Setup and run

Requires Python 3.10 or later. From the repository root:

```sh
python -m venv venv
# PowerShell: use the interpreter directly; activation is optional.
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set `PHONE_DATA_USER_AGENT` to a descriptive value with a real contact address as shown in `.env.example` (for example, in PowerShell: `$env:PHONE_DATA_USER_AGENT = 'PhoneLaunchPricesStudentProject/0.1 (contact: name@example.com)'`). Copy `.env.example` to `.env` and replace the placeholder contact. The script automatically loads `.env` beside `ingest.py`; existing process environment variables take precedence. Then run from the repository root:

```sh
.\venv\Scripts\python.exe ingest.py --max-brands 1 --max-models 2 --max-wikidata-pages 1 --wikidata-page-size 5 --max-wikipedia-articles 2
```

This trial enumerates one brand, downloads details for two models, samples five Wikidata rows and requests at most two Wikipedia articles. Inspect the run summary and raw responses, then run `python ingest.py` for the full collection. It can take hours because it requests thousands of model pages at a conservative default pace of one request per second. The discovered URLs are checkpointed in `data/discovery/`, separate from raw source responses. `PHONE_DATA_DELAY_SECONDS`, `PHONE_DATA_TIMEOUT_SECONDS` and `PHONE_DATA_RETRIES` are optional environment settings. Each source pipeline stops on an error; the other pipeline is still attempted and reports how many original responses were saved; each later run adds files rather than overwriting them.

To retry GSMArena after a partial run, use `--sources gsmarena --resume`.
This reuses saved catalog and model responses, including mobile redirects, and
fetches missing pages. Server messages requesting a slowdown are never reused;
they trigger a 60-second wait and retry, even when returned with HTTP 200.
Set `PHONE_DATA_DELAY_SECONDS=2` in `.env` for a slower pace on the next run.

GSMArena's terms restrict redistribution, so never commit `data/raw/`. Confirm the collection terms with the course instructor and provider before the full run; the code does not bypass access controls. The model catalog may include tablets or watches; classification belongs in later milestones.

## Structure

- `ingest.py` — ingestion entry point.
- `data/raw/` — timestamped original responses, kept locally.
- `data/discovery/` — local model URL inventories from catalog traversal.
- `sources.md` — data source and licence cards.
- `.env.example` — configuration template; `.env` is ignored.

**Status:** M1 — ingestion implemented.

**Team:** Oğuzhan Karacan - NevermindExpress / Osman Yiğit Doğan - se-230717001 / Onur Atıcı - se-240717002

