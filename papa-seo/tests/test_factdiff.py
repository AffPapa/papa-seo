"""Тесты scripts/factdiff.py. Запуск из папки скила:
python3 -m unittest tests.test_factdiff
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


fd = load("factdiff")


def keys(rep, cat, side):
    return [x["key"] for x in rep["categories"][cat][side]]


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fd.main(argv)
    return rc, json.loads(buf.getvalue())


class TestNumbers(unittest.TestCase):
    def test_formatting_is_not_a_change(self):
        r = fd.compare("Клиентов 5 000, рост 12,5%.", "Клиентов 5000, рост 12.5 %.")
        self.assertEqual(r["summary"]["lost"], 0)
        self.assertEqual(r["summary"]["added"], 0)

    def test_nbsp_thousands(self):
        r = fd.compare("Было 15 000 заявок.", "Было 15000 заявок.")
        self.assertEqual(r["summary"]["lost"], 0)

    def test_lost_and_added(self):
        r = fd.compare("Мы проверили 12 моделей.", "Мы проверили 15 моделей.")
        self.assertEqual(keys(r, "numbers", "lost"), ["12"])
        self.assertEqual(keys(r, "numbers", "added"), ["15"])
        self.assertTrue(any("numbers" in a for a in r["summary"]["attention"]))

    def test_multiplier(self):
        r = fd.compare("Оборот 1,5 млн за год.", "Оборот 1 500 000 за год.")
        self.assertEqual(r["summary"]["lost"], 0)

    def test_percent_changed(self):
        r = fd.compare("Конверсия 12,5%.", "Конверсия 15%.")
        self.assertEqual(keys(r, "percents", "lost"), ["12.5%"])
        self.assertEqual(keys(r, "percents", "added"), ["15%"])

    def test_multiset(self):
        r = fd.compare("10 и 10.", "10.")
        self.assertEqual(r["categories"]["numbers"]["lost"][0]["count"], 1)


class TestMoneyDates(unittest.TestCase):
    def test_money_forms(self):
        r = fd.compare("Тариф 1 990 ₽, годовой $199.", "Тариф 1990 руб., годовой 199 долларов.")
        self.assertEqual(r["categories"]["money"]["lost"], [])
        self.assertEqual(r["categories"]["money"]["kept"], 2)

    def test_currency_change(self):
        r = fd.compare("Стоит 100 €.", "Стоит 100 $.")
        self.assertEqual(keys(r, "money", "lost"), ["100 EUR"])

    def test_date_forms(self):
        r = fd.compare("Старт 12 марта 2026 года, отчёт 01.02.2026.",
                       "Старт 2026-03-12, отчёт 1 февраля 2026.")
        self.assertEqual(r["categories"]["dates"]["lost"], [])
        self.assertEqual(r["categories"]["dates"]["kept"], 2)

    def test_en_dates(self):
        r = fd.compare("Released March 12, 2026.", "Released 12 March 2026.")
        self.assertEqual(r["categories"]["dates"]["lost"], [])

    def test_date_lost(self):
        r = fd.compare("Акция до 31.12.2026.", "Акция идёт.")
        self.assertEqual(keys(r, "dates", "lost"), ["2026-12-31"])


class TestHedges(unittest.TestCase):
    def test_hedge_with_number_lost(self):
        r = fd.compare("Обслуживаем около 5 000 клиентов.", "Обслуживаем 5000 клиентов.")
        self.assertEqual(keys(r, "hedged_numbers", "lost"), ["около 5000"])
        self.assertTrue(any("оговорка" in a for a in r["summary"]["attention"]))

    def test_up_to(self):
        r = fd.compare("Saves up to 30% of time.", "Saves 30% of time.")
        self.assertIn("up to 30", keys(r, "hedged_numbers", "lost"))

    def test_date_is_not_hedge(self):
        r = fd.compare("Отчёт от 01.02.2026 готов.", "Отчёт 01.02.2026 готов.")
        self.assertEqual(r["categories"]["hedged_numbers"]["lost"], [])
        self.assertEqual(r["categories"]["hedges"]["lost"], [])

    def test_word_hedge_lost(self):
        r = fd.compare("Обычно доставка занимает день, если заказ до обеда.", "Доставка занимает день.")
        lost = keys(r, "hedges", "lost")
        self.assertIn("обычно", lost)
        self.assertIn("если", lost)

    def test_negation_change(self):
        r = fd.compare("Доставка не работает по выходным.", "Доставка работает по выходным.")
        self.assertEqual(r["negations"], {"before": 1, "after": 0})
        self.assertTrue(any("отрицан" in a for a in r["summary"]["attention"]))


class TestUrlsNames(unittest.TestCase):
    def test_url_normalized(self):
        r = fd.compare("См. https://example.com/a/.", "См. https://Example.com/a")
        self.assertEqual(r["categories"]["urls"]["lost"], [])

    def test_url_lost(self):
        r = fd.compare("Источник: https://example.com/report", "Источник: отчёт.")
        self.assertEqual(keys(r, "urls", "lost"), ["https://example.com/report"])

    def test_email(self):
        r = fd.compare("Пишите на sales@example.com.", "Пишите нам.")
        self.assertEqual(keys(r, "emails", "lost"), ["sales@example.com"])

    def test_name_case_forms(self):
        r = fd.compare("По данным Яндекса рост есть.", "Рост есть, пишет Яндекс.")
        self.assertEqual(r["categories"]["names"]["lost"], [])

    def test_name_added(self):
        r = fd.compare("Отчёт подготовил Иван Петров.", "Отчёт подготовил Иван Петров, проверил Сергей Иванов.")
        self.assertEqual(keys(r, "names", "added"), [fd.name_key("Сергей Иванов")])

    def test_multiword_name_not_across_sentence(self):
        r = fd.compare("Смотрите Google Search Console. Доставка быстрая.", "Доставка быстрая.")
        self.assertEqual(keys(r, "names", "lost"), ["google search console"])

    def test_sentence_initial_common_words_ignored(self):
        r = fd.compare("Это важно. Мы рады.", "Важно это. Рады мы.")
        self.assertEqual(r["categories"]["names"]["lost"], [])
        self.assertEqual(r["categories"]["names"]["added"], [])

    def test_quoted_name(self):
        r = fd.compare("Компания «Ромашка» работает.", "Компания работает.")
        self.assertIn(fd.name_key("Ромашка"), keys(r, "names", "lost"))

    def test_acronym_at_sentence_start(self):
        r = fd.compare("SEO важно для сайта.", "Важно для сайта.")
        self.assertIn("seo", keys(r, "names", "lost"))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = os.path.join(self.tmp.name, "a.md")
        self.b = os.path.join(self.tmp.name, "b.md")
        with open(self.a, "w", encoding="utf-8") as fh:
            fh.write("Цена 100 ₽.")
        with open(self.b, "w", encoding="utf-8") as fh:
            fh.write("Цена 120 ₽.")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stdout(self):
        rc, data = run_cli([self.a, self.b])
        self.assertEqual(rc, 0)
        self.assertEqual(data["summary"]["lost"], 1)
        self.assertEqual((data["before"], data["after"]), ("a.md", "b.md"))

    def test_out(self):
        out = os.path.join(self.tmp.name, "d.json")
        rc, data = run_cli([self.a, self.b, "--out", out])
        self.assertEqual(rc, 0)
        self.assertEqual(data["out"], out)
        self.assertTrue(os.path.isfile(out))

    def test_refusals(self):
        self.assertEqual(run_cli([self.a, self.b, "--out", "../../x"])[0], 2)
        self.assertEqual(run_cli([self.a, os.path.join(self.tmp.name, "none.md")])[0], 2)


class TestSafety(unittest.TestCase):
    def test_no_dangerous_calls(self):
        with open(os.path.join(SCRIPTS, "factdiff.py"), encoding="utf-8") as fh:
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
