#!/usr/bin/env python3
"""Safe HTTP fetcher for papa-seo. The only module in the pack that touches the network.

Library:
    f = Fetcher()                      # 2 s pause between requests by default
    r = f.fetch("https://example.com/")
    r.status, r.final_url, r.chain, r.headers, r.body, r.sha256

CLI:
    python3 scripts/http_safe.py fetch URL [--head] [--timeout S] [--max-bytes N] [--out FILE]

What it refuses:
  * any scheme except http/https; userinfo (user@host); backslash or %-encoding in the authority;
  * private, loopback, link-local, CGNAT, multicast, reserved, IPv6 ULA, cloud metadata addresses,
    including obfuscated IPv4 (0x7f000001, 2130706433, 0177.0.0.1, 127.1) and IPv4 embedded in IPv6
    (::ffff:a.b.c.d, NAT64 64:ff9b::/96, 6to4 2002::/16, Teredo);
  * a hostname if ANY of its DNS answers is non-public (fail closed, also on DNS errors).
The socket connects to the exact IP that was checked (DNS pinning); TLS SNI and Host stay the
original name. Redirects are followed by hand (<= 5), and every hop is checked again from scratch.
Body is capped (5 MB by default), compressed bodies are decompressed with the same cap.

`allow_local=True` exists only for tests on 127.0.0.1: it lets the FIRST url be a loopback address
and lets redirects stay on exactly that origin. Metadata/link-local addresses stay blocked even then.
The CLI does not expose it.

This file also holds the small CLI helpers shared by the other scripts (JSON output, --out path
checks, CSV cell escaping, file reading limits) so that each script stays stdlib-only.
"""
# Design informed by AgriciDaniel/claude-seo scripts/url_safety.py and seo-skills/geo-audit-skill
# lib/http.py (both MIT): same threat list, code written from scratch on http.client.
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import stat
import sys
import tempfile
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

try:  # POSIX advisory lock for the cross-process pause; absent on Windows
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

__version__ = "0.1.1"

USER_AGENT = "papa-seo/0.2 (+https://github.com/AffPapa/papa-seo)"
DEFAULT_DELAY = 2.0          # seconds between requests (SPEC §2 rule 3)
DEFAULT_TIMEOUT = 10.0       # per socket operation
DEFAULT_HOP_DEADLINE = 30.0  # whole request+body of one hop
MAX_BODY = 5 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_URL_LENGTH = 8192
REDIRECT_CODES = {301, 302, 303, 307, 308}

BLOCKED_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata", "metadata.google.internal", "metadata.goog", "metadata.azure.internal",
    "instance-data", "instance-data.ec2.internal", "kubernetes.default", "kubernetes.default.svc",
})
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan", ".intranet", ".corp")
METADATA_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),   # AWS/GCP/Azure/Oracle/OpenStack
    ipaddress.ip_address("169.254.170.2"),     # AWS ECS task metadata
    ipaddress.ip_address("100.100.100.200"),   # Alibaba Cloud
    ipaddress.ip_address("168.63.129.16"),     # Azure WireServer (public range, internal service)
    ipaddress.ip_address("fd00:ec2::254"),     # AWS IMDS IPv6
})
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))
_SAFE_PATH_CHARS = "/%:@!$&'()*+,;=-._~"
_SAFE_QUERY_CHARS = "/%:@!$&'()*+,;=-._~?"
# Response headers worth reporting (tech audit). Anything else is dropped from facts output.
SAFE_HEADERS = frozenset({
    "content-type", "content-length", "content-encoding", "content-language", "content-location",
    "cache-control", "expires", "age", "etag", "last-modified", "vary", "date", "pragma",
    "x-robots-tag", "link", "location", "refresh", "server", "via", "alt-svc", "retry-after",
    "strict-transport-security", "content-security-policy", "content-security-policy-report-only",
    "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy",
    "cross-origin-opener-policy", "cross-origin-embedder-policy", "cross-origin-resource-policy",
    "access-control-allow-origin", "x-xss-protection", "nel", "report-to", "server-timing",
    "cf-cache-status", "cf-ray", "cf-mitigated", "x-cache", "x-cache-status", "x-served-by",
    "x-powered-by", "x-generator", "x-redirect-by", "x-ua-compatible", "x-amz-cf-pop", "x-vercel-cache",
    "set-cookie",
})

