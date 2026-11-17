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


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_json(path):
    return json.loads(_read_text(path))


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
        # llms.txt — файл хоста: с 0.2.4 его строка уровня сайта, на странице её нет
        self.assertNotIn("ai.llms_txt", rows)
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
        # Ориентиры редактора идут после требований (QUEUE_RULE), внутри каждой части — по тяжести.
        for editor in (False, True):
            order = [au.SEVERITY_RANK[i["severity"]] for i in rep["fix_first"]
                     if bool(i.get("editor_guideline")) is editor]
            self.assertEqual(order, sorted(order))
        flags = [bool(i.get("editor_guideline")) for i in rep["fix_first"]]
        self.assertEqual(flags, sorted(flags))
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


class TestOnePageDoesNotSinkTheRun(unittest.TestCase):
    """0.2.3 (S-security №1): страница с JSON-LD-числом в 4301 цифру роняла весь прогон —
    и одиночный, и --pages/--site. Теперь одиночный разбор отчитывается о блоке,
    а внутренняя ошибка одной страницы в многостраничном режиме ложится в эту страницу."""

    BIG = ('<!doctype html><html lang="ru"><head><title>Длинное число</title>'
           '<script type="application/ld+json">{"@type":"Thing","n":' + "9" * 4301 +
           '}</script></head><body><h1>x</h1></body></html>')

    def test_single_file_with_huge_integer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "big.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.BIG)
            rc, out = run_cli([path, "--base-url", "https://example.com/", "--brief"])
        brief = json.loads(out)
        self.assertNotIn("error", brief)
        self.assertEqual(rc, 0)
        ids = [f["id"] for f in brief["findings"]]
        self.assertIn("markup.jsonld_parses", ids)

    def test_internal_error_on_one_page_keeps_the_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.html")
            bad = os.path.join(tmp, "bad.html")
            with open(BASIC, encoding="utf-8") as src, open(good, "w", encoding="utf-8") as fh:
                fh.write(src.read())
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(self.BIG)
            listing = os.path.join(tmp, "list.txt")
            with open(listing, "w", encoding="utf-8") as fh:
                fh.write(good + "\n" + bad + "\n")
            real = au.audit_page

            def flaky(src, **kw):
                if src == bad:
                    raise AttributeError("synthetic")
                return real(src, **kw)

            out_json = os.path.join(tmp, "r.json")
            au.audit_page = flaky
            try:
                rc, out = run_cli(["--pages", listing, "--json", out_json, "--quiet"])
            finally:
                au.audit_page = real
            self.assertEqual(rc, 0, out)
            rep = _read_json(out_json)
        self.assertEqual(len(rep["pages"]), 2)
        failed = [p for p in rep["pages"] if p.get("code") == "internal_error"]
        self.assertEqual(len(failed), 1)
        self.assertIn("AttributeError", failed[0]["error"])

    def test_registry_with_huge_integer_is_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = os.path.join(tmp, "registry.json")
            with open(reg, "w", encoding="utf-8") as fh:
                fh.write('{"params": [{"id": "x", "n": ' + "9" * 4301 + "}]}")
            loaded = au.load_registry(reg)
        self.assertTrue(any("не разобрался" in w for w in loaded.get("warnings", [])), loaded.get("warnings"))


class TestScriptLoweredSeverity(unittest.TestCase):
    """0.2.3: серьёзность, которую скрипт снизил по контексту страницы (слайдер, один замер TTFB),
    реестр больше не поднимает обратно — раньше «low» скрипта становилось high/medium очереди."""

    def merged(self, item):
        rows = au.imported_rows({"page": {"checks": [item]}})
        out = au.merge_registry(rows, au.load_registry(), au.CHECKS)
        return next(r for r in out if r["id"] == item["id"])

    def test_context_lowered_severity_survives(self):
        r = self.merged({"id": "speed.ttfb", "status": "warn", "severity": "low",
                         "severity_by_context": True, "group": "speed", "title": "TTFB"})
        self.assertEqual(r["severity"], "low")
        self.assertEqual(r["registry_severity"], "medium")

    def test_plain_row_takes_registry_severity(self):
        r = self.merged({"id": "speed.ttfb", "status": "warn", "severity": "low",
                         "group": "speed", "title": "TTFB"})
        self.assertEqual(r["severity"], "medium")

    def test_context_flag_cannot_raise_severity(self):
        r = self.merged({"id": "speed.ttfb", "status": "warn", "severity": "critical",
                         "severity_by_context": True, "group": "speed", "title": "TTFB"})
        self.assertEqual(r["severity"], "medium")

    def test_slider_microdata_stays_low_in_audit(self):
        html = ('<html lang=ru><head><title>t</title></head><body><h1>x</h1>'
                '<div class="t-slds__item" style="visibility:hidden"><div itemscope '
                'itemtype="https://schema.org/ImageObject"><span itemprop="name">Слайд</span>'
                '</div></div></body></html>')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            page = audit_file(path)
        merged = au.merge_registry(page["rows"], au.load_registry(), au.CHECKS)
        row = next(r for r in merged if r["id"] == "markup.hidden_markup")
        self.assertEqual((row["verdict"], row["severity"]), (au.WARN, "low"))


class TestWorstEntityRowWins(unittest.TestCase):
    """K-markup 16.11.2026 (Б1): schema_check пишет строку на сущность, сводка брала последнюю —
    «нет location» у первого Event пропадало за «норма» второго."""

    def test_two_events_first_incomplete(self):
        ev_full = ('{"@type":"Event","name":"Вторая","startDate":"2026-12-02",'
                   '"location":{"@type":"Place","name":"Зал","address":"Москва"}}')
        html = ('<!doctype html><html lang="ru"><head><title>События</title>'
                '<script type="application/ld+json">[{"@context":"https://schema.org",'
                '"@type":"Event","name":"Первая","startDate":"2026-12-01"},' + ev_full +
                ']</script></head><body><h1>Первая</h1><p>Вторая</p></body></html>')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ev.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            page = audit_file(path)
        merged = au.merge_registry(page["rows"], au.load_registry(), au.CHECKS)
        row = next(r for r in merged if r["id"] == "markup.req_event")
        self.assertEqual(row["verdict"], au.BAD)
        self.assertIn("location", row["observation"])
        self.assertIn("1 из 2", row["observation"])

    def test_own_check_still_overrides_script_row(self):
        rows = [{"id": "x.y", "verdict": au.BAD, "severity": "high", "from_script": "schema_check"},
                {"id": "x.y", "verdict": au.OK, "severity": "info"}]
        self.assertEqual(au._rows_by_id(rows)["x.y"]["verdict"], au.OK)


