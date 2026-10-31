"""M3 regression tests; all mutations and failure injections use temporary DBs."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import clean_config as cfg
from checks import fixture
from clean import clean, match_key, numeric, read_mappings, text_value
from db import ROOT, connect as db_connect, contents_digest
from load import load
from validate import validate


CLEAN_SELECTS = (
    'SELECT * FROM phone_clean ORDER BY phone_key',
    'SELECT * FROM specification_clean ORDER BY phone_key,retrieved_at,row_number',
    'SELECT * FROM field_rule_map ORDER BY source_field',
    'SELECT * FROM os_category_map ORDER BY alias',
    'SELECT * FROM currency_map ORDER BY alias',
    'SELECT * FROM phone_identity_map ORDER BY phone_key',
)


@contextlib.contextmanager
def connect(*args, **kwargs):
    con = db_connect(*args, **kwargs)
    try:
        with con:
            yield con
    finally:
        con.close()


def clean_contents(con):
    return [[tuple(r) for r in con.execute(sql)] for sql in CLEAN_SELECTS]


class CleanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root/'phones.db'
        fixture(self.root/'raw')
        load(self.root/'raw', self.db, verbose=False)
        with connect(self.db) as con:
            phone = con.execute('SELECT * FROM phone LIMIT 1').fetchone()
            self.key = phone['phone_key']
            last = con.execute('SELECT MAX(row_number) FROM specification WHERE phone_key=?', (self.key,)).fetchone()[0]
            for i, (field, value) in enumerate((('price','About 100 EUR'), ('year','2025'), ('os','Android 14'),
                                               ('internalmemory','512MB 256MB RAM'), ('weight','-5 g'),
                                               ('batdescription1','0 mAh'), ('displaysize','6.5 inches')), start=last+1):
                con.execute('INSERT INTO specification VALUES (?,?,?,?,?,?,?,?)',
                            (self.key,phone['retrieved_at'],i,'Test',field,field,value,phone['file_key']))
        clean(self.db, verbose=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_raw_untouched_and_repeat_contents_identical(self):
        with connect(self.db) as con:
            raw, cleaned = contents_digest(con), clean_contents(con)
        clean(self.db, verbose=False)
        with connect(self.db) as con:
            self.assertEqual(raw, contents_digest(con))
            self.assertEqual(cleaned, clean_contents(con))

    def test_database_failure_rolls_back_complete_layer(self):
        with connect(self.db) as con:
            raw, before = contents_digest(con), clean_contents(con)
            con.execute("CREATE TRIGGER m3_test_failure BEFORE INSERT ON specification_clean WHEN NEW.source_field='weight' BEGIN SELECT RAISE(ABORT,'injected database failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            clean(self.db, verbose=False)
        with connect(self.db) as con:
            self.assertEqual(before, clean_contents(con))
            self.assertEqual(raw, contents_digest(con))

    def test_first_build_ddl_and_rows_roll_back_together(self):
        other = self.root/'fresh.db'
        load(self.root/'raw', other, verbose=False)
        with self.assertRaises(RuntimeError):
            clean(other, verbose=False, fail_after=0)
        with connect(other) as con:
            self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='phone_clean'").fetchone())

    def test_ambiguous_missing_invalid_and_units(self):
        currencies = read_mappings(cfg.MAPPINGS)['currencies']
        def parse(value, kind):
            return numeric(value,kind,'2026-10-09T00:00:00.000000Z',currencies)
        self.assertEqual((.512,.256,'GB','unit_converted'),parse('512MB 256MB RAM','memory'))
        self.assertEqual((100.,None,'EUR','ok'),parse('About 100 EUR','price'))
        self.assertEqual('ambiguous',parse('64GB 4GB RAM, 128GB 8GB RAM','memory')[-1])
        self.assertEqual('ambiguous',parse('$ 10 / € 20','price')[-1])
        self.assertEqual('invalid_nonpositive',parse('-5 EUR','price')[-1])
        self.assertEqual('invalid_nonpositive',parse('0 mAh','battery')[-1])
        self.assertEqual((16000.,None,'mAh','ok'),parse('Li-Ion 16,000 mAh, non-removable','battery'))
        self.assertEqual((29999.,None,'INR','ok'),parse('₹ 29,999','price'))
        self.assertEqual('unparsed',parse('Li-Ion 16,00 mAh','battery')[-1])
        self.assertEqual('invalid_year',parse('2009, April. Released 2008, July','year')[-1])
        self.assertEqual('invalid_year',parse('2026, December 01','year')[-1])
        self.assertEqual('invalid_year',parse('9999','year')[-1])
        self.assertEqual('unparsed',parse('32GB','memory')[-1])
        self.assertEqual((None,'missing_token'),text_value(' n/a '))
        self.assertEqual(('No','ok'),text_value('No'))
        self.assertEqual('istanbul',match_key('İSTANBUL'))

    def test_mapping_changes_and_restoration_are_idempotent(self):
        mapped = self.root/'mappings'
        shutil.copytree(cfg.MAPPINGS,mapped)
        csv_path = mapped/'os_categories.csv'
        original = csv_path.read_text(encoding='utf-8')
        csv_path.write_text(original.replace('Android,Android,','Android,Android reviewed,'),encoding='utf-8')
        clean(self.db,mapped,verbose=False)
        with connect(self.db) as con:
            self.assertEqual('Android reviewed',con.execute("SELECT category FROM specification_clean WHERE source_field='os'").fetchone()[0])
        csv_path.write_text(original,encoding='utf-8')
        clean(self.db,mapped,verbose=False)
        with connect(self.db) as con:
            self.assertEqual('Android',con.execute("SELECT category FROM specification_clean WHERE source_field='os'").fetchone()[0])

    def test_threshold_change_only_changes_outlier_flags_and_restores(self):
        with connect(self.db) as con:
            p = con.execute('SELECT * FROM phone LIMIT 1').fetchone()
            for i in range(25):
                source_id = str(10000+i)
                cursor = con.execute('INSERT INTO phone(source_id,name,source_url,file_key,retrieved_at) VALUES(?,?,?,?,?)',
                                     (source_id,'Threshold fixture '+source_id,'https://example.test/'+source_id,p['file_key'],p['retrieved_at']))
                key = cursor.lastrowid
                con.execute('INSERT INTO phone_snapshot VALUES(?,?,?,?)',(key,p['retrieved_at'],'Fixture',p['file_key']))
                for ordinal,field,value in ((1,'os','Android 14'),(2,'price','About '+str(100+i if i<24 else 10000)+' EUR')):
                    con.execute('INSERT INTO specification VALUES(?,?,?,?,?,?,?,?)',(key,p['retrieved_at'],ordinal,'Fixture',field,field,value,p['file_key']))
        clean(self.db,verbose=False)
        with connect(self.db) as con:
            before, raw = clean_contents(con), contents_digest(con)
        original = cfg.IQR_FACTOR
        try:
            cfg.IQR_FACTOR = 10000
            clean(self.db,verbose=False)
            with connect(self.db) as con:
                after = clean_contents(con)
                self.assertEqual(raw,contents_digest(con))
            self.assertNotEqual(before,after)
            for left,right in zip(before[1],after[1]):
                self.assertEqual(left[:10]+left[11:],right[:10]+right[11:])
        finally:
            cfg.IQR_FACTOR = original
        clean(self.db,verbose=False)
        with connect(self.db) as con:
            self.assertEqual(before,clean_contents(con))

    def test_every_stop_check_fails_and_cli_returns_nonzero(self):
        attacks = (
            ('same grain and row counts','DELETE FROM specification_clean WHERE row_number=(SELECT MIN(row_number) FROM specification_clean)'),
            ('raw keys preserved','UPDATE specification_clean SET row_number=row_number+1000 WHERE row_number=(SELECT MIN(row_number) FROM specification_clean)'),
            ('no impossible numeric values',"UPDATE specification_clean SET number=-1 WHERE source_field='price'"),
            ('all foreign keys resolve',"INSERT INTO phone_clean VALUES(999999,'orphan','orphan','ok')"),
            ('all tables STRICT','CREATE TABLE not_strict_test(x TEXT)'),
            ('raw companions exact',"UPDATE phone_clean SET name_raw='altered'"),
            ('flags agree with cleaned values',"UPDATE specification_clean SET number_flag='ambiguous' WHERE source_field='price'"),
        )
        for name, attack in attacks:
            with self.subTest(check=name):
                target = self.root/'damaged.db'
                with connect(self.db, read_only=True) as source, contextlib.closing(sqlite3.connect(target)) as dest:
                    source.backup(dest)
                with sqlite3.connect(target) as con:
                    con.execute(attack)
                con.close()
                checks = validate(target, verbose=False)
                self.assertIn('STOP',[level for level,label,_ in checks if label==name])
                result = subprocess.run([sys.executable,str(ROOT/'src'/'validate.py'),'--db',str(target)],capture_output=True,text=True)
                self.assertNotEqual(0,result.returncode)
                self.assertIn('STOP  '+name,result.stdout)
                target.unlink()

    def test_warnings_do_not_fail_cli(self):
        self.assertNotIn('STOP',[level for level,_,_ in validate(self.db,verbose=False)])
        result = subprocess.run([sys.executable,str(ROOT/'src'/'validate.py'),'--db',str(self.db)],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertIn('WARN',result.stdout)

    def test_flag_typo_rejected_by_database(self):
        with connect(self.db) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE specification_clean SET number_flag='typo'")


if __name__ == '__main__':
    unittest.main()
