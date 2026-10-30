"""Doc-consistency guards. Запуск из папки скила:
python3 -m unittest tests.test_docs

Проверяет, что длина description во frontmatter SKILL.md совпадает с числом,
на которое ссылаются README (ветка claude.ai: «в пакете она N»). Число в прозе
дрейфует при каждом изменении description — этот тест ловит дрейф.

READMEs лежат в корне пакета, на уровень выше папки скила. В установленной копии
(одна папка papa-seo/) их нет, поэтому проверка мягко пропускается — набор тестов
установленного скила остаётся зелёным.
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)           # .../papa-seo
PACK_ROOT = os.path.dirname(SKILL_DIR)      # корень пакета (= корень репозитория)


def skill_description_length():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    lines = open(path, encoding="utf-8").read().split("\n")
    assert lines[0].strip() == "---", "SKILL.md без frontmatter"
    end = lines.index("---", 1)
    for line in lines[1:end]:
        if line.startswith("description:"):
            val = line[len("description:"):].strip()
            if val[:1] in "\"'" and val[-1:] in "\"'":
                val = val[1:-1]
            return len(val)
    raise AssertionError("в SKILL.md нет поля description")


class DescriptionLengthInReadme(unittest.TestCase):
    def setUp(self):
        self.n = skill_description_length()

    def _read(self, name):
        path = os.path.join(PACK_ROOT, name)
        if not os.path.isfile(path):
            self.skipTest(name + " нет (установленная копия скила) — пропуск")
        return open(path, encoding="utf-8").read()

    def test_ru_readme_cites_actual_length(self):
        text = self._read("README.md")
        phrase = "в пакете она %d" % self.n
        self.assertIn(
            phrase, text,
            "README.md ссылается не на %d символов; обнови фразу «в пакете она %d»."
            % (self.n, self.n))

    def test_en_readme_cites_actual_length(self):
        text = self._read("README.en.md")
        phrase = "the pack's is %d" % self.n
        self.assertIn(
            phrase, text,
            "README.en.md cites a stale length; the description is %d chars."
            % self.n)


if __name__ == "__main__":
    unittest.main()
