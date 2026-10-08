#!/usr/bin/env python3
"""Local-only PDCA page and XFCE notification scheduler (standard library)."""

import argparse
import copy
import json
import math
import secrets
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).with_name("pdca_focus.html")


def send_notification(title, body):
    if not shutil.which("notify-send"):
        raise RuntimeError("缺少 notify-send，请安装 libnotify-bin")
    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=行为闭环",
                "--urgency=critical",
                "--expire-time=0",
                "--",
                title,
                body,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or "桌面通知服务不可用") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("桌面通知服务响应超时") from exc


class Scheduler:
    def __init__(self, sender=send_notification):
        self.sender = sender
        self.lock = threading.Lock()
        self.pending = None
        self.pending_pomodoro = None
        self.delivered = set()
        self.error = None

    def schedule(self, item, *, independent=False):
        if item is not None:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("无效会话")
            due = item.get("deadline")
            if not (independent and due is None) and (
                isinstance(due, bool)
                or not isinstance(due, (int, float))
                or not math.isfinite(due)
            ):
                raise ValueError("无效截止时间")
            if not isinstance(item.get("purpose"), str) or len(item["purpose"]) > 300:
                raise ValueError("无效目的")
            pomo = item.get("pomodoro")
            if independent and pomo is None:
                raise ValueError("缺少番茄钟状态")
            if pomo is not None:
                if not isinstance(pomo, dict) or pomo.get("phase") not in (
                    "work",
                    "break",
                ):
                    raise ValueError("无效番茄钟阶段")
                for key in ("startedAt", "phaseEndsAt"):
                    value = pomo.get(key)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                    ):
                        raise ValueError("无效番茄钟时间")
                for key in ("workMinutes", "breakMinutes"):
                    value = pomo.get(key)
                    if type(value) is not int or not 1 <= value <= 1440:
                        raise ValueError("无效番茄钟时长")
                if pomo["phaseEndsAt"] <= pomo["startedAt"]:
                    raise ValueError("无效番茄钟时间范围")
                if any(
                    type(pomo.get(key)) is not bool
                    for key in ("auto", "waiting", "stopped")
                ):
                    raise ValueError("无效番茄钟切换设置")
        with self.lock:
            if independent:
                self.pending_pomodoro = copy.deepcopy(item)
            else:
                self.pending = copy.deepcopy(item)

    def _send(self, key, title, body):
        if key in self.delivered:
            return
        try:
            self.sender(title, body)
            self.error = None
        except (RuntimeError, OSError) as exc:
            self.error = str(exc)
        self.delivered.add(key)

    def _phase_event(self, event):
        phase = "Work · 专注" if event["phase"] == "work" else "Break · 休息"
        title = "番茄钟：阶段结束" if event["waiting"] else f"番茄钟：进入{phase}"
        message = (
            f"{phase}结束，请返回页面手动开始下一阶段。"
            if event["waiting"]
            else f"已切换到{phase}。"
        )
        key = (
            event["id"],
            "pomo-manual" if event.get("manual") else "pomo",
            event["at"],
        )
        self._send(key, title, event["purpose"] + "\n" + message)

    def phase_event(self, event):
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("id"), str)
            or event.get("phase") not in ("work", "break")
        ):
            raise ValueError("无效阶段通知")
        at = event.get("at")
        if (
            isinstance(at, bool)
            or not isinstance(at, (int, float))
            or not math.isfinite(at)
        ):
            raise ValueError("无效阶段时间")
        if (
            type(event.get("waiting")) is not bool
            or type(event.get("manual")) is not bool
        ):
            raise ValueError("无效阶段状态")
        if not isinstance(event.get("purpose"), str) or len(event["purpose"]) > 300:
            raise ValueError("无效目的")
        with self.lock:
            self._phase_event(event)
            if self.error:
                raise RuntimeError(self.error)

    def tick(self, now=None):
        with self.lock:
            now = time.time() * 1000 if now is None else now
            self._tick_item(self.pending, now)
            self._tick_item(self.pending_pomodoro, now)

    def _tick_item(self, item, now):
        if item is None:
            return
        now = time.time() * 1000 if now is None else now
        if item["deadline"] is not None and now >= item["deadline"]:
            self._send(
                (item["id"], item["deadline"]),
                "行为闭环：计划时间已到",
                item["purpose"] + "\n返回页面填写复盘，或确认延期。",
            )
            return
        pomo = item.get("pomodoro")
        if not pomo or pomo["waiting"] or pomo["stopped"]:
            return
        event = None
        while pomo["phaseEndsAt"] <= now:
            at = pomo["phaseEndsAt"]
            if not pomo["auto"]:
                pomo["waiting"] = True
                event = dict(
                    id=item["id"],
                    at=at,
                    phase=pomo["phase"],
                    waiting=True,
                    purpose=item["purpose"],
                )
                break
            pomo["phase"] = "break" if pomo["phase"] == "work" else "work"
            pomo["startedAt"] = at
            minutes = (
                pomo["workMinutes"] if pomo["phase"] == "work" else pomo["breakMinutes"]
            )
            pomo["phaseEndsAt"] = at + minutes * 60000
            event = dict(
                id=item["id"],
                at=at,
                phase=pomo["phase"],
                waiting=False,
                purpose=item["purpose"],
            )
        if event:
            self._phase_event(event)


def create_server(port, scheduler=None):
    scheduler = scheduler or Scheduler()
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value, content_type="application/json; charset=utf-8"):
            data = (
                value
                if isinstance(value, bytes)
                else json.dumps(value, ensure_ascii=False).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get("Host") == origin.removeprefix("http://")

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "Invalid host"})
            if self.path in ("/", "/pdca_focus.html"):
                page = PAGE.read_text().replace(
                    "<script>",
                    "<script>window.PDCA_NATIVE_TOKEN="
                    + json.dumps(token)
                    + ";</script><script>",
                    1,
                )
                return self.reply(200, page.encode(), "text/html; charset=utf-8")
            if self.path == "/api/status":
                with scheduler.lock:
                    return self.reply(
                        200,
                        {
                            "available": bool(shutil.which("notify-send")),
                            "error": scheduler.error,
                        },
                    )
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if (
                not self.allowed()
                or self.headers.get("Origin") != origin
                or self.headers.get("X-PDCA-Token") != token
            ):
                return self.reply(403, {"error": "Invalid origin or token"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("无效请求大小")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/schedule":
                    scheduler.schedule(data)
                elif self.path == "/api/pomodoro":
                    scheduler.schedule(data, independent=True)
                elif self.path == "/api/phase":
                    scheduler.phase_event(data)
                elif self.path == "/api/test":
                    scheduler.sender(
                        "行为闭环：测试提醒", "桌面通知通道正常。到时请返回页面复盘。"
                    )
                else:
                    return self.reply(404, {"error": "Not found"})
                self.reply(200, {"ok": True})
            except (ValueError, RuntimeError, OSError) as exc:
                self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server, scheduler = create_server(args.port)
    stopped = threading.Event()

    def worker():
        while not stopped.wait(0.5):
            scheduler.tick()

    threading.Thread(target=worker, daemon=True).start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"行为闭环：{url}\n请保持此进程运行；Ctrl+C 退出。", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()


if __name__ == "__main__":
    main()
