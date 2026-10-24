"""Test helper: a throwaway HTTP server on 127.0.0.1 with scripted routes. Not a test module."""
from __future__ import annotations

import gzip
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


class Route:
    def __init__(self, status=200, body=b"", headers=None, delay=0.0):
        self.status, self.body, self.headers, self.delay = status, body, headers or {}, delay


class LocalServer:
    """routes: path -> Route or callable(handler) -> Route. Records every request."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[dict] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep test output clean
                pass

            def _serve(self, with_body: bool):
                server.requests.append({"path": self.path, "method": self.command,
                                        "headers": {k.lower(): v for k, v in self.headers.items()}})
                route = server.routes.get(self.path.split("?")[0])
                if callable(route):
                    route = route(self)
                if route is None:
                    route = Route(404, b"not found")
                if route.delay:
                    time.sleep(route.delay)
                body = route.body.encode() if isinstance(route.body, str) else route.body
                self.send_response(route.status)
                for k, v in route.headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if with_body:
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def do_GET(self):
                self._serve(True)

            def do_HEAD(self):
                self._serve(False)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def gzip_bytes(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9)
