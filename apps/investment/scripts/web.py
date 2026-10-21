"""仅监听本机的网页入口，无额外服务或前端构建依赖。"""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit
import webbrowser

from f_analysis.web_service import PoolConflict, WebApplication

STATIC = Path(__file__).resolve().parents[1] / "f_analysis/web_static"
DEFAULT_PORT = 8766


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, app, **kwargs):
        self.app = app
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # 请求路径不包含表单内容，后台任务错误由状态接口返回。
        print(f"[web] {format % args}")

    def _send(
        self,
        status,
        body,
        content_type="application/json; charset=utf-8",
        filename=None,
    ):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Navigation can cancel an in-flight result download.

    def _local_request(self):
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit("http://" + host)
            return (
                parsed.hostname in ("127.0.0.1", "localhost")
                and parsed.port == self.server.server_port
            )
        except ValueError:
            return False

    def do_GET(self):
        if not self._local_request():
            return self._send(403, {"error": "仅允许本机访问"})
        path = unquote(urlsplit(self.path).path)
        try:
            if path == "/api/config":
                return self._send(200, self.app.configuration())
            if path == "/api/cache":
                return self._send(200, self.app.cache_info())
            if path == "/api/runs":
                return self._send(200, self.app.list_runs())
            if path.startswith("/api/jobs/"):
                return self._send(
                    200, self.app.job_status(path.removeprefix("/api/jobs/"))
                )
            if path.startswith("/api/runs/"):
                suffix = path.removeprefix("/api/runs/")
                run_id, separator, resource = suffix.partition("/")
                if not separator:
                    return self._send(200, self.app.run_details(run_id))
                if resource == "download.zip":
                    return self._send(
                        200,
                        self.app.zip_results(run_id),
                        "application/zip",
                        "backtest-results.zip",
                    )
                if resource.startswith("files/"):
                    file = self.app.result_file(run_id, resource.removeprefix("files/"))
                    return self._send(
                        200,
                        file.read_bytes(),
                        mimetypes.guess_type(file.name)[0]
                        or "application/octet-stream",
                        file.name,
                    )
                raise FileNotFoundError("接口不存在")
            files = {
                "/": "index.html",
                "/index.html": "index.html",
                "/app.js": "app.js",
                "/styles.css": "styles.css",
            }
            if path in files:
                file = STATIC / files[path]
                return self._send(
                    200,
                    file.read_bytes(),
                    (mimetypes.guess_type(file.name)[0] or "text/plain")
                    + "; charset=utf-8",
                )
            raise FileNotFoundError("页面不存在")
        except FileNotFoundError as exc:
            self._send(404, {"error": str(exc)})
        except (ValueError, OSError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception:
            self._send(500, {"error": "读取失败，请检查服务终端和结果文件"})

    def do_POST(self):
        if not self._local_request():
            return self._send(403, {"error": "仅允许本机访问"})
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host"):
            return self._send(403, {"error": "请求来源无效"})
        token = self.headers.get("X-Local-Token", "")
        if not secrets.compare_digest(token, self.app.token):
            return self._send(403, {"error": "页面已过期，请刷新后重试"})
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            return self._send(415, {"error": "请求必须使用 JSON"})
        path = urlsplit(self.path).path
        if path not in ("/api/runs", "/api/pools"):
            return self._send(404, {"error": "接口不存在"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 100_000:
                return self._send(413, {"error": "请求为空或过大"})
            data = json.loads(self.rfile.read(size))
            if path == "/api/pools":
                return self._send(200, self.app.save_pool(data))
            self._send(202, self.app.submit(data))
        except PoolConflict as exc:
            self._send(409, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception:
            self._send(500, {"error": "操作失败，请检查服务终端"})


def make_server(app, host="127.0.0.1", port=DEFAULT_PORT):
    return ThreadingHTTPServer((host, port), partial(Handler, app=app))


def main():
    parser = argparse.ArgumentParser(description="启动本机回测网页")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="自动打开默认浏览器")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1～65535 之间")
    app = WebApplication()
    try:
        server = make_server(app, port=args.port)
    except OSError as exc:
        app.close()
        parser.error(f"服务无法启动：{exc}；可使用 --port 更换端口")
    url = f"http://127.0.0.1:{args.port}"
    print(f"\n回测工作台已启动：{url}\n按 Ctrl+C 停止服务。\n", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭服务…")
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
