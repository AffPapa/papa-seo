#!/usr/bin/env python3
"""text_metrics.py — метрики текста RU/EN. Отчёт с пометкой «оценка», не гейт.

Считает: слова, знаки с пробелами и без (збп), предложения, разброс длины
предложений (CV), серии предложений одной длины, частоты основ (простой
стеммер RU/EN), «тошноту» по слову, оценку «воды» по доле служебных слов,
вхождения и плотность ключей по основам и по зонам (title, description, H1,
H2–H6, первый абзац, alt, анкоры, URL), совстречаемость слов вокруг ключа,
повторы фраз (n-граммы 2–5), канцелярит и пассив, читаемость.

Только stdlib. Без сети, без subprocess/eval/exec. Читает один файл или stdin
(`-`), пишет JSON в stdout; полный отчёт — в файл `--out <путь>.json`.

    python3 scripts/text_metrics.py article.md --keys "купить диван; диван угловой"
    python3 scripts/text_metrics.py page.html --html --out metrics.json
    python3 scripts/text_metrics.py page.html --url https://example.com/divany
    python3 scripts/text_metrics.py --compare before.html after.html --keys "диван"
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ru_text  # noqa: E402

_plural = ru_text.plural
_qty = ru_text.num

VERSION = "0.2.0"
MAX_BYTES = 10 * 1024 * 1024
# Граница «длинного предложения» — ориентир редактора, не норма поиска.
# Печатается рядом с числом, чтобы цифру можно было пересчитать по своей границе.
LONG_SENTENCE_WORDS = 30
# Предел для счёта n-грамм: на книге в 10 МБ полный счёт съел бы сотни МБ памяти.
# Если текст длиннее — в отчёте появляется поле `truncated` с этим числом.
NGRAM_MAX_WORDS = 60_000
NOTE = (
    "Оценка, не гейт. Формулы сервисов (Advego, Text.ru и др.) не публичны, "
    "цифры с ними не совпадут. Сравнивайте версии одного текста этим же "
    "скриптом. Плотность ключа и «тошнота» не являются факторами ранжирования "
    "(см. references/folklore.md); переписывать хороший текст ради цифры не нужно. "
    "Читаемость, канцелярит и пассив — тоже метрики для редактора, а не сигналы "
    "поиска: поисковики не публиковали ни одной шкалы читаемости как фактора."
)

# Параметры реестра (plans/papa-seo-v2-2026-10-30/registry.json, 0.2.0), которые
# закрывает этот скрипт: id → путь в отчёте. Контракт для audit.py: путь по точкам,
# `keys[]` — список по каждой ключевой фразе.
REGISTRY = "urn:papa-seo:registry:0.2.0"
PARAM_MAP = {
    "content.chars": "counts",
    "content.sentences": "rhythm.sentence_words",
    "content.paragraphs": "rhythm.paragraph_words",
    "content.long_sentences": "rhythm.long_sentences",
    "content.rhythm_uniform": "rhythm.similar_runs",
    "content.nausea_classic": "nausea.classic",
    "content.nausea_academic": "nausea.academic_pct",
    "content.water": "water.stopword_pct",
    "content.stopwords_list": "water.stopwords_top",
    "content.stems_top": "stems_top",
    "content.key_in_title": "keys[].zones.title",
    "content.key_in_description": "keys[].zones.description",
    "content.key_in_h1": "keys[].zones.h1",
    "content.key_in_h2h6": "keys[].zones.h2_h6",
    "content.key_in_first_para": "keys[].zones.first_paragraph",
    "content.key_in_alt": "keys[].zones.alt",
    "content.key_in_anchors": "keys[].zones.anchors",
    "content.key_in_url": "keys[].zones.url",
    "content.key_density_total": "keys[].density_pct",
    "content.key_density_by_zone": "keys[].zones.*.density_pct",
    "content.key_exact_vs_morph": "keys[].zones.*.exact_forms | .morphological",
    "content.key_stuffing": "keys[].concentration",
    "content.key_missing": "keys[].missing_everywhere",
    "content.ngram_repeats": "ngrams.repeated",
    "content.cooccurrence": "keys[].cooccurrence",
    "content.readability_en": "readability.scores",
    "content.readability_ru": "readability.scores",
    "content.passive_share": "passive",
    "content.officialese": "clerical",
    "content.compare_versions": "--compare → metrics[] + keys[].zones",
    "content.numbers_without_source": "page_text.numbers_sourced",
    "meta.title_stuffing": "page_text.title_stuffing",
    "meta.title_vs_h1": "page_text.title_vs_h1",
    "meta.title_lang": "page_text.language",
    "meta.desc_equals_title": "page_text.desc_vs_title",
    "meta.desc_truncated_text": "page_text.desc_vs_first_paragraph",
    "meta.heading_stuffing": "page_text.heading_stuffing",
    "meta.heading_length": "page_text.heading_length",
    "intl.lang_vs_text": "page_text.language",
    "ai.answer_first": "page_text.answer_first",
    "ai.claims_sourced": "page_text.numbers_sourced",
}

# ---------------------------------------------------------------- tokenizing

WORD_RE = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*")
URL_RE = re.compile(r"https?://[^\s<>()\"'«»]+|www\.[^\s<>()\"'«»]+")
FENCE_RE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
LIST_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+")
TABLE_RE = re.compile(r"^\s*\|")
QUOTE_RE = re.compile(r"^\s*>\s?")

SENT_END = re.compile(r"([.!?…]+)([\"»”’)\]]*)\s+(?=[«\"„“(\[]?[^\W\d_]|[«\"„“(\[]?\d)")
ABBR = {
    "т.е", "т.к", "т.д", "т.п", "т.н", "др", "г", "гг", "им", "ул", "д", "стр",
    "рис", "см", "тыс", "млн", "млрд", "руб", "коп", "св", "проф", "акад", "ок",
    "прим", "напр", "пр", "ср", "мин", "макс", "кв", "обл", "р-н", "e.g", "i.e",
    "mr", "mrs", "ms", "dr", "vs", "etc", "inc", "ltd", "jr", "sr", "no", "fig",
}

STOP_RU = set("""
а або без более бы был была были было быть в вам вас ваш ваша ваше ваши вдруг ведь
во вот впрочем все всё всего всех всю вы где да даже для до его ее её ей ему если есть
еще ещё же за зачем здесь и из или им иногда их к как какая какой когда кое-что
который которая которое которые которых кто куда ли либо лишь между меня мне много
может можно мой моя мы на над надо наш не него нее неё нет ни нибудь никогда ним них
ничего но ну о об однако он она они оно от очень по под после потом потому почти
при про раз разве с сам сама сами само свою себе себя сейчас со совсем так также такой
там тебя тем теперь то тоже той только том тот тут ты у уж уже хоть хотя чего чем
через что чтоб чтобы чуть эта эти этим этих это этого этой этом этот эту я
итак кстати конечно наверное вообще просто именно поэтому причем причём
каждый каждая каждое каждые каждого каждой каждую весь вся всем всеми свой своя своё свои
этот этому эту этими этого такая такое такие таких такого очень
""".split())

STOP_EN = set("""
a about above after again against all also am an and any are as at be because been
before being below between both but by can could did do does doing down during each
few for from further had has have having he her here hers herself him himself his how
i if in into is it its itself just me more most my myself no nor not now of off on once
only or other our ours ourselves out over own same she should so some such than that the
their theirs them themselves then there these they this those through to too under until
up very was we were what when where which while who whom why will with would you your
yours yourself yourselves really actually basically simply however therefore thus
""".split())

# ---------------------------------------------------------------- stemmers

_RU_V = "аеиоуыэюя"
_PERF_1 = ("вшись", "вши", "в")
_PERF_2 = ("ывшись", "ившись", "ывши", "ивши", "ыв", "ив")
_REFL = ("ся", "сь")
_ADJ = ("ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие", "ые", "ое", "ей", "ий",
        "ый", "ой", "ем", "им", "ым", "ом", "их", "ых", "ую", "юю", "ая", "яя", "ою", "ею")
_PART_1 = ("ем", "нн", "вш", "ющ", "щ")
_PART_2 = ("ивш", "ывш", "ующ")
# Краткие причастия (н, на, но, ны, нно) из первой группы убраны сознательно: иначе
# существительные на -ан/-ян рвутся по-разному («диван» → «дива», «диванами» → «диван»).
_VERB_1 = ("ете", "йте", "ешь", "ла", "ли", "ем", "ло", "ет", "ют", "ть", "й", "л")
_VERB_2 = ("ейте", "уйте", "ила", "ыла", "ена", "ите", "или", "ыли", "ило", "ыло", "ено",
           "ует", "уют", "ены", "ить", "ыть", "ишь", "ей", "уй", "ил", "ыл", "им", "ым",
           "ен", "ят", "ит", "ыт", "ую", "ю")
_NOUN = ("иями", "ями", "ами", "ией", "иям", "ием", "иях", "ев", "ов", "ие", "ье", "еи",
         "ии", "ей", "ой", "ий", "ям", "ем", "ам", "ом", "ах", "ях", "ию", "ью", "ия", "ья",
         "а", "е", "и", "й", "о", "у", "ы", "ь", "ю", "я")


def _rv_start(w: str) -> int:
    for i, ch in enumerate(w):
        if ch in _RU_V:
            return i + 1
    return len(w)


def _r2_start(w: str) -> int:
    def after_vc(s: str, start: int) -> int:
        for i in range(start + 1, len(s)):
            if s[i] not in _RU_V and s[i - 1] in _RU_V:
                return i + 1
        return len(s)
    r1 = after_vc(w, 0)
    return after_vc(w, r1) if r1 < len(w) else len(w)


def _strip(rv: str, endings, need_ay: bool = False):
    for e in sorted(endings, key=len, reverse=True):
        if rv.endswith(e):
            if need_ay:
                pre = rv[: -len(e)]
                if not pre or pre[-1] not in "ая":
                    continue
            return rv[: -len(e)], True
    return rv, False


def stem_ru(word: str) -> str:
    """Упрощённый Snowball-стеммер русского (без словаря)."""
    w = word.lower().replace("ё", "е")
    if len(w) < 3:
        return w
    p = _rv_start(w)
    pre, rv = w[:p], w[p:]
    rv2, ok = _strip(rv, _PERF_1, need_ay=True)
    if not ok:
        rv2, ok = _strip(rv, _PERF_2)
    if ok:
        rv = rv2
    else:
        rv, _ = _strip(rv, _REFL)
        rv2, ok = _strip(rv, _ADJ)
        if ok:
            rv3, ok3 = _strip(rv2, _PART_1, need_ay=True)
            if not ok3:
                rv3, ok3 = _strip(rv2, _PART_2)
            rv = rv3 if ok3 else rv2
        else:
            rv2, ok = _strip(rv, _VERB_1, need_ay=True)
            if not ok:
                rv2, ok = _strip(rv, _VERB_2)
            if ok:
                rv = rv2
            else:
                rv, _ = _strip(rv, _NOUN)
    if rv.endswith("и"):
        rv = rv[:-1]
    w2 = pre + rv
    r2 = _r2_start(w2)
    for e in ("ость", "ост"):
        if w2.endswith(e) and len(w2) - len(e) >= r2:
            w2 = w2[: -len(e)]
            break
    if w2.endswith("ейше"):
        w2 = w2[:-4]
    elif w2.endswith("ейш"):
        w2 = w2[:-3]
    if w2.endswith("нн"):
        w2 = w2[:-1]
    elif w2.endswith("ь"):
        w2 = w2[:-1]
    return w2 or w


_EN_SUFFIXES = (
    ("ational", "ate"), ("ization", "ize"), ("fulness", "ful"), ("ousness", "ous"),
    ("iveness", "ive"), ("tional", "tion"), ("ingly", ""), ("edly", ""), ("ments", "ment"),
    ("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("ly", ""), ("s", ""),
)


def stem_en(word: str) -> str:
    """Лёгкий английский стеммер (суффиксы), не Porter."""
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) <= 3:
        return w
    for suf, rep in _EN_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) + len(rep) >= 3:
            if suf == "s" and (w.endswith("ss") or w.endswith("us") or w.endswith("is")):
                continue
            if suf == "es" and not re.search(r"(sh|ch|x|z|ss)es$", w):
                continue
            w = w[: -len(suf)] + rep
            if suf in ("ing", "ed") and len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]
            break
    return w


def is_cyr(word: str) -> bool:
    return any("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in word)


def stem(word: str) -> str:
    if any(ch.isdigit() for ch in word):
        return word.lower()
    return stem_ru(word) if is_cyr(word) else stem_en(word)


def is_stop(word: str) -> bool:
    lw = word.lower().replace("ё", "е")
    return lw in STOP_RU or lw.replace("е", "ё") in STOP_RU or lw in STOP_EN


# ---------------------------------------------------------------- канцелярит, пассив

# Короткий список измеримых маркеров. Разбор с подсказками «чем заменить» —
# в deai_scan.py и references/ru-style.md; здесь только счёт для отчёта.
CLERICAL_RU = [
    "является", "являются", "являлся", "осуществляется", "осуществляются",
    "осуществляет", "производится", "производятся", "проводится работа",
    "имеет место", "в настоящее время", "на сегодняшний день", "в целях",
    "с целью", "в рамках", "в части", "в случае если", "при наличии",
    "в связи с", "в соответствии с", "необходимо отметить", "следует отметить",
    "следует учитывать", "посредством", "путем", "данный", "данная", "данное",
    "данные факторы", "в кратчайшие сроки", "в полном объеме",
    "обеспечивает возможность", "представляет собой", "в зависимости от",
]
CLERICAL_EN = [
    "in order to", "due to the fact that", "it should be noted", "it is worth noting",
    "utilize", "utilizes", "facilitate", "facilitates", "prior to", "subsequent to",
    "in the event that", "with regard to", "with respect to", "pursuant to",
    "commence", "terminate", "aforementioned", "hereby", "thereof", "herein",
    "at this point in time", "has the ability to", "in a timely manner",
    "a wide range of", "plays a key role", "serves as",
]
# Отглагольные существительные RU: признак канцелярита, но и нормальная лексика
# («решение», «значение»), поэтому отдельной строкой и с пометкой «оценка».
NOMINAL_RU_RE = re.compile(r"^[а-яё]{4,}(?:ание|анию|ания|аний|аниями|аниях|"
                           r"ение|ению|ения|ений|ениями|ениях|ность|ности|ностью|ностей)$")

PASSIVE_RU = [
    (re.compile(r"\b(?:был|была|было|были|будет|будут|бывает)\s+[а-яё]{3,}"
                r"(?:н|на|но|ны|т|та|то|ты)\b"), "быть + краткое причастие"),
    (re.compile(r"\b[а-яё]{4,}(?:ется|ются|ится|атся|ятся)\b"),
     "глагол на -ся (возвратный или пассивный)"),
    (re.compile(r"\b[а-яё]{4,}(?:ался|алась|ались|ялся|ялась|ялись)\b"),
     "глагол на -ся в прошедшем"),
]
_EN_IRREG_PART = set("""
been done gone seen taken given written known shown made found held kept left
sent built brought bought told sold paid put set let read run begun chosen driven
spoken broken frozen stolen worn born thrown grown drawn flown eaten fallen
forgotten hidden lost meant met sought taught thought understood won
""".split())
PASSIVE_EN_RE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being|gets|get|got|gotten)\s+"
    r"(?:\w+ly\s+)?(\w{3,})\b", re.I)


def _passive_hits(text: str, lang: str) -> list[str]:
    """Маркеры пассива в предложении. Эвристика: ловит и возвратные глаголы."""
    hits: list[str] = []
    low = text.lower().replace("ё", "е")
    if lang == "ru":
        for rx, label in PASSIVE_RU:
            for m in rx.finditer(low):
                hits.append(m.group(0))
    else:
        for m in PASSIVE_EN_RE.finditer(low):
            part = m.group(1)
            if part in _EN_IRREG_PART or (part.endswith("ed") and len(part) > 3):
                hits.append(m.group(0))
    return hits


def _phrase_hits(tokens_lc: list[str], phrases: list[str]) -> Counter:
    """Счёт фраз по последовательности слов: знаки между словами не учитываются."""
    found: Counter = Counter()
    for phrase in phrases:
        key = [w.lower().replace("ё", "е") for w in words_of(phrase)]
        if not key:
            continue
        n = find_seq(tokens_lc, key)
        if n:
            found[phrase] = n
    return found


# ---------------------------------------------------------------- слоги, читаемость

_RU_VOW_RE = re.compile(r"[аеёиоуыэюя]")
_EN_VOW_GROUP_RE = re.compile(r"[aeiouy]+")


def syllables_ru(word: str) -> int:
    """Слог русского слова = гласная. Слова без гласных («в», «с») — один слог."""
    return max(1, len(_RU_VOW_RE.findall(word.lower())))


def syllables_en(word: str) -> int:
    """Эвристика: группы гласных минус немая конечная -e."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    n = len(_EN_VOW_GROUP_RE.findall(w))
    if n > 1 and w.endswith("e") and not w.endswith(("le", "ee", "ye", "oe")):
        n -= 1
    return max(1, n)