# User-Agent strings for `fetch --ua-of` (WAF/CDN checks only). Fallback: the roster field `ua` in
# references/ai-bots.(json|yaml) wins. Checked against vendor docs 2026-10-26; where a doc writes the
# Chrome/Edge version as W.X.Y.Z, 131.0.0.0 is substituted. Token-only agents (Google-Extended,
# Applebot-Extended, YandexAdditional) send no requests: no UA.
BOT_USER_AGENTS = {
    "googlebot": "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/131.0.0.0 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "bingbot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) "
               "Chrome/131.0.0.0 Safari/537.36",
    "yandexbot": "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "gptbot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.4; +https://openai.com/gptbot",
    "oai-searchbot": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/131.0.0.0 Safari/537.36; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot",
    "chatgpt-user": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; "
                    "+https://openai.com/bot",
    # Anthropic publishes robots.txt tokens only, no full string: this one is the commonly reported log format.
    "claudebot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "perplexitybot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; "
                     "+https://perplexity.ai/perplexitybot)",
    "perplexity-user": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; "
                       "+https://perplexity.ai/perplexity-user)",
    "applebot": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
}
BOT_UA_NOT_FROM_DOCS = {"claudebot"}
TOKEN_ONLY_AGENTS = {"google-extended", "applebot-extended", "yandexadditional", "yandexadditionalbot"}

_EXTRA_HEADER_ALLOWLIST = {"accept", "accept-language", "if-modified-since", "if-none-match", "range"}


