"""Capture full-data raw-preservation and two-run idempotence evidence offline."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from clean import clean
from db import DEFAULT_DB, connect, contents_digest
from validate import validate

CLEAN_QUERIES = (
    'SELECT * FROM phone_clean ORDER BY phone_key',
    'SELECT * FROM specification_clean ORDER BY phone_key,retrieved_at,row_number',
    'SELECT * FROM field_rule_map ORDER BY source_field',
    'SELECT * FROM os_category_map ORDER BY alias',
    'SELECT * FROM currency_map ORDER BY alias',
    'SELECT * FROM phone_identity_map ORDER BY phone_key',
)


def digest(database):
    with contextlib.closing(connect(database,read_only=True)) as con:
        raw = contents_digest(con)
        cleaned = []
        for sql in CLEAN_QUERIES:
            sha = hashlib.sha256()
            for row in con.execute(sql):
                sha.update((json.dumps(tuple(row),ensure_ascii=False)+'\n').encode('utf-8'))
            cleaned.append(sha.hexdigest())
        return raw,cleaned


def verify(database=DEFAULT_DB):
    output = ROOT/'docs'/'m3'
    output.mkdir(parents=True,exist_ok=True)
    with contextlib.closing(connect(database,read_only=True)) as con:
        before = contents_digest(con)
    with (output/'clean-first.txt').open('w',encoding='utf-8') as stream, contextlib.redirect_stdout(stream):
        clean(database)
    raw_first,first = digest(database)
    with (output/'clean-second.txt').open('w',encoding='utf-8') as stream, contextlib.redirect_stdout(stream):
        clean(database)
    raw_second,second = digest(database)
    with (output/'validate.txt').open('w',encoding='utf-8') as stream, contextlib.redirect_stdout(stream):
        results = validate(database)
    evidence = {'m2_before':before,'m2_after_first':raw_first,'m2_after_second':raw_second,
                'm3_first':first,'m3_second':second,'raw_untouched':before==raw_first==raw_second,
                'cleaned_idempotent':first==second,'validation_no_stop':not any(r[0]=='STOP' for r in results)}
    (output/'verification.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    if not all(evidence[key] for key in ('raw_untouched','cleaned_idempotent','validation_no_stop')):
        raise RuntimeError('M3 verification failed; inspect docs/m3/verification.json')
    print('PASS: all M2 table hashes unchanged; all M3 tables identical after two runs; validation has no STOP')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    verify(parser.parse_args().db)
