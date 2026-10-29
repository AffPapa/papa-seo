"""Тесты scripts/audit.py — единая проверка и отчёт. Запуск из папки скила:
python3 -m unittest tests.test_audit
"""
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIXTURES = os.path.join(HERE, "fixtures")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from _localserver import LocalServer, Route  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


au = load("audit")
http_safe = load("http_safe")

BASIC = os.path.join(FIXTURES, "basic_page.html")
HOSTILE = os.path.join(FIXTURES, "audit_hostile.html")


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = au.main(argv)
    return rc, buf.getvalue()


def audit_file(path, **kw):
    kw.setdefault("keys", [])
    kw.setdefault("options", {"base_url": "https://example.com/catalog/", "robots": False})
    return au.audit_page(path, fetcher=None, **kw)


def rows_by_id(page):
    return {r["id"]: r for r in page["rows"]}


class TestRegistry(unittest.TestCase):
    def test_default_registry_loads(self):
        reg = au.load_registry()
        self.assertTrue(reg["params"], "реестр из references/ должен читаться")
        self.assertTrue(reg["source"].endswith("registry.json"))
        p = reg["params"][0]
        for field in ("id", "group", "title", "severity", "scope", "signal", "deterministic"):
            self.assertIn(field, p)
        self.assertIn(p["group"], au.GROUP_SLUGS)

    def test_groups_normalised(self):
        self.assertEqual(au.group_slug("intl"), "i18n")
        self.assertEqual(au.group_slug("social"), "markup")
        self.assertEqual(au.group_slug("index"), "access")
        self.assertEqual(au.group_slug("Доступность и индексация"), "access")
        self.assertEqual(au.group_slug(None), "other")

    def test_plain_list_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "registry.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([{"id": "x.one", "group": "meta", "title": "Один",
                            "severity": "high", "how": "как-то"}], fh)
            reg = au.load_registry(path)
        self.assertEqual(len(reg["params"]), 1)
        self.assertEqual(reg["params"][0]["severity"], "high")
        self.assertTrue(reg["params"][0]["deterministic"])

    def test_broken_registry_is_a_warning_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "registry.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{не json")
            reg = au.load_registry(path)
        self.assertEqual(reg["params"], [])
        self.assertTrue(any("JSON" in w for w in reg["warnings"]))

    def test_editor_guideline_flagged(self):
        reg = au.load_registry()
        editor = [p for p in reg["params"] if p["editor_guideline"]]
        self.assertTrue(editor, "в реестре есть параметры «ориентир редактора»")
        self.assertTrue(all(p["source_kind"] == "editor" or "ориентир" in str(p["source"])
                            for p in editor))


class TestImportedChecks(unittest.TestCase):
    """Проверки, которые считают другие скрипты, попадают в отчёт через один слой сопоставления."""

    def test_page_facts_checks_are_ingested(self):
        page = audit_file(BASIC)
        from_script = [r for r in page["rows"] if r.get("from_script") == "page_facts"]
        self.assertGreater(len(from_script), 30, "page_facts отдаёт свои проверки, их надо забрать")
        for row in from_script:
            self.assertIn(row["verdict"], au.VERDICT_RU)
            self.assertIn(row["group"], au.GROUP_SLUGS)

    def test_status_mapping(self):
        bundle = {"page": {"checks": [
            {"id": "a.one", "group": "social", "title": "A", "status": "fail", "severity": "high",
             "observation": "нет", "source": "ogp.me"},
            {"id": "a.two", "group": "speed", "title": "B", "status": "skip", "severity": "info",
             "observation": "нет данных", "source": "ориентир редактора"},
        ]}}
        rows = {r["id"]: r for r in au.imported_rows(bundle)}
        self.assertEqual(rows["a.one"]["verdict"], au.BAD)
        self.assertEqual(rows["a.one"]["severity"], "high")
        self.assertEqual(rows["a.one"]["group"], "markup")
        self.assertEqual(rows["a.one"]["kind"], au.DET)
        self.assertEqual(rows["a.two"]["verdict"], au.NODATA)
        self.assertEqual(rows["a.two"]["kind"], au.HEUR, "«ориентир редактора» — это оценка")

    def test_unknown_status_does_not_crash(self):
        rows = au.imported_rows({"page": {"checks": [{"id": "x", "status": "непонятно"}]}})
        self.assertEqual(rows[0]["verdict"], au.INFO)