class SafeHttpError(Exception):
    """Refusal or failure. `code` is a stable machine-readable token."""

    def __init__(self, code: str, message: str, *, url: str | None = None, chain: list | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.url = url
        self.chain = chain or []

    def to_json(self) -> dict:
        out = {"error": self.message, "code": self.code}
        if self.url:
            out["url"] = self.url
        if self.chain:
            out["chain"] = self.chain
        return out


# --------------------------------------------------------------------------- address policy

_NUMERIC_LABEL = re.compile(r"^(?:0x[0-9a-f]*|[0-9]+)$")


def parse_loose_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse the inet_aton() family of IPv4 spellings the way resolvers do.

    Returns None when `host` is clearly a name. Raises SafeHttpError when it looks numeric
    but does not form a valid address (a numeric TLD is never a real public name).
    """
    parts = host.split(".")
    if not parts or not _NUMERIC_LABEL.match(parts[-1]):
        return None
    if not all(_NUMERIC_LABEL.match(p) for p in parts) or len(parts) > 4:
        raise SafeHttpError("malformed_host", f"numeric-looking host refused: {host!r}")
    values = []
    for p in parts:
        try:
            if p.startswith("0x"):
                values.append(int(p[2:] or "0", 16))
            elif len(p) > 1 and p.startswith("0"):
                values.append(int(p, 8))
            else:
                values.append(int(p, 10))
        except ValueError:
            raise SafeHttpError("malformed_host", f"numeric-looking host refused: {host!r}") from None
    head, last = values[:-1], values[-1]
    if any(v > 255 for v in head) or last >= 256 ** (5 - len(values)):
        raise SafeHttpError("malformed_host", f"numeric host out of range: {host!r}")
    number = 0
    for v in head:
        number = (number << 8) | v
    number = (number << (8 * (5 - len(values)))) | last
    return ipaddress.IPv4Address(number)


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    for net in _NAT64:
        if ip in net:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def is_public_ip(value) -> bool:
    """True only for public unicast addresses that are not a cloud metadata service."""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if ip in METADATA_IPS:
        return False
    if ip.version == 6:
        if ip.teredo is not None:
            return False
        inner = _embedded_ipv4(ip)
        if inner is not None:
            return is_public_ip(inner)
    if ip.version == 4 and ip in _CGNAT:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified or not ip.is_global)


def _is_allowed_local_ip(value) -> bool:
    """What allow_local unlocks: loopback only, never metadata / link-local."""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback and ip not in METADATA_IPS


def normalize_host(host: str) -> str:
    """Lowercase, strip one trailing dot, IDNA-encode, canonicalise numeric IPv4 spellings."""
    if not host:
        raise SafeHttpError("missing_host", "URL has no host")
    h = host.strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if ":" in h:  # IPv6 literal (urlsplit already removed brackets)
        try:
            return str(ipaddress.IPv6Address(h))
        except ValueError:
            raise SafeHttpError("malformed_host", f"bad IPv6 literal: {host!r}") from None
    if h.endswith(".") and not h.endswith(".."):
        h = h[:-1]
    if not h or ".." in h or h.startswith("."):
        raise SafeHttpError("malformed_host", f"bad host: {host!r}")
    v4 = parse_loose_ipv4(h)
    if v4 is not None:
        return str(v4)
    if not h.isascii():
        try:
            h = h.encode("idna").decode("ascii")
        except UnicodeError:
            raise SafeHttpError("malformed_host", f"host is not valid IDNA: {host!r}") from None
    if len(h) > 253 or not re.fullmatch(r"[a-z0-9_](?:[a-z0-9_.-]*[a-z0-9_])?", h):
        raise SafeHttpError("malformed_host", f"bad host characters: {host!r}")
    if any(len(label) > 63 for label in h.split(".")):
        raise SafeHttpError("malformed_host", f"DNS label too long: {host!r}")
    return h


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class Target:
    url: str          # normalised URL (no fragment)
    scheme: str
    host: str         # normalised host (IP literal without brackets)
    port: int
    request_path: str  # path?query, percent-encoded

    @property
    def origin(self) -> tuple[str, str, int]:
        return (self.scheme, self.host, self.port)


_AUTHORITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)")


def validate_url(url: str, *, allow_local: bool = False) -> Target:
    """Parse and check a URL without touching the network. Raises SafeHttpError."""
    if not isinstance(url, str) or not url:
        raise SafeHttpError("bad_url", "empty URL")
    if len(url) > MAX_URL_LENGTH:
        raise SafeHttpError("bad_url", "URL too long")
    if any(ord(c) <= 0x20 or ord(c) == 0x7F for c in url):
        raise SafeHttpError("bad_url", "URL contains whitespace or control characters", url=url)
    m = _AUTHORITY_RE.match(url)
    if not m:
        raise SafeHttpError("scheme_not_allowed", "only absolute http(s) URLs are allowed", url=url)
    authority = m.group(1)
    if "\\" in authority:
        raise SafeHttpError("authority_confusion", "backslash in URL authority", url=url)
    if "@" in authority:
        raise SafeHttpError("userinfo_not_allowed", "userinfo (user@host) is not allowed", url=url)
    if "%" in authority:
        raise SafeHttpError("authority_confusion", "percent-encoding in URL authority", url=url)
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SafeHttpError("scheme_not_allowed", f"scheme {scheme!r} is not allowed", url=url)
    try:
        port = parts.port
    except ValueError:
        raise SafeHttpError("bad_port", "invalid port", url=url) from None
    if port is None:
        port = 443 if scheme == "https" else 80
    if not 1 <= port <= 65535:
        raise SafeHttpError("bad_port", "invalid port", url=url)
    host = normalize_host(parts.hostname or "")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        if not (allow_local and host in ("localhost", "ip6-localhost")):
            raise SafeHttpError("blocked_host", f"host {host!r} is internal", url=url)
    if _is_ip_literal(host):
        if not is_public_ip(host) and not (allow_local and _is_allowed_local_ip(host)):
            raise SafeHttpError("blocked_address", f"address {host} is not public", url=url)
    path = quote(parts.path or "/", safe=_SAFE_PATH_CHARS)
    query = quote(parts.query, safe=_SAFE_QUERY_CHARS) if parts.query else ""
    request_path = path + ("?" + query if query else "")
    netloc_host = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    netloc = netloc_host if port == default_port else f"{netloc_host}:{port}"
    normalized = urlunsplit((scheme, netloc, path, query, ""))
    return Target(normalized, scheme, host, port, request_path)


# --------------------------------------------------------------------------- DNS

_getaddrinfo = socket.getaddrinfo        # patched in tests
_gethostbyaddr = socket.gethostbyaddr    # patched in tests


def _with_timeout(fn: Callable, timeout: float, *args):
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(fn, *args).result(timeout=timeout)
    finally:
        pool.shutdown(wait=False)


def resolve_host(host: str, port: int, *, allow_local: bool = False, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Resolve and return ONE address to connect to. Every answer must pass the policy."""
    if _is_ip_literal(host):
        return host
    try:
        infos = _with_timeout(_getaddrinfo, timeout, host, port, 0, socket.SOCK_STREAM)
    except concurrent.futures.TimeoutError:
        raise SafeHttpError("dns_timeout", f"DNS timeout for {host}") from None
    except (OSError, UnicodeError) as exc:
        raise SafeHttpError("dns_failed", f"DNS lookup failed for {host}: {exc}") from None
    addresses = []
    for info in infos:
        addr = info[4][0]
        if "%" in addr:  # scoped IPv6 (fe80::1%en0)
            raise SafeHttpError("blocked_address", f"{host} resolves to a scoped address")
        addresses.append(addr)
    if not addresses:
        raise SafeHttpError("dns_failed", f"no addresses for {host}")
    for addr in addresses:
        if not is_public_ip(addr) and not (allow_local and _is_allowed_local_ip(addr)):
            raise SafeHttpError("blocked_address", f"{host} resolves to non-public {addr}")
    return addresses[0]


def reverse_dns(ip: str, *, timeout: float = 5.0) -> str | None:
    """PTR lookup. None when there is no record or on timeout."""
    try:
        name = _with_timeout(_gethostbyaddr, timeout, ip)[0]
    except (OSError, concurrent.futures.TimeoutError, UnicodeError):
        return None
    return name.rstrip(".").lower() if name else None


def forward_dns(name: str, *, timeout: float = 5.0) -> list[str]:
    """A/AAAA lookup, returns unique addresses (canonical text form)."""
    try:
        infos = _with_timeout(_getaddrinfo, timeout, name, None, 0, socket.SOCK_STREAM)
    except (OSError, concurrent.futures.TimeoutError, UnicodeError):
        return []
    seen = []
    for info in infos:
        try:
            addr = str(ipaddress.ip_address(info[4][0].split("%")[0]))
        except ValueError:
            continue
        if addr not in seen:
            seen.append(addr)
    return seen


# --------------------------------------------------------------------------- connections

class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float, context: ssl.SSLContext):
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _read_bounded(resp, limit: int, deadline: float) -> tuple[bytes, bool]:
    chunks, total = [], 0
    while total <= limit:
        if time.monotonic() > deadline:
            raise SafeHttpError("timeout", "body read exceeded the deadline")
        chunk = resp.read(min(65536, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    data = b"".join(chunks)
    return (data[:limit], True) if len(data) > limit else (data, False)


def _decompress_bounded(data: bytes, encoding: str, limit: int) -> tuple[bytes, bool, str | None]:
    enc = encoding.strip().lower()
    if enc in ("", "identity"):
        return data, False, None
    if enc in ("gzip", "x-gzip", "deflate"):
        wbits = (16 + zlib.MAX_WBITS) if enc != "deflate" else zlib.MAX_WBITS
        for bits in ((wbits, -zlib.MAX_WBITS) if enc == "deflate" else (wbits,)):
            try:
                d = zlib.decompressobj(bits)
                out = d.decompress(data, limit + 1)
                truncated = len(out) > limit or bool(d.unconsumed_tail)
                return out[:limit], truncated, None
            except zlib.error:
                continue
        return data, False, f"could not decode {enc} body"
    return data, False, f"unsupported content-encoding {enc!r}; body left as received"


_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9._:-]+)", re.I)
_META_CHARSET_RE = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?([A-Za-z0-9._:-]+)", re.I)


