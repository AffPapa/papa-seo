#!/usr/bin/env python3
"""deai_scan.py — признаки машинного текста RU/EN для редактора. Без балла «человечности».

Ищет: невидимые и bidi-символы, скрытые обращения к модели (HTML-комментарии,
теги Unicode), остатки чат-бота и разметки ассистентов, штампы и канцелярит
(словарь свой), пустые противопоставления, повтор зачинов, серии предложений
одной длины, плотность тире и «является», смешение кавычек, Title Case
в русских заголовках. Код, инлайн-код и цитаты (строки с `>`) не сканируются.

Сила признака: strong — править с одного попадания; medium — править, если
не оправдан смыслом; weak — только в кластере с другими; info — справка.
Это список мест для чтения, а не вердикт об авторстве и не цель для детектора.

Только stdlib, без сети, без subprocess/eval/exec.

    python3 scripts/deai_scan.py draft.md
    python3 scripts/deai_scan.py draft.md --genre news --out scan.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ru_text  # noqa: E402

_plural = ru_text.plural
_qty = ru_text.num

VERSION = "0.1.0"
MAX_BYTES = 10 * 1024 * 1024
STDOUT_HITS = 60
NOTE = (
    "Признаки для чтения, не балл и не вероятность ИИ. Одно попадание weak/medium "
    "ничего не доказывает — смотрите кластеры. Грамотный, ровный, формальный текст "
    "не улика. Детекторы ИИ — не цель. Грамматическое тире по-русски обязательно, "
    "считается только плотность."
)
GENRES = ("marketing", "expert", "business", "docs", "news", "academic", "legal", "fiction")

# ---------------------------------------------------------------- dictionaries
# (regex, id, strength, hint). Списки составлены для этого пакета.

CHAT_RESIDUE = [
    (r"\bкак (?:языковая |большая языковая |ии[- ]|ai[- ])?модель\b", "как модель"),
    (r"\bкак искусственный интеллект\b", "как ИИ"),
    (r"\bнадеюсь,? (?:это|мой ответ|информация) (?:поможет|помог|было полезн|будет полезн)", "надеюсь, поможет"),
    (r"\bнадеюсь,? помог(?:ла)?\b", "надеюсь, помог"),
    (r"\bесли у вас (?:остались|возникнут|появятся|есть) (?:ещё |еще |какие-либо )?вопросы", "если остались вопросы"),
    (r"\bотличный вопрос\b", "отличный вопрос"),
    (r"\bконечно[!,.] вот\b", "конечно, вот"),
    (r"\bвот (?:переработанный|исправленный|улучшенный|отредактированный|обновл[её]нный) (?:вариант|текст|версия)", "вот вариант"),
    (r"\bне стесняйтесь (?:обращаться|спрашивать|задавать)", "не стесняйтесь"),
    (r"\bна момент (?:моего )?(?:последнего )?обновления (?:моих )?(?:знаний|данных)", "граница знаний"),
    (r"\bу меня нет доступа к (?:интернету|актуальн|реальн)", "нет доступа"),
    (r"\bas an ai(?: language)? model\b", "as an AI model"),
    (r"\bi hope this (?:helps|was helpful)\b", "I hope this helps"),
    (r"\bgreat question\b", "great question"),
    (r"\bcertainly!? here(?:'s| is)\b", "certainly, here"),
    (r"\bsure!? here(?:'s| is)\b", "sure, here"),
    (r"\bhere(?:'s| is) (?:a|the) (?:revised|rewritten|polished|updated|improved) version\b", "here's a revised version"),
    (r"\blet me know if you (?:have|need|would|want)\b", "let me know if"),
    (r"\bfeel free to (?:ask|reach out)\b", "feel free to"),
    (r"\bas of my (?:last )?(?:knowledge|training) (?:update|cutoff)\b", "knowledge cutoff"),
    (r"\bi (?:don't|do not|cannot|can't) (?:browse|access) the (?:internet|web)\b", "cannot browse"),
]

# Идея ловить следы разметки ассистентов — из smixs/humanizer-ru (MIT, © 2026 Serge Shima),
# который ссылается на Vladimir-Human/humanizer-ru. Регулярки ниже написаны заново.
MARKUP_RESIDUE = [
    (r":contentReference\[oaicite:\d+\](?:\{[^}]*\})?|\boaicite:\d+|\boai_citation\b", "oaicite"),
    (r"\bturn\d+(?:search|file|fetch|news|image|view|product)\d+\b|\bciteturn\w*", "turnNsearchN"),
    (r"utm_source=(?:chatgpt\.com|openai|copilot\.com|perplexity)", "utm чат-бота"),
    (r"【\d+(?::\d+)?†[^】]{0,80}】", "сноска 【†】"),
    (r"sandbox:/mnt/data/", "sandbox:/mnt/data"),
    (r"ppl-ai-file-upload", "perplexity upload"),
    (r"</?think>", "тег think"),
]

STAMPS_RU = [
    (r"\bв (?:современном мире|современных реалиях|наше время|наши дни|эпоху \w+)", "пустой зачин", "начать с факта из текста"),
    (r"\bв условиях (?:растущ|высок|жёстк|жестк|современн|постоянн|быстро)\w* \w+", "пустой зачин", "начать с факта"),
    (r"\b(?:стоит|следует|важно|необходимо) (?:от|под)?(?:метить|черкнуть|понимать|помнить|учитывать),? что\b", "подводка", "убрать подводку, оставить утверждение"),
    (r"\bигра(?:ет|ют|л[аио]?) (?:ключев|важн|решающ|значим|огромн|центральн)\w* рол", "играет роль", "сказать, что именно делает, если это есть в тексте"),
    (r"\bнеотъемлем\w* част", "неотъемлемая часть", "убрать или назвать связь"),
    (r"\bраскры\w* (?:весь |свой |ваш )?потенциал", "раскрыть потенциал", "назвать результат или удалить"),
    (r"\bна (?:новый|качественно новый|следующий) уровень\b", "новый уровень", "назвать результат или удалить"),
    (r"\bоткрыва\w* (?:новые |широкие )?(?:горизонты|перспективы|возможности)", "новые горизонты", "назвать, какие, или удалить"),
    (r"\bкомплексн\w* (?:подход|решени)", "комплексный подход", "перечислить, что входит"),
    (r"\bиндивидуальн\w* подход", "индивидуальный подход", "сказать, в чём он, или удалить"),
    (r"\bвысококвалифицированн\w* (?:специалист|сотрудник|мастер)", "высококвалифицированные", "квалификация — фактом (стаж, допуск) или удалить"),
    (r"\bв кратчайшие сроки\b", "кратчайшие сроки", "срок цифрой или удалить"),
    (r"\bни для кого не секрет\b|\bне секрет, что\b", "не секрет", "удалить"),
    (r"\bна сегодняшний день\b", "на сегодняшний день", "«сейчас» или дата"),
    (r"\bзалог (?:успеха|качества|надёжности|надежности)\b", "залог успеха", "удалить"),
    (r"\bдавайте (?:разбер[её]мся|рассмотрим|посмотрим|погрузимся|начн[её]м)", "давайте разберёмся", "сразу к сути"),
    (r"\bпогрузи(?:мся|тесь) в\b", "погрузимся", "сразу к сути"),
    (r"\bподводя (?:итог|черту)\b|\bв заключение,|\bитак, подвед", "формульный вывод", "закончить, когда кончилось содержание"),
    (r"\b(?:уникальн|инновационн|передов|революционн)\w* (?:решени|технологи|подход|продукт|сервис)", "рекламное клише", "заменить фактом или удалить"),
    (r"\bидеальн\w* (?:решени|выбор|вариант)\b", "идеальное решение", "для кого и почему — или удалить"),
    (r"\bнастоящ\w* (?:прорыв|открыти|находк)", "настоящий прорыв", "удалить оценку без основания"),
    (r"\b(?:можно )?с уверенностью (?:можно )?сказать\b", "с уверенностью сказать", "сказать без преамбулы"),
    (r"\bширок\w* (?:спектр|ассортимент|выбор|линейк)", "широкий спектр", "перечислить или удалить"),
    (r"\bгармоничн\w* сочета|\bгармони\w* (?:вкуса|стиля|формы)", "гармония", "удалить"),
    (r"\bмы рады (?:предложить|представить|приветствовать)", "мы рады", "сразу к предложению"),
    (r"\bлидер\w* (?:рынка|отрасли|индустрии)\b", "лидер рынка", "доказать источником или удалить"),
    (r"\b(?:эксперты|специалисты|учёные|ученые|аналитики) (?:считают|отмечают|уверены|утверждают|сходятся)", "размытый авторитет", "назвать источник или убрать"),
    (r"\bисследования (?:показывают|доказывают|подтверждают)\b", "размытый авторитет", "назвать исследование или убрать"),
    (r"\bвсё больше и больше\b|\bвсе больше и больше\b", "всё больше и больше", "цифра с источником или удалить"),
]

BUREAU_RU = [
    (r"\bданн(?:ый|ая|ое|ого|ой|ому|ом|ую)\b", "данный", "этот / эта / это"),
    (r"\bосуществ\w+", "осуществлять", "глагол действия"),
    (r"\bв рамках\b", "в рамках", "предлог или перестройка"),
    (r"\bв целях\b", "в целях", "«чтобы» / «для»"),
    (r"\bпосредством\b", "посредством", "«через» / «с помощью»"),
    (r"\bв связи с этим\b", "в связи с этим", "показать связь словами текста или убрать"),
    (r"\b(?:производится|проводится|осуществляется) (?:\w+ )?(?:установк|настройк|провер|оплат|доставк)\w*", "канцелярский пассив", "кто что делает — глаголом"),
]

PARALLEL_RU = [
    (r"\bне просто\b[^.!?\n]{1,80}?,\s*(?:а|но)\b", "не просто X, а Y", "оставить, только если X и Y разные факты"),
    (r"\bне только\b[^.!?\n]{1,80}?,\s*но и\b", "не только X, но и Y", "оставить, только если X и Y разные факты"),
    (r"\bэто не (?:просто |только )?\w+[^.!?\n]{0,40}?[,—–-]\s*это\b", "это не X, это Y", "сказать одно, что имеется в виду"),
]

STAMPS_EN = [
    (r"\bdelv(?:e|es|ed|ing) (?:into|deeper)\b", "delve into", "say what you examine"),
    (r"\btapestry\b", "tapestry", "name the thing"),
    (r"\b(?:a |is a |stands as a )?testament to\b", "testament to", "state the fact"),
    (r"\bin today's (?:fast-paced |digital |modern |ever-changing )?(?:world|landscape|age|era|market)\b", "in today's world", "start with the fact"),
    (r"\bit(?:'s| is) (?:important|worth|crucial) (?:to note|noting|to remember|to understand)\b", "it's worth noting", "cut the lead-in"),
    (r"\bplays? an? (?:crucial|pivotal|vital|key|important|significant) role\b", "plays a crucial role", "say what it does"),
    (r"\bunlock(?:s|ing)? (?:the|your|its) (?:full |true )?potential\b", "unlock potential", "name the result or cut"),
    (r"\bnavigat(?:e|es|ing) the (?:complexities|landscape|world|challenges)\b", "navigate the complexities", "say what to do"),
    (r"\bin the (?:realm|world) of\b", "in the realm of", "cut"),
    (r"\belevate (?:your|the)\b", "elevate your", "say how"),
    (r"\bgame[- ]?changer\b", "game-changer", "say what changed"),
    (r"\blet's (?:dive|delve|take a (?:closer |deep )?look)\b", "let's dive in", "start with the point"),
    (r"\bin (?:conclusion|summary)\b|\bto sum up\b", "formula conclusion", "end when the content ends"),
    (r"\bharness(?:es|ing)? the (?:power|potential)\b", "harness the power", "say how"),
    (r"\ba (?:myriad|plethora) of\b", "a myriad of", "a number or 'many'"),
    (r"\b(?:cutting-edge|state-of-the-art|ever-evolving|best-in-class|world-class)\b", "inflated adjective", "fact or cut"),
    (r"\bseamless(?:ly)?\b", "seamless", "the fact it stands for"),
    (r"\brobust\b", "robust", "the fact it stands for"),
    (r"\bpivotal\b", "pivotal", "plain word"),
    (r"\bembark(?:s|ed|ing)? on\b", "embark on", "start"),
    (r"\brest assured\b|\blook no further\b", "sales cliché", "cut"),
    (r"\bexperts (?:say|agree|believe)\b|\bstudies (?:show|suggest)\b", "vague authority", "name the source or cut"),
    (r"\bnot only\b[^.!?\n]{1,80}?\bbut (?:also)?\b", "not only X but also Y", "keep only if X and Y differ"),
    (r"\bit(?:'s| is) not (?:just |only )?(?:about )?\w+[^.!?\n]{0,40}?[,;—–-]\s*it(?:'s| is)\b", "it's not X, it's Y", "say the one thing"),
]

INSTR_RE = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above)|disregard (?:the |all )?(?:previous|above)|"
    r"system prompt|you are (?:now )?(?:an? |the )?(?:ai|assistant|model|llm|agent)|"
    r"\bassistant\s*:|\bsystem\s*:|игнорируй|проигнорируй|забудь (?:все |предыдущие )?инструкц|"
    r"системн\w* (?:промпт|инструкц)|ты (?:теперь )?(?:ии|ассистент|модель|агент)|"
    r"\.env\b|api[_ -]?key|выполни (?:команду|код)|run (?:the following|this) command|"
    r"curl |wget |rm -rf|прочитай (?:файл|\.env)|read (?:the )?(?:file|\.env)",
    re.I,
)

INVISIBLE = {
    0x200B: "ZERO WIDTH SPACE", 0x200C: "ZERO WIDTH NON-JOINER", 0x200D: "ZERO WIDTH JOINER",
    0x2060: "WORD JOINER", 0xFEFF: "ZERO WIDTH NO-BREAK SPACE (BOM)", 0x180E: "MONGOLIAN VOWEL SEPARATOR",
    0x202A: "LRE", 0x202B: "RLE", 0x202C: "PDF", 0x202D: "LRO", 0x202E: "RLO",
    0x2066: "LRI", 0x2067: "RLI", 0x2068: "FSI", 0x2069: "PDI", 0x200E: "LRM", 0x200F: "RLM",
}

FENCE_RE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
LIST_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+")
TABLE_RE = re.compile(r"^\s*\|")
QUOTE_RE = re.compile(r"^\s*>")
WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")
SENT_END = re.compile(r"([.!?…]+)([\"»”’)\]]*)\s+(?=[«\"„“(\[]?[^\W\d_]|\d)")
ABBR = {"т.е", "т.к", "т.д", "т.п", "т.н", "др", "г", "гг", "им", "ул", "стр", "рис", "см",
        "тыс", "млн", "млрд", "руб", "проф", "напр", "e.g", "i.e", "mr", "mrs", "dr", "vs", "etc"}

# ---------------------------------------------------------------- io helpers


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
    return data.decode("utf-8", errors="replace")


def check_out_path(path: str) -> str:
    if "\x00" in path or not path.lower().endswith(".json"):
        raise ValueError("--out: нужен путь к файлу .json")
    ap = os.path.abspath(path)
    if os.path.islink(ap) or os.path.isdir(ap):
        raise ValueError("--out: путь — каталог или символическая ссылка")
    if not os.path.isdir(os.path.dirname(ap)):
        raise ValueError("--out: каталог для файла не существует")
    return ap


# ---------------------------------------------------------------- helpers


def _blank(m: re.Match) -> str:
    """Заменить совпадение пробелами, сохранив переводы строк (позиции не съезжают)."""
    return re.sub(r"[^\n]", " ", m.group(0))


def line_col(text: str, pos: int) -> tuple[int, int]:
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def detect_lang(text: str) -> str:
    cyr = sum(1 for ch in text if ("а" <= ch.lower() <= "я") or ch in "ёЁ")
    lat = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    if not cyr and not lat:
        return "unknown"
    return "ru" if cyr >= lat else "en"


def split_sentences(block: str) -> list[str]:
    out, start = [], 0
    for m in SENT_END.finditer(block):
        prev = block[start:m.start(1)]
        if m.group(1) == ".":
            w = re.search(r"([^\W\d_]+(?:\.[^\W\d_]+)*)$", prev)
            if w and (w.group(1).lower() in ABBR or len(w.group(1)) == 1):
                continue
        s = block[start:m.end(1) + len(m.group(2))].strip()
        if s:
            out.append(s)
        start = m.end()
    tail = block[start:].strip()
    if tail:
        out.append(tail)
    return out


def paragraphs(text: str) -> list[tuple[int, str, str]]:
    """[(start_offset, kind, text)] для prose-абзацев, заголовков и пунктов списков."""
    out: list[tuple[int, str, str]] = []
    pos, cur, cur_start = 0, [], None
    for line in text.split("\n"):
        stripped = line.strip()
        start = pos
        pos += len(line) + 1
        special = HEADING_RE.match(line) or LIST_RE.match(line) or TABLE_RE.match(line)
        if not stripped or special:
            if cur:
                out.append((cur_start, "prose", " ".join(cur)))
                cur, cur_start = [], None
            if special and stripped:
                kind = "heading" if HEADING_RE.match(line) else ("list" if LIST_RE.match(line) else "table")
                out.append((start, kind, stripped))
            continue
        if cur_start is None:
            cur_start = start
        cur.append(stripped)
    if cur:
        out.append((cur_start, "prose", " ".join(cur)))
    return out


# ---------------------------------------------------------------- scan


def scan(raw: str, genre: str = "marketing", lang: str = "auto") -> dict:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    hits: list[dict] = []

    def add(kind, strength, pos, match, hint, extra=None, src=None):
        ln, col = line_col(src if src is not None else text, pos)
        h = {"id": kind, "strength": strength, "line": ln, "col": col,
             "match": match[:120], "hint": hint, "_pos": pos}
        if extra:
            h.update(extra)
        hits.append(h)

    # 1. Невидимые символы и теги Unicode — по сырому тексту, включая код.
    tag_run: list[tuple[int, str]] = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if 0xE0000 <= cp <= 0xE007F:
            tag_run.append((i, chr(cp - 0xE0000) if 0xE0020 <= cp <= 0xE007E else ""))
            continue
        if tag_run:
            decoded = "".join(c for _, c in tag_run)
            add("hidden_instruction", "strong", tag_run[0][0],
                _qty(len(tag_run), "тег-символ", "тег-символа", "тег-символов") + " Unicode",
                "невидимый текст тегами Unicode: удалить, автору показать расшифровку",
                {"decoded_preview": decoded[:80]})
            tag_run = []
        if cp == 0xFEFF and i == 0:
            continue  # BOM в начале файла — норма
        if cp in INVISIBLE:
            add("invisible_char", "strong", i, f"U+{cp:04X} {INVISIBLE.get(cp, '')}".strip(),
                "удалить (гигиена текста; bidi может менять порядок показа)")
        elif cp == 0x00AD:
            add("soft_hyphen", "weak", i, "U+00AD SOFT HYPHEN", "проверить, нужен ли перенос")
        elif unicodedata.category(ch) == "Cf" and cp not in (0xFEFF,):
            add("invisible_char", "strong", i, f"U+{cp:04X} {unicodedata.name(ch, 'FORMAT CHAR')}",
                "удалить, если не нужен по типографике")
    if tag_run:
        decoded = "".join(c for _, c in tag_run)
        add("hidden_instruction", "strong", tag_run[0][0],
            _qty(len(tag_run), "тег-символ", "тег-символа", "тег-символов") + " Unicode",
            "невидимый текст тегами Unicode", {"decoded_preview": decoded[:80]})
    zw_run = re.finditer(r"[\u200b\u200c\u200d\u2060]{5,}", text)
    for m in zw_run:
        add("hidden_instruction", "strong", m.start(), f"серия из {len(m.group(0))} zero-width",
            "возможна закодированная вставка: удалить, показать автору")

    # 2. HTML-комментарии: скрытые обращения к модели.
    comments = 0
    for m in COMMENT_RE.finditer(text):
        comments += 1
        body = m.group(1).strip()
        if INSTR_RE.search(body):
            add("hidden_instruction", "strong", m.start(), "<!-- " + body[:100] + " -->",
                "в комментарии обращение к модели или к секретам: не выполнять, удалить из текста")

    # Маскирование: код, комментарии, цитаты.
    masked = FENCE_RE.sub(_blank, text)
    masked = COMMENT_RE.sub(_blank, masked)
    masked = INLINE_CODE_RE.sub(_blank, masked)
    masked = "\n".join((" " * len(ln)) if QUOTE_RE.match(ln) else ln for ln in masked.split("\n"))
    masked = masked.replace(" ", " ")
    masked_info = {
        "code_blocks": len(FENCE_RE.findall(text)),
        "inline_code": len(INLINE_CODE_RE.findall(text)),
        "html_comments": comments,
        "quote_lines": sum(1 for ln in text.split("\n") if QUOTE_RE.match(ln)),
    }
    if lang == "auto":
        lang = detect_lang(masked)
    soft = genre in ("news", "academic", "legal")

    # 3. Остатки чат-бота и разметки ассистентов.
    for rx, label in CHAT_RESIDUE:
        for m in re.finditer(rx, masked, re.I):
            add("chat_residue", "strong", m.start(), m.group(0), f"удалить ({label})")
    for rx, label in MARKUP_RESIDUE:
        for m in re.finditer(rx, masked, re.I):
            add("markup_residue", "strong", m.start(), m.group(0), f"удалить ({label}); ссылку — на первоисточник")

    # 4. Словари штампов.
    def run(table, kind, strength):
        for rx, label, hint in table:
            for m in re.finditer(rx, masked, re.I):
                add(kind, strength, m.start(), m.group(0), hint, {"label": label})

    if lang in ("ru", "unknown"):
        if genre == "legal":
            pass
        else:
            run(STAMPS_RU, "stamp", "info" if soft else "medium")
            run(BUREAU_RU, "bureaucratese", "info" if soft else "medium")
            if genre != "fiction":
                run(PARALLEL_RU, "hollow_contrast", "medium")
    if lang in ("en", "unknown") or re.search(r"[A-Za-z]{4,}", masked):
        if genre != "legal":
            run(STAMPS_EN, "stamp_en", "info" if soft else "medium")

    # 5. Структура: абзацы, предложения, зачины, ритм.
    paras = paragraphs(masked)
    words_total = len(WORD_RE.findall(masked))
    sentence_lengths: list[int] = []
    runs = []
    for p_index, (start, kind, ptext) in enumerate(paras):
        if kind == "heading" and lang == "ru":
            title = HEADING_RE.match(ptext).group(1) if HEADING_RE.match(ptext) else ptext
            ws = [w for w in WORD_RE.findall(title) if len(w) > 3]
            if len(ws) >= 3 and all(w[0].isupper() for w in ws) and not all(w.isupper() for w in ws):
                add("title_case_ru", "weak", start, title, "в русском заглавная только первая и имена")
        if kind != "prose":
            continue
        sents = split_sentences(ptext)
        lens = [len(WORD_RE.findall(s)) for s in sents]
        sentence_lengths.extend(lens)
        firsts = [(WORD_RE.findall(s) or [""])[0].lower() for s in sents]
        c = Counter(f for f in firsts if f)
        for w, k in c.items():
            if k >= 3 and len(sents) >= 3:
                add("repeated_opening", "medium", start, f"«{w}…» ×{k} в абзаце",
                    "разнообразить зачины, если повтор не намеренный (анафора)",
                    {"paragraph": p_index + 1})
        i = 0
        while i < len(lens):
            j = i
            while j + 1 < len(lens):
                win = lens[i:j + 2]
                if min(win) >= 5 and (max(win) - min(win)) / max(win) <= 0.2:
                    j += 1
                else:
                    break
            if j - i + 1 >= 3:
                runs.append({"paragraph": p_index + 1, "lengths": lens[i:j + 1]})
                add("rhythm_run", "weak", start,
                    f"{_qty(j - i + 1, 'предложение', 'предложения', 'предложений')} подряд "
                    f"по {lens[i:j + 1]} слов",
                    "сломать серию перестановкой, не добавлением слов", {"paragraph": p_index + 1})
                i = j + 1
            else:
                i += 1
        triads = re.findall(r"\b[^\W\d_]+, [^\W\d_]+,? (?:и|and) [^\W\d_]+\b", ptext)
        if len(triads) >= 2:
            add("triads", "weak", start,
                f"{_qty(len(triads), 'перечень', 'перечня', 'перечней')} из трёх в абзаце",
                "оставить, если перечень настоящий; искусственные тройки — до двух или четырёх",
                {"paragraph": p_index + 1})

    # 6. Плотности (info): тире, «является», отглагольные, кавычки.
    dashes = len(re.findall(r"\s[—–]\s|[—]", masked))
    jav = len(re.findall(r"\bявля(?:ется|ются|лся|лась|лось|лись)\b", masked, re.I))
    nomin = len(re.findall(r"\b[^\W\d_]{4,}(?:ение|ание|ация|ирование)\b", masked, re.I))
    per1k = (lambda n: round(1000 * n / words_total, 2) if words_total else 0)
    if lang == "ru" and "«" in masked and re.search(r'"[^"\n]{2,60}"', masked):
        add("quote_mix", "weak", masked.find('"'), 'и «ёлочки», и "прямые"', "привести кавычки к одному виду")
    if jav and not soft:
        add("javlyaetsya_density", "weak", 0, f"«является» ×{jav} ({per1k(jav)} на 1000 слов)",
            "перестроить, где это связка без смысла; терминологическое «является» оставить")

    sd = statistics.pstdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
    mean = statistics.fmean(sentence_lengths) if sentence_lengths else 0.0
    para_by_hits: Counter = Counter()
    for h in hits:
        if h["strength"] in ("medium", "weak") and "paragraph" not in h:
            for idx, (start, kind, _t) in enumerate(paras):
                nxt = paras[idx + 1][0] if idx + 1 < len(paras) else len(masked) + 1
                if start <= h["_pos"] < nxt:
                    h["paragraph"] = idx + 1
                    break
        if h["strength"] in ("medium", "weak") and "paragraph" in h:
            para_by_hits[h["paragraph"]] += 1
    clusters = [{"paragraph": p, "hits": n} for p, n in sorted(para_by_hits.items()) if n >= 3]

    for h in hits:
        h.pop("_pos", None)
    by_strength = Counter(h["strength"] for h in hits)
    by_id = Counter(h["id"] for h in hits)
    return {
        "tool": "deai_scan",
        "version": VERSION,
        "note": NOTE,
        "lang": lang,
        "genre": genre,
        "summary": {
            "strong": by_strength.get("strong", 0),
            "medium": by_strength.get("medium", 0),
            "weak": by_strength.get("weak", 0),
            "info": by_strength.get("info", 0),
            "by_id": dict(by_id),
            "clusters": clusters,
        },
        "densities": {
            "words": words_total,
            "dashes": dashes,
            "dashes_per_1000_words": per1k(dashes),
            "javlyaetsya": jav,
            "nominalizations_per_1000_words": per1k(nomin),
            "note": "Справка. Порогов нет: тире и отглагольные решает чтение и регистр.",
        },
        "rhythm": {
            "sentences": len(sentence_lengths),
            "mean_words": round(mean, 2),
            "cv": round(sd / mean, 3) if mean else None,
            "similar_runs": runs,
        },
        "masked": masked_info,
        "hits": hits,
    }



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Признаки машинного текста RU/EN (без балла).")
    ap.add_argument("path", help="файл (.md/.txt) или - для stdin")
    ap.add_argument("--genre", choices=GENRES, default="marketing",
                    help="регистр: в news/academic штампы и канцелярит — info, в legal не ищутся")
    ap.add_argument("--lang", choices=["auto", "ru", "en"], default="auto")
    ap.add_argument("--out", help="полный отчёт в этот файл .json")
    args = ap.parse_args(argv)
    try:
        out = check_out_path(args.out) if args.out else None
        rep = scan(read_input(args.path), args.genre, args.lang)
        rep["input"] = "stdin" if args.path == "-" else os.path.basename(args.path)
    except (ValueError, OSError) as exc:
        print(json.dumps({"tool": "deai_scan", "ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        print(json.dumps({"tool": "deai_scan", "summary": rep["summary"], "out": out}, ensure_ascii=False))
    else:
        if len(rep["hits"]) > STDOUT_HITS:
            rep["hits_truncated"] = len(rep["hits"]) - STDOUT_HITS
            rep["hits"] = rep["hits"][:STDOUT_HITS]
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
