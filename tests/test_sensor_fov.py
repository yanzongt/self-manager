"""Serve the integrated FOV app without exposing source or local dependency files."""
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from serve import create_server


class SensorFovTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server, _ = create_server(0, data_path=Path(self.folder.name) / 'pdca.json')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.folder.cleanup()

    def test_home_entry_and_compiled_app_assets(self):
        with urlopen(self.origin + '/') as response:
            self.assertIn(b'href="/sensor-fov/"', response.read())
        with urlopen(self.origin + '/sensor-fov') as response:
            self.assertTrue(response.url.endswith('/sensor-fov/'))
            page = response.read().decode()
        self.assertIn('传感器视场', page)
        self.assertNotIn('/src/main.ts', page)
        assets = re.findall(r'(?:src|href)="(/sensor-fov/assets/[^"]+)"', page)
        self.assertGreaterEqual(len(assets), 2)
        for asset in assets:
            with urlopen(self.origin + asset + '?v=1') as response:
                self.assertEqual(response.status, 200)
                self.assertIn(response.headers['Content-Type'].split(';')[0], ('text/javascript', 'text/css'))

    def test_source_dependencies_and_traversal_are_not_public(self):
        for path in ('/sensor-fov/src/model.ts', '/sensor-fov/.generated/package-lock.json',
                     '/sensor-fov/assets/../../package.json', '/sensor-fov/assets/missing.js',
                     '/sensor_fov/sensor_fov_vis.html'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as missing:
                urlopen(self.origin + path)
            self.assertEqual(missing.exception.code, 404)

    def test_missing_build_returns_clear_error(self):
        with patch('serve.APPS_ROOT', Path(self.folder.name)):
            with self.assertRaises(HTTPError) as unavailable:
                urlopen(self.origin + '/sensor-fov/')
            self.assertEqual(unavailable.exception.code, 503)
            self.assertIn('npm run build', unavailable.exception.read().decode())


if __name__ == '__main__':
    unittest.main()
