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
        self.assertIn(p["group"], set(au.GROUP_SLUGS) | set(au.REGISTRY_GROUPS))

    def test_groups_normalised(self):
        self.assertEqual(au.group_slug("intl"), "intl")
        self.assertEqual(au.group_slug("i18n"), "intl")
        self.assertEqual(au.group_slug("doc"), "doc", "новая группа реестра не теряется")
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
            self.assertIn(row["group"], set(au.GROUP_SLUGS) | set(au.REGISTRY_GROUPS))

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
        self.assertEqual(row["verdict_label"], "не проверяли",
                         "одно состояние — одно слово во всём отчёте")
        self.assertEqual(row["reason"], "нужен браузер, выгрузка данных или решение владельца")
        self.assertNotEqual(row["verdict"], au.OK, "непроверенное не выдаём за «в порядке»")

    def test_site_param_needs_a_crawl(self):
        merged = {r["registry_id"]: r for r in
                  au.merge_registry([], self.REG, au.SITE_CHECKS, pages=1, scope="site")
                  if r.get("in_registry")}
        row = merged["meta.title_duplicate_site"]
        self.assertEqual(row["verdict_label"], "не проверяли")
        self.assertEqual(row["reason"], "нужен обход сайта")
        self.assertIn("проверено страниц: 1", row["observation"])

    def test_names_are_shared_not_mapped(self):
        """Имя параметра одно на всех: таблицы соответствий между скриптами в пакете нет."""
        self.assertFalse(hasattr(au, "ID_ALIASES"), "слой сопоставления id убран намеренно")
        merged = {r["registry_id"]: r for r in
                  au.merge_registry(self.rows(), self.REG, au.CHECKS, pages=1, scope="page")
                  if r.get("in_registry")}
        self.assertEqual(merged["meta.title_present"]["verdict"], au.OK)
        self.assertEqual(merged["markup.og_required"]["verdict"], au.NOTCHECKED,
                         "проверка под чужим именем на параметр не встаёт")

    def test_foreign_name_is_visible_as_off_registry(self):
        merged = au.merge_registry(self.rows(), self.REG, au.CHECKS, pages=1, scope="page")
        extra = {r["id"] for r in merged if r.get("off_registry")}
        self.assertEqual(extra, {"social.og_title", "social.og_type"},
                         "чужое имя не теряется, а видно строкой «вне реестра»")

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
        hidden = rows["security.hidden_instructions"]
        self.assertIn(hidden["verdict"], (au.BAD, au.WARN))
        self.assertEqual(hidden["severity"], "high")
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

    def test_editor_guideline_tag_matches_the_source_it_shows(self):
        """Строка, у которой в источнике написано «ориентир редактора», обязана нести пометку.

        Источник в строку приходит от скрипта, а пометка приходила из реестра, и они
        расходились: `mobile.viewport_device_width` выходил проблемой severity high с
        источником «… — meta viewport; ориентир редактора» и без пометки, то есть мнение
        подавалось как требование.
        """
        for path, base in ((BASIC, "https://example.com/catalog/"),
                           (HOSTILE, "https://example.net/remont/")):
            rep = self.report(path, keys=["ремонт квартир"], base=base)
            rows = [r for p in rep["pages"] for g in p["groups"] for r in g["params"]]
            rows += [r for g in (rep.get("site") or {}).get("groups") or [] for r in g["params"]]
            self.assertTrue(rows)
            untagged = [r["id"] for r in rows
                        if au.is_editor_source(r.get("source")) and not r.get("editor_guideline")]
            self.assertEqual(untagged, [], f"{path}: источник говорит «ориентир редактора»")

    def test_value_text_reads_as_russian_not_as_python(self):
        self.assertEqual(au.value_text({"has_title": True, "has_description": False}),
                         "has_title: да · has_description: нет")
        self.assertEqual(au.value_text(["ItemList", "FAQPage"]), "ItemList, FAQPage")
        self.assertEqual(au.value_text([{"prop": "headline", "value": "x"}]),
                         "prop: headline · value: x")
        self.assertEqual(au.value_text({"nav": 2, "empty": [], "none": None}), "nav: 2")
        self.assertEqual(au.value_text(None), "")
        self.assertEqual(au.value_text(12), "12")


class TestHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        page = au.audit_page(HOSTILE, fetcher=None, keys=["ремонт квартир"],
                             options={"base_url": "https://example.net/remont/", "robots": False})
        cls.rep = au.build_report([page], registry=au.load_registry(), keys=["ремонт квартир"],
                                  options={"delay": 2.0}, requests_made=0)
        cls.html = au.render_html(cls.rep)

    def test_no_python_repr_in_the_value_column(self):
        """В отчёт владельцу сайта не попадает repr словаря из Python."""
        cells = re.findall(r'<span class="mono">(.*?)</span>', self.html, re.S)
        self.assertTrue(cells)
        for cell in cells:
            self.assertNotRegex(cell, r"\{&#x27;|&#x27;: |\[\{")
            self.assertNotRegex(cell, r"\b(True|False|None)\b")

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
        self.assertIn("нужен браузер, выгрузка данных или решение владельца", self.html)

    def test_one_state_one_word(self):
        """P7: карточка, счётчик группы и строка называют одно состояние одним словом."""
        for wrong in ("не проверяем", "не проверено автоматически", "проверки нет<"):
            self.assertNotIn(wrong, self.html)
        self.assertIn("не проверяли", self.html)


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

    def test_registry_path_that_does_not_exist_is_an_error(self):
        """Опечатка в --registry молча оставляла 99 встроенных проверок и «не проверяли 0»:
        отчёт выглядел полным, а реестра в нём не было."""
        rc, out = run_cli([BASIC, "--base-url", "https://example.com/", "--registry",
                           os.path.join(FIXTURES, "нет-такого-реестра.json")])
        self.assertNotEqual(rc, 0)
        self.assertEqual(json.loads(out)["code"], "bad_registry_path")

    def test_registry_path_that_exists_is_used(self):
        reg = os.path.join(os.path.dirname(SCRIPTS), "references", "registry.json")
        rc, out = run_cli([BASIC, "--base-url", "https://example.com/", "--registry", reg,
                           "--json", "-", "--quiet"])
        self.assertEqual(rc, 0)
        self.assertGreater(json.loads(out)["coverage"]["registry_params"], 100)


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
        # В строке Sitemap показывают адрес, а не repr словаря {'value': …, 'line': 3}.
        self.assertEqual(rows["access.robots_sitemap_line"]["value"], "http://x/sitemap.xml")
        self.assertEqual(rows["access.final_status"]["verdict"], au.OK)
        for cid in ("speed.ttfb", "speed.redirect_before_page", "speed.compression"):
            self.assertNotEqual(rows[cid]["verdict"], au.NODATA,
                                f"{cid}: ответ сервера передан в page_facts, данные есть")

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


class TestGroupsFromRegistry(unittest.TestCase):
    """Группы берутся из реестра: новая группа появляется в отчёте без правок в коде."""

    def test_report_keeps_registry_group_order_and_titles(self):
        reg = au.load_registry()
        page = audit_file(BASIC)
        rep = au.build_report([page], registry=reg, keys=[], options={"delay": 2.0},
                              requests_made=0)
        shown = [g["group"] for g in rep["pages"][0]["groups"]]
        want = [g for g in (x["id"] for x in
                            json.load(open(reg["source"], encoding="utf-8"))["groups"])
                if g in shown]
        self.assertEqual(shown, want, "порядок групп — как в реестре")
        titles = {g["group"]: g["title"] for g in rep["pages"][0]["groups"]}
        self.assertEqual(titles.get("doc"), "Разметка документа")
        self.assertIn("Разметка документа", au.render_html(rep))

    def test_unknown_registry_group_is_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "registry.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"version": "test", "groups": [{"id": "brandnew", "title": "Новая группа"}],
                           "params": [{"id": "brandnew.one", "group": "brandnew", "title": "Раз",
                                       "severity": "low", "scope": "page"}]}, fh)
            reg = au.load_registry(path)
            self.assertEqual(reg["params"][0]["group"], "brandnew")
            merged = au.merge_registry([], reg, au.CHECKS, pages=1, scope="page")
            groups = au.group_rows(merged, reg)
        self.assertEqual([g["title"] for g in groups], ["Новая группа"])
        au.load_registry()  # вернуть глобальные группы к рабочему реестру


