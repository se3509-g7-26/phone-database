import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from checks import fixture, run_checks, write_landed
from db import connect, contents_digest, counts
from load import LoadError, SpecsParser, load, timestamp


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw = self.root / 'raw'
        self.database = self.root / 'phones.db'
        fixture(self.raw, phone_id='123', item_id='Q123')

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, sql, parameters=()):
        con = connect(self.database)
        try:
            return [tuple(row) for row in con.execute(sql, parameters)]
        finally:
            con.close()

    def digest(self):
        con = connect(self.database)
        try:
            return contents_digest(con)
        finally:
            con.close()

    def test_required_checks_and_idempotence(self):
        load(self.raw, self.database, verbose=False)
        before = self.digest()
        self.assertTrue(run_checks(self.database, self.raw, temp_parent=self.root))
        self.assertEqual(before, self.digest())  # Checks never mutate the real DB.

    def test_latest_retrieval_wins_with_snapshots_and_stable_keys(self):
        load(self.raw, self.database, verbose=False)
        key = self.read('SELECT phone_key FROM phone')[0][0]
        html = '<h1>New name</h1><div id="specs-list"><table><th>Misc</th><td class="ttl">Price</td><td class="nfo" data-spec="price">n/a</td></table></div>'
        # Lexically FIRST filename has the newest retrieval, including an offset.
        write_landed(self.raw, 'gsmarena', 'a-new.html', html,
                     'https://m.gsmarena.com/renamed-123.php', '2026-10-19T13:00:00+03:00')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([(key, 'New name', '2026-10-19T10:00:00.000000Z')],
                         self.read('SELECT phone_key,name,retrieved_at FROM phone'))
        self.assertEqual([(2,)], self.read('SELECT COUNT(*) FROM phone_snapshot'))
        self.assertIn(('n/a',), self.read('SELECT value_text FROM specification'))
        before = self.digest()
        load(self.raw, self.database, verbose=False)
        self.assertEqual(before, self.digest())

    def test_tied_timestamp_has_same_winner_across_incremental_loads(self):
        html = '<h1>Winner</h1><div id="specs-list"><table><td class="nfo">value</td></table></div>'
        write_landed(self.raw, 'gsmarena', 'z-last.html', html, 'https://m.gsmarena.com/test-123.php')
        load(self.raw, self.database, verbose=False)
        write_landed(self.raw, 'gsmarena', 'a-first.html', html.replace('Winner', 'Loser'),
                     'https://m.gsmarena.com/test-123.php')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([('Winner',)], self.read('SELECT name FROM phone'))
        self.assertEqual([(1,)], self.read('SELECT COUNT(*) FROM specification'))

    def test_unknown_reference_quarantined_and_later_resolved(self):
        wd = {'results': {'bindings': [{'phone': {'value': 'http://www.wikidata.org/entity/Q999'},
                                        'gsmId': {'value': '999'}}]}}
        write_landed(self.raw, 'wikidata', 'unknown.json', json.dumps(wd), 'https://query.wikidata.org/sparql')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([('Unknown GSMArena phone ID',)], self.read('SELECT reason FROM quarantine'))
        html = '<h1>Late phone</h1><div id="specs-list"><table><td class="nfo">value</td></table></div>'
        write_landed(self.raw, 'gsmarena', 'late.html', html, 'https://m.gsmarena.com/late-999.php')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([(0,)], self.read('SELECT COUNT(*) FROM quarantine'))
        self.assertEqual([(2,)], self.read('SELECT COUNT(*) FROM phone_item_link'))

    def test_many_to_many_links_keep_both_directions(self):
        html = '<h1>Second phone</h1><div id="specs-list"><table><td class="nfo">text</td></table></div>'
        write_landed(self.raw, 'gsmarena', 'second.html', html, 'https://m.gsmarena.com/second-456.php')
        wd = {'results': {'bindings': [
            {'phone': {'value': 'http://www.wikidata.org/entity/Q123'}, 'gsmId': {'value': '456'}},
            {'phone': {'value': 'http://www.wikidata.org/entity/Q456'}, 'gsmId': {'value': '123'}}]}}
        write_landed(self.raw, 'wikidata', 'extra.json', json.dumps(wd), 'https://query.wikidata.org/sparql')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([(3,)], self.read('SELECT COUNT(*) FROM phone_item_link'))
        self.assertEqual([(2,)], self.read('SELECT COUNT(*) FROM wikidata_item'))

    def test_unknown_article_item_and_invalid_record_are_quarantined(self):
        page = {'pageid': 789, 'title': 'Unknown item', 'pageprops': {'wikibase_item': 'Q789'},
                'revisions': [{'timestamp': '2026-10-18T00:00:00Z',
                               'slots': {'main': {'content': 'Source text'}}}]}
        write_landed(self.raw, 'wikipedia', 'unknown.json', json.dumps({'query': {'pages': [page]}}),
                     'https://en.wikipedia.org/w/api.php')
        bad_rows = [None, {'phone': {'value': 'Q123'}, 'gsmId': {'value': '123'}, 'article': 'wrong shape'}]
        write_landed(self.raw, 'wikidata', 'invalid.json', json.dumps({'results': {'bindings': bad_rows}}),
                     'https://query.wikidata.org/sparql')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([(3,)], self.read('SELECT COUNT(*) FROM quarantine'))
        self.assertEqual([], self.read('PRAGMA foreign_key_check'))
        self.assertEqual([(1,)], self.read('SELECT COUNT(*) FROM wikipedia_article'))

    def test_missing_source_and_orphan_metadata_are_fatal(self):
        (self.raw / 'wikidata' / 'items.json').unlink()
        with self.assertRaises(LoadError):
            load(self.raw, self.database, verbose=False)
        fixture(self.raw)
        (self.raw / 'gsmarena' / 'orphan.meta.json').write_text('{}')
        with self.assertRaises(LoadError):
            load(self.raw, self.database, verbose=False)

    def test_bad_body_after_new_model_rolls_back_all_contents(self):
        load(self.raw, self.database, verbose=False)
        before = self.digest()
        broken = self.root / 'broken'
        fixture(broken, broken=True)
        with self.assertRaises(LoadError):
            load(broken, self.database, verbose=False)
        self.assertEqual(before, self.digest())

    def test_empty_db_failure_rolls_back_schema_too(self):
        fixture(self.raw, broken=True)
        with self.assertRaises(LoadError):
            load(self.raw, self.database, verbose=False)
        self.assertEqual([], self.read("SELECT name FROM sqlite_master WHERE type='table'"))

    def test_changed_landed_file_rejected_and_missing_metadata_fails(self):
        load(self.raw, self.database, verbose=False)
        before = self.digest()
        path = self.raw / 'gsmarena' / 'model.html'
        data = path.read_text().replace('Check model', 'Other model')
        path.write_text(data)
        with self.assertRaises(LoadError):
            load(self.raw, self.database, verbose=False)
        self.assertEqual(before, self.digest())
        path.with_suffix('.meta.json').unlink()
        with self.assertRaises(LoadError):
            load(self.raw, self.database, verbose=False)

    def test_spec_parser_preserves_continuations_and_superscripts(self):
        parser = SpecsParser()
        parser.feed('<h1>A Phone</h1><div id="specs-list"><table><th>Display</th><tr><tr>'
                    '<td class="ttl">Size</td><td class="nfo" data-spec="size">10 cm<sup>2</sup><br>more</td>'
                    '<td class="ttl"> </td><td class="nfo">continued</td>'
                    '<td class="ttl">Empty</td><td class="nfo"> </td></table></div>')
        self.assertEqual([('Display', 'Size', 'size', '10 cm2 more'),
                          ('Display', '', None, 'continued'), ('Display', 'Empty', None, None)], parser.rows)

    def test_slowdown_quarantined_catalog_retained_as_provenance(self):
        write_landed(self.raw, 'gsmarena', 'blocked.html', 'please slow down', 'https://m.gsmarena.com/x-987.php')
        write_landed(self.raw, 'gsmarena', 'catalog.html', '<h1>Index</h1>', 'https://m.gsmarena.com/acer-phones-59.php')
        stats = load(self.raw, self.database, verbose=False)
        self.assertEqual(1, stats['catalog_files'])
        self.assertEqual([(1,)], self.read('SELECT COUNT(*) FROM quarantine'))
        self.assertEqual([(1,)], self.read('SELECT COUNT(*) FROM phone'))

    def test_invalid_comment_bytes_do_not_change_valid_specifications(self):
        html = (b'<h1>Model</h1><div id="specs-list"><table><td class="nfo" data-spec="price">'
                b'About 100 EUR</td></table></div><p>Comment: \xed\xa0\xbd</p>')
        write_landed(self.raw, 'gsmarena', 'comment.html', html, 'https://m.gsmarena.com/comment-456.php')
        stats = load(self.raw, self.database, verbose=False)
        self.assertEqual(1, stats['encoding_issue_files'])
        self.assertEqual(3, stats['invalid_utf8_bytes'])
        self.assertEqual([(0,)], self.read('SELECT COUNT(*) FROM quarantine'))
        self.assertEqual([(2,)], self.read('SELECT COUNT(*) FROM phone'))

    def test_invalid_specification_bytes_quarantine_model_without_replacement(self):
        html = b'<h1>Bad model</h1><div id="specs-list"><table><td class="nfo">\xed\xa0\xbd</td></table></div>'
        write_landed(self.raw, 'gsmarena', 'bad-field.html', html, 'https://m.gsmarena.com/bad-456.php')
        load(self.raw, self.database, verbose=False)
        self.assertEqual([('Invalid UTF-8 in model fields',)], self.read('SELECT reason FROM quarantine'))
        self.assertEqual([(1,)], self.read('SELECT COUNT(*) FROM phone'))

    def test_timezone_normalization_and_rejection(self):
        self.assertEqual('2026-10-09T13:02:22.074113Z', timestamp('20261009T130222074113Z'))
        self.assertEqual('2026-10-18T09:00:00.000000Z', timestamp('2026-10-18T12:00:00+03:00'))
        with self.assertRaises(ValueError):
            timestamp('2026-10-18T12:00:00')
        with self.assertRaises(ValueError):
            timestamp('2026-99-18T12:00:00Z')


if __name__ == '__main__':
    unittest.main()
