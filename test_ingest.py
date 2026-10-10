import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import ingest


class IngestionRegressionTests(unittest.TestCase):
    def test_http_200_slowdown_retries_before_saving(self):
        c = ingest.Collector('test', 0, 20, 1)
        blocked = Mock(status_code=200, ok=True, content=b'B:H208 - please slow down! Try again in a minute.',
                       url='https://www.gsmarena.com/acer_f900-2717.php')
        good = Mock(status_code=200, ok=True, content=b'<html>phone</html>',
                    headers={'Content-Type': 'text/html'}, url=blocked.url)
        with patch.object(c.session, 'get', side_effect=[blocked, good]), \
                patch.object(c, 'save') as save, patch('ingest.time.sleep') as sleep, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.fetch('gsmarena', blocked.url), good.content)
            sleep.assert_called_once_with(60)
            save.assert_called_once_with('gsmarena', good.url, good.content, 'html')
        c.session.close()

    def test_gsmarena_requests_mobile_host_directly(self):
        c = ingest.Collector('test', 0, 20, 0)
        good = Mock(status_code=200, ok=True, content=b'<html>phone</html>',
                    headers={'Content-Type': 'text/html'},
                    url='https://m.gsmarena.com/acer_f900-2717.php')
        with patch.object(c.session, 'get', return_value=good) as get, \
                patch.object(c, 'save'), contextlib.redirect_stdout(io.StringIO()):
            c.fetch('gsmarena', 'https://www.gsmarena.com/acer_f900-2717.php')
            self.assertEqual(get.call_args.args[0], good.url)
        c.session.close()

    def test_square_brackets_are_requested_unencoded(self):
        url = 'https://m.gsmarena.com/vivo_y20s_[g]-10847.php'
        reply = MagicMock(status=200, url=url, headers={'Content-Type': 'text/html'})
        reply.read.return_value = b'<html>phone</html>'
        c = ingest.Collector('test', 0, 20, 0)
        with patch('ingest.urllib.request.urlopen', return_value=reply) as urlopen, \
                patch.object(c.session, 'get') as get, patch.object(c, 'save') as save, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.fetch('gsmarena', url.replace('//m.', '//www.')), reply.read())
            get.assert_not_called()
            self.assertEqual(urlopen.call_args.args[0].full_url, url)
            save.assert_called_once_with('gsmarena', url, reply.read(), 'html')
            # A saved copy is found again under the same unencoded address.
            with tempfile.TemporaryDirectory() as tmp:
                c.cached[url] = Path(tmp) / 'page.html'
                c.cached[url].write_bytes(reply.read())
                c.fetch('gsmarena', url)
            urlopen.assert_called_once()
        c.session.close()

    def models_fetched(self, pages):
        gsm = 'https://www.gsmarena.com/'
        c = Mock()
        c.fetch.side_effect = lambda source, url: pages[url.removeprefix(gsm)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(ingest, 'ROOT', Path(tmp)), \
                patch.object(ingest, 'RAW', Path(tmp) / 'raw'), contextlib.redirect_stdout(io.StringIO()):
            return ingest.ingest_gsm(c, None, None)

    def test_brand_filter_pages_are_not_models(self):
        self.assertEqual(self.models_fetched({
            'makers.php3': b'<a href="apple-phones-48.php">Apple</a>',
            'apple-phones-48.php': b'<a href="apple_iphone_17-13999.php">iPhone 17</a>'
                                   b'<a href="apple-phones-f-48-15.php">2015</a>',
            'apple_iphone_17-13999.php': b'<h1>iPhone 17</h1><td data-spec="year">2025</td>',
        }), 1)

    def test_slugs_with_punctuation_are_discovered(self):
        phone = b'<h1>Phone</h1><td data-spec="year">2025</td>'
        self.assertEqual(self.models_fetched({
            'makers.php3': b'<a href="at&amp;t-phones-57.php">AT&amp;T</a>',
            'at&t-phones-57.php': b'<a href="at&amp;t_quickfire-2598.php">Quickfire</a>'
                                  b'<a href="alcatel_pop_4+-7936.php">Pop 4+</a>'
                                  b'<a href="alcatel_3_(2025)-13886.php">3 (2025)</a>'
                                  b'<a href="at&amp;t-phones-f-57-0-p2.php">2</a>',
            'at&t-phones-f-57-0-p2.php': b'<a href="vivo_y20s_[g]-10847.php">Y20s [G]</a>',
            'at&t_quickfire-2598.php': phone, 'alcatel_pop_4+-7936.php': phone,
            'alcatel_3_(2025)-13886.php': phone, 'vivo_y20s_[g]-10847.php': phone,
        }), 4)

    def test_wikidata_linked_models_are_fetched_first(self):
        acer, nokia, zte = (f'https://www.gsmarena.com/{name}.php'
                            for name in ('acer_a1-1', 'nokia_3310-3', 'zte_z2-2'))
        self.assertEqual(ingest.fetch_order({acer, nokia, zte}, {'2'}), [zte, acer, nokia])

    def test_wikidata_ids_come_from_saved_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'wikidata'
            folder.mkdir()
            (folder / 'x.json').write_text(json.dumps({'results': {'bindings': [
                {'phone': {'value': 'Q1'}, 'gsmId': {'value': '11103'}}]}}))
            (folder / 'x.meta.json').write_text('{"bytes": 1}')
            with patch.object(ingest, 'RAW', Path(tmp)):
                self.assertEqual(ingest.wikidata_gsm_ids(), {'11103'})

    def test_paths_are_inside_project(self):
        self.assertEqual(ingest.ROOT, Path(ingest.__file__).resolve().parent)
        self.assertEqual(ingest.RAW, ingest.ROOT / 'data' / 'raw')

    def test_valid_dotenv_contact_and_independent_sources(self):
        settings = {'PHONE_DATA_USER_AGENT': 'PhoneProject/1 (contact: tester@example.org)'}
        def load_settings(*args, **kwargs):
            for key, value in settings.items():
                os.environ.setdefault(key, value)
        with patch.dict(os.environ, {}, clear=True), patch.object(ingest, 'load_dotenv', load_settings), \
                patch('sys.argv', ['ingest.py']), \
                patch.object(ingest, 'ingest_gsm', side_effect=ingest.IngestError('blocked')), \
                patch.object(ingest, 'ingest_wikimedia', return_value=(5, 2)) as wiki, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ingest.main(), 1)
            wiki.assert_called_once()

    def test_placeholder_contact_stops_before_requests(self):
        with patch.dict(os.environ, {'PHONE_DATA_USER_AGENT': 'your-email@example.com'}, clear=True), \
                patch.object(ingest, 'load_dotenv'), patch('sys.argv', ['ingest.py']), \
                patch.object(ingest, 'Collector') as collector, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ingest.main(), 2)
            collector.assert_not_called()


if __name__ == '__main__':
    unittest.main()