class TestMicrodataAndHeaderContacts(unittest.TestCase):
    """K-markup 16.11.2026: Б6 — Organization в микроданных давал «разметки организации нет»,
    поля микроданных молчали; телефон в <header> вне <article> давал «контактов нет»."""

    HTML = ('<!doctype html><html lang="ru"><head><title>Книга</title></head><body>'
            '<header><span class="phone">8 800 600-95-25</span></header>'
            '<div itemscope itemtype="http://schema.org/Organization"><meta itemprop="name" '
            'content="Магазин"></div><article itemscope itemtype="http://schema.org/Product">'
            '<h1 itemprop="name">Книга про зрение</h1><div itemprop="offers" itemscope '
            'itemtype="http://schema.org/Offer"><meta itemprop="price" content="68">'
            '<meta itemprop="priceCurrency" content="RUB"></div><p>Купить книгу за 68 ₽.</p>'
            '</article></body></html>')

    def test_microdata_org_and_header_phone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "md.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.HTML)
            page = audit_file(path)
        merged = {r["id"]: r for r in au.merge_registry(page["rows"], au.load_registry(), au.CHECKS)}
        self.assertEqual(merged["commerce.address_markup"]["verdict"], au.OK)
        self.assertEqual(merged["commerce.contacts_visible"]["verdict"], au.OK)
        self.assertEqual(merged["markup.req_product"]["verdict"], au.NODATA)
        self.assertIn("microdata", merged["markup.req_product"]["observation"])


class TestTextRowsWording(unittest.TestCase):
    """C-content 16.11.2026: C11 — «например, H2 → H4» было зашито; C10 — пустое evidence
    канцелярита и порог в штуках вместо плотности."""

    def test_real_heading_jump(self):
        hs = [{"level": 1, "text": "Статья"}, {"level": 2, "text": "Раздел"},
              {"level": 5, "text": "Ответить?"}, {"level": 3, "text": "x"}]
        self.assertTrue(au._heading_skip(hs).startswith("H2 → H5"))
        self.assertIsNone(au._heading_skip([{"level": 1}, {"level": 2}, {"level": 3}, {"level": 2}]))

    def test_officialese_evidence_and_density(self):
        text = ("<html lang=ru><body><main><h1>Данный товар</h1><p>" +
                "Данный товар является лучшим. В целях экономии производится доставка. " * 2 +
                "</p></main></body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            page = audit_file(path)
        row = rows_by_id(page)["content.officialese"]
        self.assertTrue(row.get("evidence") and row["evidence"].strip("; "), row)


class TestKeyMissingUsesZones(unittest.TestCase):
    """C-content 16.11.2026 (C5): ключ только в title давал «не встречается нигде»."""

    def test_key_in_title_only_is_not_missing(self):
        html = ("<html lang=ru><head><title>Складской учёт онлайн</title></head><body><main>"
                "<h1>Программа</h1><p>Текст про остатки и накладные без нужной фразы.</p>"
                "</main></body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "k.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            page = audit_file(path, keys=["складской учёт"])
        self.assertEqual(rows_by_id(page)["content.key_missing"]["verdict"], au.OK)


class TestNofollowBeyondLinkList(unittest.TestCase):
    """M-sonnet 16.11.2026: nofollow на /nestatus в подвале не попадал в счёт — список ссылок
    обрезается на 300, а проверка считала по нему."""

    def test_footer_nofollow_counted(self):
        body = "".join(f'<a href="/p{i}">Страница {i}</a>' for i in range(320))
        html = (f'<html lang=ru><head><title>t</title></head><body><h1>x</h1>{body}'
                '<footer><a href="/nestatus" rel="nofollow">Статус</a>'
                '<a href="/go/1" rel="sponsored nofollow">Партнёр</a></footer></body></html>')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "n.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            page = audit_file(path)
        row = rows_by_id(page)["links.nofollow_internal"]
        self.assertEqual(row["verdict"], au.WARN)
        self.assertIn(": 1", row["observation"])
        self.assertIn("nestatus", row["evidence"])


class TestBriefNotCheckedExplained(unittest.TestCase):
    """M-haiku 16.11.2026: «не проверено» в brief и в pages[].totals расходились без объяснения."""

    def test_reasons_add_up(self):
        rc, out = run_cli([BASIC, "--base-url", "https://example.com/", "--brief"])
        brief = json.loads(out)
        self.assertEqual(sum(brief["not_checked_reasons"].values()), brief["totals"][au.NOTCHECKED])
        self.assertIn("нужен обход сайта", brief["not_checked_reasons"])


class TestKeyZonePhraseVsWords(unittest.TestCase):
    """C-content 16.11.2026 (C4): «есть» в зоне по словам ключа вразбивку — не вхождение фразы."""

    def test_scattered_words_are_not_present(self):
        html = ("<html lang=ru><head><title>Учёт товаров на складе</title></head><body><main>"
                "<h1>Складской учёт</h1><p>Текст.</p></main></body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "z.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            page = audit_file(path, keys=["учёт товаров", "учёт на складе"])
            only_loose = audit_file(path, keys=["учёт на складе"])
        title = rows_by_id(page)["content.key_in_title"]
        self.assertEqual(title["verdict"], au.OK)
        self.assertIn("есть: учёт товаров", title["observation"])
        self.assertIn("вразбивку, не фразой: учёт на складе", title["observation"])
        self.assertEqual(rows_by_id(only_loose)["content.key_in_title"]["verdict"], au.INFO)


class TestNauseaOneNumberOneVerdict(unittest.TestCase):
    """C-content 16.11.2026 (C9): классическая тошнота решалась по академической на пороге 6."""

    def test_thresholds(self):
        fn = au.c_nausea
        class C:  # минимальный контекст: c_nausea читает только ctx.get("nausea")
            def __init__(self, n):
                self.n = n

            def get(self, key, default=None):
                return self.n if key == "nausea" else default
        self.assertEqual(fn(C({"classic": 9.17, "academic_pct": 7.33, "top_stem": "x"}))["verdict"], au.WARN)
        self.assertEqual(fn(C({"classic": 5.0, "academic_pct": 7.33, "top_stem": "x"}))["verdict"], au.OK)
        aca = au.c_nausea_academic
        self.assertEqual(aca(C({"academic_pct": 7.33, "top_stem": "x"}))["verdict"], au.OK)


class TestOutOverwrite(unittest.TestCase):
    """0.2.3: --out/--json не затирают чужой файл; свой прошлый отчёт — затирают."""

    def test_rerun_overwrites_own_reports_and_refuses_foreign(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_out = os.path.join(tmp, "r.html")
            json_out = os.path.join(tmp, "r.json")
            argv = [BASIC, "--base-url", "https://example.com/", "--out", html_out,
                    "--json", json_out, "--quiet"]
            self.assertEqual(run_cli(argv)[0], 0)
            self.assertIn('<meta name="generator" content="papa-seo', _read_text(html_out))
            self.assertEqual(_read_json(json_out)["generator"], "papa-seo")
            self.assertEqual(run_cli(argv)[0], 0, "повторный прогон в те же файлы")
            site = os.path.join(tmp, "index.html")
            with open(site, "w", encoding="utf-8") as fh:
                fh.write("<!doctype html><h1>главная сайта</h1>")
            rc, out = run_cli([BASIC, "--base-url", "https://example.com/", "--out", site, "--quiet"])
            self.assertNotEqual(rc, 0)
            self.assertEqual(json.loads(out)["code"], "out_exists")
            self.assertIn("главная сайта", _read_text(site))
            rc, _ = run_cli([BASIC, "--base-url", "https://example.com/", "--out", site,
                             "--quiet", "--force"])
            self.assertEqual(rc, 0)


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
        self.assertFalse(re.search(r"[\u200b-\u200f\u202a-\u202e\u2060-⁤\ufeff]", blob))



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
                            _read_json(reg["source"])["groups"])
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

    PAID = """<!doctype html><html lang="ru"><head><title>Каталог партнёрок</title></head><body>
<main><h1>Каталог партнёрок</h1><p>Список программ с условиями и выплатами по странам.</p>
<a href="/go/29" rel="sponsored nofollow noopener">Перейти к рекламодателю</a>
<a href="/forum/t/1" rel="ugc nofollow">Тема на форуме</a>
%s</main></body></html>"""

    def test_sponsored_redirect_on_own_host_is_not_internal_nofollow(self):
        row = self.rows(self.PAID % "", "https://portal.example/catalog/")
        self.assertEqual(row["links.nofollow_internal"]["verdict"], au.OK,
                         "sponsored/ugc на своём редиректе — пометка по правилам Google")

    def test_plain_nofollow_on_own_page_is_still_reported(self):
        row = self.rows(self.PAID % '<a href="/about" rel="nofollow">О нас</a>',
                        "https://portal.example/catalog/")
        nf = row["links.nofollow_internal"]
        self.assertEqual(nf["verdict"], au.WARN)
        self.assertIn("nofollow: 1", nf["observation"])
        self.assertIn("/about", nf["evidence"])
        self.assertNotIn("/go/29", nf["evidence"])

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
                au.html_or_refuse(_read_text(path), content_type="text/html",
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


class TestSiteSampling(unittest.TestCase):
    """Выборка адресов для --site: без сети, чистая логика."""

    def test_homepage_is_always_first(self):
        urls = ["https://s.ru/blog/1", "https://s.ru/", "https://s.ru/shop/2"]
        picked = au.sample_site_urls(urls, 10, home="https://s.ru/")
        self.assertEqual(picked[0], "https://s.ru/")

    def test_homepage_added_when_missing(self):
        urls = ["https://s.ru/blog/1", "https://s.ru/blog/2"]
        picked = au.sample_site_urls(urls, 10, home="https://s.ru/")
        self.assertEqual(picked[0], "https://s.ru/")

    def test_limit_is_respected(self):
        urls = [f"https://s.ru/blog/{i}" for i in range(100)]
        picked = au.sample_site_urls(urls, 7, home="https://s.ru/")
        self.assertEqual(len(picked), 7)
        self.assertEqual(len(set(picked)), 7, "без повторов")

    def test_sample_spreads_across_path_types(self):
        urls = ([f"https://s.ru/blog/{i}" for i in range(20)]
                + [f"https://s.ru/shop/{i}" for i in range(20)]
                + ["https://s.ru/about"])
        picked = au.sample_site_urls(urls, 7, home="https://s.ru/")
        segs = {au._first_segment(u) for u in picked}
        self.assertIn("blog", segs)
        self.assertIn("shop", segs)
        self.assertIn("about", segs)

    def test_within_type_not_only_first_in_a_row(self):
        urls = [f"https://s.ru/blog/{i:02d}" for i in range(20)]
        picked = au.sample_site_urls(urls, 5, home="https://s.ru/")
        blog = [u for u in picked if "/blog/" in u]
        self.assertGreaterEqual(len(blog), 3)
        self.assertNotEqual(blog, [f"https://s.ru/blog/{i:02d}" for i in range(len(blog))],
                            "берём не первые подряд, а вразбивку")

    def test_limit_bounds(self):
        with self.assertRaises(au.http_safe.CliError):
            au.check_site_limit(0)
        with self.assertRaises(au.http_safe.CliError):
            au.check_site_limit(au.SITE_SAMPLE_MAX + 1)
        self.assertEqual(au.check_site_limit(au.SITE_SAMPLE_MAX), au.SITE_SAMPLE_MAX)


class TestSiteCollect(unittest.TestCase):
    """--site: обнаружение карты, выборка, уважение robots.txt. Сеть — локальный сервер."""

    def _html(self):
        with open(BASIC, encoding="utf-8") as fh:
            return fh.read()

    def _sitemap_routes(self, base):
        locs = ([base + "/"]
                + [f"{base}/blog/{i}" for i in range(12)]
                + [f"{base}/shop/{i}" for i in range(6)]
                + [f"{base}/secret/x"])
        body = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                + "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
                + "</urlset>")
        html = self._html()
        routes = {
            "/robots.txt": Route(200, f"User-agent: *\nDisallow: /secret\nSitemap: {base}/sitemap.xml\n",
                                 {"Content-Type": "text/plain"}),
            "/sitemap.xml": Route(200, body, {"Content-Type": "application/xml"}),
        }
        # каждая страница отдаёт одну и ту же разметку
        def page(handler):
            return Route(200, html, {"Content-Type": "text/html; charset=utf-8"})
        for loc in locs:
            routes[urlsplit_path(loc)] = page
        return routes, locs

    def test_collect_from_sitemap_and_skip_robots(self):
        routes, locs = self._sitemap_routes("PLACEHOLDER")
        with LocalServer({}) as srv:
            # пересобрать маршруты под реальный порт
            routes, locs = self._sitemap_routes(srv.base)
            srv.routes = routes
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            options = {"robots": True, "robots_cache": {}}
            sources, meta = au.collect_site(srv.base, fetcher=fetcher, limit=8, options=options)
        self.assertEqual(meta["source"], "sitemap")
        self.assertTrue(meta["sitemap_total"] >= 19)
        self.assertEqual(sources[0], srv.base + "/")
        self.assertTrue(all("/secret" not in u for u in sources), "закрытое robots.txt не берём")
        self.assertEqual(meta["robots_disallowed"], 1)
        self.assertLessEqual(len(sources), 8)
        # robots.txt закэширован под origin — постраничный аудит его не перезапросит
        self.assertIn(srv.base, options["robots_cache"])

    def test_no_sitemap_falls_back_to_homepage(self):
        base_holder = {}
        html = ('<html><head><title>Home</title></head><body>'
                '<a href="/about">about</a><a href="/blog/1">b1</a>'
                '<a href="https://other.example/x">ext</a></body></html>')
        with LocalServer({}) as srv:
            routes = {
                "/": Route(200, html, {"Content-Type": "text/html; charset=utf-8"}),
                "/about": Route(200, html, {"Content-Type": "text/html; charset=utf-8"}),
                "/blog/1": Route(200, html, {"Content-Type": "text/html; charset=utf-8"}),
                "/robots.txt": Route(404, "no"),
                "/sitemap.xml": Route(404, "no"),
            }
            srv.routes = routes
            fetcher = http_safe.Fetcher(delay=0, allow_local=True)
            options = {"robots": True, "robots_cache": {}}
            sources, meta = au.collect_site(srv.base + "/", fetcher=fetcher, limit=10, options=options)
        self.assertEqual(meta["source"], "homepage")
        self.assertEqual(sources[0], srv.base + "/")
        self.assertTrue(any(u.endswith("/about") for u in sources))
        self.assertTrue(all("other.example" not in u for u in sources), "чужой хост не берём")


class TestSiteReport(unittest.TestCase):
    """Сводный отчёт обхода: очередь «повторяется по сайту» и честный охват."""

    def _page(self, base_url):
        return au.audit_page(HOSTILE, fetcher=None, keys=[],
                             options={"base_url": base_url, "robots": False})

    def test_recurring_queue_counts_pages(self):
        pages = [self._page("https://ex.ru/a/"), self._page("https://ex.ru/b/"),
                 self._page("https://ex.ru/c/")]
        scan = {"source": "sitemap", "sitemap_total": 42, "robots_disallowed": 2,
                "picked": 3, "candidates": 40}
        rep = au.build_report(pages, registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=5, site_scan=scan)
        self.assertTrue(rep["recurring"], "одинаковые находки на 3 страницах должны всплыть наверх")
        top = rep["recurring"][0]
        self.assertEqual(top["count"], 3)
        self.assertEqual(len(top["pages"]), 3)
        # recurring отсортирован по числу страниц, затем серьёзности
        counts = [a["count"] for a in rep["recurring"]]
        self.assertEqual(counts, sorted(counts, reverse=True))
        # постраничные дубли recurring убраны из общей очереди
        rec_ids = {a["id"] for a in rep["recurring"]}
        self.assertFalse([f for f in rep["fix_first"] if f.get("page") and f["id"] in rec_ids])

    def test_coverage_text_is_honest(self):
        pages = [self._page("https://ex.ru/a/"), self._page("https://ex.ru/b/")]
        scan = {"source": "sitemap", "sitemap_total": 500, "robots_disallowed": 3, "picked": 2}
        rep = au.build_report(pages, registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=4, site_scan=scan)
        text = au._scan_coverage_text(rep)
        self.assertIn("Проверено", text)
        self.assertIn("500", text)
        self.assertIn("robots.txt", text)
        html = au.render_html(rep)
        self.assertIn("Повторяется по сайту", html)
        self.assertIn("500", html)

    def test_homepage_source_says_no_sitemap(self):
        pages = [self._page("https://ex.ru/")]
        scan = {"source": "homepage", "sitemap_total": 4, "robots_disallowed": 0, "picked": 1}
        rep = au.build_report(pages, registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=2, site_scan=scan)
        self.assertIn("карты сайта нет", au._scan_coverage_text(rep))


def urlsplit_path(url):
    from urllib.parse import urlsplit as _us
    return _us(url).path


class TestSiteCli(unittest.TestCase):
    """--site целиком через CLI: сколько запросов уходит на сайт и что попадает в очередь.

    Fetcher подменяется через au.make_fetcher: пауза 2 с остаётся в силе, но вместо сна
    записывается — так видно, что между каждыми двумя запросами она была, и тест не ждёт."""

    def setUp(self):
        self.sleeps = []
        self.saved = au.make_fetcher

        def fake(*, delay, state_dir):
            return au.http_safe.Fetcher(delay=delay, allow_local=True, sleep=self.sleeps.append,
                                        shared_pace=False)
        au.make_fetcher = fake

    def tearDown(self):
        au.make_fetcher = self.saved

    def _site(self, base, children=6, per_child=4, index=True):
        with open(BASIC, encoding="utf-8") as fh:
            html = fh.read()
        html_route = Route(200, html, {"Content-Type": "text/html; charset=utf-8"})
        routes = {"/": html_route}
        urlset = lambda locs: ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/'
                               'sitemap/0.9">' + "".join(f"<url><loc>{u}</loc></url>" for u in locs)
                               + "</urlset>")
        child_urls = []
        for c in range(children):
            locs = [f"{base}/sec{c}/{i}" for i in range(per_child)]
            for u in locs:
                routes[urlsplit_path(u)] = html_route
            routes[f"/sm-{c}.xml"] = Route(200, urlset(locs), {"Content-Type": "application/xml"})
            child_urls.append(f"{base}/sm-{c}.xml")
        if index:
            body = ('<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    + "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in child_urls)
                    + "</sitemapindex>")
            routes["/sitemap.xml"] = Route(200, body, {"Content-Type": "application/xml"})
        routes["/robots.txt"] = Route(200, f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n",
                                      {"Content-Type": "text/plain"})
        return routes

    def _run(self, srv, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "r.json")
            rc, _ = run_cli(["--site", srv.base, "--json", out, "--quiet", *extra])
            self.assertEqual(rc, 0)
            with open(out, encoding="utf-8") as fh:
                return json.load(fh)

    def test_site_requests_are_counted_and_paced(self):
        with LocalServer({}) as srv:
            srv.routes = self._site(srv.base)
            rep = self._run(srv, "--limit", "5")
            paths = [r["path"] for r in srv.requests]
        # robots + индекс + две дочерние карты (по две страницы выборки на карту) + 5 страниц
        # + llms.txt и ai.txt (в --site по умолчанию). http:// и www у 127.0.0.1 не бывает.
        self.assertEqual(paths.count("/robots.txt"), 1)
        self.assertEqual(paths.count("/sitemap.xml"), 1)
        self.assertEqual(paths.count("/llms.txt"), 1)
        self.assertEqual(paths.count("/ai.txt"), 1)
        self.assertEqual(sum(1 for p in paths if p.startswith("/sm-")), au.children_budget(5))
        self.assertEqual(len(paths), 1 + 1 + au.children_budget(5) + 5 + 2)
        self.assertEqual(rep["requests"]["count"], len(paths))
        pages = [p for p in paths if not p.endswith((".txt", ".xml"))]
        self.assertEqual(len(pages), len(set(pages)), "ни одна страница не скачана дважды")
        self.assertEqual(len(self.sleeps), len(paths) - 1, "пауза перед каждым запросом, кроме первого")
        self.assertTrue(all(0 < s <= 2.0 for s in self.sleeps))

    def test_children_are_spread_across_the_index(self):
        with LocalServer({}) as srv:
            srv.routes = self._site(srv.base, children=10, per_child=2)
            self._run(srv, "--limit", "5")
            maps = [r["path"] for r in srv.requests if r["path"].startswith("/sm-")]
        self.assertEqual(len(maps), 2)
        self.assertNotEqual(maps, ["/sm-0.xml", "/sm-1.xml"], "не первые подряд, а вразбивку")

    def test_queue_has_no_duplicates_and_counts_pages(self):
        with LocalServer({}) as srv:
            srv.routes = self._site(srv.base)
            rep = self._run(srv, "--limit", "4")
        ids = [i["id"] for i in rep["fix_first"]]
        self.assertEqual(len(ids), len(set(ids)), "одна находка — одна строка очереди")
        self.assertTrue(rep["recurring"])
        for a in rep["recurring"]:
            self.assertEqual(a["count"], len(a["pages"]))
            self.assertGreaterEqual(a["count"], 2)
        keys = [au.queue_key(i) for i in rep["fix_first"]]
        self.assertEqual(keys, sorted(keys), "очередь отсортирована по тяжести × охвату")

    def test_sitemap_flag_reuses_the_downloaded_map(self):
        with LocalServer({}) as srv:
            srv.routes = self._site(srv.base, children=2, per_child=2)
            self._run(srv, "--limit", "3", "--sitemap")
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(paths.count("/sitemap.xml"), 1, "карту сайта второй раз не качаем")

    def test_single_404_exits_non_zero_but_writes_the_report(self):
        with LocalServer({"/gone": Route(404, "<html><body><p>нет</p></body></html>",
                                         {"Content-Type": "text/html; charset=utf-8"}),
                          "/robots.txt": Route(404, "no")}) as srv:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "r.json")
                rc, _ = run_cli([srv.base + "/gone", "--json", out, "--quiet"])
                rep = _read_json(out)
        self.assertEqual(rc, au.EXIT_PAGE_NOT_OK)
        self.assertIn("Блокирует", rep["verdict"])

    def test_verdict_is_there_without_blocking(self):
        with LocalServer({}) as srv:
            srv.routes = self._site(srv.base, children=1, per_child=2)
            rep = self._run(srv, "--limit", "2")
        self.assertIn("Блокирующих условий нет", rep["verdict"])

    def test_homepage_fallback_fetches_home_once(self):
        html = ('<html><head><title>Home</title></head><body><main><p>Главная страница сайта.</p>'
                '<a href="/about">about</a><a href="/blog/1">b1</a></main></body></html>')
        page = Route(200, html, {"Content-Type": "text/html; charset=utf-8"})
        with LocalServer({"/": page, "/about": page, "/blog/1": page,
                          "/robots.txt": Route(404, "no"), "/sitemap.xml": Route(404, "no")}) as srv:
            rep = self._run(srv, "--limit", "3")
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(rep["site_scan"]["source"], "homepage")
        self.assertEqual(paths.count("/"), 1, "главная и для ссылок, и для аудита — один запрос")


class TestQueueOrder(unittest.TestCase):
    """«Чинить первым»: блокирующее сверху, дальше тяжесть × охват, ориентиры редактора — после."""

    def _row(self, cid, severity, *, editor=False, blocking=False):
        row = {"id": cid, "title": cid, "group": "meta", "group_title": "Мета", "severity": severity,
               "verdict": au.WARN, "editor_guideline": editor}
        if blocking:
            row["blocking_text"] = "x"
        return row

    def test_reach_lifts_a_template_finding(self):
        per_page = [(f"p{i}", [self._row("tpl", "medium")]) for i in range(4)]
        per_page[0][1].append(self._row("single", "high"))
        order = [a["id"] for a in au.aggregate_findings(per_page)]
        self.assertEqual(order, ["tpl", "single"], "medium на 4 страницах (12) выше high на одной (9)")

    def test_editor_guidelines_go_last_and_blocking_first(self):
        per_page = [(f"p{i}", [self._row("ed", "high", editor=True), self._row("low", "low")])
                    for i in range(5)]
        per_page[0][1].append(self._row("gone", "critical", blocking=True))
        order = [a["id"] for a in au.aggregate_findings(per_page)]
        self.assertEqual(order, ["gone", "low", "ed"])

    def test_language_prefix_does_not_swallow_the_sample(self):
        self.assertEqual(au._first_segment("https://s.ru/en/news/1"), "en/news")
        self.assertEqual(au._first_segment("https://s.ru/en/about"), "en")
        self.assertEqual(au._first_segment("https://s.ru/blog/1"), "blog")

    def test_sample_prefers_big_path_types(self):
        urls = ([f"https://s.ru/a{i}" for i in range(3)]
                + [f"https://s.ru/big/{i}" for i in range(50)]
                + [f"https://s.ru/zz/{i}" for i in range(30)])
        picked = au.sample_site_urls(urls, 3, home="https://s.ru/")
        self.assertEqual([au._first_segment(u) for u in picked[1:]], ["big", "zz"])



class TestBrief(unittest.TestCase):
    """--brief: агенту — только находки, несколько КБ, в порядке очереди."""

    def test_brief_is_small_and_ordered(self):
        rc, out = run_cli([HOSTILE, "--base-url", "https://example.net/remont/", "--brief", "--no-robots"])
        self.assertEqual(rc, 0)
        self.assertLess(len(out.encode("utf-8")), 20000)
        data = json.loads(out)
        self.assertEqual(data["mode"], "brief")
        self.assertTrue(data["verdict"])
        self.assertTrue(data["findings"])
        for item in data["findings"]:
            self.assertTrue({"id", "title", "severity", "verdict"} <= set(item))
            self.assertIn(item["verdict"], (au.BAD, au.WARN))
        flags = [bool(i.get("editor_guideline")) for i in data["findings"]]
        self.assertEqual(flags, sorted(flags), "ориентиры редактора — после требований")

    def test_brief_and_json_stdout_conflict(self):
        rc, out = run_cli([HOSTILE, "--brief", "--json", "-"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(json.loads(out)["code"], "bad_arguments")

    def test_brief_on_site_has_reach(self):
        pages = [au.audit_page(HOSTILE, fetcher=None, keys=[],
                               options={"base_url": f"https://ex.ru/{c}/", "robots": False})
                 for c in "abc"]
        rep = au.build_report(pages, registry=au.load_registry(), keys=[], options={"delay": 2.0},
                              requests_made=3)
        brief = au.brief_report(rep)
        self.assertTrue(any(i.get("count") == 3 and len(i["pages"]) == 3 for i in brief["findings"]))


class TestEditorCount(unittest.TestCase):
    """Число «ориентиров редактора» — проверенные в этом запуске, без повторов по страницам,
    и отдельно — сколько так помечено в реестре."""

    def test_counts_are_consistent(self):
        reg = au.load_registry()
        pages = [audit_file(BASIC), audit_file(BASIC, options={"base_url": "https://example.com/b/",
                                                               "robots": False})]
        cov = au.build_report(pages, registry=reg, keys=[], options={"delay": 2.0},
                              requests_made=0)["coverage"]
        one = au.build_report(pages[:1], registry=reg, keys=[], options={"delay": 2.0},
                              requests_made=0)["coverage"]
        self.assertEqual(cov["editor_guidelines_in_registry"],
                         sum(1 for p in reg["params"] if p["editor_guideline"]))
        self.assertEqual(cov["editor_guidelines"],
                         cov["editor_guidelines_registry_flag"] + cov["editor_guidelines_by_threshold"])
        self.assertLessEqual(cov["editor_guidelines_registry_flag"], cov["editor_guidelines_in_registry"])
        self.assertLess(cov["editor_guidelines"], 2 * one["editor_guidelines"],
                        "две страницы не удваивают счёт")


if __name__ == "__main__":
    unittest.main()


class CanonicalDuplicateTest(unittest.TestCase):
    """Q2 17.11: два одинаковых canonical — не противоречие, не high."""

    def _run(self, hrefs):
        fn = next(c for c in au.CHECKS if c.id == "access.canonical_count").fn
        return fn({"canonical": [{"href": h, "in_head": True} for h in hrefs]})

    def test_identical_tags_are_low_warning(self):
        r = self._run(["https://example.ru/a/", "https://example.ru/a/"])
        self.assertEqual(r["verdict"], "warn")
        self.assertEqual(r["severity"], "low")

    def test_different_tags_stay_high(self):
        r = self._run(["https://example.ru/a/", "https://example.ru/b/"])
        self.assertEqual(r["verdict"], "problem")
        self.assertEqual(r["severity"], "high")


# ---------------------------------------------------------------------------- 0.2.4: --site по умолчанию

def _urlset(locs, lastmod=None):
    lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
    return ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{u}</loc>{lm}</url>" for u in locs) + "</urlset>")


def _site_page(links=()):
    nav = "".join(f'<a href="{h}">n</a>' for h in links)
    return Route(200, ('<html><head><title>T</title></head><body><nav><a href="/">Главная</a>'
                       '<a href="/blog/">Блог</a></nav><main><h1>Страница</h1><p>Текст страницы '
                       f'для проверки.</p>{nav}</main><footer><a href="/about">О нас</a></footer>'
                       "</body></html>"), {"Content-Type": "text/html; charset=utf-8"})


class TestSiteDefaults(unittest.TestCase):
    """--site по умолчанию разбирает карту (без новых запросов), запрашивает llms.txt и ai.txt
    один раз на хост; одиночная страница лишних запросов не делает."""

    def setUp(self):
        self.saved = au.make_fetcher
        au.make_fetcher = lambda *, delay, state_dir: au.http_safe.Fetcher(
            delay=delay, allow_local=True, sleep=lambda s: None, shared_pace=False)

    def tearDown(self):
        au.make_fetcher = self.saved

    def _routes(self, base, *, llms=None, dup=False):
        blog = [f"{base}/blog/"] + [f"{base}/blog/post-{i}" for i in range(6)]
        shop = [f"{base}/shop/item-{i}" for i in range(3)]
        locs = [base + "/"] + blog + shop + ([blog[1]] if dup else [])
        routes = {"/robots.txt": Route(200, f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n",
                                       {"Content-Type": "text/plain"}),
                  "/sitemap.xml": Route(200, _urlset(locs, "2026-11-01"),
                                        {"Content-Type": "application/xml"})}
        for u in dict.fromkeys(locs):
            routes[urlsplit_path(u)] = _site_page(links=["/blog/post-0", "/shop/item-0"])
        if llms is not None:
            routes["/llms.txt"] = llms
        return routes

    def _run(self, srv, *extra, brief=False):
        with tempfile.TemporaryDirectory() as tmp:
            out, html = os.path.join(tmp, "r.json"), os.path.join(tmp, "r.html")
            rc, stdout = run_cli(["--site", srv.base, "--json", out, "--out", html,
                                  "--brief" if brief else "--quiet", *extra])
            self.assertEqual(rc, 0)
            return _read_json(out), _read_text(html), stdout

    @staticmethod
    def site_rows(rep):
        return {r.get("registry_id") or r["id"]: r for g in rep["site"]["groups"]
                for r in g["params"] + g["not_checked"]}

    def test_sitemap_and_ai_files_by_default(self):
        llms = Route(200, "# Пример\n\n> Сайт\n\n## Документы\n- [Блог](https://x/blog/): записи\n",
                     {"Content-Type": "text/plain; charset=utf-8"})
        with LocalServer({}) as srv:
            srv.routes = self._routes(srv.base, llms=llms)
            rep, html, _ = self._run(srv, "--limit", "4")
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(paths.count("/sitemap.xml"), 1, "карту для отчёта не качаем второй раз")
        self.assertEqual(paths.count("/llms.txt"), 1)
        self.assertEqual(paths.count("/ai.txt"), 1)
        self.assertTrue(rep["inputs"]["sitemap"] and rep["inputs"]["ai_files"],
                        "в inputs — что просили, а не что осталось после первой страницы")
        rows = self.site_rows(rep)
        self.assertEqual(rows["access.sitemap_found"]["verdict"], au.OK)
        self.assertEqual(rows["access.sitemap_xml_valid"]["verdict"], au.OK)
        self.assertEqual(rows["ai.llms_txt"]["verdict"], au.INFO)
        self.assertIn("есть", rows["ai.llms_txt"]["observation"])
        self.assertEqual(rows["ai.llms_txt_format"]["verdict"], au.OK)
        self.assertIn("ссылок списком: 1", rows["ai.llms_txt_format"]["observation"])
        self.assertIn("нет", rows["ai.ai_txt"]["observation"])
        self.assertIn("Разделы сайта", html)

    def test_opt_out_flags(self):
        with LocalServer({}) as srv:
            srv.routes = self._routes(srv.base)
            rep, _, _ = self._run(srv, "--limit", "3", "--no-ai-files", "--no-sitemap")
            paths = [r["path"] for r in srv.requests]
        self.assertNotIn("/llms.txt", paths)
        self.assertNotIn("/ai.txt", paths)
        rows = self.site_rows(rep)
        for rid in ("ai.llms_txt", "access.sitemap_found", "access.sitemap_duplicates"):
            self.assertEqual(rows[rid]["verdict"], au.NOTCHECKED, rid)
            self.assertIn("не запрашивали", rows[rid]["reason"])
        self.assertFalse(rep["inputs"]["ai_files"])

    def test_single_page_makes_no_extra_requests(self):
        with LocalServer({}) as srv:
            srv.routes = self._routes(srv.base)
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "r.json")
                rc, _ = run_cli([srv.base + "/blog/", "--json", out, "--quiet"])
                rep = _read_json(out)
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(paths), ["/blog/", "/robots.txt"])
        self.assertFalse(rep["inputs"]["sitemap"] or rep["inputs"]["ai_files"]
                         or rep["inputs"]["host_variants"])
        self.assertIsNone(rep["sample_links"])

    def test_single_page_with_flags_reports_host_rows(self):
        with LocalServer({}) as srv:
            srv.routes = self._routes(srv.base, dup=True)
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "r.json")
                run_cli([srv.base + "/blog/", "--json", out, "--quiet", "--sitemap", "--ai-files"])
                rep = _read_json(out)
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(paths.count("/sitemap.xml"), 1)
        rows = self.site_rows(rep)
        self.assertEqual(rows["access.sitemap_duplicates"]["verdict"], au.WARN)
        self.assertIn("адрес повторяется: 1", rows["access.sitemap_duplicates"]["observation"])
        self.assertEqual(rows["meta.title_duplicate_site"]["verdict"], au.NOTCHECKED,
                         "по одной странице дубли title не «норма», а «не проверяли»")

    def test_child_maps_are_analysed_without_new_requests(self):
        with LocalServer({}) as srv:
            base = srv.base
            routes = {"/robots.txt": Route(200, f"Sitemap: {base}/index.xml\n",
                                           {"Content-Type": "text/plain"}),
                      "/index.xml": Route(200, '<?xml version="1.0"?><sitemapindex xmlns="http://www.'
                                          'sitemaps.org/schemas/sitemap/0.9">'
                                          f"<sitemap><loc>{base}/a.xml</loc></sitemap>"
                                          f"<sitemap><loc>{base}/b.xml</loc></sitemap></sitemapindex>",
                                          {"Content-Type": "application/xml"}),
                      "/a.xml": Route(200, _urlset([f"{base}/a/1", f"{base}/a/2"]),
                                      {"Content-Type": "application/xml"}),
                      "/b.xml": Route(200, _urlset([f"{base}/b/1", "http://other.example/x"]),
                                      {"Content-Type": "application/xml"})}
            for u in ("/", "/a/1", "/a/2", "/b/1"):
                routes[u] = _site_page()
            srv.routes = routes
            rep, _, _ = self._run(srv, "--limit", "4", "--no-ai-files")
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(paths.count("/index.xml"), 1)
        self.assertNotIn("/sitemap.xml", paths, "карта из robots.txt, /sitemap.xml не угадываем")
        rows = self.site_rows(rep)
        self.assertIn("Разобрано 3 карты", rows["access.sitemap_found"]["observation"])
        self.assertEqual(rows["access.sitemap_host"]["verdict"], au.BAD)
        self.assertIn("b.xml", rows["access.sitemap_host"]["evidence"])

    def test_brief_has_sections_links_and_host(self):
        with LocalServer({}) as srv:
            srv.routes = self._routes(srv.base)
            _, _, stdout = self._run(srv, "--limit", "5", brief=True)
        brief = json.loads(stdout)
        self.assertTrue(any(line.startswith("/blog/") for line in brief["site_sections"]))
        self.assertIn("не по всему сайту", brief["sample_links"]["note"])
        self.assertIn("ai.llms_txt", brief["host"])
        self.assertIn("access.sitemap_found", brief["host"])


