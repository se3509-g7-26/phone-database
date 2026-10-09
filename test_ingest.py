import contextlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

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