class TestFalsePositivesFromRealSites(unittest.TestCase):
    """Находки, которые на чужих сайтах оказались ложными (QA 30.10.2026)."""

    DOCS = """<!doctype html><html lang="en"><head><title>json — encoder and decoder</title>
<meta name="description" content="Source code and reference for the json module."></head><body>
<nav><ul>
<li><a href="#basic-usage">Basic Usage</a></li>
<li><a href="#encoders">Encoders and Decoders</a></li>
<li><a href="#exceptions">Exceptions</a></li>
</ul></nav>
<form action="/search.html" method="get" role="search"><input name="q"><button>Go</button></form>
<main><h1>json — encoder and decoder</h1>
<h2 id="basic-usage">Basic Usage</h2><p>The json module exposes an API familiar to users of
the standard library marshal and pickle modules.</p>
<h2 id="encoders">Encoders and Decoders</h2><p>JSON decoder objects translate a document.</p>
<h2 id="exceptions">Exceptions</h2><p>Subclass of ValueError with additional properties.</p>
</main></body></html>"""

    SHOP = """<!doctype html><html lang="ru"><head><title>Кофемолка Б3 — купить</title></head><body>
<main><h1>Кофемолка Б3</h1><p>Цена 4 578 ₽, доставка по России.</p>
<form action="/order" method="post"><label for="t">Телефон</label><input id="t" name="tel"></form>
</main></body></html>"""

    def rows(self, html, url):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "page.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            page = au.audit_page(path, fetcher=None, keys=[],
                                 options={"base_url": url, "robots": False})
        return rows_by_id(page)

    def test_fragment_links_in_nav_are_not_links_without_an_address(self):
        row = self.rows(self.DOCS, "https://docs.example.org/3/library/json.html")
        self.assertEqual(row["access.nav_without_href"]["verdict"], au.OK,
                         "оглавление на якорях — обычные ссылки, а не переходы без адреса")

    def test_search_form_alone_does_not_make_a_page_commercial(self):
        row = self.rows(self.DOCS, "https://docs.example.org/3/library/json.html")
        self.assertEqual(row["commerce.contacts_visible"]["verdict"], au.INFO,
                         "страница документации без цен — не повод требовать телефон")

    def test_order_form_with_a_price_still_asks_for_contacts(self):
        row = self.rows(self.SHOP, "https://shop.example/kofemolka-b3/")
        self.assertEqual(row["commerce.contacts_visible"]["verdict"], au.WARN)

    def test_url_shape_checks_describe_what_they_found_not_what_they_look_for(self):
        row = self.rows(self.DOCS, "https://docs.example.org/3/library/json.html")
        case = row["access.url_case"]
        self.assertEqual(case["verdict"], au.OK)
        self.assertNotIn("есть заглавные", case["observation"],
                         "в «норме» нельзя печатать текст находки")
        session = row["access.url_session_params"]
        self.assertEqual(session["verdict"], au.OK)
        self.assertNotIn("параметр сессии", session["observation"].lower()[:20])

    def test_percent_encoded_path_is_a_note_not_a_warning(self):
        row = self.rows(self.SHOP, "https://shop.example/%D0%BA%D0%BE%D1%84%D0%B5/")
        self.assertEqual(row["access.url_encoding"]["verdict"], au.INFO)

    def test_group_title_in_fix_first_matches_the_section_heading(self):
        page = audit_file(BASIC)
        reg = au.load_registry()
        rep = au.build_report([page], registry=reg, keys=[], options={"delay": 2.0},
                              requests_made=0)
        sections = {g["group"]: g["title"] for g in rep["pages"][0]["groups"]}
        rows = {r["id"]: r for r in page["rows"]}
        for item in rep["pages"][0]["fix_first"]:
            slug = rows[item["id"]]["group"]
            self.assertEqual(item["group_title"], sections[slug],
                             f'{item["id"]}: в «чинить первым» и в разделе разные названия группы')

    def test_repeated_sentence_openings_are_not_called_chat_artifacts(self):
        """Английская документация: 19 абзацев с «this…» — это ритм, а не штампы."""
        text = " ".join(
            "<p>This object is a decoder. This decoder reads a document. "
            "This document is parsed strictly.</p>" for _ in range(6))
        html = ('<!doctype html><html lang="en"><head><title>Reference for the decoder</title>'
                '</head><body><main><h1>Decoder reference</h1>' + text + "</main></body></html>")
        row = self.rows(html, "https://docs.example.org/3/library/json.html")["content.officialese"]
        self.assertNotIn("чат-бота", row["observation"] or "",
                         "повтор зачинов не выдаётся за след переписки с моделью")

    def test_summary_cards_agree_with_the_number(self):
        page = audit_file(BASIC)
        rep = au.build_report([page], registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=0)
        html = au.render_html(rep)
        t = rep["totals"]
        for n, forms in ((t[au.BAD], ("проблема", "проблемы", "проблем")),
                         (t[au.WARN], ("предупреждение", "предупреждения", "предупреждений"))):
            self.assertIn(f"<b>{n}</b><span>{au._plural(n, *forms)}</span>", html)
        self.assertEqual(au._plural(1, *("проблема", "проблемы", "проблем")), "проблема")
        self.assertEqual(au._plural(2, *("проблема", "проблемы", "проблем")), "проблемы")
        self.assertEqual(au._plural(11, *("проблема", "проблемы", "проблем")), "проблем")


