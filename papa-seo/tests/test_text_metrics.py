"""Тесты scripts/text_metrics.py. Запуск из папки скила:
python3 -m unittest tests.test_text_metrics
"""
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tm = load("text_metrics")


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = tm.main(argv)
    return rc, json.loads(buf.getvalue())


class TestCounts(unittest.TestCase):
    def test_ru_counts(self):
        r = tm.analyze("Мама мыла раму. Папа читал книгу.")
        self.assertEqual(r["lang"], "ru")
        self.assertEqual(r["counts"]["words"], 6)
        self.assertEqual(r["counts"]["sentences_prose"], 2)
        self.assertEqual(r["counts"]["chars_no_spaces"], len("Мамамылараму.Папачиталкнигу."))
        self.assertEqual(r["status"], "оценка")

    def test_en_detected(self):
        r = tm.analyze("The cat sat on the mat. Dogs were running outside.")
        self.assertEqual(r["lang"], "en")
        self.assertEqual(r["counts"]["sentences_prose"], 2)

    def test_abbreviations_do_not_split(self):
        r = tm.analyze("Выбор большой, т. е. есть из чего выбрать. Второе предложение тут.")
        self.assertEqual(r["counts"]["sentences_prose"], 2)
        r2 = tm.analyze("Цена 5 тыс. руб. за штуку. Дальше текст.")
        self.assertEqual(r2["counts"]["sentences_prose"], 2)

    def test_numbers_are_not_words(self):
        r = tm.analyze("В 2026 году было 12 моделей.")
        self.assertEqual(r["counts"]["words"], 4)
        self.assertEqual(r["counts"]["numbers"], 2)

    def test_code_comments_urls_masked(self):
        text = ("Текст до кода.\n\n```\nслово слово слово\n```\n\n"
                "<!-- скрытый комментарий -->\nСсылка https://example.com/page и `код`.")
        r = tm.analyze(text)
        self.assertEqual(r["masked"]["code_blocks"], 1)
        self.assertEqual(r["masked"]["html_comments"], 1)
        self.assertEqual(r["masked"]["urls"], 1)
        self.assertEqual(r["masked"]["inline_code"], 1)
        self.assertNotIn("слов", [s["stem"] for s in r["stems_top"]])

    def test_html_input(self):
        html = ("<html><head><title>Заголовок вкладки</title><script>var x = 'скрипт';</script>"
                "</head><body><p>Привет, мир.</p><!-- c --><p>Ещё абзац.</p></body></html>")
        r = tm.analyze(html, is_html=True)
        self.assertEqual(r["counts"]["words"], 4)
        self.assertEqual(r["counts"]["paragraphs_prose"], 2)
        self.assertEqual(r["masked"]["html_comments"], 1)

    def test_markdown_structure(self):
        text = "# Заголовок\n\nАбзац один.\n\n- пункт один\n- пункт два\n\n| a | b |\n|---|---|\n| в | г |"
        r = tm.analyze(text)
        self.assertEqual(r["counts"]["headings"], 1)
        self.assertEqual(r["counts"]["list_items"], 2)
        self.assertEqual(r["counts"]["sentences_prose"], 1)


class TestStemsAndKeys(unittest.TestCase):
    def test_ru_stemmer_merges_forms(self):
        self.assertEqual(tm.stem("кошка"), tm.stem("кошкой"))
        self.assertEqual(tm.stem("кошка"), tm.stem("кошки"))
        self.assertEqual(tm.stem("диван"), tm.stem("диванами"))
        self.assertEqual(tm.stem("купить"), tm.stem("купили"))
        self.assertEqual(tm.stem("ёлка"), tm.stem("елки"))

    def test_en_stemmer(self):
        self.assertEqual(tm.stem("studies"), tm.stem("study"))
        self.assertEqual(tm.stem("running"), "run")
        self.assertEqual(tm.stem("class"), "class")

    def test_key_by_stems_with_morphology(self):
        r = tm.analyze("Купить диван можно здесь. Мы купили диваны вчера.", keys=["купить диван"])
        k = r["keys"][0]
        self.assertEqual(k["exact_by_stems"], 2)
        self.assertGreater(k["density_pct"], 0)

    def test_key_does_not_cross_sentences(self):
        r = tm.analyze("Я люблю диван. Угловой стол стоит рядом.", keys=["диван угловой"])
        self.assertEqual(r["keys"][0]["exact_by_stems"], 0)
        self.assertEqual(r["keys"][0]["any_order_window"], 0)

    def test_key_any_order(self):
        r = tm.analyze("Угловой диван стоит в зале.", keys=["диван угловой"])
        self.assertEqual(r["keys"][0]["exact_by_stems"], 0)
        self.assertEqual(r["keys"][0]["any_order_window"], 1)

    def test_key_with_stopword(self):
        r = tm.analyze("Где купить диван в Москве недорого.", keys=["диван в москве"])
        self.assertEqual(r["keys"][0]["exact_by_stems"], 1)

    def test_parse_keys(self):
        self.assertEqual(tm.parse_keys(["a; b", "c"]), ["a", "b", "c"])


