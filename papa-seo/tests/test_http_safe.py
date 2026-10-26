"""http_safe: SSRF policy, redirects, limits, pacing, CLI. Network only to 127.0.0.1 (this test's server)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import tempfile
import unittest
from unittest import mock

import _localserver as ls
from _localserver import LocalServer, Route

import http_safe as hs


def run_cli(main, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, json.loads(buf.getvalue())


class UrlPolicyTest(unittest.TestCase):
    def assertRefused(self, url, code=None, **kw):
        with self.assertRaises(hs.SafeHttpError) as ctx:
            hs.validate_url(url, **kw)
        if code:
            self.assertEqual(ctx.exception.code, code, url)

    def test_obfuscated_ipv4_loopback(self):
        for url in ("http://0x7f000001/", "http://2130706433/", "http://0177.0.0.1/", "http://127.1/",
                    "http://0x7f.1/", "http://127.0.0.1./", "http://0x7F.0.0.1/"):
            self.assertRefused(url, "blocked_address")

    def test_parse_loose_ipv4(self):
        self.assertEqual(str(hs.parse_loose_ipv4("0x7f000001")), "127.0.0.1")
        self.assertEqual(str(hs.parse_loose_ipv4("2130706433")), "127.0.0.1")
        self.assertEqual(str(hs.parse_loose_ipv4("0251.0376.0251.0376")), "169.254.169.254")
        self.assertIsNone(hs.parse_loose_ipv4("example.com"))
        with self.assertRaises(hs.SafeHttpError):
            hs.parse_loose_ipv4("1.2.3.4.5")
        with self.assertRaises(hs.SafeHttpError):
            hs.parse_loose_ipv4("256.1.1.1")
        with self.assertRaises(hs.SafeHttpError):
            hs.parse_loose_ipv4("08.1.1.1")

    def test_userinfo_refused(self):
        self.assertRefused("http://user@example.com/", "userinfo_not_allowed")
        self.assertRefused("http://user:pass@example.com/", "userinfo_not_allowed")
        self.assertRefused("http://example.com@169.254.169.254/", "userinfo_not_allowed")

    def test_authority_confusion(self):
        self.assertRefused("http://example.com\\@evil.com/", "authority_confusion")
        self.assertRefused("http://%31%32%37.0.0.1/", "authority_confusion")
        self.assertRefused("http://[fe80::1%25en0]/", "authority_confusion")

    def test_ipv6_private_forms(self):
        for url in ("http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://[fd00::1]/", "http://[fe80::1]/",
                    "http://[fd00:ec2::254]/", "http://[64:ff9b::7f00:1]/", "http://[2002:7f00:1::]/", "http://[::]/"):
            self.assertRefused(url, "blocked_address")

    def test_metadata_and_private_v4(self):
        for url in ("http://169.254.169.254/latest/meta-data/", "http://100.100.100.200/", "http://10.0.0.1/",
                    "http://192.168.1.1/", "http://172.16.0.1/", "http://100.64.0.1/", "http://0.0.0.0/",
                    "http://224.0.0.1/", "http://168.63.129.16/"):
            self.assertRefused(url, "blocked_address")

    def test_metadata_blocked_even_with_allow_local(self):
        self.assertRefused("http://169.254.169.254/", "blocked_address", allow_local=True)
        self.assertRefused("http://10.0.0.1/", "blocked_address", allow_local=True)
        self.assertEqual(hs.validate_url("http://127.0.0.1:8080/x", allow_local=True).host, "127.0.0.1")

    def test_internal_hostnames(self):
        for url in ("http://localhost/", "http://metadata.google.internal./", "http://foo.localhost/",
                    "http://printer.local/", "http://METADATA/"):
            self.assertRefused(url, "blocked_host")

    def test_schemes(self):
        for url in ("file:///etc/passwd", "gopher://example.com/", "ftp://example.com/", "javascript:alert(1)",
                    "//example.com/", "dict://127.0.0.1:11211/"):
            self.assertRefused(url)

    def test_whitespace_and_control(self):
        self.assertRefused("http://example.com/\r\nHost: evil", "bad_url")
        self.assertRefused("http://exa mple.com/", "bad_url")

    def test_public_ok_and_normalised(self):
        t = hs.validate_url("HTTPS://Example.COM./путь?q=1#frag")
        self.assertEqual(t.host, "example.com")
        self.assertEqual(t.port, 443)
        self.assertTrue(t.request_path.startswith("/%D0%BF"))
        self.assertNotIn("frag", t.url)
        self.assertEqual(hs.validate_url("http://93.184.215.14/").host, "93.184.215.14")

    def test_dns_resolving_to_private_is_refused(self):
        fake = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with mock.patch.object(hs, "_getaddrinfo", return_value=fake):
            with self.assertRaises(hs.SafeHttpError) as ctx:
                hs.resolve_host("rebind.example", 80)
        self.assertEqual(ctx.exception.code, "blocked_address")

    def test_dns_mixed_answers_fail_closed(self):
        fake = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 80)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]
        with mock.patch.object(hs, "_getaddrinfo", return_value=fake):
            with self.assertRaises(hs.SafeHttpError):
                hs.resolve_host("mixed.example", 80)

    def test_dns_error_fails_closed(self):
        with mock.patch.object(hs, "_getaddrinfo", side_effect=socket.gaierror("nope")):
            with self.assertRaises(hs.SafeHttpError) as ctx:
                hs.resolve_host("nx.example", 80)
        self.assertEqual(ctx.exception.code, "dns_failed")

    def test_constants(self):
        self.assertEqual(hs.DEFAULT_DELAY, 2.0)
        self.assertEqual(hs.USER_AGENT, "papa-seo/0.1 (+https://affpapa.org/papa-seo)")
        self.assertEqual(hs.MAX_BODY, 5 * 1024 * 1024)
        self.assertEqual(hs.Fetcher().delay, 2.0)


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.bomb = ls.gzip_bytes(b"\0" * (20 * 1024 * 1024))

        def to_meta(h):
            return Route(302, b"", {"Location": "http://169.254.169.254/latest/meta-data/"})

        routes = {
            "/ok": Route(200, "<html>ok</html>", {"Content-Type": "text/html; charset=utf-8",
                                                  "Set-Cookie": "session=secret"}),
            "/r1": Route(301, b"", {"Location": "/r2"}),
            "/r2": Route(302, b"", {"Location": "/ok"}),
            "/meta": to_meta,
            "/hex": Route(302, b"", {"Location": "http://0x7f000001/"}),
            "/other-loopback": Route(302, b"", {"Location": "http://127.0.0.2:%d/ok"}),
            "/userinfo": Route(302, b"", {"Location": "http://user@example.com/"}),
            "/file": Route(302, b"", {"Location": "file:///etc/passwd"}),
            "/big": Route(200, b"a" * 3000),
            "/bomb": Route(200, self.bomb, {"Content-Encoding": "gzip"}),
            "/slow": Route(200, b"late", delay=1.5),
        }
        for i in range(10):
            routes[f"/loop{i}"] = Route(302, b"", {"Location": f"/loop{i + 1}"})
        self.server = LocalServer(routes)
        self.server.__enter__()
        self.server.routes["/other-loopback"] = Route(302, b"", {"Location": f"http://127.0.0.2:{self.server.port}/ok"})
        self.f = hs.Fetcher(delay=0, allow_local=True, timeout=5)

    def tearDown(self):
        self.server.__exit__(None, None, None)

    def url(self, path):
        return self.server.base + path

    def test_fetch_ok(self):
        r = self.f.fetch(self.url("/ok"))
        self.assertEqual(r.status, 200)
        self.assertEqual(r.body, b"<html>ok</html>")
        self.assertEqual(len(r.sha256), 64)
        self.assertEqual(r.headers["set-cookie"], "[redacted]")
        self.assertEqual(self.server.requests[-1]["headers"]["user-agent"], hs.USER_AGENT)
        self.assertEqual(r.text(), "<html>ok</html>")

    def test_loopback_refused_without_allow_local(self):
        with self.assertRaises(hs.SafeHttpError) as ctx:
            hs.Fetcher(delay=0).fetch(self.url("/ok"))
        self.assertEqual(ctx.exception.code, "blocked_address")
        self.assertEqual(self.server.requests, [])

    def test_same_origin_redirects(self):
        r = self.f.fetch(self.url("/r1"))
        self.assertEqual(r.status, 200)
        self.assertEqual([s["status"] for s in r.chain], [301, 302, 200])
        self.assertTrue(r.final_url.endswith("/ok"))

    def test_redirect_to_metadata_blocked(self):
        with self.assertRaises(hs.SafeHttpError) as ctx:
            self.f.fetch(self.url("/meta"))
        self.assertEqual(ctx.exception.code, "blocked_address")
        self.assertEqual(len(ctx.exception.chain), 1)

    def test_redirect_to_obfuscated_or_other_local_blocked(self):
        for path in ("/hex", "/other-loopback"):
            with self.assertRaises(hs.SafeHttpError, msg=path):
                self.f.fetch(self.url(path))

    def test_redirect_to_userinfo_or_file_blocked(self):
        with self.assertRaises(hs.SafeHttpError) as ctx:
            self.f.fetch(self.url("/userinfo"))
        self.assertEqual(ctx.exception.code, "userinfo_not_allowed")
        with self.assertRaises(hs.SafeHttpError) as ctx:
            self.f.fetch(self.url("/file"))
        self.assertEqual(ctx.exception.code, "scheme_not_allowed")

    def test_redirect_limit(self):
        with self.assertRaises(hs.SafeHttpError) as ctx:
            self.f.fetch(self.url("/loop0"))
        self.assertEqual(ctx.exception.code, "too_many_redirects")
        self.assertEqual(len(self.server.requests), 6)

    def test_body_limit(self):
        r = self.f.fetch(self.url("/big"), max_bytes=1000)
        self.assertTrue(r.truncated)
        self.assertEqual(len(r.body), 1000)

    def test_gzip_bomb_capped(self):
        r = hs.Fetcher(delay=0, allow_local=True, max_bytes=1024 * 1024).fetch(self.url("/bomb"))
        self.assertTrue(r.truncated)
        self.assertLessEqual(len(r.body), 1024 * 1024)

    def test_head(self):
        r = self.f.fetch(self.url("/ok"), method="HEAD")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.body, b"")
        self.assertEqual(self.server.requests[-1]["method"], "HEAD")

    def test_post_refused(self):
        with self.assertRaises(hs.SafeHttpError):
            self.f.fetch(self.url("/ok"), method="POST")

    def test_header_injection_refused(self):
        with self.assertRaises(hs.SafeHttpError):
            self.f.fetch(self.url("/ok"), headers={"Cookie": "a=b"})
        with self.assertRaises(hs.SafeHttpError):
            self.f.fetch(self.url("/ok"), headers={"Accept": "x\r\nX-Evil: 1"})

    def test_timeout(self):
        with self.assertRaises(hs.SafeHttpError) as ctx:
            hs.Fetcher(delay=0, allow_local=True, timeout=0.3).fetch(self.url("/slow"))
        self.assertIn(ctx.exception.code, ("timeout", "connection_failed"))

    def test_pacing_between_requests(self):
        sleeps, now = [], [100.0]

        def sleep(s):
            sleeps.append(s)
            now[0] += s
        f = hs.Fetcher(delay=2.0, allow_local=True, sleep=sleep, clock=lambda: now[0], shared_pace=False)
        f.fetch(self.url("/ok"))
        now[0] += 0.5
        f.fetch(self.url("/ok"))
        now[0] += 5.0
        f.fetch(self.url("/ok"))
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 1.5)


    def test_shared_pause_across_processes(self):
        """Two Fetchers stand in for two processes: the second waits because of the first one's file."""
        with tempfile.TemporaryDirectory() as d:
            sleeps = []
            wall = [1000.0]
            mk = lambda: hs.Fetcher(delay=2.0, allow_local=True, state_dir=d, sleep=sleeps.append,
                                    wall=lambda: wall[0])
            mk().fetch(self.url("/ok"))
            self.assertEqual(sleeps, [])
            wall[0] += 0.5
            mk().fetch(self.url("/ok"))
            self.assertEqual(len(sleeps), 1)
            self.assertAlmostEqual(sleeps[0], 1.5)
            wall[0] += 10
            mk().fetch(self.url("/ok"))
            self.assertEqual(len(sleeps), 1)
            files = os.listdir(d)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].startswith("papa-seo-pace-"))

    def test_shared_pause_future_timestamp_is_capped(self):
        with tempfile.TemporaryDirectory() as d:
            f = hs.Fetcher(delay=2.0, allow_local=True, state_dir=d, sleep=lambda s: sleeps.append(s))
            sleeps = []
            with open(f.pace_file("127.0.0.1"), "w") as fh:
                fh.write("99999999999")
            f.fetch(self.url("/ok"))
            self.assertEqual(sleeps, [2.0])

    def test_shared_pause_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            f = hs.Fetcher(delay=2.0, allow_local=True, state_dir=d, sleep=lambda s: None)
            target = os.path.join(d, "elsewhere")
            os.symlink(target, f.pace_file("127.0.0.1"))
            f.fetch(self.url("/ok"))
            self.assertFalse(os.path.exists(target))
            self.assertTrue(f.pace_notes)

    def test_pace_file_per_host(self):
        f = hs.Fetcher(state_dir="/x")
        self.assertNotEqual(f.pace_file("a.example"), f.pace_file("b.example"))
        self.assertTrue(f.pace_file("a.example").startswith("/x"))

    def test_safe_headers(self):
        self.server.routes["/hdr"] = Route(200, "x", {"Strict-Transport-Security": "max-age=1", "CF-Cache-Status": "HIT",
                                                      "X-Secret-Internal": "no", "Content-Security-Policy": "default-src 'self'"})
        r = self.f.fetch(self.url("/hdr"))
        sh = r.safe_headers()
        self.assertIn("strict-transport-security", sh)
        self.assertIn("cf-cache-status", sh)
        self.assertIn("content-security-policy", sh)
        self.assertNotIn("x-secret-internal", sh)