class TestMerge(unittest.TestCase):
    REG = {"params": [
        {"id": "meta.title_present", "group": "meta", "title": "title есть", "what": "что",
         "how": "как", "source": "Google", "source_kind": "google", "severity": "high",
         "status": "есть", "scope": "page", "signal": "fact", "deterministic": True,
         "editor_guideline": False},
        {"id": "access.soft_404", "group": "access", "title": "soft 404", "what": "что", "how": "как",
         "source": "Google", "source_kind": "google", "severity": "high", "status": "частично",
         "scope": "page", "signal": "estimate", "deterministic": False, "editor_guideline": False},
        {"id": "meta.title_duplicate_site", "group": "meta", "title": "Дубли title", "what": "что",
         "how": "как", "source": "Google", "source_kind": "google", "severity": "medium",
         "status": "нет", "scope": "site", "signal": "fact", "deterministic": True,
         "editor_guideline": False},
        {"id": "markup.og_required", "group": "markup", "title": "OG: четыре обязательных",
         "what": "что", "how": "как", "source": "ogp.me", "source_kind": "ogp", "severity": "low",
         "status": "частично", "scope": "page", "signal": "fact", "deterministic": True,
         "editor_guideline": False},
    ], "groups": {}}

    def rows(self):
        return [
            {"id": "meta.title_present", "group": "meta", "group_title": "x", "title": "title",
             "verdict": au.OK, "verdict_label": "норма", "severity": "info", "kind": au.DET,
             "kind_label": "факт", "source": None, "observation": "есть"},
            {"id": "social.og_title", "group": "markup", "group_title": "x", "title": "og:title",
             "verdict": au.OK, "verdict_label": "норма", "severity": "info", "kind": au.DET,
             "kind_label": "факт", "source": "ogp.me", "observation": "есть"},
            {"id": "social.og_type", "group": "markup", "group_title": "x", "title": "og:type",
             "verdict": au.BAD, "verdict_label": "проблема", "severity": "low", "kind": au.DET,
             "kind_label": "факт", "source": "ogp.me", "observation": "нет og:type"},
        ]

    def test_scope_page_only(self):
        merged = au.merge_registry(self.rows(), self.REG, au.CHECKS, pages=1, scope="page")
        ids = {r["registry_id"] for r in merged if r.get("in_registry")}
        self.assertNotIn("meta.title_duplicate_site", ids, "параметр сайта не место в отчёте страницы")
        self.assertIn("meta.title_present", ids)

    def test_non_deterministic_is_named_so(self):
        merged = {r["registry_id"]: r for r in
                  au.merge_registry(self.rows(), self.REG, au.CHECKS, pages=1, scope="page")
                  if r.get("in_registry")}
        row = merged["access.soft_404"]
        self.assertEqual(row["verdict"], au.NOTCHECKED)
        self.assertEqual(row["verdict_label"], "не проверено автоматически")
        self.assertNotEqual(row["verdict"], au.OK, "непроверенное не выдаём за «в порядке»")

    def test_site_param_needs_a_crawl(self):
        merged = {r["registry_id"]: r for r in
                  au.merge_registry([], self.REG, au.SITE_CHECKS, pages=1, scope="site")
                  if r.get("in_registry")}
        self.assertEqual(merged["meta.title_duplicate_site"]["verdict_label"], "нужен обход сайта")

    def test_alias_tuple_takes_the_worst(self):
        merged = {r["registry_id"]: r for r in
                  au.merge_registry(self.rows(), self.REG, au.CHECKS, pages=1, scope="page")
                  if r.get("in_registry")}
        row = merged["markup.og_required"]
        self.assertEqual(row["verdict"], au.BAD, "из четырёх проверок OG в строку идёт худшая")
        self.assertEqual(row["severity"], "low")
        self.assertTrue(row.get("also"), "остальные проверки перечислены рядом")

    def test_off_registry_rows_survive(self):
        reg = {"params": [self.REG["params"][0]], "groups": {}}
        merged = au.merge_registry(self.rows(), reg, au.CHECKS, pages=1, scope="page")
        extra = [r for r in merged if r.get("off_registry")]
        self.assertEqual({r["id"] for r in extra}, {"social.og_title", "social.og_type"})