class TestSoftLlms(unittest.TestCase):
    def test_html_200_is_not_a_file(self):
        with LocalServer({"/llms.txt": Route(200, "<!doctype html><html><body>404</body></html>",
                                             {"Content-Type": "text/html"})}) as srv:
            f = http_safe.Fetcher(delay=0, allow_local=True)
            data = au.adapter_extra_file(srv.base + "/", "llms.txt", fetcher=f)
        self.assertTrue(data["soft_404"])
        row = au.s_llms([{"facts": {"llms_txt": data}}])
        self.assertEqual(row["verdict"], au.INFO)
        self.assertIn("llms.txt нет", row["observation"])
        fmt = au.s_llms_format([{"facts": {"llms_txt": data}}])
        self.assertEqual(fmt["verdict"], au.NODATA)

    def test_outline(self):
        o = au.llms_outline("\n# Проект\n> кратко\n## Docs\n- [A](https://a/x): y\n* [B](/b)\ntext\n")
        self.assertEqual(o["h1"], "Проект")
        self.assertEqual((o["h2"], o["links"]), (1, 2))
        self.assertIsNone(au.llms_outline("Проект\n## Docs\n")["h1"])
        row = au.s_llms_format([{"facts": {"llms_txt": {"status": 200, "outline":
                                                        au.llms_outline("Проект\n")}}}])
        self.assertEqual(row["verdict"], au.WARN)