class TestNotHtml(unittest.TestCase):
    """P4: не HTML — одна строка отказа, а не восемь выдуманных находок."""

    def write(self, tmp, name, text):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_plain_text_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "notes.txt", "Просто текст без тегов.\nВторая строка.\n")
            rc, out = run_cli([path])
        data = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertEqual(data["code"], "not_html")
        self.assertIn("не веб-страница", data["error"])

    def test_json_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "data.json", '{"title": "нет тегов", "items": [1, 2, 3]}')
            rc, out = run_cli([path])
        self.assertEqual(json.loads(out)["code"], "not_html")

    def test_content_type_decides_for_urls(self):
        routes = {"/data.json": Route(200, '{"a": 1}', {"Content-Type": "application/json"}),
                  "/page": Route(200, "<html><body><p>есть разметка</p></body></html>",
                                 {"Content-Type": "text/html"})}
        with LocalServer(routes) as srv:
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            with self.assertRaises(au.http_safe.CliError) as caught:
                au.audit_page(srv.base + "/data.json", fetcher=fetcher, keys=[],
                              options={"robots": False})
            self.assertEqual(caught.exception.code, "not_html")
            self.assertIn("application/json", caught.exception.message)
            page = au.audit_page(srv.base + "/page", fetcher=fetcher, keys=[],
                                 options={"robots": False})
        self.assertNotIn("error", page)

    def test_html_fixtures_still_pass_the_gate(self):
        for name in ("basic_page.html", "audit_hostile.html", "csr_page.html", "zero_width.html"):
            path = os.path.join(FIXTURES, name)
            if os.path.exists(path):
                au.html_or_refuse(open(path, encoding="utf-8").read(), content_type="text/html",
                                  source=name)


class TestBlockingShortList(unittest.TestCase):
    """P6: сработало блокирующее условие — в очереди только оно."""

    def routes(self, status):
        with open(BASIC, encoding="utf-8") as fh:
            html = fh.read()
        return {"/gone": Route(status, html, {"Content-Type": "text/html; charset=utf-8"}),
                "/robots.txt": Route(200, "User-agent: *\nAllow: /\n", {"Content-Type": "text/plain"})}

    def report_for(self, status):
        with LocalServer(self.routes(status)) as srv:
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            page = au.audit_page(srv.base + "/gone", fetcher=fetcher, keys=[], options={"robots": True})
        return au.build_report([page], registry=au.load_registry(), keys=[],
                               options={"delay": 2.0}, requests_made=2)

    def test_404_collapses_the_queue(self):
        rep = self.report_for(404)
        self.assertEqual(rep["pages"][0]["blocking"], ["страница не отвечает 200"])
        self.assertEqual([i["id"] for i in rep["fix_first"]], ["access.final_status"])
        self.assertGreater(rep["pages"][0]["postponed"], 0, "отложенные находки сосчитаны, не скрыты")
        html = au.render_html(rep)
        self.assertIn("Пока держится блокирующее условие", html)
        self.assertNotIn("og:description", html.split("<h2>Параметры по группам</h2>")[0],
                         "до таблиц советов про Open Graph быть не должно")

    def test_200_keeps_the_full_queue(self):
        rep = self.report_for(200)
        self.assertEqual(rep["pages"][0]["blocking"], [])
        self.assertEqual(rep["pages"][0]["postponed"], 0)
        self.assertGreater(len(rep["fix_first"]), 1)


class TestSiteBlockForOnePage(unittest.TestCase):
    """P7: на одной странице раздел «Сайт целиком» — строка, а не семь пустых таблиц."""

    def test_collapsed(self):
        page = audit_file(BASIC)
        rep = au.build_report([page], registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=0)
        html = au.render_html(rep)
        head, _, tail = html.partition('<h2 id="site">Сайт целиком</h2>')
        self.assertTrue(tail)
        self.assertIn("Проверена одна страница", tail)
        self.assertLess(tail.index("<details>"), tail.index("<h3"),
                        "таблицы групп спрятаны под сворачиваемую строку")