class TestPageAudit(unittest.TestCase):
    def test_runs_on_a_local_file_without_network(self):
        page = audit_file(BASIC)
        self.assertNotIn("error", page)
        self.assertGreater(len(page["rows"]), 100)
        for row in page["rows"]:
            self.assertIn(row["verdict"], au.VERDICT_RU)
            self.assertIn(row["severity"], au.SEVERITIES)

    def test_every_check_has_a_unique_id(self):
        ids = [c.id for c in au.CHECKS + au.SITE_CHECKS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_check_raises(self):
        page = audit_file(HOSTILE, options={"base_url": "https://example.net/remont/", "robots": False})
        broken = [r for r in page["rows"] if "не выполнилась" in (r.get("observation") or "")]
        self.assertEqual(broken, [], f"упавшие проверки: {[r['id'] for r in broken]}")

    def test_findings_on_the_hostile_fixture(self):
        page = audit_file(HOSTILE, options={"base_url": "https://example.net/remont/", "robots": False})
        rows = rows_by_id(page)
        self.assertEqual(rows["markup.jsonld_parses"]["verdict"], au.BAD)
        self.assertEqual(rows["security.hidden_instructions"]["verdict"], au.BAD)
        self.assertEqual(rows["ai.max_snippet"]["verdict"], au.BAD, "max-snippet:0 — находка")
        self.assertEqual(rows["links.javascript_links"]["verdict"], au.WARN)
        self.assertEqual(rows["links.generic_anchor"]["verdict"], au.WARN)

    def test_absent_data_is_no_data_not_ok(self):
        page = audit_file(BASIC)
        rows = rows_by_id(page)
        self.assertEqual(rows["access.robots_googlebot"]["verdict"], au.NODATA)
        self.assertEqual(rows["ai.llms_txt"]["verdict"], au.NODATA)
        self.assertEqual(rows["speed.compression"]["verdict"], au.NODATA)

    def test_keys_by_zone_use_text_metrics(self):
        page = au.audit_page(BASIC, fetcher=None, keys=["партнёрские программы"],
                             options={"base_url": "https://example.com/catalog/", "robots": False})
        rows = rows_by_id(page)
        self.assertEqual(rows["content.key_in_title"]["verdict"], au.OK)
        self.assertEqual(rows["content.key_in_h1"]["verdict"], au.OK)
        zones = page["facts"]["text"]["keys"][0]["zones"]
        self.assertTrue(zones["title"]["present"])

    def test_keys_absent_without_keys(self):
        page = audit_file(BASIC)
        rows = rows_by_id(page)
        self.assertEqual(rows["content.key_in_title"]["verdict"], au.NODATA)
        self.assertEqual(rows["content.key_missing"]["verdict"], au.NODATA)

    def test_blocking_conditions(self):
        page = audit_file(HOSTILE, options={"base_url": "https://example.net/remont/", "robots": False})
        merged = au.merge_registry(page["rows"], au.load_registry(), au.CHECKS, pages=1)
        self.assertIsInstance(au.blocking_of(merged), list)


class TestReport(unittest.TestCase):
    def report(self, path=BASIC, keys=(), base="https://example.com/catalog/"):
        page = au.audit_page(path, fetcher=None, keys=list(keys),
                             options={"base_url": base, "robots": False})
        return au.build_report([page], registry=au.load_registry(), keys=list(keys),
                               options={"delay": 2.0}, requests_made=0)

    def test_coverage_is_honest(self):
        rep = self.report()
        cov = rep["coverage"]
        self.assertGreater(cov["registry_params"], 100)
        self.assertGreater(cov["registry_checked"], 50)
        self.assertEqual(cov["registry_params"],
                         cov["registry_checked"] + cov["registry_not_checked"])
        self.assertTrue(cov["not_checked_reasons"])

    def test_no_invented_score(self):
        rep = self.report()
        self.assertNotIn("score", rep)
        self.assertIn("Сводного балла нет", rep["scoring"])
        html = au.render_html(rep)
        self.assertNotRegex(html, r"\b\d{1,3}\s*/\s*100\b")

    def test_fix_first_sorted_by_severity(self):
        rep = self.report(HOSTILE, base="https://example.net/remont/")
        order = [au.SEVERITY_RANK[i["severity"]] for i in rep["fix_first"]]
        self.assertEqual(order, sorted(order))
        self.assertTrue(all(i["verdict"] in (au.BAD, au.WARN) for i in rep["fix_first"]))

    def test_json_is_serialisable(self):
        rep = self.report(keys=["партнёрские программы"])
        text = http_safe.dump_json(rep)
        again = json.loads(text)
        self.assertEqual(again["tool"], "audit")


class TestHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        page = au.audit_page(HOSTILE, fetcher=None, keys=["ремонт квартир"],
                             options={"base_url": "https://example.net/remont/", "robots": False})
        cls.rep = au.build_report([page], registry=au.load_registry(), keys=["ремонт квартир"],
                                  options={"delay": 2.0}, requests_made=0)
        cls.html = au.render_html(cls.rep)

    def test_self_contained(self):
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("src=\"http", self.html)
        self.assertNotIn("@import", self.html)
        for bad in ("cdn.", "googleapis.com", "unpkg.com", "fonts."):
            self.assertNotIn(bad, self.html)
        self.assertEqual(self.html.count("<style>"), 1)

    def test_themes_and_print(self):
        self.assertIn("prefers-color-scheme:dark", self.html)
        self.assertIn("@media print", self.html)
        self.assertIn("@media (max-width:720px)", self.html)
        self.assertIn('<html lang="ru"', self.html)
        self.assertIn('name="viewport"', self.html)
        self.assertIn('name="robots" content="noindex"', self.html)

    def test_untrusted_text_is_escaped(self):
        self.assertNotIn("<script>alert(1)</script>", self.html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.html)
        self.assertNotIn("</td><td>вставка", self.html)

    def test_explains_itself(self):
        for phrase in ("Чинить первым", "Как читать этот отчёт", "ориентир редактора",
                       "оценка", "не проверен"):
            self.assertIn(phrase, self.html)

    def test_not_checked_rows_are_visible(self):
        self.assertIn("Не проверяли:", self.html)
        self.assertIn("не проверено автоматически", self.html)


class TestCli(unittest.TestCase):
    def test_list_checks(self):
        rc, out = run_cli(["--list-checks"])
        data = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["count"], len(au.CHECKS) + len(au.SITE_CHECKS))
        self.assertTrue(all(c["id"] and c["title"] for c in data["checks"]))

    def test_file_run_writes_both_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "report.html")
            json_path = os.path.join(tmp, "report.json")
            rc, out = run_cli([BASIC, "--base-url", "https://example.com/catalog/",
                               "--keys", "партнёрские программы", "--out", html_path,
                               "--json", json_path])
            self.assertEqual(rc, 0)
            self.assertIn("проблем", out)
            self.assertIn("реестр", out)
            with open(html_path, encoding="utf-8") as fh:
                self.assertIn("<!doctype html>", fh.read())
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["inputs"]["keys"], ["партнёрские программы"])
            self.assertEqual(data["requests"]["count"], 0, "локальный файл — без запросов")

    def test_json_to_stdout(self):
        rc, out = run_cli([BASIC, "--base-url", "https://example.com/", "--json", "-"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["tool"], "audit")

    def test_out_json_extension_refused(self):
        rc, out = run_cli([BASIC, "--out", "report.json"])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out)["code"], "bad_arguments")

    def test_source_and_pages_are_exclusive(self):
        rc, out = run_cli([BASIC, "--pages", "list.txt"])
        self.assertEqual(json.loads(out)["code"], "bad_arguments")

    def test_pages_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "list.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(f"https://example.com/{i}" for i in range(au.MAX_PAGES + 1)))
            rc, out = run_cli(["--pages", path])
        self.assertEqual(json.loads(out)["code"], "too_many_urls")

    def test_bad_file(self):
        rc, out = run_cli([os.path.join(FIXTURES, "нет-такого.html")])
        self.assertEqual(json.loads(out)["code"], "bad_input")


