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
        self.item = {"id": "session", "deadline": 1000, "purpose": "学习"}

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
        self.scheduler.schedule({**self.item, "deadline": 2000})
        self.scheduler.tick(1999)
        self.assertEqual(len(self.sent), 1)
        self.scheduler.tick(2000)
        self.assertEqual(len(self.sent), 2)
        self.scheduler.schedule({**self.item, "deadline": 3000})
        self.scheduler.schedule(None)
        self.scheduler.tick(4000)
        self.assertEqual(len(self.sent), 2)

    def test_error_is_reported_without_repeated_spam(self):
        self.scheduler.sender = lambda *args: (_ for _ in ()).throw(
            RuntimeError("D-Bus unavailable")
        )
        self.scheduler.schedule(self.item)
        self.scheduler.tick(1000)
        self.assertEqual(self.scheduler.error, "D-Bus unavailable")
        self.assertEqual(len(self.scheduler.delivered), 1)

    def test_invalid_payload(self):
        for value in [
            [],
            {},
            {**self.item, "deadline": float("nan")},
            {**self.item, "deadline": True},
        ]:
            with self.assertRaises(ValueError):
                self.scheduler.schedule(value)

    def pomo_item(self, auto=True):
        return {
            "id": "pomo-session",
            "deadline": 600000,
            "purpose": "专注",
            "pomodoro": {
                "phase": "work",
                "startedAt": 0,
                "phaseEndsAt": 60000,
                "workMinutes": 1,
                "breakMinutes": 1,
                "auto": auto,
                "waiting": False,
                "stopped": False,
            },
        }

    def test_pomodoro_auto_and_browser_dedup(self):
        item = self.pomo_item()
        self.scheduler.schedule(item)
        self.scheduler.tick(60000)
        self.assertIn("Break", self.sent[-1][0])
        self.assertEqual(
            item["pomodoro"]["phase"], "work"
        )  # Do not mutate caller data.
        self.scheduler.phase_event(
            dict(
                id="pomo-session",
                at=60000,
                phase="break",
                waiting=False,
                manual=False,
                purpose="专注",
            )
        )
        self.assertEqual(len(self.sent), 1)
        self.scheduler.tick(120000)
        self.assertIn("Work", self.sent[-1][0])
        self.assertEqual(len(self.sent), 2)

    def test_pomodoro_catch_up_and_deadline_priority(self):
        self.scheduler.schedule(self.pomo_item())
        self.scheduler.tick(190000)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.scheduler.pending["pomodoro"]["phaseEndsAt"], 240000)
        self.scheduler.tick(600000)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("计划时间已到", self.sent[-1][0])

    def test_pomodoro_manual_wait_and_resume(self):
        item = self.pomo_item(False)
        self.scheduler.schedule(item)
        self.scheduler.tick(60000)
        self.scheduler.tick(120000)
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.scheduler.pending["pomodoro"]["waiting"])
        self.scheduler.phase_event(
            dict(
                id="pomo-session",
                at=120000,
                phase="break",
                waiting=False,
                manual=True,
                purpose="专注",
            )
        )
        item["pomodoro"].update(phase="break", startedAt=120000, phaseEndsAt=180000)
        self.scheduler.schedule(item)
        self.scheduler.tick(180000)
        self.assertEqual(len(self.sent), 3)

    def test_independent_pomodoro_survives_session_deadline_and_cancel(self):
        timer = {**self.pomo_item(), "deadline": None}
        self.scheduler.schedule(timer, independent=True)
        self.scheduler.schedule(self.item)
        self.scheduler.tick(1000)
        self.assertIn("计划时间已到", self.sent[-1][0])
        self.scheduler.schedule(None)
        self.scheduler.tick(60000)
        self.assertIn("Break", self.sent[-1][0])
        self.scheduler.phase_event(
            dict(
                id=timer["id"],
                at=60000,
                phase="break",
                waiting=False,
                manual=False,
                purpose="番茄钟",
            )
        )
        self.assertEqual(len(self.sent), 2)
        self.scheduler.schedule(None, independent=True)
        self.scheduler.schedule({**self.item, "deadline": 120000})
        self.scheduler.tick(120000)
        self.assertEqual(len(self.sent), 3)
        self.assertIn("计划时间已到", self.sent[-1][0])

    def test_pomodoro_bad_duration_rejected(self):
        for duration in [0, -1, 1.5, True, 1441]:
            item = self.pomo_item()
            item["pomodoro"]["workMinutes"] = duration
            with self.assertRaises(ValueError):
                self.scheduler.schedule(item)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        # Pick a free port first so the enforced origin matches the actual listener.
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.server, self.scheduler = create_server(port, Scheduler(lambda *args: None))
        self.url = f"http://127.0.0.1:{port}"
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
        headers = {
            "Origin": self.url,
            "X-PDCA-Token": token,
            "Content-Type": "application/json",
        }
        item = {"id": "s", "deadline": 1000, "purpose": "阅读"}
        with urlopen(
            Request(self.url + "/api/schedule", json.dumps(item).encode(), headers)
        ) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertEqual(self.scheduler.pending, item)
        with urlopen(Request(self.url + "/api/schedule", b"null", headers)):
            pass
        self.assertIsNone(self.scheduler.pending)
        event = dict(
            id="s", at=1000, phase="break", waiting=False, manual=False, purpose="阅读"
        )
        with urlopen(
            Request(self.url + "/api/phase", json.dumps(event).encode(), headers)
        ) as response:
            self.assertTrue(json.load(response)["ok"])

    def test_authenticated_independent_timer_and_cancellation(self):
        import re

        with urlopen(self.url) as response:
            page = response.read().decode()
        token = json.loads(re.search(r'window.PDCA_NATIVE_TOKEN=("[^"]+")', page)[1])
        headers = {
            "Origin": self.url,
            "X-PDCA-Token": token,
            "Content-Type": "application/json",
        }
        timer = SchedulerTests().pomo_item()
        timer["deadline"] = None
        for payload in [timer, None]:
            with urlopen(
                Request(
                    self.url + "/api/pomodoro", json.dumps(payload).encode(), headers
                )
            ) as response:
                self.assertTrue(json.load(response)["ok"])
            self.assertEqual(self.scheduler.pending_pomodoro, payload)
        self.assertIsNone(self.scheduler.pending)

    def test_reject_foreign_origin_and_host(self):
        for headers in [{"Origin": "https://example.com"}, {"Host": "example.com"}]:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.url + "/api/test", b"{}", headers))
            self.assertEqual(error.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
