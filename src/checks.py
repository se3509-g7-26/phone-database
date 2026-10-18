"""Prove M2 constraints, idempotence and atomicity on a temporary DB copy."""
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile

from db import DEFAULT_DB, ROOT, connect, contents_digest, counts
from load import LoadError, load

STAMP = '2026-10-18T12:00:00.000000Z'


def write_landed(root, source, filename, body, url, stamp=STAMP):
    """Write synthetic landed responses for checks, never into real raw folders."""
    folder = Path(root) / source
    folder.mkdir(parents=True, exist_ok=True)
    body = body.encode('utf-8') if isinstance(body, str) else body
    path = folder / filename
    path.write_bytes(body)
    path.with_suffix('.meta.json').write_text(json.dumps({
        'source': source, 'url': url, 'retrieved_at_utc': stamp, 'bytes': len(body)
    }), encoding='utf-8')
    return path


def fixture(root, *, broken=False, phone_id='999999999999', item_id='Q999999999999'):
    """A new model is written before the deliberately broken Wikidata response."""
    write_landed(root, 'gsmarena', 'model.html', '''<h1>Check model</h1>
        <div id="specs-list"><table><tr><th>Misc</th></tr>
        <tr><td class="ttl">Price</td><td class="nfo" data-spec="price">About 100 EUR</td></tr>
        </table></div>''', 'https://m.gsmarena.com/check-' + phone_id + '.php')
    wd = {'results': {'bindings': [{'phone': {'value': 'http://www.wikidata.org/entity/' + item_id},
                                   'gsmId': {'value': phone_id}}]}}
    write_landed(root, 'wikidata', 'items.json', '{broken' if broken else json.dumps(wd), 'https://query.wikidata.org/sparql')
    wp = {'query': {'pages': [{'pageid': int(phone_id), 'title': 'Check model',
                             'pageprops': {'wikibase_item': item_id},
                             'revisions': [{'timestamp': STAMP, 'slots': {'main': {'content': 'Test wikitext'}}}]}]}}
    write_landed(root, 'wikipedia', 'articles.json', json.dumps(wp), 'https://en.wikipedia.org/w/api.php')


def rejected(con, sql, values):
    con.execute('SAVEPOINT constraint_probe')
    try:
        con.execute(sql, values)
    except sqlite3.IntegrityError:
        return True
    finally:
        con.execute('ROLLBACK TO constraint_probe')
        con.execute('RELEASE constraint_probe')
    return False


def run_checks(database=DEFAULT_DB, raw=ROOT / 'data' / 'raw', *, temp_parent=None):
    if not Path(database).is_file():
        raise LoadError('Database is missing; run python src/load.py first')
    results = {}
    with tempfile.TemporaryDirectory(dir=temp_parent) as directory:
        copied = Path(directory) / 'check.db'
        # SQLite backup gets a consistent snapshot; the source opens read-only.
        source = connect(database, read_only=True)
        target = connect(copied)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        con = connect(copied)
        try:
            phone = con.execute('SELECT * FROM phone LIMIT 1').fetchone()
            if phone is None:
                raise LoadError('Checks need at least one loaded phone')
            values = (phone['source_id'], 'Duplicate', 'https://example.invalid', phone['file_key'], STAMP)
            results['Duplicate natural key'] = rejected(con, '''INSERT INTO phone
                (source_id,name,source_url,file_key,retrieved_at) VALUES (?, ?, ?, ?, ?)''', values)
            unknown_key = con.execute('SELECT COALESCE(MAX(phone_key),0)+1 FROM phone').fetchone()[0]
            results['Orphan event'] = rejected(con, 'INSERT INTO phone_snapshot VALUES (?, ?, ?, ?)',
                                               (unknown_key, STAMP, 'Orphan', phone['file_key']))
            results['NULL key'] = rejected(con, 'INSERT INTO phone_snapshot VALUES (?, ?, ?, ?)',
                                          (None, STAMP, 'NULL', phone['file_key']))
            results['Wrong type'] = rejected(con, '''INSERT INTO raw_file
                (source_id,source,url,byte_count,sha256,retrieved_at) VALUES (?, ?, ?, ?, ?, ?)''',
                ('check/wrong-type', 'gsmarena', 'https://example.invalid', 'n/a', '0' * 64, STAMP))
        finally:
            con.close()
        # Compare all values, including provenance and stable surrogate keys.
        load(raw, copied, verbose=False)
        con = connect(copied)
        try:
            before_counts, before_content = counts(con), contents_digest(con)
        finally:
            con.close()
        load(raw, copied, verbose=False)
        con = connect(copied)
        try:
            results['Idempotence'] = before_counts == counts(con) and before_content == contents_digest(con)
        finally:
            con.close()
        broken_raw = Path(directory) / 'broken_raw'
        fixture(broken_raw, broken=True)
        failed = False
        try:
            load(broken_raw, copied, verbose=False)
        except LoadError:
            failed = True
        con = connect(copied)
        try:
            results['Atomicity'] = failed and before_counts == counts(con) and before_content == contents_digest(con)
            results['foreign_key_check'] = not list(con.execute('PRAGMA foreign_key_check'))
            results['All tables STRICT'] = all(row['strict'] for row in con.execute('PRAGMA table_list')
                                              if row['name'] not in ('sqlite_schema', 'sqlite_temp_schema'))
        finally:
            con.close()
    for name, passed in results.items():
        print(f'{name}: {"PASS" if passed else "FAIL"}', flush=True)
    return all(results.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--raw', type=Path, default=ROOT / 'data' / 'raw')
    args = parser.parse_args()
    try:
        return 0 if run_checks(args.db, args.raw) else 1
    except (LoadError, OSError, sqlite3.Error) as exc:
        print(f'CHECKS: FAILED: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
