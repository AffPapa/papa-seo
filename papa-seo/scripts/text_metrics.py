#!/usr/bin/env python3
"""text_metrics.py — метрики текста RU/EN. Отчёт с пометкой «оценка», не гейт.

Считает: слова, знаки с пробелами и без (збп), предложения, разброс длины
предложений (CV), серии предложений одной длины, частоты основ (простой
стеммер RU/EN), «тошноту» по слову, оценку «воды» по доле служебных слов,
вхождения и плотность ключей по основам.

Только stdlib. Без сети, без subprocess/eval/exec. Читает один файл или stdin
(`-`), пишет JSON в stdout; полный отчёт — в файл `--out <путь>.json`.

    python3 scripts/text_metrics.py article.md --keys "купить диван; диван угловой"
    python3 scripts/text_metrics.py page.html --html --out metrics.json
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

VERSION = "0.1.0"
MAX_BYTES = 10 * 1024 * 1024
NOTE = (
    "Оценка, не гейт. Формулы сервисов (Advego, Text.ru и др.) не публичны, "
    "цифры с ними не совпадут. Сравнивайте версии одного текста этим же "
    "скриптом. Плотность ключа и «тошнота» не являются факторами ранжирования "
    "(см. references/folklore.md); переписывать хороший текст ради цифры не нужно."
)

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


def analyze(text: str, keys: list[str] | None = None, lang: str = "auto",
            is_html: bool = False) -> dict:
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
    for kind, t in blocks:
        if kind != "prose":
            continue
        sents = split_sentences(t)
        lens = [len(letter_words(s)) for s in sents]
        lens = [x for x in lens if x > 0]
        sent_lengths.extend(lens)
        para_lengths.append(sum(lens))

    content = [w for w in words if not is_stop(w) and len(w) > 1]
    stems_all = [stem(w) for w in words]
    stem_counts = Counter(stem(w) for w in content)
    surface: dict[str, Counter] = {}
    for w in content:
        surface.setdefault(stem(w), Counter())[w.lower()] += 1
    top = stem_counts.most_common(20)
    stop_n = n_words - len(content)
    top_count = top[0][1] if top else 0

    report = {
        "tool": "text_metrics",
        "version": VERSION,
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
            "formula": "доля служебных слов (предлоги, союзы, частицы, местоимения, "
                       "вводные) среди всех слов, % (оценка; у сервисов своя формула)",
        },
        "masked": masked,
    }

    if keys:
        segments: list[list[str]] = []
        for kind, t in blocks:
            parts = split_sentences(t) if kind == "prose" else [t]
            for part in parts:
                seg = [stem(w) for w in letter_words(part) if not is_stop(w)]
                if seg:
                    segments.append(seg)
        out_keys = []
        for key in keys:
            kw = letter_words(key)
            kstems_full = [stem(w) for w in kw]
            kstems = [stem(w) for w in kw if not is_stop(w)] or kstems_full
            exact = sum(find_seq(seg, kstems) for seg in segments)
            window = sum(find_window(seg, kstems) for seg in segments)
            per = {s: sum(seg.count(s) for seg in segments) for s in dict.fromkeys(kstems)}
            out_keys.append({
                "key": key,
                "stems": kstems,
                "exact_by_stems": exact,
                "any_order_window": window,
                "per_stem": per,
                "density_pct": round(100 * exact * len(kstems) / n_words, 2) if n_words else 0,
                "density_formula": "слова, занятые прямыми вхождениями по основам / все слова, %",
            })
        report["keys"] = out_keys
    return report


def short_summary(r: dict) -> dict:
    c = r["counts"]
    return {
        "tool": r["tool"], "status": r["status"], "lang": r["lang"],
        "words": c["words"], "chars_no_spaces": c["chars_no_spaces"],
        "sentence_cv": r["rhythm"]["sentence_words"].get("cv"),
        "similar_runs": len(r["rhythm"]["similar_runs"]),
        "nausea_classic": r["nausea"]["classic"], "water_pct": r["water"]["stopword_pct"],
        "keys": [{"key": k["key"], "exact": k["exact_by_stems"], "density_pct": k["density_pct"]}
                 for k in r.get("keys", [])],
    }


def parse_keys(values: list[str]) -> list[str]:
    out = []
    for v in values or []:
        for part in re.split(r"[;\n]", v):
            p = part.strip()
            if p:
                out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Метрики текста RU/EN (оценка, не гейт).")
    ap.add_argument("path", help="файл (.md/.txt/.html) или - для stdin")
    ap.add_argument("--keys", action="append", default=[],
                    help="ключевые фразы через ; (можно повторять)")
    ap.add_argument("--lang", choices=["auto", "ru", "en"], default="auto")
    ap.add_argument("--html", action="store_true", help="вход — HTML (иначе по расширению)")
    ap.add_argument("--out", help="записать полный отчёт в этот файл .json")
    args = ap.parse_args(argv)
    try:
        out = check_out_path(args.out) if args.out else None
        raw = read_input(args.path)
        is_html = args.html or args.path.lower().endswith((".html", ".htm"))
        rep = analyze(raw, parse_keys(args.keys), args.lang, is_html)
        rep["input"] = "stdin" if args.path == "-" else os.path.basename(args.path)
    except (ValueError, OSError) as exc:
        print(json.dumps({"tool": "text_metrics", "ok": False, "error": str(exc)},
                         ensure_ascii=False))
        return 2
    emit(rep, short_summary(rep), out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
