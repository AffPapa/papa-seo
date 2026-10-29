"""Тесты scripts/ru_text.py — согласование русских числительных. Запуск из папки скила:
python3 -m unittest tests.test_ru_text
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Скрипты тянут ru_text обычным import по своему sys.path, поэтому и здесь берём его так же:
# иначе в тесте окажется второй экземпляр модуля и сравнение по is ничего не докажет.
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import ru_text as ru  # noqa: E402

FORMS = ("картинка", "картинки", "картинок")


class PluralTest(unittest.TestCase):
    def test_forms_by_number(self):
        expected = {
            0: "картинок", 1: "картинка", 2: "картинки", 4: "картинки", 5: "картинок",
            11: "картинок", 21: "картинка", 111: "картинок",
        }
        for n, form in expected.items():
            with self.subTest(n=n):
                self.assertEqual(ru.plural(n, *FORMS), form)

    def test_teens_are_not_units(self):
        # 11–14 ломают наивное «по последней цифре»: 11 ≠ 1, 12 ≠ 2.
        for n in (11, 12, 13, 14, 111, 112, 1013):
            with self.subTest(n=n):
                self.assertEqual(ru.plural(n, *FORMS), "картинок")

    def test_negative_counts_read_as_positive(self):
        self.assertEqual(ru.plural(-1, *FORMS), "картинка")
        self.assertEqual(ru.plural(-3, *FORMS), "картинки")

    def test_fraction_takes_the_few_form(self):
        # При дробном числе существительное стоит в родительном единственного:
        # «12.4 слова», а не «12.4 слов».
        self.assertEqual(ru.plural(12.4, "слово", "слова", "слов"), "слова")
        self.assertEqual(ru.plural(1.0, "слово", "слова", "слов"), "слова")
        self.assertEqual(ru.plural(21.5, "слово", "слова", "слов"), "слова")

    def test_num_glues_number_and_form(self):
        self.assertEqual(ru.num(1, *FORMS), "1 картинка")
        self.assertEqual(ru.num(2, *FORMS), "2 картинки")
        self.assertEqual(ru.num(5, *FORMS), "5 картинок")
        self.assertEqual(ru.num(0, *FORMS), "0 картинок")
        self.assertEqual(ru.num(12.4, "слово", "слова", "слов"), "12.4 слова")


class AuditWrapperTest(unittest.TestCase):
    """audit.py держит _plural как имя: на него ссылаются его собственные тесты."""

    def test_audit_reexports_the_same_function(self):
        au = load("audit")
        self.assertIs(au._plural, ru.plural)
        self.assertIs(au._qty, ru.num)
        self.assertEqual(au._plural(1, "проблема", "проблемы", "проблем"), "проблема")
        self.assertEqual(au._plural(21, "проблема", "проблемы", "проблем"), "проблема")

    def test_every_script_with_russian_counters_shares_the_module(self):
        for name in ("page_facts", "text_metrics", "schema_check", "audit", "robots_check",
                     "sitemap_check", "link_graph", "deai_scan"):
            with self.subTest(script=name):
                mod = load(name)
                self.assertIs(mod._plural, ru.plural)
                self.assertIs(mod._qty, ru.num)


if __name__ == "__main__":
    unittest.main()