def decode_body(body: bytes, content_type: str | None = None) -> str:
    """bytes -> str using BOM, Content-Type charset, <meta charset>, then UTF-8 (replace)."""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if body.startswith(bom):
            return body[len(bom):].decode(enc, errors="replace")
    candidates = []
    if content_type:
        m = _CHARSET_RE.search(content_type)
        if m:
            candidates.append(m.group(1))
    m = _META_CHARSET_RE.search(body[:4096])
    if m:
        candidates.append(m.group(1).decode("ascii", "replace"))
    for enc in candidates:
        try:
            return body.decode(enc, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


@dataclass
class Response:
    url: str
    final_url: str
    method: str
    status: int
    reason: str
    headers: dict
    chain: list
    body: bytes = field(repr=False)
    truncated: bool
    ip: str
    elapsed_ms: int
    fetched_at: str
    notes: list = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    def text(self) -> str:
        return decode_body(self.body, self.content_type)

    def safe_headers(self) -> dict:
        return {k: v for k, v in self.headers.items() if k in SAFE_HEADERS}

    def to_json(self) -> dict:
        return {
            "url": self.url, "final_url": self.final_url, "method": self.method,
            "status": self.status, "reason": self.reason, "chain": self.chain,
            "headers": self.headers, "bytes": len(self.body), "sha256": self.sha256,
            "truncated": self.truncated, "content_type": self.content_type, "ip": self.ip,
            "elapsed_ms": self.elapsed_ms, "fetched_at": self.fetched_at, "notes": self.notes,
        }


def _headers_to_dict(pairs: Iterable[tuple[str, str]]) -> dict:
    out: dict[str, str] = {}
    for k, v in pairs:
        key = k.strip().lower()
        if key == "set-cookie":
            v = "[redacted]"
        out[key] = v if key not in out else out[key] + ", " + v
    return out


class Fetcher:
    """Sequential fetcher with a pause between requests. Not thread-safe by design: one stream."""

    def __init__(self, *, delay: float = DEFAULT_DELAY, timeout: float = DEFAULT_TIMEOUT,
                 max_bytes: int = MAX_BODY, max_redirects: int = MAX_REDIRECTS,
                 user_agent: str = USER_AGENT, allow_local: bool = False,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 state_dir: str | None = None, shared_pace: bool = True,
                 wall: Callable[[], float] = time.time):
        self.delay = max(0.0, float(delay))
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.allow_local = allow_local
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self._ssl = ssl.create_default_context()
        self.requests_made = 0
        self.state_dir = state_dir
        self.shared_pace = shared_pace
        self._wall = wall
        self.pace_notes: list[str] = []
        self.waited_s = 0.0

    def _pace(self, host: str):
        """Pause before a request: in-process, and across processes via a per-host timestamp file."""
        local_wait = 0.0
        if self._last is not None and self.delay > 0:
            local_wait = self.delay - (self._clock() - self._last)
        if self.delay > 0 and self.shared_pace:
            self._pace_shared(host, local_wait)
        elif local_wait > 0:
            self._do_sleep(local_wait)
        self._last = self._clock()

    def _do_sleep(self, seconds: float):
        self.waited_s += seconds
        self._sleep(seconds)

    def pace_file(self, host: str) -> str:
        base = self.state_dir or tempfile.gettempdir()
        digest = hashlib.sha256(host.encode("utf-8")).hexdigest()[:24]
        return os.path.join(base, f"papa-seo-pace-{digest}.ts")

    def _pace_shared(self, host: str, local_wait: float):
        path = self.pace_file(host)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except OSError as exc:
            self.pace_notes.append(f"shared pause unavailable ({exc.strerror}); in-process pause only")
            if local_wait > 0:
                self._do_sleep(local_wait)
            return
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)  # serialises concurrent processes on this host
            raw = os.read(fd, 64)
            try:
                last = float(raw.decode("ascii").strip())
            except ValueError:
                last = None
            shared_wait = 0.0
            if last is not None:
                elapsed = self._wall() - last
                shared_wait = self.delay if elapsed < 0 else self.delay - elapsed
            wait = min(self.delay, max(local_wait, shared_wait))
            if wait > 0:
                self._do_sleep(wait)
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, repr(self._wall()).encode("ascii"))
        finally:
            os.close(fd)  # releases the flock

    def fetch(self, url: str, *, method: str = "GET", headers: dict | None = None,
              max_bytes: int | None = None, allow_local: bool | None = None) -> Response:
        method = method.upper()
        if method not in ("GET", "HEAD"):
            raise SafeHttpError("method_not_allowed", "only GET and HEAD are allowed")
        limit = self.max_bytes if max_bytes is None else int(max_bytes)
        local = self.allow_local if allow_local is None else allow_local
        extra = {}
        for k, v in (headers or {}).items():
            if k.lower() not in _EXTRA_HEADER_ALLOWLIST or any(c in str(v) for c in "\r\n"):
                raise SafeHttpError("header_not_allowed", f"header {k!r} is not allowed")
            extra[k] = str(v)

        target = validate_url(url, allow_local=local)
        local_origin = target.origin if (local and not is_public_ip(target.host)) else None
        chain: list[dict] = []
        started = time.monotonic()
        current_method = method
        for hop in range(self.max_redirects + 1):
            hop_local = local_origin is not None and target.origin == local_origin
            if hop > 0:
                target = validate_url(target.url, allow_local=hop_local)
            ip = resolve_host(target.host, target.port, allow_local=hop_local, timeout=self.timeout)
            self._pace(target.host)
            status, reason, hdrs, body, truncated, notes = self._one_request(
                target, ip, current_method, extra, limit)
            self.requests_made += 1
            location = hdrs.get("location")
            step = {"url": target.url, "status": status}
            if status in REDIRECT_CODES and location:
                step["location"] = location
            chain.append(step)
            if status in REDIRECT_CODES and location:
                if hop == self.max_redirects:
                    raise SafeHttpError("too_many_redirects", f"more than {self.max_redirects} redirects",
                                        url=url, chain=chain)
                next_url = urljoin(target.url, location.strip())
                try:
                    next_target = validate_url(next_url, allow_local=False)
                except SafeHttpError as exc:
                    same_local = False
                    if local_origin is not None:
                        try:
                            same_local = validate_url(next_url, allow_local=True).origin == local_origin
                        except SafeHttpError:
                            same_local = False
                    if not same_local:
                        exc.url, exc.chain = next_url, chain
                        exc.message = "redirect refused: " + exc.message
                        raise exc
                    next_target = validate_url(next_url, allow_local=True)
                if target.scheme == "https" and next_target.scheme == "http":
                    notes.append("redirect downgrades https -> http")
                if status == 303 and current_method != "HEAD":
                    current_method = "GET"
                target = next_target
                continue
            return Response(
                url=url, final_url=target.url, method=current_method, status=status, reason=reason,
                headers=hdrs, chain=chain, body=body, truncated=truncated, ip=ip,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), notes=notes)
        raise SafeHttpError("too_many_redirects", "redirect limit reached", url=url, chain=chain)

    def _one_request(self, target: Target, ip: str, method: str, extra: dict, limit: int):
        if target.scheme == "https":
            conn = _PinnedHTTPSConnection(target.host, target.port, ip, self.timeout, self._ssl)
        else:
            conn = _PinnedHTTPConnection(target.host, target.port, ip, self.timeout)
        deadline = time.monotonic() + max(self.timeout, DEFAULT_HOP_DEADLINE)
        notes: list[str] = []
        try:
            conn.putrequest(method, target.request_path, skip_accept_encoding=True)
            base = {"User-Agent": self.user_agent, "Accept": "*/*", "Accept-Encoding": "identity",
                    "Connection": "close"}
            base.update(extra)
            for k, v in base.items():
                conn.putheader(k, v)
            conn.endheaders()
            resp = conn.getresponse()
            hdrs = _headers_to_dict(resp.getheaders())
            if method == "HEAD" or resp.status in REDIRECT_CODES:
                body, truncated = (b"", False) if method == "HEAD" else _read_bounded(resp, 65536, deadline)
            else:
                body, truncated = _read_bounded(resp, limit, deadline)
                enc = hdrs.get("content-encoding", "")
                if enc:
                    body, dtrunc, note = _decompress_bounded(body, enc, limit)
                    truncated = truncated or dtrunc
                    if note:
                        notes.append(note)
            if truncated:
                notes.append(f"body truncated at {limit} bytes")
            return resp.status, resp.reason, hdrs, body, truncated, notes
        except SafeHttpError:
            raise
        except ssl.SSLError as exc:
            raise SafeHttpError("tls_error", f"TLS error: {exc}", url=target.url) from None
        except (socket.timeout, TimeoutError):
            raise SafeHttpError("timeout", "connection timed out", url=target.url) from None
        except (OSError, http.client.HTTPException) as exc:
            raise SafeHttpError("connection_failed", f"{type(exc).__name__}: {exc}", url=target.url) from None
        finally:
            conn.close()


