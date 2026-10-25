"""Build the M2 database offline: python src/load.py (no network calls)."""
from __future__ import annotations

import argparse
from collections import Counter
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse

from db import ROOT, DEFAULT_DB, connect, counts, create_schema


class LoadError(RuntimeError):
    """Broken landed files/metadata are fatal, invalid individual rows are quarantined."""


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be text')
    if re.fullmatch(r'\d{8}T\d{12}Z', value):
        dt = datetime.strptime(value, '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc)
    else:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError('timestamp needs an explicit timezone')
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def numeric_id(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]*', str(value)):
        raise ValueError('expected a positive decimal source ID')
    return str(value)


def qid(value):
    value = str(value).rsplit('/', 1)[-1]
    if not re.fullmatch(r'Q[1-9][0-9]*', value):
        raise ValueError('invalid Wikidata QID')
    return value


class SpecsParser(HTMLParser):
    """Extract labeled source text, including continuation rows, without inference.

    The mobile HTML has nested/unclosed tr tags. Cells, rather than tr nesting,
    define a specification row. br adds a space; inline sup/text stays intact.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.cell = None
        self.parts = []
        self.section = ''
        self.label = ''
        self.field = None
        self.rows = []
        self.heading = False
        self.heading_parts = []

    def finish_cell(self):
        value = re.sub(r'\s+', ' ', ''.join(self.parts)).strip()
        if self.cell == 'th':
            self.section = value
        elif self.cell == 'ttl':
            self.label = value
        elif self.cell == 'nfo':
            self.rows.append((self.section, self.label, self.field, value or None))
            self.label = ''
        self.cell = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1':
            self.heading = True
        if tag == 'div':
            if self.div_depth:
                self.div_depth += 1
            elif attrs.get('id') == 'specs-list':
                self.div_depth = 1
        if self.div_depth and tag in ('th', 'td'):
            self.finish_cell()
            classes = attrs.get('class', '').split()
            self.cell = 'th' if tag == 'th' else ('nfo' if 'nfo' in classes else 'ttl')
            self.field = attrs.get('data-spec')
        if tag == 'br' and self.cell:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.heading = False
        if tag in ('td', 'th') and self.cell:
            self.finish_cell()
        if tag == 'div' and self.div_depth:
            self.div_depth -= 1

    def handle_data(self, data):
        if self.heading:
            self.heading_parts.append(data)
        if self.cell:
            self.parts.append(data)

    @property
    def name(self):
        return re.sub(r'\s+', ' ', ''.join(self.heading_parts)).strip()


@dataclass(frozen=True)
class LandedFile:
    path: Path
    source_id: str
    source: str
    url: str
    retrieved_at: str
    byte_count: int


def inventory(raw):
    """No implicit timestamps or filesystem mtime fallback: metadata is required."""
    result = []
    for source, suffix in [('gsmarena', '.html'), ('wikidata', '.json'), ('wikipedia', '.json')]:
        folder = raw / source
        paths = sorted(p for p in folder.glob('*' + suffix) if not p.name.endswith('.meta.json'))
        if not paths:
            raise LoadError(f'No {source} responses under {folder}; land all three sources first')
        for path in paths:
            try:
                meta = json.loads(path.with_suffix('.meta.json').read_bytes())
                stamp = timestamp(meta['retrieved_at_utc'])
                if meta['source'] != source or not isinstance(meta['url'], str):
                    raise ValueError('source/url metadata mismatch')
                size = meta['bytes']
                if type(size) is not int or size < 0:
                    raise ValueError('invalid byte count')
                result.append(LandedFile(path, path.relative_to(raw).as_posix(), source,
                                         meta['url'], stamp, size))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise LoadError(f'{path}: invalid/missing metadata: {exc}') from exc
        for meta_path in folder.glob('*.meta.json'):
            if not meta_path.with_name(meta_path.name.replace('.meta.json', suffix)).is_file():
                raise LoadError(f'{meta_path}: metadata has no landed response')
    # Source passes establish parents before references. Clock/path determine
    # winners, not glob order. SQL also enforces this for incremental loads.
    return sorted(result, key=lambda f: (f.source, f.retrieved_at, f.source_id))


def prefetched(files):
    """Bounded read-ahead for many small files, with SQL kept on one thread.

    Keep at most sixty-four bodies in flight. Consume in inventory order so I/O
    completion order cannot change surrogate keys or version selection.
    """
    with ThreadPoolExecutor(max_workers=32) as pool:
        pending = deque()
        remaining = iter(files)
        for f in remaining:
            pending.append((f, pool.submit(f.path.read_bytes)))
            if len(pending) == 64:
                break
        while pending:
            yield pending.popleft()
            f = next(remaining, None)
            if f is not None:
                pending.append((f, pool.submit(f.path.read_bytes)))


def quarantine(con, file_key, record_key, reason, payload, stamp, stats):
    con.execute('''INSERT INTO quarantine VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(file_key, record_key) DO UPDATE SET
        reason=excluded.reason, payload_json=excluded.payload_json,
        retrieved_at=excluded.retrieved_at''',
        (file_key, str(record_key), reason, json.dumps(payload, ensure_ascii=False), stamp))
    stats['quarantined_this_run'] += 1
    stats['reason: ' + reason] += 1


def load_gsm(con, f, file_key, body, stats):
    name = Path(urlparse(f.url).path).name
    match = re.fullmatch(r'.+-([1-9][0-9]*)\.php', name, re.I)
    if b'please slow down' in body.lower():
        quarantine(con, file_key, 'response', 'GSMArena slowdown response', f.url, f.retrieved_at, stats)
        return
    if not match or '-phones-' in name:
        stats['catalog_files'] += 1
        return
    parser = SpecsParser()
    # Some pages declare UTF-8 but contain lone-surrogate byte sequences in
    # visitor comments. Preserve undecodable bytes as surrogates while parsing,
    # then refuse any modeled field containing them. We never replace evidence
    # with U+FFFD or guess a different encoding for the whole page.
    text = body.decode('utf-8', errors='surrogateescape')
    invalid_bytes = len(re.findall('[\udc80-\udcff]', text))
    if invalid_bytes:
        stats['encoding_issue_files'] += 1
        stats['invalid_utf8_bytes'] += invalid_bytes
    parser.feed(text)
    parser.close()
    if not parser.name or not parser.rows:
        quarantine(con, file_key, 'model', 'Missing model heading/specifications', f.url, f.retrieved_at, stats)
        return
    modeled_text = [parser.name] + [v for row in parser.rows for v in row if v is not None]
    if any(re.search('[\udc80-\udcff]', value) for value in modeled_text):
        quarantine(con, file_key, 'model', 'Invalid UTF-8 in model fields', f.url, f.retrieved_at, stats)
        return
    source_id = match[1]
    con.execute('''INSERT INTO phone(source_id,name,source_url,file_key,retrieved_at)
        VALUES (?, ?, ?, ?, ?) ON CONFLICT(source_id) DO UPDATE SET
        name=excluded.name, source_url=excluded.source_url,
        file_key=excluded.file_key, retrieved_at=excluded.retrieved_at
        WHERE (excluded.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=excluded.file_key))
            > (phone.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=phone.file_key))''',
        (source_id, parser.name, f.url, file_key, f.retrieved_at))
    phone_key = con.execute('SELECT phone_key FROM phone WHERE source_id=?', (source_id,)).fetchone()[0]
    # A timestamp tie has a stable path-based winner. No mixing of two payloads.
    old = con.execute('''SELECT r.source_id FROM phone_snapshot s JOIN raw_file r USING(file_key)
        WHERE s.phone_key=? AND s.retrieved_at=?''', (phone_key, f.retrieved_at)).fetchone()
    if old and old[0] > f.source_id:
        return
    con.execute('''INSERT INTO phone_snapshot VALUES (?, ?, ?, ?)
        ON CONFLICT(phone_key,retrieved_at) DO UPDATE SET name=excluded.name,file_key=excluded.file_key''',
        (phone_key, f.retrieved_at, parser.name, file_key))
    con.executemany('''INSERT INTO specification VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(phone_key,retrieved_at,row_number) DO UPDATE SET
        section=excluded.section, label=excluded.label, source_field=excluded.source_field,
        value_text=excluded.value_text, file_key=excluded.file_key''',
                    ((phone_key, f.retrieved_at, i, section, label, field, value, file_key)
                     for i, (section, label, field, value) in enumerate(parser.rows, 1)))
    # A winning payload with fewer cells must not keep the loser's trailing cells.
    con.execute('DELETE FROM specification WHERE phone_key=? AND retrieved_at=? AND row_number>?',
                (phone_key, f.retrieved_at, len(parser.rows)))
    stats['values_to_null'] += sum(value is None for _, _, _, value in parser.rows)
    stats['model_responses'] += 1


def load_wd(con, f, file_key, body, stats):
    rows = json.loads(body)['results']['bindings']
    if not isinstance(rows, list):
        raise LoadError('Wikidata bindings must be a list')
    for i, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                raise ValueError('record must be an object')
            item_id = qid(row['phone']['value'])
            phone_id = numeric_id(row['gsmId']['value'])
            article = row.get('article', {}).get('value')
            if article is not None and (not isinstance(article, str) or not article.startswith('https://en.wikipedia.org/wiki/')):
                raise ValueError('invalid English article URL')
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            quarantine(con, file_key, i, 'Invalid Wikidata record: ' + str(exc), row, f.retrieved_at, stats)
            continue
        con.execute('''INSERT INTO wikidata_item(source_id,file_key,retrieved_at) VALUES (?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET file_key=excluded.file_key,retrieved_at=excluded.retrieved_at
            WHERE (excluded.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=excluded.file_key))
                > (wikidata_item.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=wikidata_item.file_key))''',
            (item_id, file_key, f.retrieved_at))
        item_key = con.execute('SELECT item_key FROM wikidata_item WHERE source_id=?', (item_id,)).fetchone()[0]
        phone = con.execute('SELECT phone_key FROM phone WHERE source_id=?', (phone_id,)).fetchone()
        if phone is None:
            quarantine(con, file_key, i, 'Unknown GSMArena phone ID', row, f.retrieved_at, stats)
            continue
        con.execute('''INSERT INTO phone_item_link VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(phone_key,item_key) DO UPDATE SET article_url=excluded.article_url,
            file_key=excluded.file_key,retrieved_at=excluded.retrieved_at
            WHERE (excluded.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=excluded.file_key))
                > (phone_item_link.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=phone_item_link.file_key))''',
            (phone[0], item_key, article, file_key, f.retrieved_at))


def load_wp(con, f, file_key, body, stats):
    pages = json.loads(body)['query']['pages']
    if not isinstance(pages, list):
        raise LoadError('Wikipedia pages must be a list (formatversion=2)')
    for i, page in enumerate(pages):
        try:
            if not isinstance(page, dict):
                raise ValueError('record must be an object')
            if 'missing' in page or 'invalid' in page:
                raise ValueError('missing/invalid Wikipedia page')
            page_id = numeric_id(page['pageid'])
            title = page['title']
            if not isinstance(title, str) or not title.strip():
                raise ValueError('missing article title')
            item_id = page.get('pageprops', {}).get('wikibase_item')
            item = None
            if item_id:
                item = con.execute('SELECT item_key FROM wikidata_item WHERE source_id=?', (qid(item_id),)).fetchone()
                if item is None:
                    raise ValueError('unknown Wikidata item')
            revisions = []
            for revision in page['revisions']:
                stamp = timestamp(revision['timestamp'])
                content = revision['slots']['main']['content']
                if not isinstance(content, str):
                    raise ValueError('revision content is not text')
                revisions.append((stamp, content))
            if not revisions:
                raise ValueError('no revision content')
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            quarantine(con, file_key, i, 'Invalid Wikipedia record: ' + str(exc), page, f.retrieved_at, stats)
            continue
        con.execute('''INSERT INTO wikipedia_article(source_id,title,item_key,file_key,retrieved_at)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(source_id) DO UPDATE SET
            title=excluded.title,item_key=excluded.item_key,file_key=excluded.file_key,retrieved_at=excluded.retrieved_at
            WHERE (excluded.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=excluded.file_key))
                > (wikipedia_article.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=wikipedia_article.file_key))''',
            (page_id, title, item[0] if item else None, file_key, f.retrieved_at))
        article_key = con.execute('SELECT article_key FROM wikipedia_article WHERE source_id=?', (page_id,)).fetchone()[0]
        for stamp, content in revisions:
            con.execute('''INSERT INTO article_revision VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(article_key,revision_at) DO UPDATE SET content=excluded.content,
                file_key=excluded.file_key,retrieved_at=excluded.retrieved_at
                WHERE (excluded.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=excluded.file_key))
                    > (article_revision.retrieved_at, (SELECT source_id FROM raw_file WHERE file_key=article_revision.file_key))''',
                (article_key, stamp, content, file_key, f.retrieved_at))


def load(raw=ROOT / 'data' / 'raw', database=DEFAULT_DB, *, verbose=True):
    raw = Path(raw).resolve()
    files = inventory(raw)
    stats = Counter()
    con = connect(database)
    try:
        before = counts(con)
        with closing(prefetched(files)) as bodies, con:
            con.execute('BEGIN')
            create_schema(con)
            for number, (f, body_future) in enumerate(bodies, 1):
                try:
                    body = body_future.result()
                    if len(body) != f.byte_count:
                        raise LoadError('body size differs from landed metadata')
                    digest = hashlib.sha256(body).hexdigest()
                    prior = con.execute('SELECT * FROM raw_file WHERE source_id=?', (f.source_id,)).fetchone()
                    if prior and (prior['sha256'], prior['url'], prior['retrieved_at'], prior['source']) != (
                            digest, f.url, f.retrieved_at, f.source):
                        raise LoadError('landed file/metadata changed since earlier load; use a fresh database')
                    con.execute('''INSERT INTO raw_file(source_id,source,url,byte_count,sha256,retrieved_at)
                        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(source_id) DO NOTHING''',
                        (f.source_id, f.source, f.url, f.byte_count, digest, f.retrieved_at))
                    file_key = con.execute('SELECT file_key FROM raw_file WHERE source_id=?', (f.source_id,)).fetchone()[0]
                    # Re-evaluate quarantine when newly landed parents make a link resolvable.
                    con.execute('DELETE FROM quarantine WHERE file_key=?', (file_key,))
                    {'gsmarena': load_gsm, 'wikidata': load_wd, 'wikipedia': load_wp}[f.source](
                        con, f, file_key, body, stats)
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                    raise LoadError(f'{f.path}: {exc}') from exc
                stats['files_read'] += 1
                if verbose and number % 1000 == 0:
                    print(f'Processed {number:,}/{len(files):,} raw files', flush=True)
            if con.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise LoadError('foreign_key_check failed')
            after = counts(con)
        if verbose:
            print(f"files read: {stats['files_read']:,} raw files ({min(f.retrieved_at for f in files)} .. {max(f.retrieved_at for f in files)})")
            for table, total in after.items():
                diff = total - before[table]
                change = f"{diff:+,} this run" if diff != 0 else "0 new this run"
                print(f'{table}: {total:,} in database ({change})')
            print(f"catalog files: {stats['catalog_files']:,} (provenance only)")
            print(f"values cleaned: {stats['values_to_null']:,} (empty specification cells -> NULL; other source text preserved)")
            print(f"encoding issues: {stats['encoding_issue_files']:,} HTML files / {stats['invalid_utf8_bytes']:,} invalid UTF-8 bytes (invalid modeled fields quarantined)")
            print(f"quarantined: {stats['quarantined_this_run']:,} records")
            for key, value in sorted(stats.items()):
                if key.startswith('reason: '):
                    print(f'  {key}: {value}')
            print('foreign_key_check: OK\nSTATUS: COMPLETE')
        return stats
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'data' / 'raw')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    try:
        load(args.raw, args.db)
    except (LoadError, OSError, sqlite3.Error, UnicodeError) as exc:
        print(f'STATUS: FAILED (no changes committed): {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
