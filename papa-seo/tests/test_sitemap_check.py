"""sitemap_check: structure, limits, lastmod plausibility, XXE / entity bombs, gzip, index following."""
from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
import unittest
from datetime import datetime, timezone

import _localserver as ls
from _localserver import LocalServer, Route

import http_safe
import sitemap_check as sc

FIX = ls.FIXTURES
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def read(name):
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


def codes(report):
    return {i["code"]: i for i in report["issues"]}


def run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = sc.main(argv)
    return code, json.loads(buf.getvalue())


def urlset(locs, lastmod=None):
    body = "".join(f"<url><loc>{u}</loc>{f'<lastmod>{lastmod}</lastmod>' if lastmod else ''}</url>" for u in locs)
    return (f'<?xml version="1.0"?><urlset xmlns="{sc.SITEMAP_NS}">{body}</urlset>').encode()


class BasicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = sc.analyze(sc.parse_sitemap(read("sitemap_basic.xml")), site="https://example.com/", now=NOW)

    def test_type_and_count(self):
        self.assertEqual(self.r["type"], "urlset")
        self.assertEqual(self.r["entries"], 9)
        self.assertEqual(self.r["extensions"].get("hreflang_links"), 1)

    def test_issues(self):
        c = codes(self.r)
        self.assertEqual(c["http_url"]["count"], 1)
        self.assertEqual(c["foreign_host"]["examples"], ["https://evil.example.net/c"])
        self.assertEqual(c["www_variant"]["count"], 1)
        self.assertEqual(c["duplicate"]["count"], 1)
        self.assertEqual(c["near_duplicate"]["count"], 1)
        self.assertEqual(c["not_absolute"]["count"], 1)
        self.assertEqual(c["fragment"]["count"], 1)
        self.assertEqual(c["lastmod_future"]["count"], 1)
        self.assertEqual(c["lastmod_invalid_date"]["count"], 1)
        self.assertEqual(c["lastmod_time_without_timezone"]["count"], 1)
        self.assertEqual(c["priority_out_of_range"]["count"], 1)
        self.assertIn("note", self.r["info"])

    def test_gzip_same_result(self):
        rg = sc.analyze(sc.parse_sitemap(read("sitemap_basic.xml.gz")), site="https://example.com/", now=NOW)
        self.assertTrue(rg["gzip"])
        self.assertEqual(rg["entries"], self.r["entries"])
        self.assertEqual(set(codes(rg)), set(codes(self.r)))

    def test_w3c_parser(self):
        self.assertIsNone(sc.parse_w3c("2026-10-01")[1])
        self.assertIsNone(sc.parse_w3c("2026-10-01T10:00:00+03:00")[1])
        self.assertIsNone(sc.parse_w3c("2026")[1])
        self.assertEqual(sc.parse_w3c("01.10.2026")[1], "invalid_format")
        self.assertEqual(sc.parse_w3c("2026-10-01T10:00")[1], "time_without_timezone")
        dt, _ = sc.parse_w3c("2026-10-01T03:00:00+03:00")
        self.assertEqual(dt.hour, 0)


class PlausibilityTest(unittest.TestCase):
    def test_uniform_lastmod(self):
        data = urlset([f"https://e.com/p{i}" for i in range(20)], lastmod="2026-01-01")
        r = sc.analyze(sc.parse_sitemap(data), now=NOW)
        self.assertIn("lastmod_uniform", codes(r))
        self.assertEqual(r["reference_host_source"], "inferred_majority")

    def test_all_recent(self):
        data = urlset([f"https://e.com/p{i}" for i in range(12)], lastmod="2026-10-24T11:00:00Z")
        self.assertIn("lastmod_all_recent", codes(sc.analyze(sc.parse_sitemap(data), now=NOW)))

    def test_over_limit(self):
        data = urlset([f"https://e.com/{i}" for i in range(sc.MAX_URLS + 1)])
        r = sc.analyze(sc.parse_sitemap(data), now=NOW)
        self.assertIn("over_50000", codes(r))
        self.assertEqual(r["entries"], sc.MAX_URLS + 1)

    def test_index(self):
        r = sc.analyze(sc.parse_sitemap(read("sitemap_index.xml")), now=NOW)
        self.assertEqual(r["type"], "sitemapindex")
        self.assertEqual([c["loc"] for c in r["children"]],
                         ["https://example.com/s1.xml", "https://example.com/s2.xml.gz"])

    def test_wrong_root_and_namespace(self):
        r = sc.analyze(sc.parse_sitemap(b"<rss><channel/></rss>"), now=NOW)
        self.assertIn("unknown_root", codes(r))
        self.assertIn("namespace", codes(r))