_default_fetcher: Fetcher | None = None


def fetch(url: str, **kwargs) -> Response:
    """Module-level fetch sharing one paced Fetcher (2 s between calls)."""
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = Fetcher()
    return _default_fetcher.fetch(url, **kwargs)


# --------------------------------------------------------------------------- shared CLI helpers

class CliError(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code


class JsonArgumentParser(argparse.ArgumentParser):
    """argparse that reports usage errors as JSON instead of printing to stderr."""

    def error(self, message):  # noqa: D401
        raise CliError(message, "bad_arguments")


# Characters an agent cannot see but a model still reads: zero-width, bidi controls, tag block.
INVISIBLE_CHARS = frozenset(
    [0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180E, 0x3164, 0xFEFF, 0xFFA0]
    + list(range(0x200B, 0x2010)) + list(range(0x202A, 0x202F)) + list(range(0x2060, 0x2070))
    + list(range(0xFFF9, 0xFFFC))
)


def _is_invisible(cp: int) -> bool:
    return (cp in INVISIBLE_CHARS or 0xE0000 <= cp <= 0xE007F or 0x80 <= cp <= 0x9F
            or 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF)


def _json_escape_cp(cp: int) -> str:
    if cp <= 0xFFFF:
        return "\\u%04x" % cp
    v = cp - 0x10000
    return "\\u%04x\\u%04x" % (0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF))


