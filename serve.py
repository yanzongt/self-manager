#!/usr/bin/env python3
"""Local-only PDCA page and XFCE notification scheduler (standard library)."""

import argparse
import copy
import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess
import tempfile
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


class DataConflict(ValueError):
    pass


class DataStore:
    """JSON storage with atomic replacement, one backup and stale-write protection."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    @staticmethod
    def validate(data):
        if not isinstance(data, dict):
            raise ValueError("无效数据")
        if (
            not isinstance(data.get("tags"), list)
            or not data["tags"]
            or not all(isinstance(t, str) for t in data["tags"])
        ):
            raise ValueError("无效项目标签")
        if not isinstance(data.get("records"), list):
            raise ValueError("无效历史记录")

        def session(item):
            if not isinstance(item, dict) or not all(
                isinstance(item.get(k), str) for k in ("id", "purpose", "tag")
            ):
                raise ValueError("无效会话记录")
            at = item.get("startedAt")
            if (
                isinstance(at, bool)
                or not isinstance(at, (int, float))
                or not math.isfinite(at)
            ):
                raise ValueError("无效会话开始时间")

        for record in data["records"]:
            session(record)
        active = data.get("active")
        if active is not None:
            session(active)
            for key in ("budgetMinutes", "extraMinutes"):
                value = active.get(key, 0 if key == "extraMinutes" else None)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise ValueError("无效会话时长")
            Scheduler(lambda *args: None).schedule(
                dict(
                    id=active["id"],
                    purpose=active["purpose"],
                    deadline=active["startedAt"]
                    + (active["budgetMinutes"] + active.get("extraMinutes", 0)) * 60000,
                )
            )
        items = data.get("workItems", [])
        if not isinstance(items, list) or not all(
            isinstance(w, dict)
            and isinstance(w.get("id"), str)
            and isinstance(w.get("title"), str)
            and type(w.get("important")) is bool
            and type(w.get("urgent")) is bool
            for w in items
        ):
            raise ValueError("无效工作事项")
        pomo = data.get("pomodoro")
        if pomo is not None:
            Scheduler(lambda *args: None).schedule(
                dict(
                    id=pomo.get("id") if isinstance(pomo, dict) else None,
                    deadline=None,
                    purpose="番茄钟",
                    pomodoro=pomo,
                ),
                independent=True,
            )

    def _read(self):
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {"data": None, "revision": None}, None
        try:
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("version") != 1:
                raise ValueError("无效文件格式")
            self.validate(document.get("data"))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(
                f"数据文件无法读取，请检查 {self.path.name} 或使用 "
                f"{self.path.name}.bak 恢复；原文件未被覆盖"
            ) from exc
        return {
            "data": document["data"],
            "revision": hashlib.sha256(raw).hexdigest(),
        }, raw

    def read(self):
        with self.lock:
            return self._read()[0]

    @staticmethod
    def _atomic_write(path, raw):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=path.name + ".", delete=False
            ) as f:
                temporary = Path(f.name)
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def write(self, data, revision):
        self.validate(data)
        raw = (
            json.dumps(
                {"version": 1, "data": data},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        with self.lock:
            current, previous = self._read()
            if previous == raw:
                return {"ok": True, "revision": current["revision"]}
            if revision != current["revision"]:
                raise DataConflict(
                    "数据已被其他页面修改。请先导出本页 JSON，再刷新读取最新数据，避免覆盖。"
                )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if previous is not None and previous != raw:
                self._atomic_write(
                    self.path.with_suffix(self.path.suffix + ".bak"), previous
                )
            self._atomic_write(self.path, raw)
            return {"ok": True, "revision": hashlib.sha256(raw).hexdigest()}


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


def create_server(port, scheduler=None, data_path=None):
    scheduler = scheduler or Scheduler()
    store = DataStore(data_path or PAGE.parent / "data" / "pdca.json")
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

        def authorized(self):
            return self.allowed() and self.headers.get("X-PDCA-Token") == token

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
            if self.path == "/api/data":
                if not self.authorized():
                    return self.reply(403, {"error": "Invalid token"})
                try:
                    return self.reply(200, store.read())
                except (ValueError, OSError) as exc:
                    return self.reply(500, {"error": str(exc)})
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
                limit = 16 * 1024 * 1024 if self.path == "/api/data" else 4096
                if not 0 < length <= limit:
                    raise ValueError("无效请求大小")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/data":
                    if not isinstance(data, dict) or "revision" not in data:
                        raise ValueError("缺少数据版本")
                    return self.reply(
                        200, store.write(data.get("data"), data["revision"])
                    )
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
            except DataConflict as exc:
                self.reply(409, {"error": str(exc)})
            except OSError as exc:
                self.reply(500, {"error": str(exc)})
            except (ValueError, RuntimeError) as exc:
                self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.data_store = store
    # Restore reminders from disk, including when no browser is open after restart.
    try:
        saved = store.read()["data"]
    except (ValueError, OSError):
        saved = None  # The data endpoint reports the error; do not overwrite the file.
    if saved:
        active = saved.get("active")
        if active:
            scheduler.schedule(
                dict(
                    id=active["id"],
                    purpose=active["purpose"],
                    deadline=active["startedAt"]
                    + (active["budgetMinutes"] + active.get("extraMinutes", 0)) * 60000,
                )
            )
        pomo = saved.get("pomodoro")
        if pomo:
            scheduler.schedule(
                dict(
                    id=pomo["id"],
                    purpose="番茄钟",
                    deadline=None,
                    pomodoro=pomo,
                ),
                independent=True,
            )
    return server, scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--data-file", type=Path, default=PAGE.parent / "data" / "pdca.json"
    )
    args = parser.parse_args()
    server, scheduler = create_server(args.port, data_path=args.data_file)
    stopped = threading.Event()

    def worker():
        while not stopped.wait(0.5):
            scheduler.tick()

    threading.Thread(target=worker, daemon=True).start()
    url = f"http://127.0.0.1:{args.port}"
    print(
        f"行为闭环：{url}\n数据文件：{server.data_store.path.resolve()}\n请保持此进程运行；Ctrl+C 退出。",
        flush=True,
    )
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
