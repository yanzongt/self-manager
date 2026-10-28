"""Exercise the mounted backtest routes with the existing real-engine HTTP suite."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from serve import create_server

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "apps/investment"))
sys.path.insert(0, str(PROJECT / "apps/investment/tests"))
from scripts.web import Handler
from test_web import WebTests


class PortalTests(WebTests):
    def setUp(self):
        def combined_server(app, port=0):
            return create_server(
                port, data_path=app.root / "pdca.json", investment=(app, Handler)
            )[0]

        with patch("test_web.make_server", combined_server):
            super().setUp()

    def http(self, path, payload=None, headers=None):
        return super().http("/investment" + path, payload, headers)

    def test_home_and_other_tools(self):
        for path, expected in [
            ("/", "把时间，留给重要的事。"),
            ("/pdca/", "window.PDCA_NATIVE_TOKEN="),
            ("/strength/", "strengthTracker_v1"),
            ("/sensor-fov/", "传感器视场"),
            ("/pdca_focus.html", "window.PDCA_NATIVE_TOKEN="),
            ("/strength_training_tracker.html", "strengthTracker_v1"),
        ]:
            with self.subTest(path=path):
                status, _, body = super().http(path)
                self.assertEqual(status, 200)
                self.assertIn(expected.encode(), body)
        self.assertIn(b'"investment": true', super().http("/api/tools")[2])
        for path in ("/pdca", "/strength", "/investment", "/sensor-fov"):
            self.assertEqual(super().http(path)[0], 200)  # follows redirect
        self.assertEqual(super().http("/serve.py")[0], 404)
        self.assertEqual(super().http("/data/pdca.json")[0], 404)
        self.assertEqual(super().http("/", headers={"Host": "example.com"})[0], 403)


# Avoid also collecting the imported standalone test class.
del WebTests

if __name__ == "__main__":
    unittest.main()