class TestEstimates(unittest.TestCase):
    def test_nausea_classic(self):
        r = tm.analyze(" ".join(["окно"] * 9) + ".")
        self.assertEqual(r["nausea"]["classic"], 3.0)
        self.assertEqual(r["nausea"]["top_stem"], tm.stem("окно"))

    def test_water_bounds(self):
        r = tm.analyze("И вот он, и она, и они тоже здесь, но окно открыто.")
        self.assertGreater(r["water"]["stopword_pct"], 50)
        self.assertLessEqual(r["water"]["stopword_pct"], 100)

    def test_empty_text(self):
        r = tm.analyze("")
        self.assertEqual(r["counts"]["words"], 0)
        self.assertEqual(r["water"]["stopword_pct"], 0)

    def test_similar_runs(self):
        self.assertEqual(len(tm.similar_runs([6, 6, 7, 6])), 1)
        self.assertEqual(tm.similar_runs([3, 12, 5, 20]), [])
        self.assertEqual(tm.similar_runs([2, 2, 2]), [])  # короткие не считаем

    def test_cv_reported(self):
        r = tm.analyze("Одно короткое. А это предложение заметно длиннее предыдущего и тянется дальше.")
        self.assertIsNotNone(r["rhythm"]["sentence_words"]["cv"])


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "a.md")
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write("Текст для проверки. Ещё одно предложение.")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stdout_json(self):
        rc, data = run_cli([self.src, "--keys", "текст"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["tool"], "text_metrics")
        self.assertEqual(data["input"], "a.md")

    def test_out_file(self):
        out = os.path.join(self.tmp.name, "r.json")
        rc, data = run_cli([self.src, "--out", out])
        self.assertEqual(rc, 0)
        self.assertEqual(data["out"], out)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["tool"], "text_metrics")

    def test_out_traversal_without_json_refused(self):
        rc, data = run_cli([self.src, "--out", "../../x"])
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])

    def test_out_symlink_refused(self):
        target = os.path.join(self.tmp.name, "target.json")
        link = os.path.join(self.tmp.name, "link.json")
        open(target, "w").close()
        os.symlink(target, link)
        rc, _ = run_cli([self.src, "--out", link])
        self.assertEqual(rc, 2)

    def test_out_missing_dir_refused(self):
        rc, _ = run_cli([self.src, "--out", os.path.join(self.tmp.name, "no", "r.json")])
        self.assertEqual(rc, 2)

    def test_missing_input(self):
        rc, data = run_cli([os.path.join(self.tmp.name, "nope.md")])
        self.assertEqual(rc, 2)
        self.assertIn("error", data)

    def test_binary_refused(self):
        b = os.path.join(self.tmp.name, "b.bin")
        with open(b, "wb") as fh:
            fh.write(b"\x00\x01\x02text")
        rc, _ = run_cli([b])
        self.assertEqual(rc, 2)


class TestSafety(unittest.TestCase):
    def test_no_dangerous_calls(self):
        with open(os.path.join(SCRIPTS, "text_metrics.py"), encoding="utf-8") as fh:
            src = fh.read()
        bad = [
            r"^\s*(?:import|from)\s+(?:subprocess|socket|urllib|requests|http\.client|ctypes|pickle)\b",
            r"(?<![\w.])(?:eval|exec|compile|__import__)\(",
            r"os\.(?:system|popen|exec\w*|spawn\w*|environ|getenv)",
            r"expanduser|Path\.home",
        ]
        for rx in bad:
            self.assertIsNone(re.search(rx, src, re.M), rx)


if __name__ == "__main__":
    unittest.main()
