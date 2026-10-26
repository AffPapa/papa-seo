# Adapted from seo-skills/seo-audit-skill@fac4b75 (MIT, © 2024-present SEOmator). Changes: RFC 9309 matcher
# cases from src/crawler/robots.test.ts rewritten for Python unittest; Yandex, roster, status and ReDoS cases are ours.
"""robots_check: RFC 9309 matching, Yandex semantics, status handling, roster loading."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
import unittest

import _localserver as ls
from _localserver import LocalServer, Route

import http_safe
import robots_check as rc

FIX = ls.FIXTURES
BOT = {"name": "SEOmator", "ignores_star": False, "obeys_robots": True}


def allowed(text, url, bot=None):
    return rc.Robots(rc.parse_robots(text)).check(bot or BOT, url)["allowed"]


def U(path):
    return "https://example.com" + path


def run_cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = rc.main(argv)
    return code, json.loads(buf.getvalue())


class Rfc9309Test(unittest.TestCase):
    def test_empty_allows_everything(self):
        self.assertTrue(allowed("", U("/anything")))

    def test_disallowed_prefix(self):
        txt = "User-agent: *\nDisallow: /blocked\n"
        self.assertFalse(allowed(txt, U("/blocked")))
        self.assertFalse(allowed(txt, U("/blocked/deeper")))
        self.assertTrue(allowed(txt, U("/public")))

    def test_empty_disallow(self):
        self.assertTrue(allowed("User-agent: *\nDisallow:\n", U("/anything")))

    def test_longest_match(self):
        txt = "User-agent: *\nDisallow: /admin\nAllow: /admin/public\n"
        self.assertFalse(allowed(txt, U("/admin/secret")))
        self.assertTrue(allowed(txt, U("/admin/public/page")))

    def test_equal_length_allow_wins(self):
        self.assertTrue(allowed("User-agent: *\nDisallow: /x\nAllow: /x\n", U("/x")))

    def test_wildcard(self):
        txt = "User-agent: *\nDisallow: /*.pdf\n"
        self.assertFalse(allowed(txt, U("/files/report.pdf")))
        self.assertTrue(allowed(txt, U("/files/report.html")))

    def test_end_anchor(self):
        txt = "User-agent: *\nDisallow: /page$\n"
        self.assertFalse(allowed(txt, U("/page")))
        self.assertTrue(allowed(txt, U("/page/child")))

    def test_query_string(self):
        txt = "User-agent: *\nDisallow: /*?session=\n"
        self.assertFalse(allowed(txt, U("/p?session=abc")))
        self.assertTrue(allowed(txt, U("/p?page=2")))

    def test_literal_punctuation(self):
        txt = "User-agent: *\nDisallow: /a+b(c)\n"
        self.assertFalse(allowed(txt, U("/a+b(c)")))
        self.assertTrue(allowed(txt, U("/aaab")))

    def test_named_group_over_star(self):
        txt = "User-agent: *\nDisallow: /\n\nUser-agent: SEOmator\nDisallow: /private\n"
        self.assertTrue(allowed(txt, U("/public")))
        self.assertFalse(allowed(txt, U("/private")))

    def test_fallback_to_star(self):
        txt = "User-agent: Googlebot\nDisallow:\n\nUser-agent: *\nDisallow: /nope\n"
        self.assertFalse(allowed(txt, U("/nope")))

    def test_comments_blank_lines(self):
        txt = "# a comment\n\nUser-agent: *   # trailing\nDisallow: /x  # here\n"
        self.assertFalse(allowed(txt, U("/x")))

    def test_case_insensitive(self):
        self.assertFalse(allowed("USER-AGENT: seomator\nDISALLOW: /nope\n", U("/nope")))

    def test_shared_group(self):
        self.assertFalse(allowed("User-agent: bingbot\nUser-agent: seomator\nDisallow: /shared\n", U("/shared")))

    def test_malformed_url_allowed(self):
        self.assertTrue(allowed("User-agent: *\nDisallow: /\n", "not a url"))

    def test_groups_for_same_agent_merge(self):
        txt = "User-agent: seomator\nDisallow: /a\n\nUser-agent: other\nDisallow: /\n\nUser-agent: seomator\nDisallow: /b\n"
        self.assertFalse(allowed(txt, U("/a")))
        self.assertFalse(allowed(txt, U("/b")))
        self.assertTrue(allowed(txt, U("/c")))

    def test_robots_txt_always_allowed(self):
        self.assertTrue(allowed("User-agent: *\nDisallow: /\n", U("/robots.txt")))

    def test_percent_encoding_normalised(self):
        txt = "User-agent: *\nDisallow: /каталог/\n"
        self.assertFalse(allowed(txt, U("/%D0%BA%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3/x")))
        self.assertFalse(allowed("User-agent: *\nDisallow: /%7Euser\n", U("/~user/page")))

    def test_ua_with_version(self):
        self.assertFalse(allowed("User-agent: SEOmator/2.1\nDisallow: /\n", U("/x")))

    def test_rule_outside_group_and_typos(self):
        parsed = rc.parse_robots("Disallow: /x\nUser-agent: *\nDissallow: /typo\nfoo bar\n")
        codes = [w["code"] for w in parsed["warnings"]]
        self.assertIn("rule_outside_group", codes)
        self.assertIn("typo_directive", codes)
        self.assertIn("not_a_directive", codes)
        self.assertFalse(rc.Robots(parsed).check(BOT, "/typo/a")["allowed"])

    def test_500kib_limit(self):
        filler = "# " + "x" * 1000 + "\n"
        text = "User-agent: *\n" + filler * 520 + "Disallow: /late\n"
        parsed = rc.parse_robots(text)
        self.assertTrue(parsed["truncated"])
        self.assertTrue(rc.Robots(parsed).check(BOT, "/late")["allowed"])

    def test_no_redos(self):
        txt = "User-agent: *\nDisallow: /" + "*a" * 60 + "b\n"
        start = time.monotonic()
        self.assertTrue(allowed(txt, U("/" + "a" * 3000)))
        self.assertLess(time.monotonic() - start, 2.0)

    def test_wildcard_match_unit(self):
        self.assertTrue(rc.wildcard_match("/a*c$", "/abbbc"))
        self.assertFalse(rc.wildcard_match("/a*c$", "/abbbcd"))
        self.assertTrue(rc.wildcard_match("/a*c", "/abbbcd"))
        self.assertTrue(rc.wildcard_match("*", "/anything"))
        self.assertTrue(rc.wildcard_match("/$", "/"))
        self.assertFalse(rc.wildcard_match("/$", "/x"))


class YandexTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(FIX, "robots_yandex.txt"), encoding="utf-8") as fh:
            self.parsed = rc.parse_robots(fh.read())
        self.robots = rc.Robots(self.parsed)
        self.roster = {b["name"]: b for b in rc._normalize_roster(rc.BUILTIN_ROSTER)}

    def check(self, bot, url):
        return self.robots.check(self.roster[bot], url)

    def test_additional_not_under_star(self):
        r = rc.Robots(rc.parse_robots("User-agent: *\nDisallow: /\n"))
        for name in ("YandexAdditional", "YandexAdditionalBot"):
            row = r.check(self.roster[name], "/page")
            self.assertTrue(row["allowed"], name)
            self.assertEqual(row["via"], "none")
        self.assertFalse(r.check(self.roster["YandexBot"], "/page")["allowed"])
        self.assertFalse(r.check(self.roster["GPTBot"], "/page")["allowed"])

    def test_additional_explicit_group(self):
        r = rc.Robots(rc.parse_robots("User-agent: YandexAdditional\nDisallow: /\n"))
        self.assertFalse(r.check(self.roster["YandexAdditional"], "/page")["allowed"])

    def test_additional_not_covered_by_yandex_group(self):
        row = self.check("YandexAdditional", "/private/x")
        self.assertTrue(row["allowed"])
        self.assertTrue(any("Yandex" in n for n in row["notes"]))

    def test_yandex_group_replaces_star(self):
        row = self.check("YandexBot", "/admin/x")
        self.assertTrue(row["allowed"], "Yandex group exists, so * rules do not apply to YandexBot")
        self.assertEqual(row["via"], "yandex_family")
        self.assertFalse(self.check("YandexBot", "/private/a")["allowed"])
        self.assertFalse(self.check("Googlebot", "/admin/x")["allowed"])

    def test_host_and_crawl_delay_ignored(self):
        self.assertTrue(self.parsed["host"][0]["ignored"])
        self.assertEqual(self.parsed["host"][0]["value"], "https://example.ru")
        self.assertTrue(self.parsed["crawl_delay"][0]["ignored"])
        self.assertIn("note", self.parsed["crawl_delay"][0])

    def test_clean_param(self):
        cps = self.parsed["clean_params"]
        self.assertEqual(cps[0]["params"], ["utm_source", "utm_medium", "utm_campaign"])
        self.assertEqual(cps[0]["path"], "/catalog/")
        self.assertIsNone(cps[1]["path"])
        eff = rc.clean_param_effect(self.parsed, "https://example.ru/catalog/a?utm_source=x&id=1&sid=5")
        self.assertEqual(eff["dropped_params"], ["sid", "utm_source"])
        self.assertEqual(eff["yandex_canonical_like"], "https://example.ru/catalog/a?id=1")
        self.assertIsNone(rc.clean_param_effect(self.parsed, "https://example.ru/news/?utm_source=x"))

    def test_clean_param_invalid(self):
        parsed = rc.parse_robots("Clean-param: bad$name /x\n")
        self.assertFalse(parsed["clean_params"][0]["valid"])

    def test_sitemaps(self):
        self.assertEqual([s["absolute"] for s in self.parsed["sitemaps"]], [True, False])

    def test_google_extended_follows_star_and_applebot_fallback(self):
        r = rc.Robots(rc.parse_robots("User-agent: *\nDisallow: /x\n\nUser-agent: Googlebot\nDisallow: /g\n"))
        self.assertFalse(r.check(self.roster["Google-Extended"], "/x")["allowed"])
        apple = r.check(self.roster["Applebot"], "/g")
        self.assertFalse(apple["allowed"])
        self.assertEqual(apple["via"], "fallback_googlebot")


class StatusAndInjectionTest(unittest.TestCase):
    def test_status_semantics_file_mode(self):
        path = os.path.join(FIX, "robots_yandex.txt")
        for status, expect in ((404, True), (410, True), (503, False), (500, False), (429, False)):
            code, data = run_cli([path, "--status", str(status), "--bots", "Googlebot", "--url", "/admin", "--full"])
            self.assertEqual(code, 0)
            self.assertEqual(data["access"][0]["allowed"], expect, status)

    def test_comment_instructions_flagged_not_obeyed(self):
        code, data = run_cli([os.path.join(FIX, "robots_injection.txt"), "--bots", "Googlebot", "--url", "/secret", "--full"])
        self.assertEqual(code, 0)
        self.assertEqual(len(data["hidden_instructions"]), 2)
        self.assertFalse(data["access"][0]["allowed"])
        self.assertIn("noindex_in_robots", [w["code"] for w in data["warnings"]])

    def test_fetch_robots_live_statuses(self):
        routes = {"/robots.txt": Route(200, "User-agent: *\nDisallow: /a\n")}
        with LocalServer(routes) as srv:
            f = http_safe.Fetcher(delay=0, allow_local=True)
            robots, meta = rc.fetch_robots(srv.base + "/some/page", f, allow_local=True)
            self.assertEqual(robots.state, "parsed")
            self.assertFalse(robots.check(BOT, "/a/b")["allowed"])
            srv.routes["/robots.txt"] = Route(404, "")
            robots, _ = rc.fetch_robots(srv.base + "/", f, allow_local=True)
            self.assertEqual(robots.state, "unavailable")
            self.assertTrue(robots.check(BOT, "/a")["allowed"])
            srv.routes["/robots.txt"] = Route(503, "")
            robots, _ = rc.fetch_robots(srv.base + "/", f, allow_local=True)
            self.assertEqual(robots.state, "unreachable")
            self.assertFalse(robots.check(BOT, "/x")["allowed"])
            srv.routes["/robots.txt"] = Route(302, "", {"Location": "http://169.254.169.254/robots.txt"})
            with self.assertRaises(http_safe.SafeHttpError):
                rc.fetch_robots(srv.base + "/", f, allow_local=True)

    def test_cli_refuses_private_url(self):
        code, data = run_cli(["http://127.0.0.1:9/"])
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "blocked_address")

    def test_cli_out_traversal(self):
        code, data = run_cli([os.path.join(FIX, "robots_yandex.txt"), "--out", "../../x"])
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "bad_out_path")


class CompactReportTest(unittest.TestCase):
    TEXT = ("User-agent: *\nDisallow: /admin\n\nUser-agent: Bytespider\nDisallow: /\n\n"
            "User-agent: anthropic-ai\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /tmp\n\n"
            "User-agent: GPTBot\nDisallow: /x\n\nClean-param: utm_source&utm_medium\n")

    def write(self, d):
        p = os.path.join(d, "robots.txt")
        with open(p, "w") as fh:
            fh.write(self.TEXT)
        return p

    def test_default_is_compact(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run_cli([self.write(d), "--url", "/admin/a", "--url", "/news?utm_source=x&sort=new&ref=tg"])
        self.assertEqual(code, 0)
        self.assertNotIn("access", data)
        self.assertNotIn("roster", data)
        row = data["matrix"][0]
        self.assertFalse(row["bots"]["Googlebot"])
        self.assertTrue(row["bots"]["YandexAdditional"])
        self.assertEqual(set(data["unknown_vendor_agents"]), {"Bytespider", "anthropic-ai"})
        self.assertFalse(data["matrix"][1]["bots"]["Bytespider"])
        self.assertLess(len(json.dumps(data)), 20000)

    def test_full_keeps_rows(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run_cli([self.write(d), "--url", "/admin/a", "--full"])
        self.assertIn("access", data)
        self.assertTrue(any(r["bot"] == "anthropic-ai" for r in data["access"]))

    def test_identical_and_repeated_groups(self):
        parsed = rc.parse_robots(self.TEXT)
        ov = rc.group_overlaps(parsed)
        self.assertEqual(len(ov["identical_groups"]), 1)
        self.assertEqual(set(ov["identical_groups"][0]["agents"]), {"Bytespider", "anthropic-ai"})
        self.assertEqual(ov["agent_in_multiple_groups"][0]["agent"], "gptbot")

    def test_param_hints(self):
        with tempfile.TemporaryDirectory() as d:
            hints = os.path.join(d, "params.txt")
            with open(hints, "w") as fh:
                fh.write("sort\nref\nutm_medium\n=bad(\n")
            code, data = run_cli([self.write(d), "--param-hints", hints, "--url", "/news?page=2"])
        cov = data["clean_param_coverage"]
        self.assertEqual(cov["missing"], ["page", "ref", "sort"])
        self.assertEqual(cov["covered"], ["utm_medium"])
        self.assertIn("Нет Clean-param", cov["note"])
        code, data = run_cli([os.path.join(FIX, "robots_yandex.txt"), "--param-hints", "utm_source,sid"])
        self.assertEqual(data["clean_param_coverage"]["missing"], [])

    def test_bots_filter_does_not_make_known_bots_unknown(self):
        code, data = run_cli([os.path.join(FIX, "robots_yandex.txt"), "--bots", "Googlebot"])
        self.assertEqual(data["unknown_vendor_agents"], [])


class RosterTest(unittest.TestCase):
    def test_builtin_contents(self):
        names = {b["name"] for b in rc._normalize_roster(rc.BUILTIN_ROSTER)}
        for n in ("Googlebot", "Bingbot", "YandexBot", "YandexAdditional", "YandexAdditionalBot", "GPTBot",
                  "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "PerplexityBot",
                  "Perplexity-User", "Google-Extended", "Applebot", "Applebot-Extended"):
            self.assertIn(n, names)
        ge = [b for b in rc.BUILTIN_ROSTER if b["name"] == "Google-Extended"][0]
        self.assertTrue(ge["token_only"])
        self.assertNotIn("ua", ge)

    def test_missing_roster_falls_back(self):
        roster, source, warnings = rc.load_roster(os.path.join(FIX, "nope.yaml"))
        self.assertEqual(source, "builtin")
        self.assertTrue(warnings)

    def test_yaml_subset(self):
        roster, source, warnings = rc.load_roster(os.path.join(FIX, "ai-bots-sample.yaml"))
        self.assertEqual(source, "ai-bots-sample.yaml")
        by = {b["name"]: b for b in roster}
        self.assertEqual(set(by), {"GPTBot", "YandexAdditional", "Claude-User"}, "not_included must be skipped")
        self.assertEqual(by["GPTBot"]["doc"], "https://platform.openai.com/docs/bots")
        self.assertTrue(by["YandexAdditional"]["ignores_star"])
        self.assertIsNone(by["Claude-User"]["doc"])

    def test_yaml_grouped_sections(self):
        roster, _, _ = rc.load_roster(os.path.join(FIX, "ai-bots-grouped.yaml"))
        self.assertEqual({b["name"]: b["group"] for b in roster}, {"OAI-SearchBot": "search", "ClaudeBot": "training"})

    def test_json_roster_with_tokens(self):
        data = {"bots": [{"name": "YandexAdditional", "tokens": ["YandexAdditional", "YandexAdditionalBot"],
                          "respects_star": False, "group": "search_ai"},
                         {"name": "Google user-triggered fetchers", "tokens": ["Google-Agent"],
                          "obeys_robots": False, "respects_star": None}]}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bots.json")
            with open(p, "w") as fh:
                json.dump(data, fh)
            roster, source, _ = rc.load_roster(p)
        by = {b["name"]: b for b in roster}
        self.assertTrue(by["YandexAdditionalBot"]["ignores_star"])
        self.assertEqual(by["Google-Agent"]["record"], "Google user-triggered fetchers")
        row = rc.Robots(rc.parse_robots("User-agent: *\nDisallow: /\n")).check(by["Google-Agent"], "/x")
        self.assertTrue(any("не соблюдает" in n for n in row["notes"]))

    def test_broken_yaml_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.yaml")
            with open(p, "w") as fh:
                fh.write("bots:\n  - name: A\n      bad: indent\n\tx: 1\n")
            roster, source, warnings = rc.load_roster(p)
        self.assertEqual(source, "builtin")
        self.assertTrue(warnings)

    def test_reference_roster_yaml_matches_json(self):
        y = os.path.join(rc.REFERENCES_DIR, "ai-bots.yaml")
        j = os.path.join(rc.REFERENCES_DIR, "ai-bots.json")
        if not (os.path.isfile(y) and os.path.isfile(j)):
            self.skipTest("reference roster not present")
        ry, sy, _ = rc.load_roster(y)
        rj, sj, _ = rc.load_roster(j)
        self.assertEqual(sy, "ai-bots.yaml")
        self.assertEqual([b["name"] for b in ry], [b["name"] for b in rj])
        names = {b["name"] for b in ry}
        self.assertIn("YandexAdditional", names)

    def test_reference_roster_user_agents(self):
        y = os.path.join(rc.REFERENCES_DIR, "ai-bots.yaml")
        j = os.path.join(rc.REFERENCES_DIR, "ai-bots.json")
        if not (os.path.isfile(y) and os.path.isfile(j)):
            self.skipTest("reference roster not present")
        ry, _, _ = rc.load_roster(y)
        rj, _, _ = rc.load_roster(j)
        uy = {b["name"]: (b.get("ua"), b.get("ua_checked")) for b in ry}
        uj = {b["name"]: (b.get("ua"), b.get("ua_checked")) for b in rj}
        self.assertEqual(uy, uj, "ua in ai-bots.yaml and ai-bots.json must match")
        with_ua = {n: v for n, v in uy.items() if v[0]}
        for must in ("Googlebot", "bingbot", "YandexBot", "GPTBot", "OAI-SearchBot", "ChatGPT-User",
                     "PerplexityBot", "Perplexity-User", "Applebot"):
            self.assertIn(must, with_ua)
        for name, (ua, checked) in with_ua.items():
            self.assertIn(name.lower(), ua.lower(), "UA must carry its own token")
            self.assertRegex(checked or "", r"^\d{4}-\d{2}-\d{2}$")
            builtin = http_safe.BOT_USER_AGENTS.get(name.lower())
            if builtin:
                self.assertEqual(builtin, ua, f"built-in UA for {name} drifted from the roster")
        # ua belongs to the first token of a record only
        self.assertNotIn("Googlebot-Image", with_ua)
        self.assertNotIn("Yandex", with_ua)
        # vendors that publish no full string / bots that send no requests carry no ua
        for name in ("ClaudeBot", "Claude-User", "Claude-SearchBot", "YandexAdditional", "Google-Extended"):
            self.assertNotIn(name, with_ua)


if __name__ == "__main__":
    unittest.main()