def dump_json(data, *, indent: int | None = 1) -> str:
    """JSON with readable Cyrillic but every invisible character spelled as an escape."""
    text = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    if any(_is_invisible(ord(c)) for c in text):
        text = "".join(_json_escape_cp(ord(c)) if _is_invisible(ord(c)) else c for c in text)
    return text


def escape_snippet(text: str, limit: int = 200) -> str:
    """Untrusted text for evidence: invisible chars as <U+XXXX>, newlines collapsed, truncated."""
    out = []
    for c in text:
        cp = ord(c)
        if _is_invisible(cp):
            out.append("<U+%04X>" % cp)
        elif c in "\r\n\t":
            out.append(" ")
        elif cp < 0x20 or cp == 0x7F:
            out.append("<U+%04X>" % cp)
        else:
            out.append(c)
    s = re.sub(r" {2,}", " ", "".join(out)).strip()
    return s if len(s) <= limit else s[:limit] + "…"


def safe_out_path(path: str) -> str:
    """Validate an --out path: no '..' components, not a symlink, not a directory, parent exists."""
    if not path or "\x00" in path:
        raise CliError("empty or invalid --out path", "bad_out_path")
    parts = re.split(r"[\\/]+", path)
    if any(p == ".." for p in parts):
        raise CliError(f"--out path may not contain '..': {path!r}", "bad_out_path")
    full = os.path.abspath(path)
    if os.path.islink(full):
        raise CliError("--out path is a symlink", "bad_out_path")
    if os.path.isdir(full):
        raise CliError("--out path is a directory", "bad_out_path")
    if not os.path.isdir(os.path.dirname(full)):
        raise CliError("--out directory does not exist", "bad_out_path")
    return full