class AttackTest(unittest.TestCase):
    def test_xxe_refused(self):
        with self.assertRaises(sc.SitemapError) as ctx:
            sc.parse_sitemap(read("sitemap_xxe.xml"))
        self.assertEqual(ctx.exception.code, "dtd_refused")

    def test_billion_laughs_refused(self):
        with self.assertRaises(sc.SitemapError):
            sc.parse_sitemap(read("sitemap_bomb.xml"))

    def test_gzip_bomb_capped(self):
        bomb = gzip.compress(b" " * (5 * 1024 * 1024))
        with self.assertRaises(sc.SitemapError) as ctx:
            sc.parse_sitemap(bomb, max_bytes=1024 * 1024)
        self.assertEqual(ctx.exception.code, "too_large")

    def test_invalid_xml(self):
        with self.assertRaises(sc.SitemapError):
            sc.parse_sitemap(b"<urlset><url><loc>x</url>")

    def test_cli_errors_are_json(self):
        code, data = run_cli([os.path.join(FIX, "sitemap_xxe.xml")])
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "dtd_refused")
        code, data = run_cli([os.path.join(FIX, "missing.xml")])
        self.assertNotEqual(code, 0)
        code, data = run_cli([os.path.join(FIX, "sitemap_basic.xml"), "--sample", "3"])
        self.assertNotEqual(code, 0)
        code, data = run_cli([os.path.join(FIX, "sitemap_basic.xml"), "--out", "../../x"])
        self.assertEqual(data["code"], "bad_out_path")
        code, data = run_cli(["https://example.com/sitemap.xml", "--delay", "0.5"])
        self.assertEqual(data["code"], "bad_arguments")

    def test_cli_file_ok(self):
        code, data = run_cli([os.path.join(FIX, "sitemap_basic.xml"), "--site", "https://example.com/"])
        self.assertEqual(code, 0)
        self.assertEqual(data["type"], "urlset")


class LiveTest(unittest.TestCase):
    def test_follow_index_and_sample_local(self):
        with LocalServer({}) as srv:
            b = srv.base
            srv.routes.update({
                "/index.xml": Route(200, f'<?xml version="1.0"?><sitemapindex xmlns="{sc.SITEMAP_NS}">'
                                         f'<sitemap><loc>{b}/s1.xml</loc></sitemap>'
                                         f'<sitemap><loc>{b}/s2.xml.gz</loc></sitemap>'
                                         f'<sitemap><loc>https://other.example/s3.xml</loc></sitemap>'
                                         f'</sitemapindex>'),
                "/s1.xml": Route(200, urlset([f"{b}/a", f"{b}/b"]).decode()),
                "/s2.xml.gz": Route(200, gzip.compress(urlset([f"{b}/c"]))),
                "/a": Route(200, "<html><head><meta name='robots' content='noindex'></head></html>"),
                "/b": Route(301, b"", {"Location": "/a"}),
            })
            f = http_safe.Fetcher(delay=0, allow_local=True)
            parsed, meta = sc.fetch_sitemap(b + "/index.xml", f, allow_local=True)
            report = sc.analyze(parsed, sitemap_url=meta["final_url"])
            kids = sc.follow_index(report, meta["final_url"], f, allow_local=True, limit=5)
            self.assertEqual(kids[0]["entries"], 2)
            self.assertEqual(kids[1]["entries"], 1)
            self.assertEqual(kids[2]["skipped"], "other_host")
            p1, m1 = sc.fetch_sitemap(b + "/s1.xml", f, allow_local=True)
            sample = sc.sample_urls(p1["entries"], 5, f, ref=m1["final_url"], allow_local=True)
            self.assertEqual(len(sample), 2)
            self.assertTrue(sample[0]["noindex_meta"])
            self.assertTrue(sample[1]["redirected"])
            paths = [r["path"] for r in srv.requests]
            self.assertNotIn("/s3.xml", paths)
            before = len(srv.requests)
            report["children_checked"] = sc.follow_index(report, meta["final_url"], f, allow_local=True, limit=1)
            self.assertEqual(len(srv.requests) - before, 1)
            skip = sc.children_skip_report(report, 1)
            self.assertEqual(skip["children_not_checked"], 2)
            self.assertIn("пропущено 2", skip["children_warning"])

    def test_default_max_children(self):
        self.assertEqual(sc.DEFAULT_MAX_CHILDREN, 2)
        code, data = run_cli(["https://example.com/sitemap.xml", "--follow-index", "--max-children", "50"])
        self.assertEqual(data["code"], "bad_arguments")


if __name__ == "__main__":
    unittest.main()