class TestAiSearchBots(unittest.TestCase):
    """0.2.3 падала NameError (AI_BOTS) и писала «нет данных» на каждой странице."""

    def ctx(self, bots, others=()):
        return au.Facts({"robots": {"matrix": [{"bots": bots, "others_blocked": list(others)}]}},
                        keys=[], options={})

    def test_open_and_closed(self):
        self.assertIn("OAI-SearchBot", au.ai_search_bots())
        opened = au.c_ai_bots(self.ctx({"OAI-SearchBot": True, "Claude-SearchBot": True, "GPTBot": False}))
        self.assertEqual(opened["verdict"], au.OK, "GPTBot — бот обучения, не поиска")
        closed = au.c_ai_bots(self.ctx({"OAI-SearchBot": False, "PerplexityBot": True}))
        self.assertEqual(closed["verdict"], au.INFO)
        self.assertIn("OAI-SearchBot", closed["observation"])
        extra = au.c_ai_bots(self.ctx({}, others=["Claude-SearchBot"]))
        self.assertIn("Claude-SearchBot", extra["observation"])

    def test_row_is_not_broken_in_a_page_audit(self):
        page = au.audit_page(BASIC, fetcher=None, keys=[], options={"base_url": "https://e.ru/", "robots": False})
        row = rows_by_id(page)["ai.search_bots_access"]
        self.assertNotIn("не выполнилась", row["observation"])


