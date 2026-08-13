"""Zero-dependency HTTP server: router, static files, JSON plumbing.

Built on http.server.ThreadingHTTPServer so the whole application runs with
nothing but a Python 3.9+ interpreter. No pip install, no virtualenv, no admin
rights — which is the difference between "we can use this next week" and "we
filed a ticket".
"""

import json
import mimetypes
import os
import posixpath
import re
import socket
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from harness import auth, db

ROUTES = []
STATIC_DIR = None
COOKIE = "mdmp_session"


class HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def route(method, pattern, auth_required=True):
    """Register a handler. `pattern` uses {name} for path parameters."""
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
                       + "$")

    def wrap(fn):
        ROUTES.append((method.upper(), regex, fn, auth_required))
        return fn
    return wrap


class Request:
    def __init__(self, method, path, query, body, headers, params, user, token):
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.headers = headers
        self.params = params
        self.user = user
        self.token = token

    def json(self):
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError:
            raise HttpError(400, "request body was not valid JSON")

    def arg(self, name, default=None):
        vals = self.query.get(name)
        return vals[0] if vals else default

    def int_arg(self, name, default=0):
        try:
            return int(self.arg(name, default))
        except (TypeError, ValueError):
            return default


class Response:
    def __init__(self, body=b"", status=200, content_type="application/json",
                 headers=None):
        self.body = body
        self.status = status
        self.content_type = content_type
        self.headers = headers or {}


def json_response(data, status=200, headers=None):
    return Response(json.dumps(data, default=str).encode("utf-8"), status,
                    "application/json; charset=utf-8", headers)


def text_response(text, status=200, content_type="text/plain; charset=utf-8",
                  filename=None):
    headers = {}
    if filename:
        headers["Content-Disposition"] = 'attachment; filename="%s"' % filename
    body = text if isinstance(text, bytes) else text.encode("utf-8")
    return Response(body, status, content_type, headers)


class Handler(BaseHTTPRequestHandler):
    server_version = "MDMP-Harness/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("MDMP_QUIET"):
            return
        code = args[1] if len(args) > 1 else ""
        if str(code).startswith(("4", "5")):
            print("  %s %s" % (self.address_string(), fmt % args))

    # -- plumbing -------------------------------------------------------
    def _cookies(self):
        raw = self.headers.get("Cookie", "")
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        if length > 32 * 1024 * 1024:
            raise HttpError(413, "request too large")
        return self.rfile.read(length)

    def _send(self, resp):
        self.send_response(resp.status)
        self.send_header("Content-Type", resp.content_type)
        self.send_header("Content-Length", str(len(resp.body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in resp.headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp.body)

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)

        try:
            body = self._read_body()
        except HttpError as e:
            return self._send(json_response({"error": e.message}, e.status))

        token = self._cookies().get(COOKIE)
        user = None
        try:
            user = auth.user_for_token(token)
        except Exception:
            user = None

        for m, regex, fn, auth_required in ROUTES:
            if m != method:
                continue
            match = regex.match(path)
            if not match:
                continue
            if auth_required and not user:
                return self._send(json_response(
                    {"error": "sign in required", "auth": False}, 401))
            req = Request(method, path, query, body, self.headers,
                          match.groupdict(), user, token)
            try:
                result = fn(req)
            except HttpError as e:
                return self._send(json_response({"error": e.message}, e.status))
            except Exception:
                traceback.print_exc()
                return self._send(json_response(
                    {"error": "internal error — see the server console"}, 500))
            if isinstance(result, Response):
                return self._send(result)
            return self._send(json_response(result))

        if method in ("GET", "HEAD"):
            return self._send(self._static(path))
        return self._send(json_response({"error": "not found"}, 404))

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        safe = posixpath.normpath(path).lstrip("/")
        if safe.startswith("..") or os.path.isabs(safe):
            return json_response({"error": "not found"}, 404)
        full = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(full):
            # Single-page app: unknown paths fall back to the shell.
            full = os.path.join(STATIC_DIR, "index.html")
            if not os.path.isfile(full):
                return json_response({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            data = fh.read()
        return Response(data, 200, ctype, {"Cache-Control": "no-cache"})

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def local_addresses():
    """Every address other laptops could reach this server on."""
    addrs = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" in ip:
                continue
            if ip.startswith("127."):
                continue
            addrs.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 1))  # TEST-NET-1; no packet is actually sent
        addrs.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(addrs)


def serve(host="0.0.0.0", port=8080, static_dir=None):
    global STATIC_DIR
    STATIC_DIR = static_dir
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd
