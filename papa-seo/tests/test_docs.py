"""Doc-consistency guards. Запуск из папки скила:
python3 -m unittest tests.test_docs

Проверяет, что длина description во frontmatter SKILL.md совпадает с числом,
на которое ссылаются README (ветка claude.ai: «в пакете она N»). Число в прозе
дрейфует при каждом изменении description — этот тест ловит дрейф.

READMEs лежат в корне пакета, на уровень выше папки скила. В установленной копии
(одна папка papa-seo/) их нет, поэтому проверка мягко пропускается — набор тестов
установленного скила остаётся зелёным.
"""
import glob
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)           # .../papa-seo
PACK_ROOT = os.path.dirname(SKILL_DIR)      # корень пакета (= корень репозитория)


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _frontmatter():
    lines = _read_text(os.path.join(SKILL_DIR, "SKILL.md")).split("\n")
    assert lines[0].strip() == "---", "SKILL.md без frontmatter"
    end = lines.index("---", 1)
    out = {}
    for line in lines[1:end]:
        if ":" in line and not line.startswith(" "):
            key, val = line.split(":", 1)
            out[key.strip()] = val.strip()
    return out


def skill_description_length():
    path = os.path.join(SKILL_DIR, "SKILL.md")
    lines = _read_text(path).split("\n")
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
        return _read_text(path)

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



# Лимит description по спецификации Agent Skills — 1024 знака. Codex длиннее не отказывает,
# а молча обрезает до 1024 (замерено на codex-cli 0.162.1 через `codex debug prompt-input`
# 12.11.2026): в 0.2.1 описание было 1050 знаков, и хвост с фразами-триггерами терялся.
DESCRIPTION_MAX = 1024
# claude.ai принимает description не длиннее 200 знаков; README даёт строку для замены.
CLAUDE_AI_MAX = 200


class Frontmatter(unittest.TestCase):
    def test_name_matches_folder_and_spec(self):
        name = _frontmatter().get("name")
        self.assertEqual(name, "papa-seo")
        self.assertRegex(name, r"^[a-z0-9-]{1,64}$")

    def test_description_within_spec_limit(self):
        n = skill_description_length()
        self.assertLessEqual(n, DESCRIPTION_MAX,
                             "description %d знаков, лимит %d: Codex обрежет хвост" % (n, DESCRIPTION_MAX))

    def test_description_is_plain_yaml_safe(self):
        # Значение без кавычек: «: » и « #» YAML читает как новый ключ и комментарий.
        val = _frontmatter()["description"]
        self.assertNotIn(": ", val)
        self.assertNotIn(" #", val)
        self.assertNotRegex(val[:1], r"[\[\]{}>|*&!%@`'\"#,?:-]")

    def test_description_names_key_triggers(self):
        val = _frontmatter()["description"].lower()
        for phrase in ("проверь страницу", "проверь весь сайт", "seo-аудит", "составь тз",
                       "напиши статью", "убери ии-стиль", "seo audit", "--site", "415"):
            self.assertIn(phrase, val)


class ClaudeAiReplacement(unittest.TestCase):
    """Строка, которой README велит заменить description для claude.ai."""
    PATTERNS = {
        "README.md": r'description во frontmatter на эту строку \(целиком, в одну строку\): "([^"]+)"',
        "README.en.md": r'with this line \(all of it, on one line\): "([^"]+)"',
    }

    def _line(self, name):
        path = os.path.join(PACK_ROOT, name)
        if not os.path.isfile(path):
            self.skipTest(name + " нет (установленная копия скила) — пропуск")
        m = re.search(self.PATTERNS[name], _read_text(path))
        self.assertIsNotNone(m, name + ": не нашёл строку замены description для claude.ai")
        return m.group(1)

    def test_short_description_fits_and_parses(self):
        lines = [self._line(n) for n in self.PATTERNS]
        self.assertEqual(lines[0], lines[1], "строки для claude.ai в README.md и README.en.md разошлись")
        self.assertLessEqual(len(lines[0]), CLAUDE_AI_MAX)
        self.assertNotIn(": ", lines[0])
        self.assertNotIn(" #", lines[0])


def _doc_files():
    files = [os.path.join(SKILL_DIR, "SKILL.md")]
    for sub in ("modules", "policies", "templates", "references"):
        files += sorted(glob.glob(os.path.join(SKILL_DIR, sub, "*.md")))
    return files


def _body(path):
    # Первая строка-комментарий — атрибуция донора, пути в ней чужие.
    text = _read_text(path)
    if text.startswith("<!--"):
        text = text[text.index("-->") + 3:]
    return text