class TestSectionsAndSampling(unittest.TestCase):
    def test_one_slot_takes_a_card_two_slots_take_hub_and_card(self):
        bucket = ["https://s.ru/blog/"] + [f"https://s.ru/blog/p{i}" for i in range(9)]
        one = au._pick_in_section(bucket, 1)
        self.assertEqual(len(one), 1)
        self.assertNotEqual(one[0], "https://s.ru/blog/", "при одном месте — карточка, не хаб")
        two = au._pick_in_section(bucket, 2)
        self.assertEqual(two[0], "https://s.ru/blog/")
        self.assertTrue(two[1].startswith("https://s.ru/blog/p"))

    def test_sections_count_urls_and_sample(self):
        urls = (["https://s.ru/"] + [f"https://s.ru/news/{i}" for i in range(30)]
                + [f"https://s.ru/shop/{i}" for i in range(5)] + ["https://s.ru/about"])
        picked = au.sample_site_urls(urls, 5, home="https://s.ru/")
        sec = au.site_sections(urls, picked, source="sitemap", shown=2)
        self.assertEqual(sec["items"][0], {"section": "/news/", "urls": 30,
                                           "picked": sum("/news/" in u for u in picked)})
        self.assertEqual(sec["total"], 4)
        self.assertEqual(sec["rest"]["sections"], 2)
        self.assertEqual(sec["urls"], len(urls))
        self.assertTrue(au.sections_lines(sec)[-1].startswith("ещё 2 разделов"))

    def test_coverage_names_unparsed_child_maps(self):
        rep = {"site_scan": {"source": "sitemap", "sitemap_total": 900, "sitemap_children_total": 11,
                             "sitemap_children_parsed": 5},
               "pages": [{"url": "https://s.ru/"}]}
        text = au._scan_coverage_text(rep)
        self.assertIn("по 5 дочерним картам из 11", text)


