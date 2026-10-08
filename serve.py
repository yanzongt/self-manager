#!/usr/bin/env python3
"""Local-only PDCA page and XFCE notification scheduler (standard library)."""
import argparse
import json
import math
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser

PAGE = Path(__file__).with_name('pdca_focus.html')


def send_notification(title, body):
    if not shutil.which('notify-send'):
        raise RuntimeError('缺少 notify-send，请安装 libnotify-bin')
    try:
        subprocess.run(['notify-send', '--app-name=行为闭环', '--urgency=critical',
                        '--expire-time=0', '--', title, body],
                       check=True, capture_output=True, text=True, timeout=10)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or '桌面通知服务不可用') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('桌面通知服务响应超时') from exc


class Scheduler:
    def __init__(self, sender=send_notification):
        self.sender = sender
        self.lock = threading.Lock()
        self.pending = None
        self.delivered = set()
        self.error = None

    def schedule(self, item):
        if item is not None:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                raise ValueError('无效会话')
            due = item.get('deadline')
            if isinstance(due, bool) or not isinstance(due, (int, float)) or not math.isfinite(due):
                raise ValueError('无效截止时间')
            if not isinstance(item.get('purpose'), str) or len(item['purpose']) > 300:
                raise ValueError('无效目的')
        with self.lock:
            self.pending = item

    def tick(self, now=None):
        with self.lock:
            item = self.pending
            if item is None or item['deadline'] > (time.time() * 1000 if now is None else now):
                return
            key = (item['id'], item['deadline'])
            if key in self.delivered:
                return
            # Hold the lock so cancel/extend cannot overtake an in-flight alert.
            try:
                self.sender('行为闭环：计划时间已到', item['purpose'] + '\n返回页面填写复盘，或确认延期。')
                self.error = None
            except (RuntimeError, OSError) as exc:
                self.error = str(exc)
            self.delivered.add(key)


def create_server(port, scheduler=None):
    scheduler = scheduler or Scheduler()
    token = secrets.token_urlsafe(32)
    origin = f'http://127.0.0.1:{port}'

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value, content_type='application/json; charset=utf-8'):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get('Host') == origin.removeprefix('http://')

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {'error': 'Invalid host'})
            if self.path in ('/', '/pdca_focus.html'):
                page = PAGE.read_text().replace('<script>', '<script>window.PDCA_NATIVE_TOKEN=' + json.dumps(token) + ';</script><script>', 1)
                return self.reply(200, page.encode(), 'text/html; charset=utf-8')
            if self.path == '/api/status':
                with scheduler.lock:
                    return self.reply(200, {'available': bool(shutil.which('notify-send')), 'error': scheduler.error})
            self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.allowed() or self.headers.get('Origin') != origin or self.headers.get('X-PDCA-Token') != token:
                return self.reply(403, {'error': 'Invalid origin or token'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('无效请求大小')
                data = json.loads(self.rfile.read(length))
                if self.path == '/api/schedule':
                    scheduler.schedule(data)
                elif self.path == '/api/test':
                    scheduler.sender('行为闭环：测试提醒', '桌面通知通道正常。到时请返回页面复盘。')
                else:
                    return self.reply(404, {'error': 'Not found'})
                self.reply(200, {'ok': True})
            except (ValueError, RuntimeError, OSError) as exc:
                self.reply(400, {'error': str(exc)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    return server, scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server, scheduler = create_server(args.port)
    stopped = threading.Event()

    def worker():
        while not stopped.wait(0.5):
            scheduler.tick()

    threading.Thread(target=worker, daemon=True).start()
    url = f'http://127.0.0.1:{args.port}'
    print(f'行为闭环：{url}\n请保持此进程运行；Ctrl+C 退出。', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()


if __name__ == '__main__':
    main()