def safe_filename(name: str, default: str = "file") -> str:
    """Turn an untrusted name (URL slug, header value) into one safe path component."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "")
    base = re.sub(r"\.{2,}", "_", base).lstrip(".-")
    return base[:120] or default


def write_atomic(path: str, data: str | bytes) -> None:
    full = safe_out_path(path)
    fd, tmp = tempfile.mkstemp(prefix=".papa-seo-", dir=os.path.dirname(full))
    try:
        if isinstance(data, bytes):
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        else:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(data)
        os.replace(tmp, full)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def emit(data: dict, out: str | None, summary: dict | None = None) -> int:
    """Print JSON, or write it to --out and print a short summary."""
    if out:
        write_atomic(out, dump_json(data) + "\n")
        print(dump_json({"ok": True, "out": os.path.abspath(out), **(summary or {})}))
    else:
        print(dump_json(data))
    return 0


def emit_error(message: str, code: str = "error", extra: dict | None = None) -> int:
    print(dump_json({"error": message, "code": code, **(extra or {})}))
    return 2 if code == "bad_arguments" else 1


def run_cli(fn: Callable[[], int]) -> int:
    """Run a CLI body and convert every failure to a JSON error with a non-zero exit code."""
    try:
        return fn()
    except CliError as exc:
        return emit_error(exc.message, exc.code)
    except SafeHttpError as exc:
        print(dump_json(exc.to_json()))
        return 1
    except KeyboardInterrupt:
        return emit_error("interrupted", "interrupted")
    except Exception as exc:  # last resort: still JSON, never a traceback into the agent
        return emit_error(f"{type(exc).__name__}: {exc}", "internal_error")


def read_input_file(path: str, max_bytes: int) -> tuple[bytes, bool]:
    """Read a regular file with a size cap. Devices, FIFOs and directories are refused."""
    if not path or "\x00" in path:
        raise CliError("invalid file path", "bad_input")
    try:
        st = os.stat(path)
    except OSError as exc:
        raise CliError(f"cannot read {path!r}: {exc.strerror}", "bad_input") from None
    if not stat.S_ISREG(st.st_mode):
        raise CliError(f"{path!r} is not a regular file", "bad_input")
    with open(path, "rb") as fh:
        data = fh.read(max_bytes + 1)
    return (data[:max_bytes], True) if len(data) > max_bytes else (data, False)


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠")


def is_formula_like(value) -> bool:
    return isinstance(value, str) and value.lstrip(" ").startswith(_FORMULA_START)


def csv_safe(value):
    """Escape a cell for CSV export so spreadsheets do not run it as a formula."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    s = str(value)
    return "'" + s if is_formula_like(s) else s


def is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value or "", re.I))


def check_state_dir(path: str | None) -> str | None:
    """--state-dir: an existing directory (not created, not a symlink). None -> system temp dir."""
    if not path:
        return None
    if "\x00" in path or any(p == ".." for p in re.split(r"[\\/]+", path)):
        raise CliError("--state-dir may not contain '..'", "bad_arguments")
    if os.path.islink(path) or not os.path.isdir(path):
        raise CliError("--state-dir must be an existing directory (not a symlink)", "bad_arguments")
    return os.path.abspath(path)


def add_pace_args(p: argparse.ArgumentParser, *, delay: bool = True):
    if delay:
        p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="pause between requests, >= 2 s")
    p.add_argument("--state-dir", help="where the per-host pause timestamp lives (default: system temp)")


