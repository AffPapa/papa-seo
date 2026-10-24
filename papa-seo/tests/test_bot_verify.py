"""bot_verify: rDNS + forward confirmation with a fake resolver (no real DNS in tests)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import tempfile
import unittest
from unittest import mock

import _localserver  # noqa: F401  (sets sys.path)

import bot_verify as bv
import http_safe

PTR = {
    "66.249.66.1": "crawl-66-249-66-1.googlebot.com",
    "5.255.253.1": "spider-5-255-253-1.spider.yandex.com",
    "40.77.167.1": "msnbot-40-77-167-1.search.msn.com",
    "45.33.32.9": "crawl.googlebot.com.evil.net",   # suffix trick
    "104.16.0.7": "evilgooglebot.com",              # no label boundary
    "93.184.215.14": "crawl-1.googlebot.com",         # forged PTR, forward does not match
}
FWD = {
    "crawl-66-249-66-1.googlebot.com": ["66.249.66.1"],
    "spider-5-255-253-1.spider.yandex.com": ["5.255.253.1"],
    "msnbot-40-77-167-1.search.msn.com": ["40.77.167.1"],
    "crawl-1.googlebot.com": ["66.249.66.200"],
}


def fake_reverse(ip):
    return PTR.get(ip)


def fake_forward(name):
    return FWD.get(name, [])


class VerifyTest(unittest.TestCase):
    def v(self, ip, claimed=("google",)):
        return bv.verify_ip(ip, list(claimed), reverse=fake_reverse, forward=fake_forward)

    def test_verified(self):
        self.assertEqual(self.v("66.249.66.1")["verdict"], "verified")
        self.assertEqual(self.v("5.255.253.1", ["yandex"])["ptr_vendor"], "yandex")
        self.assertEqual(self.v("40.77.167.1", ["bing"])["verdict"], "verified")

    def test_suffix_tricks_fail(self):
        self.assertEqual(self.v("45.33.32.9")["verdict"], "fake")
        self.assertEqual(self.v("104.16.0.7")["verdict"], "fake")
        self.assertFalse(bv.domain_matches("evilgooglebot.com", "googlebot.com"))
        self.assertFalse(bv.domain_matches("googlebot.com.evil.net", "googlebot.com"))
        self.assertTrue(bv.domain_matches("a.googlebot.com.", "googlebot.com"))

    def test_forged_ptr_without_forward(self):
        row = self.v("93.184.215.14")
        self.assertEqual(row["verdict"], "fake")
        self.assertFalse(row["forward_confirmed"])

    def test_no_ptr(self):
        self.assertEqual(self.v("192.0.2.200", [])["verdict"], "private_ip")
        self.assertEqual(self.v("8.8.4.4")["verdict"], "unverified_no_ptr")
        self.assertEqual(self.v("8.8.4.4", [])["verdict"], "no_ptr")

    def test_private_not_looked_up(self):
        calls = []
        row = bv.verify_ip("10.1.2.3", ["google"], reverse=lambda ip: calls.append(ip), forward=fake_forward)
        self.assertEqual(row["verdict"], "private_ip")
        self.assertEqual(calls, [])

    def test_ip_range_bot(self):
        row = bv.verify_ip("20.1.2.3", [], reverse=fake_reverse, forward=fake_forward, ua_ip_range_bot=True)
        self.assertEqual(row["verdict"], "needs_ip_ranges")


class LogParseTest(unittest.TestCase):
    def test_caddy_json(self):
        line = json.dumps({"request": {"remote_ip": "66.249.66.1", "client_ip": "66.249.66.1",
                                       "headers": {"User-Agent": ["Mozilla/5.0 (compatible; Googlebot/2.1)"]}}})
        ip, ua = bv.parse_log_line(line)
        self.assertEqual(ip, "66.249.66.1")
        self.assertEqual(bv.claimed_vendors(ua), ["google"])

    def test_combined(self):
        line = ('5.255.253.1 - - [24/Oct/2026:10:00:00 +0000] "GET / HTTP/1.1" 200 512 "-" '
                '"Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"')
        ip, ua = bv.parse_log_line(line)
        self.assertEqual(ip, "5.255.253.1")
        self.assertEqual(bv.claimed_vendors(ua), ["yandex"])

    def test_garbage(self):
        self.assertEqual(bv.parse_log_line("{not json"), (None, None))
        self.assertEqual(bv.parse_log_line(""), (None, None))
        self.assertEqual(bv.parse_log_line("2001:db8::1 - - x")[0], "2001:db8::1")


class CliTest(unittest.TestCase):
    def run_cli(self, argv):
        def fake_gai(host, port, *a, **k):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in FWD.get(host, [])] or \
                (_ for _ in ()).throw(socket.gaierror("nx"))

        def fake_gba(ip):
            if ip not in PTR:
                raise socket.herror("no ptr")
            return PTR[ip], [], [ip]
        buf = io.StringIO()
        with mock.patch.object(http_safe, "_gethostbyaddr", fake_gba), \
                mock.patch.object(http_safe, "_getaddrinfo", fake_gai), contextlib.redirect_stdout(buf):
            code = bv.main(argv)
        return code, json.loads(buf.getvalue())

    def test_log_file(self):
        lines = [
            json.dumps({"request": {"remote_ip": "66.249.66.1", "headers": {"User-Agent": ["Googlebot/2.1"]}}}),
            '45.33.32.9 - - [x] "GET / HTTP/1.1" 200 1 "-" "Mozilla/5.0 (compatible; Googlebot/2.1)"',
            '10.0.0.5 - - [x] "GET / HTTP/1.1" 200 1 "-" "Googlebot"',
            '20.1.2.3 - - [x] "GET / HTTP/1.1" 200 1 "-" "Mozilla/5.0; GPTBot/1.1"',
            "garbage line",
        ]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "access.log")
            with open(p, "w") as fh:
                fh.write("\n".join(lines) + "\n")
            code, r = self.run_cli(["--log", p])
        self.assertEqual(code, 0, r)
        by = {row["ip"]: row["verdict"] for row in r["results"]}
        self.assertEqual(by["66.249.66.1"], "verified")
        self.assertEqual(by["45.33.32.9"], "fake")
        self.assertEqual(by["10.0.0.5"], "private_ip")
        self.assertEqual(by["20.1.2.3"], "needs_ip_ranges")

    def test_args_and_errors(self):
        code, r = self.run_cli(["66.249.66.1", "not-an-ip"])
        self.assertEqual(code, 0)
        self.assertEqual(r["bad_inputs"], 1)
        code, r = self.run_cli([])
        self.assertNotEqual(code, 0)
        self.assertIn("error", r)
        code, r = self.run_cli(["66.249.66.1", "--out", "../../x"])
        self.assertEqual(r["code"], "bad_out_path")


if __name__ == "__main__":
    unittest.main()