def count_syllables(word: str, lang: str = "auto") -> int:
    """Кириллица — по гласным, латиница — по группам гласных. lang не меняет правило."""
    return syllables_ru(word) if is_cyr(word) else syllables_en(word)


def readability(words: list[str], sentences: int, lang: str) -> dict:
    """Читаемость. EN — Flesch (формула указана), RU — адаптация, помечена «оценка»."""
    n = len(words)
    rep: dict = {
        "words": n,
        "sentences_prose": sentences,
        "syllables": None,
        "words_per_sentence": None,
        "syllables_per_word": None,
        "long_words_pct": None,
        "long_words_rule": "слова от 4 слогов, % от всех слов (факт подсчёта, не норма)",
        "counts_status": "факт для слов и предложений; слоги RU — по гласным (факт), "
                         "слоги EN — эвристика групп гласных",
        "scores": [],
        "note": "Ни Google, ни Яндекс не публиковали шкалу читаемости как фактор "
                "ранжирования. Это метрика редактора: сравнивать версии одного текста.",
    }
    if not n or not sentences:
        rep["unavailable"] = "нет данных: нужен сплошной текст с предложениями"
        return rep
    syl = [count_syllables(w, lang) for w in words]
    total_syl = sum(syl)
    asl = n / sentences
    asw = total_syl / n
    rep["syllables"] = total_syl
    rep["words_per_sentence"] = round(asl, 2)
    rep["syllables_per_word"] = round(asw, 2)
    rep["long_words_pct"] = round(100 * sum(1 for s in syl if s >= 4) / n, 2)
    if lang not in ("ru", "en"):
        rep["unavailable"] = ("нет формулы для этого языка: считаем только слова, "
                              "предложения и слоги")
        return rep
    if lang == "ru":
        rep["scores"].append({
            "name": "Флеш, адаптация под русский",
            "value": round(206.835 - 1.3 * asl - 60.1 * asw, 1),
            "formula": "206,835 − 1,3 × (слова / предложения) − 60,1 × (слоги / слова)",
            "status": "оценка",
            "source": "адаптация Флеша под русскую слоговую структуру "
                      "(И. В. Оборнева, 2006); у поисковиков такой шкалы нет",
            "scale": "выше — проще читать; шкала исходно школьная, калибровки "
                     "под веб-тексты нет, поэтому сравнивать только версии одного текста",
        })
    else:
        rep["scores"].append({
            "name": "Flesch Reading Ease",
            "value": round(206.835 - 1.015 * asl - 84.6 * asw, 1),
            "formula": "206.835 − 1.015 × (words / sentences) − 84.6 × (syllables / words)",
            "status": "факт по формуле, оценка по смыслу (слоги считаются эвристикой)",
            "source": "Flesch R. «A new readability yardstick», 1948",
            "scale": "90–100 очень просто, 60–70 обычная проза, 0–30 очень сложно "
                     "(шкала автора формулы, не требование поисковика)",
        })
        rep["scores"].append({
            "name": "Flesch–Kincaid Grade Level",
            "value": round(0.39 * asl + 11.8 * asw - 15.59, 1),
            "formula": "0.39 × (words / sentences) + 11.8 × (syllables / words) − 15.59",
            "status": "факт по формуле, оценка по смыслу",
            "source": "Kincaid J. P. et al., 1975 (US Navy)",
            "scale": "число ≈ класс школы США",
        })
    return rep


# ---------------------------------------------------------------- input / output


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCK = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6",
             "br", "tr", "td", "th", "blockquote", "header", "footer", "main", "ul", "ol",
             "table", "nav", "aside", "figure", "figcaption", "dd", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0
        self.comments = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)

    def handle_comment(self, data):
        self.comments += 1


def html_to_text(raw: str) -> tuple[str, int]:
    p = _HTMLText()
    p.feed(raw)
    p.close()
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip(), p.comments


# ---------------------------------------------------------------- зоны страницы

ZONE_ORDER = ["title", "description", "h1", "h2_h6", "first_paragraph",
              "alt", "anchors", "url", "body"]
ZONE_TITLES = {
    "title": "<title>",
    "description": "meta description",
    "h1": "H1",
    "h2_h6": "H2–H6",
    "first_paragraph": "первый абзац",
    "alt": "alt изображений",
    "anchors": "текст ссылок",
    "url": "URL страницы",
    "body": "весь текст",
}

_PCT_RE = re.compile(r"(?:%[0-9A-Fa-f]{2})+")
_TRANSLIT = {
    "а": ("a",), "б": ("b",), "в": ("v",), "г": ("g",), "д": ("d",), "е": ("e",),
    "ё": ("e", "yo"), "ж": ("zh", "j"), "з": ("z",), "и": ("i",), "й": ("y", "i"),
    "к": ("k",), "л": ("l",), "м": ("m",), "н": ("n",), "о": ("o",), "п": ("p",),
    "р": ("r",), "с": ("s",), "т": ("t",), "у": ("u",), "ф": ("f",),
    "х": ("h", "kh"), "ц": ("c", "ts"), "ч": ("ch",), "ш": ("sh",),
    "щ": ("sch", "shch"), "ъ": ("",), "ы": ("y",), "ь": ("",), "э": ("e",),
    "ю": ("yu", "iu"), "я": ("ya", "ia"),
}
TRANSLIT_CAP = 24