class TestManyPages(unittest.TestCase):
    def test_site_checks_find_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(BASIC, encoding="utf-8") as fh:
                html = fh.read()
            paths = []
            for name in ("a.html", "b.html"):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(html)
                paths.append(path)
            listing = os.path.join(tmp, "list.txt")
            with open(listing, "w", encoding="utf-8") as fh:
                fh.write("\n".join(paths))
            out_json = os.path.join(tmp, "r.json")
            rc, _ = run_cli(["--pages", listing, "--json", out_json, "--quiet"])
            self.assertEqual(rc, 0)
            with open(out_json, encoding="utf-8") as fh:
                rep = json.load(fh)
        self.assertEqual(len(rep["pages"]), 2)
        self.assertIsNotNone(rep["site"])
        site_rows = {r["id"]: r for g in rep["site"]["groups"] for r in g["params"]}
        self.assertEqual(site_rows["meta.title_duplicate_site"]["verdict"], au.WARN)
        self.assertEqual(site_rows["site.pages_noindex"]["verdict"], au.OK)


class TestNetwork(unittest.TestCase):
    """Сеть — только на локальном сервере, поднятом тестом, и только через http_safe."""

    def routes(self):
        with open(BASIC, encoding="utf-8") as fh:
            html = fh.read()
        return {
            "/page": Route(200, html, {"Content-Type": "text/html; charset=utf-8",
                                       "Content-Encoding": "identity"}),
            "/robots.txt": Route(200, "User-agent: *\nDisallow: /secret\nSitemap: http://x/sitemap.xml\n",
                                 {"Content-Type": "text/plain"}),
        }

    def test_url_audit_asks_for_robots_once(self):
        with LocalServer(self.routes()) as srv:
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            page = au.audit_page(srv.base + "/page", fetcher=fetcher, keys=[],
                                 options={"robots": True})
            self.assertEqual(fetcher.requests_made, 2, "страница и robots.txt, больше ничего")
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(paths, ["/page", "/robots.txt"])
        rows = rows_by_id(page)
        self.assertEqual(rows["access.robots_googlebot"]["verdict"], au.OK)
        self.assertEqual(rows["access.robots_txt_status"]["verdict"], au.OK)
        self.assertEqual(rows["access.robots_sitemap_line"]["verdict"], au.OK)
        self.assertEqual(rows["access.final_status"]["verdict"], au.OK)

    def test_blocked_url_is_critical(self):
        routes = self.routes()
        routes["/robots.txt"] = Route(200, "User-agent: *\nDisallow: /page\n",
                                      {"Content-Type": "text/plain"})
        with LocalServer(routes) as srv:
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            page = au.audit_page(srv.base + "/page", fetcher=fetcher, keys=[],
                                 options={"robots": True})
        rows = rows_by_id(page)
        self.assertEqual(rows["access.robots_googlebot"]["verdict"], au.BAD)
        self.assertEqual(rows["access.robots_googlebot"]["severity"], "critical")
        merged = au.merge_registry(page["rows"], au.load_registry(), au.CHECKS, pages=1)
        self.assertIn("адрес закрыт для Googlebot", au.blocking_of(merged))

    def test_no_robots_flag_saves_a_request(self):
        with LocalServer(self.routes()) as srv:
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            au.audit_page(srv.base + "/page", fetcher=fetcher, keys=[], options={"robots": False})
            self.assertEqual(fetcher.requests_made, 1)

    def test_ssrf_guard_still_applies(self):
        rc, out = run_cli(["http://169.254.169.254/latest/meta-data/"])
        data = json.loads(out)
        self.assertNotEqual(rc, 0)
        self.assertIn(data.get("code"), ("blocked_address", "blocked_host"))


