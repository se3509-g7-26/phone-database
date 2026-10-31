"""Read-only M3 investigation; notebook and exports use this same code."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics

import clean_config as cfg
from clean import match_key, normal_text, prepared, read_mappings
from db import DEFAULT_DB, ROOT, TABLES, connect


def write_csv(path, header, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def profile(database=DEFAULT_DB, output=None):
    con = connect(database, read_only=True)
    try:
        # Raw observations precede all hypothetical cleaning measurements below.
        from db import counts as table_counts
        counts = table_counts(con)
        text_columns = list(con.execute('SELECT source_field,section,label,value_text FROM specification'))
        distinct = Counter((r['source_field'], r['section'], r['label'], repr(r['value_text'])) for r in text_columns)
        records, fences = prepared(con, read_mappings(cfg.MAPPINGS))
        current = {r['phone_key']: dict(r) for r in con.execute('SELECT * FROM phone')}
        latest = [r for r in records if r['retrieved_at'] == current[r['phone_key']]['retrieved_at']]
        by_field = defaultdict(list)
        for r in latest:
            by_field[r['source_field']].append(r)
        summary = {'m2_counts': counts, 'latest_fields': {}, 'raw_text': {}, 'by_announcement_year': {},
                   'by_os': {}, 'sequence': {}, 'identity': {}, 'unusual_examples': [], 'cross_field': {}}
        raw_values = [r['value_text'] for r in records if r['value_text'] is not None]
        summary['raw_text'] = {
            'null_cells': sum(r['value_text'] is None for r in records),
            'explicit_missing_tokens': dict(Counter(repr(v) for v in raw_values if match_key(v) in cfg.MISSING_TOKENS)),
            'normalization_changes': sum(normal_text(v) != v for v in raw_values),
            'name_normalization_changes': sum(normal_text(r['name']) != r['name'] for r in current.values()),
            'top_values_repr': Counter(repr(v) for v in raw_values).most_common(15),
        }
        for field in cfg.NUMERIC_FIELDS + ('os',):
            rows = by_field[field]
            numbers = [r['number'] for r in rows if r['number'] is not None]
            summary['latest_fields'][field] = {
                'cells': len(rows), 'entities': len({r['phone_key'] for r in rows}),
                'absent_entities': len(current) - len({r['phone_key'] for r in rows}),
                'null_cells': sum(r['value_text'] is None for r in rows),
                'numeric_usable': len(numbers),
                'min_median_max': [min(numbers), statistics.median(numbers), max(numbers)] if numbers and field != 'price' else None,
                'by_unit': {unit: {'n':len(vals), 'min_median_max':[min(vals),statistics.median(vals),max(vals)]}
                            for unit in sorted({r['unit'] for r in rows if r['number'] is not None})
                            for vals in [[r['number'] for r in rows if r['number'] is not None and r['unit']==unit]]},
                'number_flags': dict(Counter(r['number_flag'] for r in rows)),
                'top_raw_repr': Counter(repr(r['value_text']) for r in rows).most_common(6),
            }
        values = {(r['phone_key'], r['source_field']): r for r in latest if r['source_field'] in cfg.NUMERIC_FIELDS + ('os',)}
        for key in current:
            year = values.get((key, 'year'), {}).get('number')
            os_value = values.get((key, 'os'), {}).get('category') or 'unmapped_or_absent'
            for section, group in (('by_announcement_year', str(int(year)) if year else 'unknown'), ('by_os', os_value)):
                bucket = summary[section].setdefault(group, {'entities': 0, 'price_absent': 0, 'price_unusable': 0, 'memory_unusable': 0})
                bucket['entities'] += 1
                bucket['price_absent'] += int((key, 'price') not in values)
                bucket['price_unusable'] += int(values.get((key, 'price'), {}).get('number') is None)
                bucket['memory_unusable'] += int(values.get((key, 'internalmemory'), {}).get('number') is None)
        sequence_rows = []
        for row in con.execute('SELECT phone_key,COUNT(*) AS n,MIN(retrieved_at) AS first,MAX(retrieved_at) AS last FROM phone_snapshot GROUP BY phone_key'):
            sequence_rows.append(tuple(row))
        summary['sequence']['snapshots_per_entity'] = dict(Counter(r[1] for r in sequence_rows))
        changes = list(con.execute('SELECT s.phone_key,s.retrieved_at,s.source_field,s.value_text FROM specification s WHERE s.phone_key IN (SELECT phone_key FROM phone_snapshot GROUP BY phone_key HAVING COUNT(*)>1) ORDER BY s.phone_key,s.source_field,s.retrieved_at,s.row_number'))
        summary['sequence']['repeated_observations'] = [dict(r) for r in changes if r['source_field'] in cfg.NUMERIC_FIELDS + ('os',)]
        summary['sequence']['raw_time_range'] = tuple(con.execute('SELECT MIN(retrieved_at),MAX(retrieved_at) FROM raw_file').fetchone())
        summary['identity']['models_multiple_qids'] = [dict(r) for r in con.execute('SELECT p.source_id,COUNT(*) AS n FROM phone_item_link l JOIN phone p USING(phone_key) GROUP BY l.phone_key HAVING COUNT(*)>1')]
        summary['identity']['qids_multiple_models'] = [dict(r) for r in con.execute('SELECT w.source_id,COUNT(*) AS n FROM phone_item_link l JOIN wikidata_item w USING(item_key) GROUP BY l.item_key HAVING COUNT(*)>1')]
        name_ids = defaultdict(list)
        for r in current.values():
            name_ids[match_key(r['name'])].append(r['source_id'])
        summary['identity']['normalized_name_collisions'] = {k: v for k, v in name_ids.items() if len(v)>1}
        summary['identity']['quarantine_reasons'] = dict(con.execute('SELECT reason,COUNT(*) FROM quarantine GROUP BY reason').fetchall())
        summary['identity']['wikipedia_redirects'] = con.execute("SELECT COUNT(*) FROM article_revision WHERE lower(ltrim(content)) LIKE '#redirect%'").fetchone()[0]
        summary['identity']['articles_without_qid'] = con.execute('SELECT COUNT(*) FROM wikipedia_article WHERE item_key IS NULL').fetchone()[0]
        summary['invalid_examples'] = [{'source_id':current[r['phone_key']]['source_id'],'name':current[r['phone_key']]['name'],
                                      'field':r['source_field'],'raw':r['value_text'],'flag':r['number_flag']}
                                     for r in latest if r['number_flag'].startswith('invalid')]
        summary['cross_field']['release_before_announcement'] = []
        summary['cross_field']['future_exact_announcement'] = []
        import re
        from datetime import datetime
        for r in by_field['year']:
            raw = r['value_text'] or ''
            m = re.match(r'^(\d{4}), ([A-Za-z]+) (\d{1,2})\b', raw)
            if m:
                try:
                    announced = datetime.strptime(' '.join(m.groups()), '%Y %B %d').date()
                    if announced.isoformat() > r['retrieved_at'][:10]:
                        summary['cross_field']['future_exact_announcement'].append({'source_id': current[r['phone_key']]['source_id'], 'raw':raw})
                except ValueError:
                    pass
            m = re.search(r'Released\s+(\d{4})', raw)
            leading = re.match(r'^(\d{4})',raw)
            if m and leading and int(m[1]) < int(leading[1]):
                summary['cross_field']['release_before_announcement'].append({'source_id': current[r['phone_key']]['source_id'], 'raw':raw})
        for r in latest:
            if r['number_flag'].startswith('unusual'):
                summary['unusual_examples'].append({'source_id': current[r['phone_key']]['source_id'], 'name':current[r['phone_key']]['name'],
                                                   'field':r['source_field'], 'raw':r['value_text'], 'number':r['number'], 'unit':r['unit'], 'flag':r['number_flag']})
        summary['robust_fences'] = [{'field': k[0], 'unit': k[1], 'os': k[2], 'low':v[0], 'high':v[1]} for k,v in sorted(fences.items())]
        if output:
            output = Path(output)
            output.mkdir(parents=True, exist_ok=True)
            (output/'profile.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            write_csv(output/'distinct-spec-text.csv', ('source_field','section','label','value_repr','count'),
                      ((f, s, l, v, n) for (f,s,l,v),n in sorted(distinct.items(), key=lambda x: repr(x[0]))))
            write_csv(output/'entity-coverage.csv', ('phone_key','source_id','name_repr','snapshots','first_seen','last_seen'),
                      ((key,current[key]['source_id'],repr(current[key]['name']),n,first,last) for key,n,first,last in sequence_rows))
            write_csv(output/'entity-measurements.csv', ('phone_key','source_id','field','raw_repr','number','ram_gb','unit','flag'),
                      ((r['phone_key'],current[r['phone_key']]['source_id'],r['source_field'],repr(r['value_text']),r['number'],r['secondary'],r['unit'],r['number_flag']) for r in latest if r['source_field'] in cfg.NUMERIC_FIELDS))
            per_entity = defaultdict(list)
            for r in records:
                if r['source_field'] in cfg.NUMERIC_FIELDS:
                    per_entity[(r['phone_key'],r['source_field'])].append(r)
            entity_profiles = []
            for key in current:
                for field in cfg.NUMERIC_FIELDS:
                    rows = per_entity[(key,field)]
                    nums = [r['number'] for r in rows if r['number'] is not None]
                    units = {r['unit'] for r in rows if r['number'] is not None}
                    entity_profiles.append((key,current[key]['source_id'],field,len(rows),sum(r['value_text'] is None for r in rows),
                                            len(nums),min(nums) if nums and len(units)==1 else None,
                                            statistics.median(nums) if nums and len(units)==1 else None,
                                            max(nums) if nums and len(units)==1 else None,
                                            repr(Counter(repr(r['value_text']) for r in rows).most_common())))
            write_csv(output/'entity-field-profile.csv',('phone_key','source_id','field','observations','null_count','trusted_count','min','median','max','raw_modes_repr'),entity_profiles)
            write_csv(output/'phone-text.csv',('source_id_repr','name_repr','url_repr','count'),
                      ((repr(r['source_id']),repr(r['name']),repr(r['source_url']),1) for r in current.values()))
        return summary
    finally:
        con.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--output', type=Path, default=ROOT/'docs'/'m3')
    args = parser.parse_args()
    result = profile(args.db, args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('unusual_examples','sequence')}, ensure_ascii=False, indent=2))