class TestSampleLinks(unittest.TestCase):
    """Сводка перелинковки по выборке: шаблон против основного текста. Сирот и глубины нет."""

    def _page(self, url, links):
        return {"target": url, "url": url, "facts": {"links_internal": links}}

    def _pages(self):
        nav = [["https://s.ru/", "nav", False], ["https://s.ru/blog/", "nav", False],
               ["https://s.ru/about", "footer", False]]
        return [self._page("https://s.ru/", nav + [["https://s.ru/blog/p1", "main", False]]),
                self._page("https://s.ru/blog/", nav + [["https://s.ru/blog/p1/", "main", False]]),
                self._page("https://s.ru/blog/p1", nav),
                self._page("https://s.ru/shop/x", nav)]

    def test_summary(self):
        g = au.sample_link_graph(self._pages())
        self.assertEqual(g["pages"], 4)
        self.assertEqual(g["template_targets"]["count"], 3)
        self.assertEqual(g["main_text_targets"], 1, "/blog/p1 и /blog/p1/ — одна цель")
        self.assertEqual(g["contextual_inlinks"], 1)
        self.assertIn("не по всему сайту", g["note"])
        self.assertNotIn("orphans", json.dumps(g))
        self.assertIsNone(au.sample_link_graph(self._pages()[:1]))

    def test_rows_are_observations_on_the_sample(self):
        rep = au.build_report(
            [dict(p, rows=[], status=200, title="t") for p in self._pages()],
            registry=au.load_registry(), keys=[], options={"delay": 2.0}, requests_made=0)
        rows = {r.get("registry_id"): r for g in rep["site"]["groups"]
                for r in g["params"] + g["not_checked"]}
        row = rows["links.incoming_by_region"]
        self.assertEqual(row["verdict"], au.INFO)
        self.assertEqual(row["severity"], "info")
        self.assertEqual(row["sample_scope"], "выборка")
        self.assertIn("(выборка)", row["title"])
        self.assertIn("не по всему сайту", row["observation"])
        for rid in ("links.orphan_pages", "links.click_depth"):
            self.assertEqual(rows[rid]["verdict"], au.NOTCHECKED, "сирот по выборке не выдаём")
        self.assertNotIn("links.incoming_by_region", [i["id"] for i in rep["fix_first"]])
        self.assertIn("Сирот и глубину", au.render_html(rep))


