"""link_graph: orphans, depth, PageRank, regions, HTML-folder mode, CSV formula injection, symlinks."""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import unittest

import _localserver as ls

import link_graph as lg

FIX = ls.FIXTURES


def run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = lg.main(argv)
    return code, json.loads(buf.getvalue())


class CsvGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code, cls.r = run_cli([os.path.join(FIX, "edges_basic.csv")])
        assert code == 0, cls.r

    def test_counts(self):
        r = self.r
        self.assertEqual(r["site"], "example.com")
        self.assertEqual(r["nodes"], 6)
        self.assertEqual(r["edges"], 6)
        self.assertEqual(r["stats"]["external_links"], 1)
        self.assertEqual(r["stats"]["self_links"], 1)
        self.assertEqual(r["stats"]["duplicate_edges"], 1)
        self.assertEqual(r["stats"]["bad_rows"], 1)
        self.assertEqual(r["stats"]["empty_anchor"], 1)

    def test_orphans_depth(self):
        self.assertEqual(self.r["start"], "https://example.com/")
        self.assertEqual(self.r["orphans"]["examples"], ["https://example.com/orphan"])
        self.assertEqual(self.r["unreachable_from_start"]["examples"], ["https://example.com/orphan"])
        self.assertEqual(self.r["depth_histogram"], {"0": 1, "1": 2, "2": 1, "3": 1})

    def test_nav_only(self):
        nav_only = set(self.r["only_nav_footer_inlinks"]["examples"])
        self.assertEqual(nav_only, {"https://example.com/", "https://example.com/a", "https://example.com/b",
                                    "https://example.com/d"})

    def test_pagerank(self):
        top = self.r["top_pagerank"]
        total = sum(n["pagerank"] for n in top)
        self.assertAlmostEqual(total, 1.0, places=4)
        ranks = {n["url"]: n["pagerank"] for n in top}
        self.assertGreater(ranks["https://example.com/c"], ranks["https://example.com/a"])
        self.assertEqual(ranks["https://example.com/a"], ranks["https://example.com/b"])

    def test_pages_list_finds_true_orphans(self):
        with tempfile.TemporaryDirectory() as d:
            pages = os.path.join(d, "pages.txt")
            with open(pages, "w") as fh:
                fh.write("https://example.com/lonely\nhttps://other.org/x\nnot a url\n")
            code, r = run_cli([os.path.join(FIX, "edges_basic.csv"), "--pages", pages])
        self.assertEqual(code, 0)
        self.assertIn("https://example.com/lonely", r["orphans"]["examples"])
        self.assertIn("переданного списка", r["orphans"]["coverage"])
        self.assertEqual(r["nodes"], 7)

    def test_nofollow_excluded_from_pagerank(self):
        g = lg.Graph("https://e.com/")
        g.add_edge("https://e.com/", "https://e.com/a", "a", "main")
        g.add_edge("https://e.com/", "https://e.com/b", "b", "main", "nofollow")
        m = g.compute(None)
        pr = dict(zip(g.urls, m["pr"]))
        self.assertGreater(pr["https://e.com/a"], pr["https://e.com/b"])
        self.assertEqual(m["indeg"][g.ids["https://e.com/b"]], 1)


class FormulaInjectionTest(unittest.TestCase):
    def test_csv_export_escapes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "nodes.csv")
            code, r = run_cli([os.path.join(FIX, "edges_formula.csv"), "--csv-out", out])
            self.assertEqual(code, 0)
            self.assertGreaterEqual(r["formula_like_values"], 3)
            with open(out, newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
        for row in rows[1:]:
            for cell in row:
                self.assertFalse(cell.lstrip().startswith(("=", "+", "-", "@")), cell)
        anchors = {row[0]: row[-1] for row in rows[1:]}
        self.assertTrue(anchors["https://example.com/a"].startswith("'=HYPERLINK("))
        self.assertTrue(anchors["https://example.com/b"].startswith("'"))

    def test_formula_target_is_not_a_node(self):
        code, r = run_cli([os.path.join(FIX, "edges_formula.csv")])
        self.assertEqual(code, 0)
        self.assertEqual(r["stats"]["bad_rows"], 1)

    def test_out_traversal_refused(self):
        code, r = run_cli([os.path.join(FIX, "edges_basic.csv"), "--csv-out", "../../x"])
        self.assertNotEqual(code, 0)
        self.assertEqual(r["code"], "bad_out_path")
        code, r = run_cli([os.path.join(FIX, "edges_basic.csv"), "--out", "../../x"])
        self.assertEqual(r["code"], "bad_out_path")


class HtmlDirTest(unittest.TestCase):
    def test_html_site(self):
        code, r = run_cli(["--html-dir", os.path.join(FIX, "html_site"), "--base-url", "https://example.com/"])
        self.assertEqual(code, 0, r)
        self.assertEqual(r["nodes"], 4)
        self.assertEqual(r["stats"]["files"], 4)
        self.assertEqual(r["stats"]["external_links"], 1)
        self.assertEqual(r["orphans"]["count"], 0)
        about = [n for n in r["top_pagerank"] if n["url"] == "https://example.com/about.html"][0]
        self.assertEqual(about["inlinks"], 2)
        self.assertEqual(about["contextual_inlinks"], 0)

    def test_symlink_escape_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            site = os.path.join(d, "site")
            shutil.copytree(os.path.join(FIX, "html_site"), site)
            outside = os.path.join(d, "secret.html")
            with open(outside, "w") as fh:
                fh.write('<a href="/stolen">x</a>')
            os.symlink(outside, os.path.join(site, "link.html"))
            os.symlink(d, os.path.join(site, "updir"))
            code, r = run_cli(["--html-dir", site, "--base-url", "https://example.com/"])
        self.assertEqual(code, 0)
        self.assertEqual(r["stats"]["skipped_symlinks"], 1)
        self.assertEqual(r["nodes"], 4)

    def test_requires_base_url(self):
        code, r = run_cli(["--html-dir", os.path.join(FIX, "html_site")])
        self.assertNotEqual(code, 0)
        self.assertIn("error", r)

    def test_needs_one_input(self):
        code, r = run_cli([])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
