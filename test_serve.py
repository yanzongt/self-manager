import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from serve import Scheduler, create_server


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.scheduler = Scheduler(lambda *args: self.sent.append(args))
        self.item = {'id': 'session', 'deadline': 1000, 'purpose': '学习'}

    def test_due_once_even_after_resync(self):
        self.scheduler.schedule(self.item)
        self.scheduler.tick(999)
        self.assertEqual(self.sent, [])
        self.scheduler.tick(1000)
        self.scheduler.schedule(self.item)
        self.scheduler.tick(1500)
        self.assertEqual(len(self.sent), 1)

    def test_extend_and_cancel(self):
        self.scheduler.schedule(self.item)
        self.scheduler.tick(1000)
        self.scheduler.schedule({**self.item, 'deadline': 2000})
        self.scheduler.tick(1999)
        self.assertEqual(len(self.sent), 1)
        self.scheduler.tick(2000)
        self.assertEqual(len(self.sent), 2)
        self.scheduler.schedule({**self.item, 'deadline': 3000})
        self.scheduler.schedule(None)
        self.scheduler.tick(4000)
        self.assertEqual(len(self.sent), 2)

    def test_error_is_reported_without_repeated_spam(self):
        self.scheduler.sender = lambda *args: (_ for _ in ()).throw(RuntimeError('D-Bus unavailable'))
        self.scheduler.schedule(self.item)
        self.scheduler.tick(1000)
        self.assertEqual(self.scheduler.error, 'D-Bus unavailable')
        self.assertEqual(len(self.scheduler.delivered), 1)

    def test_invalid_payload(self):
        for value in [[], {}, {**self.item, 'deadline': float('nan')}, {**self.item, 'deadline': True}]:
            with self.assertRaises(ValueError):
                self.scheduler.schedule(value)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        # Pick a free port first so the enforced origin matches the actual listener.
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.server, self.scheduler = create_server(port, Scheduler(lambda *args: None))
        self.url = f'http://127.0.0.1:{port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_page_and_authenticated_schedule(self):
        import re
        with urlopen(self.url) as response:
            page = response.read().decode()
        token = json.loads(re.search(r'window.PDCA_NATIVE_TOKEN=("[^"]+")', page)[1])
        headers = {'Origin': self.url, 'X-PDCA-Token': token, 'Content-Type': 'application/json'}
        item = {'id': 's', 'deadline': 1000, 'purpose': '阅读'}
        with urlopen(Request(self.url + '/api/schedule', json.dumps(item).encode(), headers)) as response:
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(self.scheduler.pending, item)
        with urlopen(Request(self.url + '/api/schedule', b'null', headers)):
            pass
        self.assertIsNone(self.scheduler.pending)

    def test_reject_foreign_origin_and_host(self):
        for headers in [{'Origin': 'https://example.com'}, {'Host': 'example.com'}]:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.url + '/api/test', b'{}', headers))
            self.assertEqual(error.exception.code, 403)


if __name__ == '__main__':
    unittest.main()
