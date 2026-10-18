"""Test proposed natural keys against landed records BEFORE creating a schema.

Only repeated IDs need HTML parsing to check name consistency. No database or
network access. Run: python src/profile_keys.py > docs/m2/key-audit.json
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from db import ROOT
from load import SpecsParser, inventory, timestamp


def profile(raw):
    files = inventory(Path(raw))
    models = defaultdict(list)
    pairs = Counter()
    pages = Counter()
    revisions = Counter()
    article_qids = set()
    missing_pages = 0
    catalogs = 0
    short_bodies = []
    for f in files:
        if f.source == 'gsmarena':
            name = Path(urlparse(f.url).path).name
            match = re.fullmatch(r'.+-([1-9][0-9]*)\.php', name)
            if match and '-phones-' not in name:
                models[match[1]].append(f)
            else:
                catalogs += 1
            if f.byte_count < 100:
                short_bodies.append(f.source_id)
        elif f.source == 'wikidata':
            for row in json.loads(f.path.read_bytes())['results']['bindings']:
                pairs[(row['phone']['value'].rsplit('/', 1)[-1], row['gsmId']['value'])] += 1
        else:
            for page in json.loads(f.path.read_bytes())['query']['pages']:
                if 'missing' in page or 'invalid' in page:
                    missing_pages += 1
                    continue
                pages[page['pageid']] += 1
                item = page.get('pageprops', {}).get('wikibase_item')
                if item:
                    article_qids.add(item)
                for revision in page.get('revisions', []):
                    revisions[(page['pageid'], timestamp(revision['timestamp']))] += 1
    item_phones = defaultdict(set)
    phone_items = defaultdict(set)
    for item, phone in pairs:
        item_phones[item].add(phone)
        phone_items[phone].add(item)
    changed_names = {}
    missing_names = []
    snapshot_keys = Counter()
    for phone, copies in models.items():
        for f in copies:
            snapshot_keys[phone, f.retrieved_at] += 1
        if len(copies) > 1:
            names = set()
            for f in copies:
                parser = SpecsParser()
                parser.feed(f.path.read_text(encoding='utf-8'))
                if parser.name:
                    names.add(parser.name)
                else:
                    missing_names.append(f.source_id)
            if len(names) > 1:
                changed_names[phone] = sorted(names)
    return {
        'raw_files': len(files), 'gsmarena_catalog_files': catalogs,
        'gsmarena_model_responses': sum(map(len, models.values())),
        'gsmarena_distinct_ids': len(models),
        'gsmarena_refetched_copies': sum(map(len, models.values())) - len(models),
        'duplicate_phone_snapshot_keys': sum(n-1 for n in snapshot_keys.values()),
        'refetched_ids_with_changed_names': changed_names,
        'refetched_responses_without_model_heading': missing_names,
        'gsmarena_bodies_under_100_bytes': short_bodies,
        'wikidata_rows': sum(pairs.values()), 'distinct_item_phone_pairs': len(pairs),
        'duplicate_item_phone_pairs': sum(n-1 for n in pairs.values()),
        'distinct_wikidata_items': len(item_phones), 'distinct_linked_phone_ids': len(phone_items),
        'items_linking_multiple_phones': sum(len(v)>1 for v in item_phones.values()),
        'phones_linking_multiple_items': sum(len(v)>1 for v in phone_items.values()),
        'unknown_phone_references': sorted(set(phone_items)-set(models), key=int),
        'wikipedia_page_records': sum(pages.values()), 'distinct_wikipedia_page_ids': len(pages),
        'duplicate_page_ids': sum(n-1 for n in pages.values()),
        'duplicate_article_revision_keys': sum(n-1 for n in revisions.values()),
        'wikipedia_missing_pages': missing_pages,
        'unknown_wikipedia_item_references': sorted(article_qids-set(item_phones)),
        'retrieval_min': min(f.retrieved_at for f in files),
        'retrieval_max': max(f.retrieved_at for f in files),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'data' / 'raw')
    args = parser.parse_args()
    print(json.dumps(profile(args.raw), ensure_ascii=False, indent=2))