class TestSummary(unittest.TestCase):
    def test_text_summary_is_short_and_plain(self):
        page = au.audit_page(HOSTILE, fetcher=None, keys=[],
                             options={"base_url": "https://example.net/remont/", "robots": False})
        rep = au.build_report([page], registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=0)
        text = au.text_summary(rep)
        self.assertLessEqual(len(text.splitlines()), 20)
        self.assertIn("чинить первым", text)
        self.assertNotIn("<", text, "в сводку не должна попасть разметка страницы")

    def test_invisible_characters_are_escaped_everywhere(self):
        page = au.audit_page(os.path.join(FIXTURES, "zero_width.html"), fetcher=None, keys=[],
                             options={"base_url": "https://example.com/", "robots": False})
        rep = au.build_report([page], registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=0)
        blob = http_safe.dump_json(rep) + au.render_html(rep) + au.text_summary(rep)
        self.assertFalse(re.search(r"[​-‏‪-‮⁠-⁤﻿]", blob))


if __name__ == "__main__":
    unittest.main()


class TestSchemaAdapter(unittest.TestCase):
    """schema_check может появиться или не появиться — отчёт должен быть честным в обоих случаях."""

    def test_schema_rows_arrive_when_the_script_is_there(self):
        page = audit_file(BASIC)
        if au.schema_check is None:
            self.skipTest("schema_check в пакете нет")
        rows = rows_by_id(page)
        self.assertIn("markup.req_breadcrumb", rows)
        self.assertEqual(rows["markup.req_breadcrumb"]["from_script"], "schema_check")
        self.assertEqual(page["facts"]["schema"]["url"], "https://example.com/catalog/")

    def test_without_schema_check_params_stay_unchecked(self):
        saved = au.schema_check
        au.schema_check = None
        try:
            page = audit_file(BASIC)
            self.assertNotIn("schema", page["facts"])
            merged = au.merge_registry(page["rows"], au.load_registry(), au.CHECKS, pages=1)
            row = {r["registry_id"]: r for r in merged if r.get("in_registry")}["markup.req_product"]
            self.assertEqual(row["verdict"], au.NOTCHECKED)
        finally:
            au.schema_check = saved


class TestManyPagesNetwork(unittest.TestCase):
    def test_robots_is_fetched_once_per_host(self):
        with open(BASIC, encoding="utf-8") as fh:
            html = fh.read()
        routes = {
            "/one": Route(200, html, {"Content-Type": "text/html; charset=utf-8"}),
            "/two": Route(200, html, {"Content-Type": "text/html; charset=utf-8"}),
            "/robots.txt": Route(200, "User-agent: *\nDisallow: /two\n", {"Content-Type": "text/plain"}),
        }
        with LocalServer(routes) as srv:
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            cache = {}
            pages = [au.audit_page(srv.base + path, fetcher=fetcher, keys=[],
                                   options={"robots": True, "robots_cache": cache})
                     for path in ("/one", "/two")]
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(paths.count("/robots.txt"), 1, "robots.txt один на хост")
        self.assertEqual(rows_by_id(pages[0])["access.robots_googlebot"]["verdict"], au.OK)
        self.assertEqual(rows_by_id(pages[1])["access.robots_googlebot"]["verdict"], au.BAD,
                         "таблица доступа считается для каждого адреса своя")