class HelpersTest(unittest.TestCase):
    def test_safe_out_path_traversal(self):
        for bad in ("../../x", "a/../../x", "..\\..\\x", ""):
            with self.assertRaises(hs.CliError):
                hs.safe_out_path(bad)

    def test_safe_out_path_symlink_and_dir(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "real.json")
            open(target, "w").close()
            link = os.path.join(d, "link.json")
            os.symlink(target, link)
            with self.assertRaises(hs.CliError):
                hs.safe_out_path(link)
            with self.assertRaises(hs.CliError):
                hs.safe_out_path(d)
            self.assertTrue(hs.safe_out_path(os.path.join(d, "new.json")).endswith("new.json"))

    def test_safe_filename(self):
        for bad in ("../../x", "..", "/etc/passwd", "a/../../b", "..\\..\\x", ".hidden"):
            name = hs.safe_filename(bad)
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertNotIn("..", name)
            self.assertFalse(name.startswith("."))
            self.assertEqual(os.path.basename(name), name)

    def test_csv_safe(self):
        self.assertEqual(hs.csv_safe('=HYPERLINK("http://e","x")'), '\'=HYPERLINK("http://e","x")')
        for v in ("+1", "-1+1", "@SUM(A1)", "\t=1", " =1", "＝1"):
            self.assertTrue(hs.csv_safe(v).startswith("'"), v)
        self.assertEqual(hs.csv_safe("обычный текст"), "обычный текст")
        self.assertEqual(hs.csv_safe(5), 5)

    def test_dump_json_escapes_invisible(self):
        out = hs.dump_json({"t": "a​b‮c" + chr(0xE0041)})
        self.assertNotIn("​", out)
        self.assertNotIn("‮", out)
        self.assertNotIn(chr(0xE0041), out)
        self.assertIn("\\u200b", out)
        self.assertEqual(json.loads(out)["t"], "a​b‮c" + chr(0xE0041))

    def test_read_input_file_refuses_non_regular(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(hs.CliError):
                hs.read_input_file(d, 10)


class CliTest(unittest.TestCase):
    def fake_response(self, body=b"<html><body><nav>menu words</nav><main><p>Main text here</p></main></body></html>"):
        return hs.Response(url="https://example.com/p", final_url="https://example.com/p", method="GET", status=200,
                           reason="OK", headers={"content-type": "text/html; charset=utf-8"},
                           chain=[{"url": "https://example.com/p", "status": 200}], body=body, truncated=False,
                           ip="93.184.215.14", elapsed_ms=12, fetched_at="2026-10-24T00:00:00Z", notes=[])

    def run_fetch(self, argv):
        seen = {}

        def fake_fetch(fetcher, url, **kw):
            seen["ua"] = fetcher.user_agent
            seen["state_dir"] = fetcher.state_dir
            return self.fake_response()
        with mock.patch.object(hs.Fetcher, "fetch", fake_fetch):
            code, data = run_cli(hs.main, argv)
        return code, data, seen

    def test_cli_save_body_and_text(self):
        with tempfile.TemporaryDirectory() as d:
            body = os.path.join(d, "page.html")
            code, data, seen = self.run_fetch(["fetch", "https://example.com/p", "--save-body", body, "--text",
                                              "--state-dir", d])
            self.assertEqual(code, 0, data)
            with open(body, "rb") as fh:
                self.assertEqual(fh.read(), self.fake_response().body)
            self.assertEqual(seen["state_dir"], os.path.abspath(d))
        self.assertEqual(data["text"]["scope"], "main")
        self.assertEqual(data["text"]["text"], "Main text here")
        self.assertEqual(seen["ua"], hs.USER_AGENT)

    def test_cli_save_body_traversal(self):
        code, data, _ = self.run_fetch(["fetch", "https://example.com/p", "--save-body", "../../x"])
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "bad_out_path")

    def test_cli_state_dir_checks(self):
        for bad in ("../tmp", "/definitely/not/here"):
            code, data, _ = self.run_fetch(["fetch", "https://example.com/p", "--state-dir", bad])
            self.assertNotEqual(code, 0)

    def test_cli_ua_of(self):
        code, data, seen = self.run_fetch(["fetch", "https://example.com/p", "--ua-of", "GPTBot"])
        self.assertEqual(code, 0, data)
        self.assertIn("GPTBot/", seen["ua"])
        self.assertEqual(data["as_bot"], "GPTBot")
        self.assertTrue(any("User-Agent бота" in n for n in data["notes"]))
        self.assertIn("документация вендора", data["ua_source"])
        code, data, seen = self.run_fetch(["fetch", "https://example.com/p", "--ua-of", "ClaudeBot"])
        self.assertEqual(code, 0, data)
        self.assertIn("ClaudeBot/", seen["ua"])
        self.assertIn("не публикует", data["ua_source"])
        code, data, _ = self.run_fetch(["fetch", "https://example.com/p", "--ua-of", "Googlebot-Image"])
        self.assertEqual(data["code"], "unknown_bot_ua", "Googlebot's UA must not be sent for Googlebot-Image")
        code, data, _ = self.run_fetch(["fetch", "https://example.com/p", "--ua-of", "Google-Extended"])
        self.assertEqual(data["code"], "unknown_bot_ua")
        code, data, _ = self.run_fetch(["fetch", "https://example.com/p", "--ua-of", "NoSuchBot"])
        self.assertEqual(data["code"], "unknown_bot_ua")

    def test_cli_blocks_loopback(self):
        code, data = run_cli(hs.main, ["fetch", "http://127.0.0.1:1/"])
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "blocked_address")

    def test_cli_userinfo(self):
        code, data = run_cli(hs.main, ["fetch", "http://user@example.com/"])
        self.assertNotEqual(code, 0)
        self.assertIn("error", data)

    def test_cli_bad_args_json(self):
        code, data = run_cli(hs.main, [])
        self.assertNotEqual(code, 0)
        self.assertIn("error", data)

    def test_cli_out_traversal(self):
        code, data = run_cli(hs.main, ["fetch", "https://example.com/", "--out", "../../x"])
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "bad_out_path")


if __name__ == "__main__":
    unittest.main()
