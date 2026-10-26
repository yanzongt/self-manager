import copy
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from serve import CheckinStore, DataConflict, create_server


class CheckinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'checkins.json'
        self.store = CheckinStore(self.path)
        self.data = {'items': [
            {'id': 'water', 'name': '喝水', 'type': 'count', 'records': [{'start': 1000}]},
            {'id': 'read', 'name': '阅读', 'type': 'timer', 'activeSince': 3000,
             'records': [{'start': 1000, 'end': 2000}]},
        ]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_persistence_backup_and_conflict(self):
        revision = self.store.write(self.data, None)['revision']
        self.assertEqual(CheckinStore(self.path).read()['data'], self.data)
        updated = copy.deepcopy(self.data)
        updated['items'][0]['records'].append({'start': 5000})
        self.store.write(updated, revision)
        self.assertEqual(json.loads(self.path.with_suffix('.json.bak').read_text())['data'], self.data)
        with self.assertRaises(DataConflict):
            self.store.write(self.data, revision)

    def test_invalid_records_never_written(self):
        for change in [
            lambda d: d['items'][1]['records'][0].update(end=0),
            lambda d: d['items'][0].update(activeSince=1000),
            lambda d: d['items'][0]['records'][0].update(start=True),
            lambda d: d['items'].append(d['items'][0]),
        ]:
            value = copy.deepcopy(self.data)
            change(value)
            with self.assertRaises(ValueError):
                self.store.write(value, None)
            self.assertFalse(self.path.exists())

    def test_routes_auth_and_save(self):
        server, _ = create_server(0, data_path=Path(self.tmp.name) / 'pdca.json')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(origin + '/checkins') as response:
                page = response.read().decode()
            token = json.loads(re.search(r'const TOKEN=(.*?);', page)[1])
            def call(body=None, authorized=True):
                headers = {'Origin': origin, 'Content-Type': 'application/json'}
                if authorized:
                    headers['X-PDCA-Token'] = token
                request = Request(origin + '/api/checkins', headers=headers,
                                  data=None if body is None else json.dumps(body).encode())
                with urlopen(request) as response:
                    return json.load(response)
            with self.assertRaises(HTTPError) as error:
                call(authorized=False)
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(call(), {'data': None, 'revision': None})
            call({'data': self.data, 'revision': None})
            self.assertEqual(call()['data'], self.data)
            with self.assertRaises(HTTPError) as error:
                call({'data': {'items': []}, 'revision': None})
            self.assertEqual(error.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
