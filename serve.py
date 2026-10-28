"""个人工具主页、本地数据服务与桌面提醒。"""

import argparse
import copy
import errno
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent
APPS_ROOT = PROJECT_ROOT / "apps"
PAGE = APPS_ROOT / "pdca" / ".generated" / "static" / "index.html"


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
            raise TypeError("无效数据")
        if (
            not isinstance(data.get("tags"), list)
            or not data["tags"]
            or not all(isinstance(t, str) for t in data["tags"])
        ):
            raise ValueError("无效项目标签")
        if not isinstance(data.get("records"), list):
            raise TypeError("无效历史记录")

        utilization_hours = data.get("utilizationHours", 8)
        if (
            isinstance(utilization_hours, bool)
            or not isinstance(utilization_hours, (int, float))
            or not math.isfinite(utilization_hours)
            or not 0.1 <= utilization_hours <= 24
        ):
            raise ValueError("每日目标时长需为 0.1 至 24 小时")

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


class CheckinStore(DataStore):
    """Independent check-in records, using the same atomic storage contract."""

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("无效打卡数据")
        ids = set()

        def timestamp(value):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 8640000000000000):
                raise ValueError("无效打卡时间")

        for item in data["items"]:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or not item["id"] or item["id"] in ids
                    or not isinstance(item.get("name"), str)
                    or not 1 <= len(item["name"].strip()) <= 80
                    or item.get("type") not in ("count", "timer")
                    or not isinstance(item.get("records"), list)):
                raise ValueError("无效打卡事项")
            ids.add(item["id"])
            active = item.get("activeSince")
            if active is not None:
                if item["type"] != "timer":
                    raise ValueError("计次事项不能计时")
                timestamp(active)
            for record in item["records"]:
                if not isinstance(record, dict):
                    raise ValueError("无效打卡记录")
                timestamp(record.get("start"))
                if item["type"] == "timer":
                    timestamp(record.get("end"))
                    if record["end"] < record["start"]:
                        raise ValueError("结束时间不能早于开始时间")


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


def load_investment():
    """Reuse the backtest application and HTTP routes in this server process."""
    project = APPS_ROOT / "investment"
    sys.path.insert(0, str(project))
    from f_analysis.web_service import WebApplication
    from scripts.web import Handler

    return WebApplication(project_root=project), Handler