def pct_decode(s: str) -> str:
    def rep(m: re.Match) -> str:
        try:
            return bytes.fromhex(m.group(0).replace("%", "")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return m.group(0)
    return _PCT_RE.sub(rep, s)


def translit_variants(word: str) -> set[str]:
    """Варианты латиницы для кириллического слова (эвристика для slug'ов)."""
    out = {""}
    for ch in word.lower():
        opts = _TRANSLIT.get(ch)
        if opts is None:
            opts = (ch,) if ch.isalnum() else ("",)
        out = {acc + o for acc in out for o in opts}
        if len(out) > TRANSLIT_CAP:
            out = set(sorted(out)[:TRANSLIT_CAP])
    return {w for w in out if w}


def url_tokens(url: str) -> list[str]:
    """Слова из URL: хост и путь после процентного декодирования.

    Дефис, точка, слеш и подчёркивание — разделители слов, как в слагах.
    """
    u = pct_decode(url or "")
    u = re.sub(r"^[a-zA-Z][\w+.-]*://", "", u)
    return [t.lower().replace("ё", "е") for t in re.split(r"[\W_]+", u)
            if t and not t.isdigit()]


class _HTMLZones(HTMLParser):
    """Зоны страницы из сырого HTML. Без браузера, по тегам."""

    SKIP = {"script", "style", "noscript", "template", "svg", "iframe"}
    CAPTURE = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "a"}
    # Блочный тег закрывает незакрытые <p> и <h1>–<h6>: так делает и браузер.
    BLOCKY = {"p", "div", "section", "article", "main", "aside", "nav", "header",
              "footer", "ul", "ol", "li", "table", "tr", "td", "th", "blockquote",
              "h1", "h2", "h3", "h4", "h5", "h6", "figure", "figcaption", "dl",
              "dd", "dt", "form", "pre", "hr", "body"}
    AUTO_CLOSE = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.frames: list[list] = []          # [tag, chars, in_main]
        self.main_depth = 0
        self.title: str | None = None
        self.description: str | None = None
        self.canonical: str | None = None
        self.og_url: str | None = None
        self.headings: dict[str, list[str]] = {f"h{i}": [] for i in range(1, 7)}
        self.paragraphs: list[tuple[bool, str]] = []
        self.alts: list[str] = []
        self.anchors: list[str] = []
        self.html_lang: str | None = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP:
            self.skip_depth += 1
            return
        if tag == "html" and self.html_lang is None:
            self.html_lang = a.get("lang", "").strip() or None
        if tag in self.BLOCKY:
            while self.frames and self.frames[-1][0] in self.AUTO_CLOSE:
                self._store(self.frames.pop())
        if tag == "meta":
            name = a.get("name", "").lower()
            prop = a.get("property", "").lower()
            if name == "description" and self.description is None:
                self.description = a.get("content", "").strip()
            elif prop == "og:url" and self.og_url is None:
                self.og_url = a.get("content", "").strip()
            return
        if tag == "link":
            rels = a.get("rel", "").lower().split()
            if "canonical" in rels and self.canonical is None:
                self.canonical = a.get("href", "").strip()
            return
        if tag == "img":
            alt = a.get("alt", "").strip()
            if alt:
                self.alts.append(alt)
            return
        if tag in ("main", "article"):
            self.main_depth += 1
            return
        if tag in self.CAPTURE:
            self.frames.append([tag, [], self.main_depth > 0])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.SKIP and tag not in ("meta", "link", "img", "main", "article"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in ("main", "article"):
            self.main_depth = max(0, self.main_depth - 1)
            return
        for i in range(len(self.frames) - 1, -1, -1):
            if self.frames[i][0] == tag:
                for frame in self.frames[i:]:
                    self._store(frame)
                del self.frames[i:]
                return

    def _store(self, frame) -> None:
        tag, chars, in_main = frame
        text = re.sub(r"\s+", " ", "".join(chars)).strip()
        if not text:
            return
        if tag == "title":
            if self.title is None:
                self.title = text
        elif tag == "p":
            self.paragraphs.append((in_main, text))
        elif tag == "a":
            self.anchors.append(text)
        else:
            self.headings[tag].append(text)

    def handle_data(self, data):
        if self.skip_depth:
            return
        for frame in self.frames:
            frame[1].append(data)

    def close(self):
        super().close()
        for frame in self.frames:
            self._store(frame)
        self.frames.clear()


def _zone(items: list[str]) -> dict:
    items = [i for i in items if i and i.strip()]
    return {
        "items": items,
        "text": "\n".join(items),
        "words": sum(len(letter_words(i)) for i in items),
        "count": len(items),
    }


def zones_from_html(raw: str, url: str | None = None) -> dict:
    p = _HTMLZones()
    p.feed(raw)
    p.close()
    first, source = None, "none"
    for want_main in (True, False):
        for in_main, text in p.paragraphs:
            if (in_main or not want_main) and len(letter_words(text)) >= 3:
                first, source = text, "main" if in_main else "body"
                break
        if first:
            break
    page_url = url or p.canonical or p.og_url or ""
    zones = {
        "title": _zone([p.title or ""]),
        "description": _zone([p.description or ""]),
        "h1": _zone(p.headings["h1"]),
        "h2_h6": _zone([t for i in range(2, 7) for t in p.headings[f"h{i}"]]),
        "first_paragraph": _zone([first or ""]),
        "alt": _zone(p.alts),
        "anchors": _zone(p.anchors),
        "url": _zone([page_url]),
    }
    zones["_levels"] = {k: list(v) for k, v in p.headings.items()}
    zones["_meta"] = {
        "source": "live_html",
        "html_lang": p.html_lang,
        "first_paragraph_rule": "первый <p> от 3 слов, сначала внутри <main>/<article>, "
                                "иначе первый в документе",
        "first_paragraph_source": source,
        "url_source": "аргумент --url" if url else (
            "link rel=canonical" if p.canonical else (
                "og:url" if p.og_url else "нет данных")),
        "headings_by_level": {k: len(v) for k, v in p.headings.items() if v},
        "note": "alt без текста и пустые ссылки в зоны не попадают; аудит самих "
                "атрибутов — в page_facts.py",
    }
    return zones


def zones_from_markdown(text: str) -> dict:
    """Зоны из Markdown: title и description в разметке Markdown отсутствуют."""
    levels: dict[str, list[str]] = {f"h{i}": [] for i in range(1, 7)}
    for line in text.split("\n"):
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            levels[f"h{len(m.group(1))}"].append(m.group(2).strip())
    h1 = levels["h1"]
    rest = [t for i in range(2, 7) for t in levels[f"h{i}"]]
    alts = [m.group(1).strip() for m in MD_IMAGE_RE.finditer(text) if m.group(1).strip()]
    anchors = [m.group(1).strip() for m in
               re.finditer(r"(?<!!)\[([^\]]+)\]\([^)]*\)", text) if m.group(1).strip()]
    plain, _ = clean_markdown(text)
    first = next((t for kind, t in split_blocks(plain) if kind == "prose"), "")
    zones = {
        "title": _zone([]),
        "description": _zone([]),
        "h1": _zone(h1),
        "h2_h6": _zone(rest),
        "first_paragraph": _zone([first]),
        "alt": _zone(alts),
        "anchors": _zone(anchors),
        "url": _zone([]),
    }
    zones["_levels"] = levels
    zones["_meta"] = {
        "source": "user_file",
        "html_lang": None,
        "first_paragraph_rule": "первый абзац сплошного текста",
        "first_paragraph_source": "markdown",
        "url_source": "аргумент --url",
        "absent": ["title", "description", "url"],
        "note": "В Markdown нет <title>, meta description и URL: зоны пустые, "
                "это «нет данных», а не «ключа нет».",
    }
    return zones


def read_input(path: str) -> str:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
    else:
        if "\x00" in path or not os.path.isfile(path):
            raise ValueError(f"нет такого файла: {path!r}")
        if os.path.getsize(path) > MAX_BYTES:
            raise ValueError(f"файл больше {MAX_BYTES} байт")
        with open(path, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"вход больше {MAX_BYTES} байт")
    if b"\x00" in data[:4096]:
        raise ValueError("похоже на бинарный файл")
    return data.decode("utf-8-sig", errors="replace")


def check_out_path(path: str) -> str:
    """--out пишет ровно в переданный путь .json: не каталог, не симлинк, каталог существует."""
    if "\x00" in path or not path.lower().endswith(".json"):
        raise ValueError("--out: нужен путь к файлу .json")
    ap = os.path.abspath(path)
    if os.path.islink(ap) or os.path.isdir(ap):
        raise ValueError("--out: путь — каталог или символическая ссылка")
    if not os.path.isdir(os.path.dirname(ap)):
        raise ValueError("--out: каталог для файла не существует")
    return ap


def emit(report: dict, short: dict, out: str | None) -> None:
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        short = dict(short, out=out)
        print(json.dumps(short, ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- text model


def clean_markdown(text: str) -> tuple[str, dict]:
    masked = {"code_blocks": 0, "inline_code": 0, "html_comments": 0, "urls": 0}
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    text = re.sub(r"[\u200b-\u200d\u2060\ufeff\u00ad]", "", text)

    def cnt(key):
        def f(_m):
            masked[key] += 1
            return " "
        return f

    text = FENCE_RE.sub(cnt("code_blocks"), text)
    text = COMMENT_RE.sub(cnt("html_comments"), text)
    text = INLINE_CODE_RE.sub(cnt("inline_code"), text)
    text = MD_IMAGE_RE.sub(lambda m: m.group(1), text)
    text = MD_LINK_RE.sub(lambda m: m.group(1), text)
    text = URL_RE.sub(cnt("urls"), text)
    text = TAG_RE.sub(" ", text)
    return text, masked


def split_blocks(text: str) -> list[tuple[str, str]]:
    """[(kind, text)] где kind: prose | heading | list | table | quote."""
    blocks: list[tuple[str, str]] = []
    para: list[str] = []

    def flush():
        if para:
            blocks.append(("prose", " ".join(para)))
            para.clear()

    for line in text.split("\n"):
        s = line.strip()
        if not s:
            flush()
            continue
        if HEADING_RE.match(line):
            flush()
            blocks.append(("heading", HEADING_RE.sub("", line).strip("# ").strip()))
        elif TABLE_RE.match(line):
            flush()
            if not re.fullmatch(r"[\s|:\-]+", s):
                blocks.append(("table", s.replace("|", " ")))
        elif LIST_RE.match(line):
            flush()
            blocks.append(("list", LIST_RE.sub("", line).strip()))
        elif QUOTE_RE.match(line):
            flush()
            blocks.append(("quote", QUOTE_RE.sub("", line).strip()))
        else:
            para.append(s)
    flush()
    cleaned = []
    for kind, t in blocks:
        t = re.sub(r"(\*\*|__|\*|_|~~)(?=\S)|(?<=\S)(\*\*|__|\*|_|~~)", "", t).strip()
        if t:
            cleaned.append((kind, t))
    return cleaned


def split_sentences(block: str) -> list[str]:
    out, start = [], 0
    for m in SENT_END.finditer(block):
        prev = block[start:m.start(1)]
        if m.group(1) == ".":
            w = re.search(r"([^\W\d_]+(?:[.\-][^\W\d_]+)*)$", prev)
            if w:
                tok = w.group(1).lower()
                if tok in ABBR or len(tok) == 1:
                    continue
        end = m.end(1) + len(m.group(2))
        s = block[start:end].strip()
        if s:
            out.append(s)
        start = m.end()
    tail = block[start:].strip()
    if tail:
        out.append(tail)
    return out


def words_of(s: str) -> list[str]:
    return WORD_RE.findall(s)


def letter_words(s: str) -> list[str]:
    return [w for w in words_of(s) if any(ch.isalpha() for ch in w)]


def detect_lang(text: str) -> str:
    cyr = sum(1 for ch in text if ("а" <= ch.lower() <= "я") or ch in "ёЁ")
    lat = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    if cyr == 0 and lat == 0:
        return "unknown"
    return "ru" if cyr >= lat else "en"


def similar_runs(lengths: list[int], tolerance: float = 0.2, min_run: int = 3,
                 min_len: int = 5) -> list[dict]:
    """Серии соседних предложений почти одной длины (эвристика, не порог)."""
    runs, i, n = [], 0, len(lengths)
    while i < n:
        j = i
        while j + 1 < n:
            window = lengths[i:j + 2]
            lo, hi = min(window), max(window)
            if lo >= min_len and hi > 0 and (hi - lo) / hi <= tolerance:
                j += 1
            else:
                break
        if j - i + 1 >= min_run:
            runs.append({"start": i, "count": j - i + 1, "lengths": lengths[i:j + 1]})
            i = j + 1
        else:
            i += 1
    return runs


def describe(values: list[int]) -> dict:
    if not values:
        return {"count": 0}
    mean = statistics.fmean(values)
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "count": len(values),
        "mean": round(mean, 2),
        "median": statistics.median(values),
        "stdev": round(sd, 2),
        "cv": round(sd / mean, 3) if mean else None,
        "min": min(values),
        "max": max(values),
    }


def find_seq(seq: list[str], key: list[str]) -> int:
    if not key or len(key) > len(seq):
        return 0
    n, k, i, c = len(seq), len(key), 0, 0
    while i <= n - k:
        if seq[i:i + k] == key:
            c += 1
            i += k
        else:
            i += 1
    return c


def find_window(seq: list[str], key: list[str], slack: int = 2) -> int:
    """Все основы ключа в окне длиной len(key)+slack, в любом порядке, без перекрытий."""
    if not key:
        return 0
    need = Counter(key)
    w, i, c = len(key) + slack, 0, 0
    while i < len(seq):
        if seq[i] in need:
            win = Counter(seq[i:i + w])
            if all(win[s] >= m for s, m in need.items()):
                c += 1
                i += w
                continue
        i += 1
    return c


# ---------------------------------------------------------------- повторы, окружение


def _lc(word: str) -> str:
    return word.lower().replace("ё", "е")


def repeated_ngrams(segments: list[list[str]], n_min: int = 2, n_max: int = 5,
                    top: int = 15) -> dict:
    """Повторяющиеся n-граммы 2–5 слов внутри предложений и доля самоповтора."""
    cut, seen = [], 0
    for seg in segments:
        if seen >= NGRAM_MAX_WORDS:
            break
        cut.append(seg)
        seen += len(seg)
    truncated = len(cut) < len(segments)
    by_n: dict[str, list[dict]] = {}
    distinct: dict[str, int] = {}
    covered: set[tuple[int, int]] = set()
    total_words = sum(len(s) for s in cut)
    for n in range(n_min, n_max + 1):
        counts: Counter = Counter()
        for seg in cut:
            for i in range(len(seg) - n + 1):
                counts[tuple(seg[i:i + n])] += 1
        rep = {g: c for g, c in counts.items() if c > 1}
        order = sorted(rep.items(), key=lambda gc: (-gc[1], " ".join(gc[0])))
        by_n[str(n)] = [{"phrase": " ".join(g), "count": c} for g, c in order[:top]]
        distinct[str(n)] = len(rep)
        if n >= 3 and rep:
            for si, seg in enumerate(cut):
                for i in range(len(seg) - n + 1):
                    if tuple(seg[i:i + n]) in rep:
                        covered.update((si, k) for k in range(i, i + n))
    out = {
        "repeated": by_n,
        "repeated_distinct": distinct,
        "repeated_distinct_note": f"столько разных n-грамм встретилось больше одного "
                                  f"раза; в «repeated» — первые {top} по частоте",
        "self_repeat_pct": round(100 * len(covered) / total_words, 2) if total_words else 0,
        "self_repeat_formula": "слова, попавшие хотя бы в одну повторяющуюся n-грамму "
                               "длиной 3–5 слов (встретилась ≥ 2 раз), / все слова, %",
        "status": "факт подсчёта; что из этого лишнее — решает редактор",
        "rule": "n-граммы считаются внутри одного предложения (или одного элемента "
                "списка, заголовка, ячейки); через границу предложения не склеиваются",
    }
    if truncated:
        out["truncated"] = (f"повторы считаны по {_plural(total_words, 'первому', 'первым', 'первым')} "
                            f"{_qty(total_words, 'значимому слову', 'значимым словам', 'значимым словам')} "
                            f"(предел {NGRAM_MAX_WORDS}); остальной текст в этот счёт "
                            "не вошёл")
    return out


def cooccurrence(segments: list[list[str]], key_stems: list[str], window: int = 10,
                 top: int = 12) -> dict:
    """Совстречаемость: какие основы стоят в окне ±N значимых слов от ключа."""
    need = set(key_stems)
    hits, near = 0, Counter()
    for seg in segments:
        if not need or not need.issubset(set(seg)):
            continue
        hits += 1
        keep: set[int] = set()
        for i, s in enumerate(seg):
            if s in need:
                keep.update(range(max(0, i - window), min(len(seg), i + window + 1)))
        for j in keep:
            if seg[j] not in need:
                near[seg[j]] += 1
    return {
        "segments_with_key": hits,
        "window_words": window,
        "window_rule": f"±{window} значимых слов от каждой основы ключа внутри одного "
                       "предложения; служебные слова в окно не входят, поэтому в сырых "
                       "словах окно шире",
        "top": [{"stem": s, "count": c} for s, c in near.most_common(top)],
        "status": "факт подсчёта",
        "note": "Это статистика соседства, а не «LSI-ключи»: латентно-семантического "
                "индексирования поисковики не объявляли (references/folklore.md). "
                "Добавлять слова из этого списка в текст ради списка не нужно.",
    }


def key_in_zone(zone: dict, kw_lc: list[str], kstems: list[str],
                is_url: bool = False) -> dict:
    """Вхождения ключа в одной зоне: точное по словоформам и морфологическое по основам."""
    exact = morph = window = 0
    translit_found: list[str] = []
    items: list[dict] = []
    for n, item in enumerate(zone["items"], 1):
        toks = url_tokens(item) if is_url else [_lc(w) for w in letter_words(item)]
        stems = [stem(w) for w in toks]
        e, m, wd = find_seq(toks, kw_lc), find_seq(stems, kstems), find_window(stems, kstems)
        exact += e
        morph += m
        window += wd
        if e or m or wd:
            items.append({"n": n, "text": item[:160], "exact_forms": e,
                          "morphological": m, "any_order_window": wd})
        if is_url and any(is_cyr(w) for w in kw_lc):
            translit_found = _translit_in_tokens(kstems, toks)
    words = len(url_tokens(zone["text"])) if is_url else zone["words"]
    out = {
        "words": words,
        "items_total": zone["count"],
        "exact_forms": exact,
        "morphological": morph,
        "any_order_window": window,
        "items_with_key": items,
        "present": bool(exact or morph or window or translit_found),
        "density_pct": round(100 * morph * len(kstems) / words, 2) if words else None,
    }
    if is_url:
        out["translit_stems"] = translit_found
        out["translit_rule"] = ("основы ключа переведены в латиницу и сверены с началом "
                                "слов в URL; варианты х/kh, ц/c/ts, ю/yu/iu учтены, "
                                "это эвристика для слагов, а не чтение смысла URL")
    return out


def _translit_in_tokens(kstems: list[str], toks: list[str]) -> list[str]:
    """Какие основы ключа нашлись в URL латиницей (по началу слова)."""
    found = []
    for st in kstems:
        if not is_cyr(st):
            continue
        variants = {v for v in translit_variants(st) if len(v) >= 3}
        if any(t.startswith(v) for v in variants for t in toks if len(t) >= 3):
            found.append(st)
    return found


# ------------------------------------------------- проверки по зонам (meta, ai)

SOURCE_MARKERS_RU = ("по данным", "источник", "согласно", "сообщает", "сообщил",
                     "отчет", "отчёт", "исследован", "опрос", "статистик",
                     "по подсчет", "по оценк", "выгрузк", "замер")
SOURCE_MARKERS_EN = ("according to", "source", "reported", "report", "study",
                     "survey", "data from", "statistics", "measured", "we counted")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _norm_phrase(s: str) -> str:
    return " ".join(_lc(w) for w in letter_words(s))


def _stems_set(s: str) -> set[str]:
    return {stem(w) for w in letter_words(s) if not is_stop(w) and len(w) > 1}


def alphabet_share(s: str) -> dict:
    cyr = sum(1 for ch in s if ("а" <= ch.lower() <= "я") or ch in "ёЁ")
    lat = sum(1 for ch in s if "a" <= ch.lower() <= "z")
    total = cyr + lat
    return {
        "letters": total,
        "cyrillic_pct": round(100 * cyr / total, 1) if total else None,
        "latin_pct": round(100 * lat / total, 1) if total else None,
        "detected": detect_lang(s) if total else "unknown",
    }


def page_text_checks(zones: dict, lang: str, prose_sentences: list[str]) -> dict:
    """Текстовая часть параметров meta.* / ai.* / intl.*: сравнение зон между собой."""
    title = zones["title"]["text"]
    desc = zones["description"]["text"]
    h1 = zones["h1"]["items"][0] if zones["h1"]["items"] else ""
    first = zones["first_paragraph"]["text"]
    levels = zones.get("_levels", {})
    nt, nd, nf = _norm_phrase(title), _norm_phrase(desc), _norm_phrase(first)

    t_stems = [stem(w) for w in letter_words(title) if not is_stop(w) and len(w) > 1]
    t_rep = [{"stem": s, "count": c} for s, c in Counter(t_stems).most_common() if c > 2]
    t_letters = [ch for ch in title if ch.isalpha()]
    h1_set, t_set = _stems_set(h1), set(t_stems)

    heading_stuffing = []
    for lvl in (f"h{i}" for i in range(2, 7)):
        items = levels.get(lvl) or []
        if len(items) < 2:
            continue
        seen = Counter(s for item in items for s in _stems_set(item))
        for s, c in seen.most_common():
            if c * 2 > len(items):
                heading_stuffing.append({"level": lvl, "stem": s, "in_headings": c,
                                         "of": len(items)})

    head_words = [len(letter_words(t)) for t in zones["h2_h6"]["items"]]
    with_numbers = [s for s in prose_sentences if any(ch.isdigit() for ch in s)]
    markers = SOURCE_MARKERS_RU if lang == "ru" else SOURCE_MARKERS_EN
    sourced = [s for s in with_numbers
               if any(m in _lc(s) for m in markers) or _YEAR_RE.search(s)]
    first_sents = split_sentences(first)

    return {
        "title_stuffing": {
            "repeated_stems": t_rep,
            "uppercase_pct": round(100 * sum(1 for ch in t_letters if ch.isupper())
                                   / len(t_letters), 1) if t_letters else None,
            "status": "факт подсчёта",
            "rule": "одна основа больше двух раз в title и доля заглавных букв. "
                    "Опирается на спам-политику keyword stuffing (facts-2026 §9); "
                    "числовой нормы в документации нет",
        },
        "title_vs_h1": {
            "shared_stems": sorted(h1_set & t_set),
            "h1_stems_in_title_pct": round(100 * len(h1_set & t_set) / len(h1_set), 1)
                                     if h1_set else None,
            "title_stems_in_h1_pct": round(100 * len(h1_set & t_set) / len(t_set), 1)
                                     if t_set else None,
            "status": "оценка",
            "rule": "пересечение значимых основ title и первого H1. Порога нет: "
                    "совпадение 0 % у страницы с осмысленным title бывает законным "
                    "(бренд в title, вопрос в H1) — смотреть глазами",
        },
        "desc_vs_title": {
            "equal": bool(nd) and nd == nt,
            "contains": bool(nd) and bool(nt) and (nd in nt or nt in nd) and nd != nt,
            "status": "факт",
        },
        "desc_vs_first_paragraph": {
            "is_prefix": bool(nd) and bool(nf) and nf.startswith(nd),
            "equal": bool(nd) and nd == nf,
            "status": "факт",
            "rule": "нормализованное description — начало первого абзаца: описание "
                    "просто обрезает текст",
        },
        "heading_stuffing": {
            "repeated": heading_stuffing,
            "status": "факт подсчёта",
            "rule": "основа встречается более чем в половине заголовков своего уровня "
                    "(уровни от двух заголовков)",
        },
        "heading_length": {
            "words": describe(head_words),
            "longest_words": max(head_words) if head_words else None,
            "status": "факт",
            "rule": "порога нет: выводится распределение по H2–H6",
        },
        "language": {
            "html_lang": zones.get("_meta", {}).get("html_lang"),
            "text_detected": lang,
            "title": alphabet_share(title),
            "body_vs_title_mismatch": bool(title) and detect_lang(title) != lang
                                      and detect_lang(title) != "unknown",
            "status": "оценка",
            "rule": "язык определяется только по алфавиту (кириллица против латиницы), "
                    "без словаря: для коротких title, смеси языков и для языков вне "
                    "этих двух алфавитов вывод ненадёжен. Значение атрибута lang "
                    "читается из <html lang> и ни с чем не сверяется автоматически",
        },
        "numbers_sourced": {
            "sentences_with_numbers": len(with_numbers),
            "with_source_marker": len(sourced),
            "without_source_marker": len(with_numbers) - len(sourced),
            "status": "оценка",
            "rule": "в предложении есть цифра и рядом — слово-указание на источник "
                    "или год. Ссылку рядом с цифрой этот скрипт не видит (ссылки "
                    "обезличены в тексте) — за ссылками в page_facts.py",
        },
        "answer_first": {
            "first_paragraph_words": zones["first_paragraph"]["words"],
            "first_paragraph_sentences": len(first_sents),
            "first_sentence_words": len(letter_words(first_sents[0])) if first_sents else None,
            "first_sentence_is_question": first_sents[0].rstrip().endswith("?")
                                          if first_sents else None,
            "status": "оценка",
            "rule": "цифры о начале страницы, а не оценка ответа: нормы длины пассажа "
                    "нет (facts-2026 §10), «есть ли прямой ответ» решает читатель",
        },
    }


def analyze(text: str, keys: list[str] | None = None, lang: str = "auto",
            is_html: bool = False, url: str | None = None) -> dict:
    raw = text
    html_comments = 0
    if is_html:
        text, html_comments = html_to_text(text)
    plain, masked = clean_markdown(text)
    masked["html_comments"] += html_comments
    blocks = split_blocks(plain)
    plain_text = "\n".join(t for _, t in blocks)
    if lang == "auto":
        lang = detect_lang(plain_text)

    tokens = words_of(plain_text)
    words = [t for t in tokens if any(ch.isalpha() for ch in t)]
    numbers = [t for t in tokens if not any(ch.isalpha() for ch in t)]
    n_words = len(words)

    sent_lengths: list[int] = []
    para_lengths: list[int] = []
    prose_sentences: list[str] = []
    for kind, t in blocks:
        if kind != "prose":
            continue
        sents = split_sentences(t)
        prose_sentences.extend(sents)
        lens = [len(letter_words(s)) for s in sents]
        lens = [x for x in lens if x > 0]
        sent_lengths.extend(lens)
        para_lengths.append(sum(lens))

    # Сегменты: предложение сплошного текста либо один заголовок / пункт / ячейка.
    seg_lc: list[list[str]] = []
    seg_stems: list[list[str]] = []
    for kind, t in blocks:
        parts = split_sentences(t) if kind == "prose" else [t]
        for part in parts:
            lw = [_lc(w) for w in letter_words(part)]
            if lw:
                seg_lc.append(lw)
            seg = [stem(w) for w in letter_words(part) if not is_stop(w)]
            if seg:
                seg_stems.append(seg)

    content = [w for w in words if not is_stop(w) and len(w) > 1]
    stems_all = [stem(w) for w in words]
    stem_counts = Counter(stem(w) for w in content)
    surface: dict[str, Counter] = {}
    for w in content:
        surface.setdefault(stem(w), Counter())[w.lower()] += 1
    top = stem_counts.most_common(20)
    stop_n = n_words - len(content)
    top_count = top[0][1] if top else 0

    zones = zones_from_html(raw, url) if is_html else zones_from_markdown(raw)
    if url and not zones["url"]["items"]:
        zones["url"] = _zone([url])
        zones["_meta"]["url_source"] = "аргумент --url"
    zones["body"] = _zone([plain_text])

    tokens_lc = [_lc(w) for w in words]
    if lang == "ru":
        clerical_list = CLERICAL_RU
    elif lang == "en":
        clerical_list = CLERICAL_EN
    else:
        clerical_list = CLERICAL_RU + CLERICAL_EN
    clerical = _phrase_hits(tokens_lc, clerical_list)
    nominal = [w for w in tokens_lc if NOMINAL_RU_RE.match(w)]
    passive_sent = [s for s in prose_sentences if _passive_hits(s, lang)]
    passive_marks = Counter(m for s in prose_sentences for m in _passive_hits(s, lang))

    report = {
        "tool": "text_metrics",
        "version": VERSION,
        "registry": REGISTRY,
        "status": "оценка",
        "note": NOTE,
        "lang": lang,
        "counts": {
            "chars_total": len(plain_text),
            "chars_no_spaces": sum(1 for ch in plain_text if not ch.isspace()),
            "words": n_words,
            "numbers": len(numbers),
            "unique_words": len({w.lower() for w in words}),
            "unique_stems": len(set(stems_all)),
            "sentences_prose": len(sent_lengths),
            "paragraphs_prose": len(para_lengths),
            "headings": sum(1 for k, _ in blocks if k == "heading"),
            "list_items": sum(1 for k, _ in blocks if k == "list"),
        },
        "rhythm": {
            "sentence_words": describe(sent_lengths),
            "paragraph_words": describe(para_lengths),
            "long_sentences": {
                "threshold_words": LONG_SENTENCE_WORDS,
                "count": sum(1 for x in sent_lengths if x > LONG_SENTENCE_WORDS),
                "pct": round(100 * sum(1 for x in sent_lengths if x > LONG_SENTENCE_WORDS)
                             / len(sent_lengths), 2) if sent_lengths else None,
                "longest": max(sent_lengths) if sent_lengths else None,
                "rule": f"предложения длиннее {LONG_SENTENCE_WORDS} слов. Граница — "
                        "ориентир редактора, а не норма поиска: её видно рядом с числом, "
                        "чтобы цифру можно было пересчитать по своей границе",
            },
            "similar_runs": similar_runs(sent_lengths),
            "similar_runs_rule": "≥3 соседних предложения, длины в пределах 20 % "
                                 "(условность чтения, не замеренный порог)",
            "note": "Ритм меряется только по сплошному тексту; списки и таблицы — none.",
        },
        "stems_top": [
            {"stem": s, "count": c, "share_pct": round(100 * c / n_words, 2) if n_words else 0,
             "forms": [f for f, _ in surface[s].most_common(4)]}
            for s, c in top
        ],
        "nausea": {
            "classic": round(math.sqrt(top_count), 2) if top_count else 0,
            "classic_formula": "√ частоты самой частой значимой основы (оценка)",
            "academic_pct": round(100 * top_count / n_words, 2) if n_words else 0,
            "academic_formula": "доля самой частой значимой основы среди всех слов, % (оценка)",
            "top_stem": top[0][0] if top else None,
        },
        "water": {
            "stopword_pct": round(100 * stop_n / n_words, 2) if n_words else 0,
            "stopwords": stop_n,
            "stopwords_top": [{"word": w, "count": c} for w, c in
                              Counter(w for w in tokens_lc if is_stop(w)).most_common(10)],
            "formula": "доля служебных слов (предлоги, союзы, частицы, местоимения, "
                       "вводные) среди всех слов, % (оценка; у сервисов своя формула)",
            "list_size": {"ru": len(STOP_RU), "en": len(STOP_EN)},
        },
        "readability": readability(words, len(sent_lengths), lang),
        "clerical": {
            "markers": [{"marker": m, "count": c} for m, c in clerical.most_common()],
            "total": sum(clerical.values()),
            "per_1000_words": round(1000 * sum(clerical.values()) / n_words, 1)
                              if n_words else None,
            "nominal_nouns": {
                "count": len(nominal),
                "pct": round(100 * len(nominal) / n_words, 2) if n_words else None,
                "top": [{"word": w, "count": c} for w, c in Counter(nominal).most_common(10)],
                "rule": "слова на -ание/-ение/-ность и их формы; среди них есть "
                        "обычная лексика («решение», «значение») — смотреть глазами",
            },
            "status": "оценка",
            "note": "Список маркеров короткий и свой: подбор замен и полный разбор — "
                    "в deai_scan.py и references/ru-style.md. В договоре и научном "
                    "тексте канцелярит — норма жанра, не дефект.",
        },
        "passive": {
            "sentences_with_marker": len(passive_sent),
            "sentences_prose": len(sent_lengths),
            "pct": round(100 * len(passive_sent) / len(sent_lengths), 2)
                   if sent_lengths else None,
            "markers_top": [{"marker": m, "count": c} for m, c in passive_marks.most_common(10)],
            "status": "эвристика",
            "rule": "RU: «быть» + краткое причастие, глаголы на -ся (вместе с "
                    "возвратными — «нравится» тоже попадёт); EN: be/get + причастие "
                    "на -ed или из списка нерегулярных. Без разбора подлежащего "
                    "точной доли пассива не получить.",
        },
        "ngrams": repeated_ngrams(seg_lc),
        "zones": {
            name: {
                "title": ZONE_TITLES[name],
                "count": zones[name]["count"],
                "words": zones[name]["words"],
                "text": zones[name]["text"][:400] if name != "body" else None,
            }
            for name in ZONE_ORDER if name in zones
        },
        "zones_meta": zones["_meta"],
        "page_text": page_text_checks(zones, lang, prose_sentences),
        "masked": masked,
    }

    if keys:
        segments = seg_stems
        out_keys = []
        for key in keys:
            kw = letter_words(key)
            kw_lc = [_lc(w) for w in kw]
            kstems_full = [stem(w) for w in kw]
            kstems = [stem(w) for w in kw if not is_stop(w)] or kstems_full
            exact = sum(find_seq(seg, kstems) for seg in segments)
            forms = sum(find_seq(seg, kw_lc) for seg in seg_lc)
            window = sum(find_window(seg, kstems) for seg in segments)
            per = {s: sum(seg.count(s) for seg in segments) for s in dict.fromkeys(kstems)}
            by_zone = {}
            for name in ZONE_ORDER:
                if name not in zones or name == "body":
                    continue
                by_zone[name] = key_in_zone(zones[name], kw_lc, kstems, is_url=name == "url")
            by_zone["body"] = {
                "words": n_words,
                "exact_forms": forms,
                "morphological": exact,
                "any_order_window": window,
                "present": bool(forms or exact or window),
                "density_pct": round(100 * exact * len(kstems) / n_words, 2) if n_words else None,
            }
            out_keys.append({
                "key": key,
                "stems": kstems,
                "forms": kw_lc,
                "exact_forms": forms,
                "exact_by_stems": exact,
                "any_order_window": window,
                "per_stem": per,
                "density_pct": round(100 * exact * len(kstems) / n_words, 2) if n_words else 0,
                "density_formula": "слова, занятые прямыми вхождениями по основам / все слова, %",
                "match_rules": {
                    "exact_forms": "те же словоформы в том же порядке; знаки между "
                                   "словами не учитываются",
                    "morphological": "основы ключа подряд, служебные слова ключа "
                                     "отброшены: «купить диван» находит «купили диваны»",
                    "any_order_window": "все основы ключа в окне длиной ключ + 2 слова, "
                                        "в любом порядке",
                    "zone_scope": "в зонах вхождение не склеивается через границу "
                                  "элемента (заголовка, alt, ссылки); в body — через "
                                  "границу предложения",
                },
                "zones": by_zone,
                "zones_note": "Пустая зона — «нет данных» (например, title у Markdown), "
                              "а не «ключа нет»; смотрите zones_meta.",
                "missing_everywhere": not any(
                    v["present"] for v in by_zone.values()),
                "missing_rule": "ни одного вхождения ни в одной зоне: страница, "
                                "возможно, не про эту фразу — читать текст, а не "
                                "дописывать ключ",
                "concentration": {
                    "max_in_one_sentence": max((find_seq(seg, kstems) for seg in segments),
                                               default=0),
                    "adjacent_repeats": sum(find_seq(seg, kstems + kstems)
                                            for seg in segments),
                    "zones_with_key": sum(1 for z, v in by_zone.items()
                                          if z != "body" and v["present"]),
                    "zones_with_data": sum(1 for z, v in by_zone.items()
                                           if z != "body" and v["words"]),
                    "status": "оценка",
                    "note": "Набивка — это картина, а не процент: ключ подряд в одном "
                            "предложении и сразу во всех зонах. Порога нет; спам-политика "
                            "keyword stuffing описывает приём, а не долю "
                            "(facts-2026 §9).",
                },
                "cooccurrence": cooccurrence(segments, kstems),
            })
        report["keys"] = out_keys
    return report


def short_summary(r: dict) -> dict:
    c = r["counts"]
    scores = r.get("readability", {}).get("scores") or []
    return {
        "tool": r["tool"], "status": r["status"], "lang": r["lang"],
        "words": c["words"], "chars_no_spaces": c["chars_no_spaces"],
        "sentence_cv": r["rhythm"]["sentence_words"].get("cv"),
        "similar_runs": len(r["rhythm"]["similar_runs"]),
        "nausea_classic": r["nausea"]["classic"], "water_pct": r["water"]["stopword_pct"],
        "readability": {"name": scores[0]["name"], "value": scores[0]["value"],
                        "status": scores[0]["status"]} if scores else None,
        "self_repeat_pct": r.get("ngrams", {}).get("self_repeat_pct"),
        "passive_pct": r.get("passive", {}).get("pct"),
        "clerical_total": r.get("clerical", {}).get("total"),
        "keys": [{
            "key": k["key"],
            "exact_forms": k["exact_forms"],
            "morphological": k["exact_by_stems"],
            "density_pct": k["density_pct"],
            "zones_with_key": [z for z, v in k.get("zones", {}).items()
                               if z != "body" and v.get("present")],
            "zones_empty": [z for z, v in k.get("zones", {}).items()
                            if z != "body" and not v.get("words")],
        } for k in r.get("keys", [])],
    }


# ---------------------------------------------------------------- сравнение версий

_CMP_FIELDS: list[tuple[str, str, object]] = [
    ("words", "слова", lambda r: r["counts"]["words"]),
    ("chars_no_spaces", "знаки без пробелов", lambda r: r["counts"]["chars_no_spaces"]),
    ("sentences_prose", "предложения", lambda r: r["counts"]["sentences_prose"]),
    ("unique_stems", "уникальные основы", lambda r: r["counts"]["unique_stems"]),
    ("sentence_mean", "средняя длина предложения",
     lambda r: r["rhythm"]["sentence_words"].get("mean")),
    ("sentence_cv", "разброс длины (CV)", lambda r: r["rhythm"]["sentence_words"].get("cv")),
    ("similar_runs", "серии одной длины", lambda r: len(r["rhythm"]["similar_runs"])),
    ("nausea_classic", "тошнота классическая", lambda r: r["nausea"]["classic"]),
    ("nausea_academic_pct", "тошнота академическая, %",
     lambda r: r["nausea"]["academic_pct"]),
    ("water_pct", "вода, %", lambda r: r["water"]["stopword_pct"]),
    ("self_repeat_pct", "самоповтор фраз, %", lambda r: r["ngrams"]["self_repeat_pct"]),
    ("passive_pct", "предложения с маркером пассива, %", lambda r: r["passive"]["pct"]),
    ("clerical_total", "маркеры канцелярита", lambda r: r["clerical"]["total"]),
    ("readability", "читаемость",
     lambda r: (r["readability"]["scores"] or [{}])[0].get("value")),
]


def _delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return round(b - a, 2)
    return None


def compare(before: dict, after: dict) -> dict:
    """Что изменилось между двумя версиями. Сравнивать только одним скриптом."""
    metrics = []
    for fid, title, get in _CMP_FIELDS:
        try:
            a, b = get(before), get(after)
        except (KeyError, IndexError, TypeError):
            a = b = None
        metrics.append({"id": fid, "title": title, "before": a, "after": b,
                        "delta": _delta(a, b)})
    keys = []
    after_by_key = {k["key"]: k for k in after.get("keys", [])}
    for kb in before.get("keys", []):
        ka = after_by_key.get(kb["key"])
        if not ka:
            continue
        zones = []
        for zone in kb.get("zones", {}):
            za, zb = kb["zones"][zone], ka["zones"].get(zone, {})
            zones.append({
                "zone": zone,
                "before": {"exact_forms": za.get("exact_forms"),
                           "morphological": za.get("morphological")},
                "after": {"exact_forms": zb.get("exact_forms"),
                          "morphological": zb.get("morphological")},
                "changed": za.get("exact_forms") != zb.get("exact_forms")
                           or za.get("morphological") != zb.get("morphological"),
            })
        keys.append({
            "key": kb["key"],
            "exact_forms": {"before": kb["exact_forms"], "after": ka["exact_forms"],
                            "delta": _delta(kb["exact_forms"], ka["exact_forms"])},
            "morphological": {"before": kb["exact_by_stems"], "after": ka["exact_by_stems"],
                              "delta": _delta(kb["exact_by_stems"], ka["exact_by_stems"])},
            "density_pct": {"before": kb["density_pct"], "after": ka["density_pct"],
                            "delta": _delta(kb["density_pct"], ka["density_pct"])},
            "zones": zones,
        })
    sb = {s["stem"] for s in before.get("stems_top", [])}
    sa = {s["stem"] for s in after.get("stems_top", [])}
    return {
        "tool": "text_metrics",
        "version": VERSION,
        "mode": "compare",
        "status": "оценка",
        "note": NOTE,
        "lang": {"before": before.get("lang"), "after": after.get("lang")},
        "input": {"before": before.get("input"), "after": after.get("input")},
        "metrics": metrics,
        "keys": keys,
        "stems_top": {"appeared": sorted(sa - sb), "gone": sorted(sb - sa)},
        "compare_note": "Разница считается одним и тем же скриптом на одних и тех же "
                        "ключах. Знак разницы не говорит, что текст стал лучше или хуже: "
                        "это материал для редактора.",
    }


def compare_short(c: dict) -> dict:
    return {
        "tool": c["tool"], "mode": "compare", "status": c["status"],
        "changed": [{"title": m["title"], "before": m["before"], "after": m["after"],
                     "delta": m["delta"]} for m in c["metrics"] if m["delta"]],
        "keys": [{"key": k["key"], "exact_forms_delta": k["exact_forms"]["delta"],
                  "morphological_delta": k["morphological"]["delta"]} for k in c["keys"]],
    }


def parse_keys(values: list[str]) -> list[str]:
    out = []
    for v in values or []:
        for part in re.split(r"[;\n]", v):
            p = part.strip()
            if p:
                out.append(p)
    return out


def _one(path: str, keys: list[str], lang: str, html: bool, url: str | None) -> dict:
    raw = read_input(path)
    is_html = html or path.lower().endswith((".html", ".htm"))
    rep = analyze(raw, keys, lang, is_html, url)
    rep["input"] = "stdin" if path == "-" else os.path.basename(path)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Метрики текста RU/EN (оценка, не гейт).")
    ap.add_argument("path", nargs="?", help="файл (.md/.txt/.html) или - для stdin")
    ap.add_argument("--keys", action="append", default=[],
                    help="ключевые фразы через ; (можно повторять)")
    ap.add_argument("--lang", choices=["auto", "ru", "en"], default="auto")
    ap.add_argument("--html", action="store_true", help="вход — HTML (иначе по расширению)")
    ap.add_argument("--url", help="адрес страницы для зоны URL (иначе canonical или og:url)")
    ap.add_argument("--compare", nargs=2, metavar=("ДО", "ПОСЛЕ"),
                    help="сравнить две версии одного текста")
    ap.add_argument("--out", help="записать полный отчёт в этот файл .json")
    args = ap.parse_args(argv)
    try:
        if not args.path and not args.compare:
            raise ValueError("нужен путь к файлу или --compare ДО ПОСЛЕ")
        out = check_out_path(args.out) if args.out else None
        keys = parse_keys(args.keys)
        if args.compare:
            a = _one(args.compare[0], keys, args.lang, args.html, args.url)
            b = _one(args.compare[1], keys, args.lang, args.html, args.url)
            rep = compare(a, b)
            emit(rep, compare_short(rep), out)
            return 0
        rep = _one(args.path, keys, args.lang, args.html, args.url)
    except (ValueError, OSError) as exc:
        print(json.dumps({"tool": "text_metrics", "ok": False, "error": str(exc)},
                         ensure_ascii=False))
        return 2
    emit(rep, short_summary(rep), out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