class TestHostVariants(unittest.TestCase):
    def facts(self, http=None, www=None):
        return [{"facts": {"host_variants": {"origin": "https://s.ru", "host": "s.ru",
                                             "http": http or {}, "www": www or {}}}}]

    def test_https_redirect(self):
        ok = au.s_https_redirect(self.facts(http={"url": "http://s.ru/", "status": 301,
                                                   "location": "https://s.ru/"}))
        self.assertEqual(ok["verdict"], au.OK)
        bad = au.s_https_redirect(self.facts(http={"url": "http://s.ru/", "status": 200}))
        self.assertEqual(bad["verdict"], au.BAD)
        tmp = au.s_https_redirect(self.facts(http={"url": "http://s.ru/", "status": 302,
                                                    "location": "https://s.ru/"}))
        self.assertEqual((tmp["verdict"], tmp["severity"]), (au.WARN, "low"))
        down = au.s_https_redirect(self.facts(http={"url": "http://s.ru/", "error": "connection_failed"}))
        self.assertEqual(down["verdict"], au.OK)

    def test_www(self):
        ok = au.s_host_duplicates(self.facts(www={"url": "https://www.s.ru/", "status": 301,
                                                   "location": "https://s.ru/"}))
        self.assertEqual(ok["verdict"], au.OK)
        dup = au.s_host_duplicates(self.facts(www={"url": "https://www.s.ru/", "status": 200}))
        self.assertEqual(dup["verdict"], au.WARN)
        nodns = au.s_host_duplicates(self.facts(www={"url": "https://www.s.ru/", "error": "dns_failed"}))
        self.assertEqual(nodns["verdict"], au.OK)
        self.assertEqual(au.s_host_duplicates([{"facts": {}}])["verdict"], au.NOTCHECKED)

    def test_probe_does_not_follow_redirects(self):
        with LocalServer({"/": Route(301, "", {"Location": "/elsewhere"})}) as srv:
            f = http_safe.Fetcher(delay=0, allow_local=True)
            probe = au._variant_probe(srv.base + "/", f)
            paths = [r["path"] for r in srv.requests]
        self.assertEqual(probe["status"], 301)
        self.assertEqual(probe["location"], srv.base + "/elsewhere")
        self.assertEqual(paths, ["/"], "один запрос, без перехода")

    def test_ip_host_has_no_www_variant(self):
        class F:
            calls = []

            def fetch(self, url, **kw):
                self.calls.append(url)
                raise au.http_safe.SafeHttpError("connection_failed", "x")
        f = F()
        data = au.adapter_host_variants("http://127.0.0.1:8080/", fetcher=f)
        self.assertEqual(f.calls, [])
        self.assertIn("skipped", data["http"])
        self.assertIn("skipped", data["www"])
        data = au.adapter_host_variants("https://s.ru/", fetcher=f)
        self.assertEqual(f.calls, ["http://s.ru/", "https://www.s.ru/"])


class TestCoverageCountsNoData(unittest.TestCase):
    def test_no_data_is_not_checked(self):
        page = audit_file(BASIC)
        rep = au.build_report([page], registry=au.load_registry(), keys=[],
                              options={"delay": 2.0}, requests_made=0)
        cov = rep["coverage"]
        checked = {r["registry_id"] for p in rep["pages"] for g in p["groups"] for r in g["params"]
                   if r["verdict"] not in (au.NODATA, au.NOTCHECKED)}
        self.assertEqual(cov["registry_checked"], len(checked))
        self.assertGreater(cov["registry_no_data_only"], 0)
        self.assertEqual(cov["registry_params"], cov["registry_checked"] + cov["registry_not_checked"])


class TestHelpInRussian(unittest.TestCase):
    def test_help(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit):
                au.main(["--help"])
        text = buf.getvalue()
        self.assertIn("использование:", text)
        self.assertIn("пауза между запросами", text)
        for english in ("pause between", "per-host", "show this help", "usage:", "options:"):
            self.assertNotIn(english, text)
        for flag in ("--no-sitemap", "--no-ai-files", "--no-host-variants"):
            self.assertIn(flag, text)


class TestHyphenKeyInH1(unittest.TestCase):
    def test_key_with_space_matches_hyphenated_h1(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('<html><head><title>Интернет-магазин чая</title></head><body><main>'
                         '<h1>Интернет-магазин чая</h1><p>Интернет-магазин чая с доставкой.</p>'
                         "</main></body></html>")
            page = au.audit_page(path, fetcher=None, keys=["интернет магазин чая"],
                                 options={"base_url": "https://s.ru/", "robots": False})
        rows = rows_by_id(page)
        self.assertEqual(rows["content.key_in_h1"]["verdict"], au.OK)
        self.assertEqual(rows["content.key_in_title"]["verdict"], au.OK)