def check_delay(value: float) -> float:
    if value < 2.0:
        raise CliError("--delay must be >= 2 seconds", "bad_arguments")
    return value


def resolve_bot_ua(name: str) -> tuple[str, str, str]:
    """(name, User-Agent, source) for a known bot token: roster `ua` field first, then BOT_USER_AGENTS."""
    key = (name or "").strip().lower()
    if key in TOKEN_ONLY_AGENTS:
        raise CliError(f"{name} is a robots.txt token only and sends no requests: no User-Agent", "unknown_bot_ua")
    try:
        import robots_check  # lazy: robots_check imports this module
        roster, _, _ = robots_check.load_roster()
        for bot in roster:
            if bot["name"].lower() == key and bot.get("ua"):
                src = "roster: документация вендора" + (f", сверено {bot['ua_checked']}" if bot.get("ua_checked") else "")
                return bot["name"], str(bot["ua"]), src
    except (ImportError, CliError):
        pass
    if key in BOT_USER_AGENTS:
        src = ("встроенная таблица: вендор полной строки не публикует, формат по логам сайтов"
               if key in BOT_UA_NOT_FROM_DOCS else "встроенная таблица: документация вендора, сверено 2026-10-26")
        return name, BOT_USER_AGENTS[key], src
    known = ", ".join(sorted(BOT_USER_AGENTS))
    raise CliError(f"no known User-Agent for {name!r}; known: {known}", "unknown_bot_ua")


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    def body() -> int:
        p = JsonArgumentParser(prog="http_safe.py", description="Safe GET/HEAD, JSON out")
        sub = p.add_subparsers(dest="cmd")
        f = sub.add_parser("fetch", help="fetch one URL")
        f.add_argument("url")
        f.add_argument("--head", action="store_true", help="HEAD instead of GET")
        f.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
        f.add_argument("--max-bytes", type=int, default=MAX_BODY)
        f.add_argument("--save-body", help="write the raw body to this file (same path rules as --out)")
        f.add_argument("--text", action="store_true", help="add visible text of <main> (or <body>)")
        f.add_argument("--text-limit", type=int, default=20000, help="max characters of --text")
        f.add_argument("--ua-of", help="send the User-Agent of this bot (WAF/CDN check), e.g. GPTBot")
        add_pace_args(f, delay=False)
        f.add_argument("--out")
        args = p.parse_args(argv)
        if args.cmd != "fetch":
            raise CliError("usage: http_safe.py fetch URL [--head] [--out FILE]", "bad_arguments")
        if not 0 < args.max_bytes <= 50 * 1024 * 1024:
            raise CliError("--max-bytes must be between 1 and 52428800", "bad_arguments")
        if not 100 <= args.text_limit <= 1_000_000:
            raise CliError("--text-limit must be 100..1000000", "bad_arguments")
        for path in (args.out, args.save_body):
            if path:
                safe_out_path(path)
        if args.out and args.save_body and os.path.abspath(args.out) == os.path.abspath(args.save_body):
            raise CliError("--out and --save-body must differ", "bad_arguments")
        ua, as_bot, ua_source = USER_AGENT, None, None
        if args.ua_of:
            as_bot, ua, ua_source = resolve_bot_ua(args.ua_of)
        fetcher = Fetcher(timeout=args.timeout, max_bytes=args.max_bytes, user_agent=ua,
                          state_dir=check_state_dir(args.state_dir))
        resp = fetcher.fetch(args.url, method="HEAD" if args.head else "GET")
        data = resp.to_json()
        data["user_agent"] = ua
        if as_bot:
            data["as_bot"] = as_bot
            data["ua_source"] = ua_source
            data["notes"].append(f"Запрос шёл с User-Agent бота {as_bot}: это проверка WAF/CDN, "
                                 f"а не настоящий визит бота (IP не его)")
        if fetcher.waited_s:
            data["waited_s"] = round(fetcher.waited_s, 2)
        data["notes"].extend(fetcher.pace_notes)
        if args.save_body:
            write_atomic(args.save_body, resp.body)
            data["body_saved_to"] = os.path.abspath(args.save_body)
        if args.text and not args.head:
            import page_facts  # lazy: page_facts imports this module
            data["text"] = page_facts.visible_text(resp.text(), resp.final_url, limit=args.text_limit)
        return emit(data, args.out, {"status": resp.status, "bytes": len(resp.body)})

    return run_cli(body)


if __name__ == "__main__":
    sys.exit(main())