def create_server(port, scheduler=None, data_path=None, investment=None):
    scheduler = scheduler or Scheduler()
    store = DataStore(data_path or PROJECT_ROOT / "data" / "pdca.json")
    checkins = CheckinStore(store.path.with_name("checkins.json"))
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"

    investment_app, investment_handler = investment or (None, BaseHTTPRequestHandler)

    class Handler(investment_handler):
        def __init__(self, *args, **kwargs):
            self.app = investment_app
            BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

        def investment_request(self, method):
            if investment_app is None:
                return self.reply(
                    503,
                    '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                    "<title>回测服务未就绪</title><h1>回测服务未就绪</h1>"
                    "<p>请在项目目录运行 ./start.sh；首次使用请先执行 ./setup.sh。"
                    '若仍不可用，请查看启动终端中的错误信息。</p><a href="/">返回首页</a></html>'.encode(),
                    "text/html; charset=utf-8",
                )
            original = self.path
            self.path = self.path.removeprefix("/investment")
            try:
                return getattr(investment_handler, method)(self)
            finally:
                self.path = original

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
            try:
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The browser may leave the tool before a response finishes.

        def allowed(self):
            return self.headers.get("Host") == origin.removeprefix("http://")

        def authorized(self):
            return self.allowed() and self.headers.get("X-PDCA-Token") == token

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "Invalid host"})
            path = urlsplit(self.path).path
            if path in ("/pdca", "/strength", "/investment", "/checkins", "/sensor-fov"):
                self.send_response(302)
                self.send_header("Location", path + "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path.startswith("/investment/"):
                return self.investment_request("do_GET")
            if path in ("/", "/index.html"):
                return self.reply(
                    200,
                    (APPS_ROOT / "portal" / "index.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
            if path in ("/shared/theme.css", "/portal/style.css"):
                stylesheet = APPS_ROOT / path.lstrip("/")
                return self.reply(200, stylesheet.read_bytes(), "text/css; charset=utf-8")
            if path == "/sensor-fov/":
                page = APPS_ROOT / "sensor-fov" / ".generated" / "static" / "index.html"
                if not page.is_file():
                    return self.reply(503, {"error": "传感器视场前端尚未构建，请运行 apps/sensor-fov/setup.sh 和 npm run build --prefix apps/sensor-fov"})
                return self.reply(200, page.read_bytes(), "text/html; charset=utf-8")
            if path == "/checkins/":
                page_path = APPS_ROOT / "checkins" / ".generated" / "static" / "index.html"
                if not page_path.is_file():
                    return self.reply(503, {"error": "打卡前端尚未构建，请运行 apps/checkins/setup.sh 和 npm run build --prefix apps/checkins"})
                page = page_path.read_text().replace(
                    "/*SERVER_TOKEN*/null", json.dumps(token), 1
                )
                return self.reply(200, page.encode(), "text/html; charset=utf-8")
            if path.startswith(("/checkins/assets/", "/pdca/assets/", "/sensor-fov/assets/", "/strength/assets/")):
                app_name = path.split("/")[1]
                assets = (APPS_ROOT / app_name / ".generated" / "static" / "assets").resolve()
                asset = (assets / path.removeprefix(f"/{app_name}/assets/")).resolve()
                if asset.parent != assets or not asset.is_file() or asset.suffix not in (".js", ".css"):
                    return self.reply(404, {"error": "Not found"})
                content_type = "text/javascript; charset=utf-8" if asset.suffix == ".js" else "text/css; charset=utf-8"
                return self.reply(200, asset.read_bytes(), content_type)
            if path == "/api/checkins":
                if not self.authorized():
                    return self.reply(403, {"error": "Invalid token"})
                try:
                    return self.reply(200, checkins.read())
                except (ValueError, OSError) as exc:
                    return self.reply(500, {"error": str(exc)})
            if path == "/api/tools":
                return self.reply(200, {"investment": investment_app is not None})
            if path in ("/strength/", "/strength_training_tracker.html"):
                page = APPS_ROOT / "strength" / ".generated" / "static" / "index.html"
                if not page.is_file():
                    return self.reply(503, {"error": "力量训练前端尚未构建，请运行 apps/strength/setup.sh 和 npm run build --prefix apps/strength"})
                return self.reply(200, page.read_bytes(), "text/html; charset=utf-8")
            if path in ("/pdca/", "/pdca_focus.html"):
                if not PAGE.is_file():
                    return self.reply(503, {"error": "PDCA 前端尚未构建，请运行 apps/pdca/setup.sh 和 npm run build --prefix apps/pdca"})
                page = PAGE.read_text().replace("/*SERVER_TOKEN*/null", json.dumps(token), 1)
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
            if urlsplit(self.path).path.startswith("/investment/"):
                return self.investment_request("do_POST")
            if (
                not self.allowed()
                or self.headers.get("Origin") != origin
                or self.headers.get("X-PDCA-Token") != token
            ):
                return self.reply(403, {"error": "Invalid origin or token"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = 16 * 1024 * 1024 if self.path in ("/api/data", "/api/checkins") else 4096
                if not 0 < length <= limit:
                    raise ValueError("无效请求大小")
                data = json.loads(self.rfile.read(length))
                if self.path in ("/api/data", "/api/checkins"):
                    if not isinstance(data, dict) or "revision" not in data:
                        raise ValueError("缺少数据版本")
                    return self.reply(
                        200, (checkins if self.path == "/api/checkins" else store).write(
                            data.get("data"), data["revision"])
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
                message = (
                    "打卡数据已被其他页面修改，请刷新读取最新记录后重试。"
                    if self.path == "/api/checkins" else str(exc)
                )
                self.reply(409, {"error": message})
            except OSError as exc:
                self.reply(500, {"error": str(exc)})
            except (ValueError, TypeError, RuntimeError) as exc:
                self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    origin = f"http://127.0.0.1:{server.server_port}"
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


def listening_pids(port):
    """Find TCP listeners using available system tools, without stopping them."""
    commands = [
        ("ss", ["ss", "-H", "-ltnp", f"sport = :{port}"],
         lambda output: re.findall(r"pid=(\d+)", output)),
        ("lsof", ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
         lambda output: [line for line in output.splitlines() if line.isdigit()]),
    ]
    for tool, command, parse in commands:
        if not shutil.which(tool):
            continue
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=3, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            pids = sorted({int(pid) for pid in parse(result.stdout)})
            if pids:
                return pids
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--data-file", type=Path, default=PROJECT_ROOT / "data" / "pdca.json"
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1～65535 之间")
    investment = None
    try:
        investment = load_investment()
    except ImportError as exc:
        print(
            f"回测服务未加载：{exc}。请使用 ./start.sh；首次使用先执行 ./setup.sh。",
            flush=True,
        )
    try:
        server, scheduler = create_server(
            args.port, data_path=args.data_file, investment=investment
        )
    except OSError as exc:
        if investment:
            investment[0].close()
        if exc.errno == errno.EADDRINUSE:
            pids = listening_pids(args.port)
            detail = (
                "占用进程 PID：" + ", ".join(str(pid) for pid in pids)
                if pids else
                "未能获取占用进程 PID（可能权限不足或缺少 ss / lsof）"
            )
            parser.error(
                f"端口 {args.port} 已被占用；{detail}；可使用 --port 更换端口"
            )
        parser.error(f"服务无法启动：{exc}；可使用 --port 更换端口")
    stopped = threading.Event()

    def worker():
        while not stopped.wait(0.5):
            scheduler.tick()

    threading.Thread(target=worker, daemon=True).start()
    url = f"http://127.0.0.1:{args.port}"
    print(
        f"个人主页：{url}\n工具入口：/pdca/ · /strength/ · /investment/ · /checkins/ · /sensor-fov/\n数据文件：{server.data_store.path.resolve()}\n请保持此进程运行；Ctrl+C 退出。",
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
        if investment:
            investment[0].close()


if __name__ == "__main__":
    main()