class DocReferences(unittest.TestCase):
    """Модули и роутер ссылаются только на то, что есть в пакете."""

    @classmethod
    def setUpClass(cls):
        cls.scripts = {}
        for path in glob.glob(os.path.join(SKILL_DIR, "scripts", "*.py")):
            cls.scripts[os.path.basename(path)[:-3]] = _read_text(path)
        cls.modules = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(SKILL_DIR, "modules", "*.md"))}
        facts = _read_text(os.path.join(SKILL_DIR, "references", "facts-2026.md"))
        yandex = _read_text(os.path.join(SKILL_DIR, "references", "yandex.md"))
        cls.facts_sections = set(re.findall(r"^## §(\d+)", facts, re.M))
        cls.yandex_sections = set(re.findall(r"^## (\d+)\.", yandex, re.M))

    def _flags(self, script):
        return set(re.findall(r"[\"'](--[a-z][a-z0-9-]*)[\"']", self.scripts[script]))

    def test_scripts_and_flags_exist(self):
        bad = []
        for path in _doc_files():
            rel = os.path.relpath(path, SKILL_DIR)
            for m in re.finditer(r"\b([a-z_]+)\.py\b([^\n`|]*)", _body(path)):
                name = m.group(1)
                if name not in self.scripts:
                    bad.append("%s: нет scripts/%s.py" % (rel, name))
                    continue
                flags = self._flags(name) | {"--help"}
                for flag in re.findall(r"(--[a-z][a-z0-9-]*)", m.group(2)):
                    if flag not in flags:
                        bad.append("%s: у %s.py нет флага %s" % (rel, name, flag))
        self.assertEqual(bad, [])

    def test_files_exist(self):
        bad = []
        for path in _doc_files():
            rel = os.path.relpath(path, SKILL_DIR)
            for m in re.finditer(r"\b(references|templates|policies|modules)/([\w.-]+\.(?:md|json|yaml))", _body(path)):
                if not os.path.exists(os.path.join(SKILL_DIR, m.group(1), m.group(2))):
                    bad.append("%s: нет %s" % (rel, m.group(0)))
            if re.search(r"\bSPEC\b", _body(path)):
                bad.append("%s: ссылка на SPEC — в пакете такого файла нет" % rel)
        self.assertEqual(bad, [])

    def test_sections_exist(self):
        bad = []
        for path in _doc_files():
            rel = os.path.relpath(path, SKILL_DIR)
            body = _body(path)
            for pattern, known, label in (
                    (r"facts-2026(?:\.md)?`?\s*§\s*(\d+)((?:\s*,\s*§?\s*\d+)*)", self.facts_sections, "facts-2026"),
                    (r"yandex\.md`?\s*§\s*(\d+)((?:\s*,\s*§?\s*\d+)*)", self.yandex_sections, "yandex.md")):
                for m in re.finditer(pattern, body):
                    for num in [m.group(1)] + re.findall(r"\d+", m.group(2)):
                        if num not in known:
                            bad.append("%s: нет раздела %s §%s" % (rel, label, num))
        self.assertEqual(bad, [])

    def test_router_module_columns_exist(self):
        text = _read_text(os.path.join(SKILL_DIR, "SKILL.md"))
        bad, seen = [], set()
        for table in re.findall(r"(?:^\|.*\|\n)+", text, re.M):
            rows = table.strip().split("\n")
            header = [c.strip() for c in rows[0].strip("|").split("|")]
            if header[-1] not in ("Модули", "Модуль"):
                continue
            for row in rows[2:]:
                cell = row.strip().strip("|").split("|")[-1]
                for tok in re.findall(r"`([a-z-]+)`", cell):
                    seen.add(tok)
                    if tok not in self.modules:
                        bad.append(tok)
        self.assertEqual(bad, [], "в таблицах роутера модули, которых нет в modules/")
        self.assertTrue(seen, "не нашёл таблиц роутера с колонкой «Модули»")

    def test_every_module_reachable_from_router(self):
        text = _read_text(os.path.join(SKILL_DIR, "SKILL.md"))
        missing = sorted(m for m in self.modules if "`%s`" % m not in text)
        self.assertEqual(missing, [], "модули, о которых роутер не знает")


class NumbersMatchRegistry(unittest.TestCase):
    """415 параметров и 77 «ориентиров редактора» в прозе — из реестра, не по памяти."""

    @classmethod
    def setUpClass(cls):
        reg = json.loads(_read_text(os.path.join(SKILL_DIR, "references", "registry.json")))
        cls.total = reg["counts"]["total"]
        cls.editor = reg["counts"]["editor_reference_only"]
        cls.groups = len(reg["groups"])

    def _read(self, name):
        path = os.path.join(PACK_ROOT, name)
        if not os.path.isfile(path):
            self.skipTest(name + " нет (установленная копия скила) — пропуск")
        return _read_text(path)

    def test_skill_md(self):
        text = _read_text(os.path.join(SKILL_DIR, "SKILL.md"))
        self.assertIn("%d parameters" % self.total, text)
        self.assertIn("(%d параметров)" % self.total, text)

    def test_readmes_and_quickstart(self):
        ru = self._read("README.md")
        self.assertIn("**%d параметров** в %d группах" % (self.total, self.groups), ru)
        self.assertIn("таких параметров %d" % self.editor, ru)
        en = self._read("README.en.md")
        self.assertIn("**%d parameters** in %d " % (self.total, self.groups), en)
        self.assertIn("%d registry parameters carry that" % self.editor, en)
        qs = self._read("QUICKSTART.md")
        self.assertIn("%d параметров" % self.total, qs)
        self.assertIn("таких параметров в реестре %d" % self.editor, qs)


if __name__ == "__main__":
    unittest.main()
