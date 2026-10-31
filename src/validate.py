"""M3 data-quality expectations: WARN continues, STOP returns a failing status."""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

import clean_config as cfg
from db import DEFAULT_DB, connect


def validate(database=DEFAULT_DB, *, verbose=True):
    con = connect(database, read_only=True)
    checks = []

    def result(name, passed, detail, severity='STOP'):
        checks.append(('PASS' if passed else severity, name, str(detail)))

    try:
        pairs = con.execute('SELECT (SELECT COUNT(*) FROM phone),(SELECT COUNT(*) FROM phone_clean),'
                            '(SELECT COUNT(*) FROM specification),(SELECT COUNT(*) FROM specification_clean)').fetchone()
        result('same grain and row counts', pairs[0] == pairs[1] and pairs[2] == pairs[3], tuple(pairs))
        badkeys = con.execute('SELECT COUNT(*) FROM specification s LEFT JOIN specification_clean c '
                             'USING(phone_key,retrieved_at,row_number) WHERE c.phone_key IS NULL').fetchone()[0]
        badkeys += con.execute('SELECT COUNT(*) FROM phone p LEFT JOIN phone_clean c USING(phone_key) WHERE c.phone_key IS NULL').fetchone()[0]
        result('raw keys preserved', badkeys == 0, badkeys)
        invalid = con.execute("SELECT COUNT(*) FROM specification_clean WHERE number<=0 OR ram_gb<=0 OR "
                              "(source_field='year' AND (number<? OR number>CAST(substr(retrieved_at,1,4) AS INTEGER) OR number<>CAST(number AS INTEGER))) "
                              "OR (number IS NOT NULL AND (abs(number)>? OR (source_field='price' AND unit IS NULL)))",
                              (cfg.MIN_YEAR, sys.float_info.max)).fetchone()[0]
        from clean import numeric
        for row in con.execute("SELECT value_raw,number,retrieved_at FROM specification_clean WHERE source_field='year' AND number IS NOT NULL"):
            if numeric(row['value_raw'],'year',row['retrieved_at'],[])[-1] == 'invalid_year':
                invalid += 1
        result('no impossible numeric values', invalid == 0, invalid)
        foreign = con.execute('PRAGMA foreign_key_check').fetchall()
        result('all foreign keys resolve', not foreign, len(foreign))
        not_strict = [r['name'] for r in con.execute('PRAGMA table_list') if r['type'] == 'table' and
                      not r['name'].startswith('sqlite_') and not r['strict']]
        result('all tables STRICT', not not_strict, not_strict)
        raw_changed = con.execute('SELECT COUNT(*) FROM specification s JOIN specification_clean c '
                                 'USING(phone_key,retrieved_at,row_number) WHERE c.value_raw IS NOT s.value_text '
                                 'OR c.number_raw IS NOT s.value_text OR c.category_raw IS NOT s.value_text '
                                 'OR c.source_field IS NOT s.source_field OR c.file_key IS NOT s.file_key').fetchone()[0]
        raw_changed += con.execute('SELECT COUNT(*) FROM phone p JOIN phone_clean c USING(phone_key) WHERE c.name_raw IS NOT p.name').fetchone()[0]
        result('raw companions exact', raw_changed == 0, raw_changed)
        inconsistency = con.execute("SELECT COUNT(*) FROM specification_clean WHERE "
                                    "(number_flag IN ('missing_not_reported','missing_token','unparsed','ambiguous','invalid_nonpositive','invalid_year','not_applicable') AND (number IS NOT NULL OR ram_gb IS NOT NULL)) "
                                    "OR (number_flag IN ('ok','unit_converted','unusual_low','unusual_high') AND number IS NULL) "
                                    "OR (value_flag IN ('missing_not_reported','missing_token') AND value IS NOT NULL) "
                                    "OR (category_flag IN ('unmapped','not_applicable','missing_not_reported') AND category IS NOT NULL)").fetchone()[0]
        result('flags agree with cleaned values', inconsistency == 0, inconsistency)
        # Absent rows count as unavailable; checking only existing cells hides missing fields.
        shortages = []
        for field in cfg.NUMERIC_FIELDS:
            n = con.execute('SELECT COUNT(DISTINCT phone_key) FROM specification_current WHERE source_field=? AND number IS NOT NULL', (field,)).fetchone()[0]
            share = 1 - n / pairs[0] if pairs[0] else 1
            if share > cfg.MISSING_WARN_SHARE:
                shortages.append(field + '=' + format(share, '.1%'))
        threshold_label = format(cfg.MISSING_WARN_SHARE, '.0%')
        result('numeric missing share per catalog field <=' + threshold_label, not shortages, ', '.join(shortages) or 'all below threshold', 'WARN')
        per_entity = con.execute("SELECT COUNT(*) FROM phone p WHERE "
                                "(SELECT COUNT(DISTINCT s.source_field) FROM specification_current s WHERE s.phone_key=p.phone_key AND s.number IS NOT NULL)<?",
                                ((1 - cfg.MISSING_WARN_SHARE) * len(cfg.NUMERIC_FIELDS),)).fetchone()[0]
        result('numeric missing share per entity <=' + threshold_label, per_entity == 0, str(per_entity) + ' models exceed threshold', 'WARN')
        newest = con.execute('SELECT MAX(retrieved_at) FROM phone').fetchone()[0]
        cutoff = (datetime.fromisoformat(newest.replace('Z', '+00:00')) - timedelta(days=cfg.COVERAGE_DAYS)).isoformat(timespec='microseconds').replace('+00:00', 'Z') if newest else ''
        stale = con.execute('SELECT COUNT(*) FROM (SELECT resolved_phone_key,MAX(retrieved_at) AS last_seen FROM phone_resolved GROUP BY resolved_phone_key) WHERE last_seen<?', (cutoff,)).fetchone()[0]
        result('resolved entities covered in latest snapshot window', stale == 0, str(stale) + ' outside ' + str(cfg.COVERAGE_DAYS) + ' days; anchor=' + str(newest), 'WARN')
        ambiguous = con.execute("SELECT COUNT(*) FROM specification_current WHERE source_field='price' AND number_flag IN ('ambiguous','unparsed')").fetchone()[0]
        result('price strings have one interpretable amount', ambiguous == 0, str(ambiguous) + ' unresolved current price cells', 'WARN')
        links = con.execute('SELECT COUNT(*) FROM (SELECT phone_key FROM phone_item_link GROUP BY phone_key HAVING COUNT(*)>1)').fetchone()[0]
        result('model to Wikidata identity unambiguous', links == 0, str(links) + ' models have multiple QIDs; no automatic merge', 'WARN')
        # M2 does not contain source-verified market/configuration/launch evidence.
        result('launch MSRP evidence available', False, 'catalog prices only; no verified launch/configuration/market linkage', 'WARN')
    except Exception as exc:
        result('validation executable', False, str(exc))
    finally:
        con.close()
    if verbose:
        for level, name, detail in checks:
            print(level + '  ' + name + '  ' + detail)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    try:
        checks = validate(args.db)
        return int(any(level == 'STOP' for level, _, _ in checks))
    except Exception as exc:
        print('STOP  database accessible  ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
