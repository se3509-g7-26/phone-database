"""Build the M3 layer exclusively from M2 tables, atomically and offline."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata

import clean_config as cfg
from db import DEFAULT_DB, ROOT, connect


def normal_text(value):
    return ' '.join(unicodedata.normalize('NFC', value).split())


def match_key(value):
    # Explicit Turkish folding before casefold; no locale-dependent lower().
    return normal_text(value).translate(str.maketrans('İıŞşĞğÜüÖöÇç', 'iiSsGgUuOoCc')).casefold()


def text_value(raw):
    if raw is None:
        return None, 'missing_not_reported'
    value = normal_text(raw)
    if match_key(value) in cfg.MISSING_TOKENS:
        return None, 'missing_token'
    return value, 'ok' if value == raw else 'text_normalized'


def mapping_rows(directory, name):
    with (Path(directory) / name).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        if not all(row.get(key) for key in ('decided_by', 'decided_at', 'note')):
            raise ValueError('Mapping metadata missing in ' + name)
        date.fromisoformat(row['decided_at'])
    return rows


def read_mappings(directory):
    return {name: mapping_rows(directory, name + '.csv') for name in
            ('field_rules', 'os_categories', 'currencies', 'phone_identity')}


def category(value, categories):
    if value is None:
        return None
    key = match_key(value)
    matches = [r for r in categories if key == match_key(r['alias']) or
               key.startswith(match_key(r['alias']) + ' ')]
    return max(matches, key=lambda r: len(r['alias'])) if matches else None


def numeric(value, kind, retrieved_at, currencies):
    """Return number, secondary RAM number, unit, flag; never select a variant."""
    if value is None:
        return None, None, None, 'missing_not_reported'
    if kind is None:
        return None, None, None, 'not_applicable'
    number = secondary = unit = None
    flag = 'ok'
    if kind == 'price':
        # Strip the source's estimate qualifier without asserting launch-price status.
        body = re.sub(r'^About\s+', '', value, flags=re.I)
        matches = []
        for row in currencies:
            token = re.escape(row['alias'])
            for pattern in ('(' + cfg.NUMBER_PATTERN + r')\s*' + token,
                            token + r'\s*(' + cfg.NUMBER_PATTERN + ')'):
                m = re.fullmatch(pattern, body)
                if m:
                    matches.append((float(m[1].replace(',', '')), row['currency']))
        if len(matches) == 1:
            number, unit = matches[0]
        else:
            return None, None, None, 'ambiguous' if re.search(r'[/|$]|\d.*\d', body) else 'unparsed'
    elif kind == 'year':
        m = re.match(r'^(\d{4})(?:\b|,)', value)
        if not m:
            return None, None, 'year', 'unparsed'
        number, unit = float(m[1]), 'year'
        if not cfg.MIN_YEAR <= number <= int(retrieved_at[:4]):
            return None, None, unit, 'invalid_year'
        release = re.search(r'Released\s+(\d{4})', value)
        if release and int(release[1]) < number:
            return None, None, unit, 'invalid_year'
        exact = re.match(r'^(\d{4}), ([A-Za-z]+) (\d{1,2})\b', value)
        if exact:
            try:
                observed_date = datetime.strptime(' '.join(exact.groups()), '%Y %B %d').date()
            except ValueError:
                return None, None, unit, 'invalid_year'
            if observed_date.isoformat() > retrieved_at[:10]:
                return None, None, unit, 'invalid_year'
    elif kind == 'memory':
        m = re.fullmatch(r'(-?\d+(?:\.\d+)?)(MB|GB|TB)\s+(-?\d+(?:\.\d+)?)(MB|GB|TB)\s+RAM', value, re.I)
        if not m:
            return None, None, 'GB', 'ambiguous' if ',' in value or '/' in value else 'unparsed'
        # SI byte prefixes; MB / 1000 and TB * 1000; retain original units in raw text.
        def gigabytes(amount, prefix):
            return float(amount) * (cfg.MEMORY_UNIT_BASE ** ('MB', 'GB', 'TB').index(prefix.upper())) / cfg.MEMORY_UNIT_BASE
        number, secondary, unit = gigabytes(m[1], m[2]), gigabytes(m[3], m[4]), 'GB'
        if m[2].upper() != 'GB' or m[4].upper() != 'GB':
            flag = 'unit_converted'
    else:
        pattern, unit = {
            'weight': ('^(' + cfg.NUMBER_PATTERN + r')\s*g\b', 'g'),
            'display': ('^(' + cfg.NUMBER_PATTERN + r')\s*inches\b', 'inch'),
            'battery': (r'(?<![\d.,])(' + cfg.NUMBER_PATTERN + r')\s*mAh\b', 'mAh'),
        }[kind]
        m = re.search(pattern, value, re.I)
        if not m:
            return None, None, unit, 'unparsed'
        # A slash or alternative measurement makes selecting the first unsafe.
        if '/' in value or len(re.findall(cfg.NUMBER_PATTERN + r'\s*' +
                                         {'weight': 'g', 'display': 'inches', 'battery': 'mAh'}[kind] + r'\b', value, re.I)) > 1:
            return None, None, unit, 'ambiguous'
        number = float(m[1].replace(',', ''))
    if number is not None and (not math.isfinite(number) or number <= 0 or
                              (secondary is not None and secondary <= 0)):
        return None, None, unit, 'invalid_nonpositive'
    return number, secondary, unit, flag


def prepared(con, mappings):
    rules = {r['source_field']: r for r in mappings['field_rules']}
    os_by_snapshot = {}
    for row in con.execute("SELECT phone_key,retrieved_at,value_text FROM specification WHERE source_field='os' ORDER BY row_number"):
        match = category(row['value_text'], mappings['os_categories'])
        os_by_snapshot[(row['phone_key'], row['retrieved_at'])] = match['category'] if match else 'unknown'
    records, groups = [], defaultdict(list)
    for row in con.execute('SELECT * FROM specification ORDER BY phone_key,retrieved_at,row_number'):
        value, flag = text_value(row['value_text'])
        rule = rules.get(row['source_field'])
        number, secondary, unit, nflag = numeric(value, rule['kind'] if rule else None,
                                                row['retrieved_at'], mappings['currencies'])
        if flag.startswith('missing'):
            nflag = flag if rule else 'not_applicable'
        match = category(value, mappings['os_categories']) if row['source_field'] == 'os' else None
        catflag = ('missing_not_reported' if value is None else 'mapped' if match else 'unmapped') if row['source_field'] == 'os' else 'not_applicable'
        record = dict(row)
        record.update(value=value, value_flag=flag, number=number, secondary=secondary,
                      unit=unit, number_flag=nflag, category=match['category'] if match else None,
                      category_flag=catflag)
        records.append(record)
        # Current snapshot only estimates fences; historical copies do not inflate cohorts.
    latest = {r['phone_key']: r['retrieved_at'] for r in con.execute('SELECT phone_key,retrieved_at FROM phone')}
    source_ids = {r['phone_key']: r['source_id'] for r in con.execute('SELECT phone_key,source_id FROM phone')}
    canonical = {r['source_id']: r['canonical_source_id'] for r in mappings['phone_identity']}
    representatives = {}
    for r in records:
        if r['number'] is not None and latest[r['phone_key']] == r['retrieved_at'] and r['source_field'] != 'year':
            cohort = (r['source_field'], r['unit'], os_by_snapshot.get((r['phone_key'], r['retrieved_at']), 'unknown'))
            source_id = source_ids[r['phone_key']]
            resolved = canonical.get(source_id, source_id)
            key = (resolved, r['source_field'])
            order = (r['retrieved_at'], source_id, r['row_number'])
            if key not in representatives or order > representatives[key][0]:
                representatives[key] = (order, cohort, r['number'])
            if r['secondary'] is not None:
                ram_key = (resolved, 'ram_gb')
                if ram_key not in representatives or order > representatives[ram_key][0]:
                    representatives[ram_key] = (order, ('ram_gb',r['unit'],cohort[2]), r['secondary'])
    for _, cohort, number in representatives.values():
        groups[cohort].append(number)
    fences = {}
    for key, values in groups.items():
        if len(values) >= cfg.MIN_COHORT:
            q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
            if q3 > q1:
                fences[key] = (q1 - cfg.IQR_FACTOR * (q3 - q1), q3 + cfg.IQR_FACTOR * (q3 - q1))
    for r in records:
        key = (r['source_field'], r['unit'], os_by_snapshot.get((r['phone_key'], r['retrieved_at']), 'unknown'))
        if r['number'] is not None and key in fences:
            low, high = fences[key]
            if r['number'] < low:
                r['number_flag'] = 'unusual_low'
            elif r['number'] > high:
                r['number_flag'] = 'unusual_high'
        ram_key = ('ram_gb', r['unit'], os_by_snapshot.get((r['phone_key'],r['retrieved_at']), 'unknown'))
        if r['secondary'] is not None and ram_key in fences and not r['number_flag'].startswith('unusual'):
            low,high = fences[ram_key]
            if r['secondary'] < low:
                r['number_flag'] = 'unusual_low'
            elif r['secondary'] > high:
                r['number_flag'] = 'unusual_high'
    return records, fences


def clean(database=DEFAULT_DB, mappings_dir=cfg.MAPPINGS, *, verbose=True, fail_after=None):
    mappings = read_mappings(mappings_dir)
    con = connect(database)
    try:
        con.execute('BEGIN IMMEDIATE')
        if not con.execute('SELECT COUNT(*) FROM phone').fetchone()[0]:
            raise ValueError('M2 has no phone rows; load the landed data first')
        for statement in (ROOT / 'sql' / 'clean_schema.sql').read_text(encoding='utf-8').split(';'):
            if statement.strip():
                con.execute(statement)
        # All mutations below target only M3-owned tables, inside this transaction.
        con.execute('DELETE FROM specification_clean')
        con.execute('DELETE FROM phone_clean')
        con.execute('DELETE FROM phone_identity_map')
        con.execute('DELETE FROM field_rule_map')
        con.execute('DELETE FROM os_category_map')
        con.execute('DELETE FROM currency_map')
        con.executemany('INSERT INTO field_rule_map VALUES (?,?,?,?,?,?)',
                        [tuple(r[k] for k in ('source_field','kind','unit','decided_by','decided_at','note')) for r in mappings['field_rules']])
        con.executemany('INSERT INTO os_category_map VALUES (?,?,?,?,?)',
                        [tuple(r[k] for k in ('alias','category','decided_by','decided_at','note')) for r in mappings['os_categories']])
        con.executemany('INSERT INTO currency_map VALUES (?,?,?,?,?)',
                        [tuple(r[k] for k in ('alias','currency','decided_by','decided_at','note')) for r in mappings['currencies']])
        ids = {r['source_id']: r['phone_key'] for r in con.execute('SELECT phone_key,source_id FROM phone')}
        aliases = {r['source_id'] for r in mappings['phone_identity']}
        for row in mappings['phone_identity']:
            if row['source_id'] not in ids or row['canonical_source_id'] not in ids:
                raise ValueError('Unmatched identity mapping: ' + repr(row))
            if row['canonical_source_id'] in aliases:
                raise ValueError('Identity chains or cycles require a direct canonical mapping')
            con.execute('INSERT INTO phone_identity_map VALUES (?,?,?,?,?)',
                        (ids[row['source_id']], ids[row['canonical_source_id']], row['decided_by'], row['decided_at'], row['note']))
        for row in con.execute('SELECT phone_key,name FROM phone').fetchall():
            name, flag = text_value(row['name'])
            con.execute('INSERT INTO phone_clean VALUES (?,?,?,?)', (row['phone_key'], row['name'], name, flag))
        records, fences = prepared(con, mappings)
        for i, r in enumerate(records):
            con.execute('INSERT INTO specification_clean VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (r['phone_key'], r['retrieved_at'], r['row_number'], r['value_text'], r['value'], r['value_flag'],
                         r['value_text'], r['number'], r['secondary'], r['unit'], r['number_flag'],
                         r['value_text'], r['category'], r['category_flag'], r['source_field'], r['file_key']))
            if fail_after is not None and i >= fail_after:
                raise RuntimeError('Injected M3 failure after insertion')
        summary = {
            'phone_clean': {'rows': con.execute('SELECT COUNT(*) FROM phone_clean').fetchone()[0],
                            'name_flag': dict(con.execute('SELECT name_flag,COUNT(*) FROM phone_clean GROUP BY name_flag').fetchall())},
            'specification_clean': {'rows': len(records),
                                    **{col: dict(Counter(r[col] for r in records)) for col in ('value_flag','number_flag','category_flag')}},
            'mappings_loaded': {key: len(value) for key, value in mappings.items()},
            'unmatched_mapping_entries': {
                'os_categories': [r['alias'] for r in mappings['os_categories'] if not any(
                    x['source_field'] == 'os' and category(x['value'], [r]) for x in records)],
                'field_rules': [r['source_field'] for r in mappings['field_rules'] if not any(x['source_field'] == r['source_field'] for x in records)],
                'currencies': [r['alias'] for r in mappings['currencies'] if not any(
                    x['source_field'] == 'price' and r['alias'] in (x['value'] or '') for x in records)],
                'phone_identity': [],
            },
            'robust_cohorts': len(fences), 'status': 'COMPLETE',
        }
        con.commit()
        if verbose:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print('STATUS: COMPLETE')
        return summary
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--mappings', type=Path, default=cfg.MAPPINGS)
    args = parser.parse_args()
    try:
        clean(args.db, args.mappings)
    except Exception as exc:
        parser.exit(1, 'STATUS: FAILED: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
