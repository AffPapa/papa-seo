#!/usr/bin/env python3
"""factdiff.py — сохранность фактов при правке: что пропало и что появилось.

Сравнивает две версии текста (до / после) по категориям: числа, проценты,
деньги, даты, URL, e-mail, имена собственные (последовательности слов
с заглавной, аббревиатуры, названия в «ёлочках»), оговорки при фактах
(«около», «до 5000», «обычно», «если», «up to», «may»…) и счётчик отрицаний.
Сравнение — как мультимножества: «5 000» и «5000» одно и то же, «Яндекса»
и «Яндекс» одно имя (грубая основа). Числа словами («пять тысяч») не видит.

Только stdlib, без сети, без subprocess/eval/exec.

    python3 scripts/factdiff.py before.md after.md
    python3 scripts/factdiff.py before.md after.md --out diff.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

VERSION = "0.1.0"
MAX_BYTES = 10 * 1024 * 1024
NOTE = (
    "Список мест для сверки, не вердикт. «Пропало» — проверить, не потерян ли факт "
    "или оговорка; «появилось» — проверить, есть ли у нового источник. Перефраз "
    "без потери смысла допустим. Числа словами и смысловые сдвиги («риск» → "
    "«придётся») скрипт не видит — их сверяет человек."
)

MONTHS_RU = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
             "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
MONTHS_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
             "sep": 9, "oct": 10, "nov": 11, "dec": 12}
RU_MONTH_RX = r"(январ[ьяе]|феврал[ьяе]|март[ае]?|апрел[ьяе]|ма[йяе]|июн[ьяе]|июл[ьяе]|август[ае]?|сентябр[ьяе]|октябр[ьяе]|ноябр[ьяе]|декабр[ьяе])"
EN_MONTH_RX = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

NUM = r"[-+−]?\d{1,3}(?:[ ]\d{3})+(?:[.,]\d+)?|[-+−]?\d+(?:[.,]\d+)?"
MULT = r"(тыс\.?|тысяч\w*|млн\.?|миллион\w*|млрд\.?|миллиард\w*|k\b|m\b|bn\b|thousand|million|billion)"
CURRENCY = r"(₽|руб\.?|рубл\w*|\$|usd|долл\w*|€|eur|евро|£|usdt|btc|₸|тенге|грн|₴)"

URL_RE = re.compile(r"https?://[^\s<>()\"'«»\]]+", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
ISO_DATE_RE = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
DOT_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.((?:19|20)?\d{2})\b")
RU_DATE_RE = re.compile(r"\b(\d{1,2})\s+" + RU_MONTH_RX + r"(?:\s+((?:19|20)\d{2})(?:\s*г(?:ода|\.)?)?)?", re.I)
EN_DATE1_RE = re.compile(r"\b" + EN_MONTH_RX + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b", re.I)
EN_DATE2_RE = re.compile(r"\b(\d{1,2})\s+" + EN_MONTH_RX + r"\.?,?\s+((?:19|20)\d{2})\b", re.I)
MONEY_RE = re.compile(
    r"(?:(?P<c1>" + CURRENCY + r")\s?(?P<n1>" + NUM + r")(?:\s?(?P<m1>" + MULT + r"))?)"
    r"|(?:(?P<n2>" + NUM + r")(?:\s?(?P<m2>" + MULT + r"))?\s?(?P<c2>" + CURRENCY + r"))", re.I)
PERCENT_RE = re.compile(r"(?P<n>" + NUM + r")\s?(?:%|процент\w*|п\.\s?п\.|percent\b)", re.I)
NUMBER_RE = re.compile(r"(?<![\w.,])(?P<n>" + NUM + r")(?:\s?(?P<m>" + MULT + r"))?(?![\w])", re.I)

HEDGES_RU = [
    r"около", r"примерно", r"приблизительно", r"порядка", r"почти", r"не более", r"не менее",
    r"не больше", r"не меньше", r"свыше", r"более чем", r"менее чем", r"обычно", r"часто",
    r"иногда", r"как правило", r"может быть", r"возможно", r"вероятно", r"скорее всего",
    r"только", r"лишь", r"если", r"при условии", r"по данным", r"по оценк\w+", r"ожида\w+",
    r"планиру\w+", r"один из", r"одна из", r"одно из", r"риск\w*", r"может", r"могут",
    r"до(?=\s?\d)", r"от(?=\s?\d)", r"более(?=\s?\d)", r"менее(?=\s?\d)",
]
HEDGES_EN = [
    r"about", r"approximately", r"around", r"roughly", r"nearly", r"almost", r"up to",
    r"at least", r"at most", r"more than", r"less than", r"usually", r"often", r"sometimes",
    r"typically", r"may", r"might", r"could", r"possibly", r"likely", r"only", r"if", r"unless",
    r"according to", r"estimated", r"expected", r"planned", r"one of", r"over(?=\s?\$?\d)",
    r"under(?=\s?\$?\d)",
]
HEDGE_RE = re.compile(r"(?<![\w-])(" + "|".join(HEDGES_RU + HEDGES_EN) + r")(?![\w-])", re.I)
HEDGED_NUM_RE = re.compile(
    r"(?<![\w-])(около|примерно|приблизительно|порядка|почти|до|от|свыше|более|менее|не более|не менее|"
    r"about|approximately|around|roughly|nearly|almost|up to|at least|at most|over|under|more than|less than)"
    r"\s?(?:чем\s)?(" + NUM + r")", re.I)
NEG_RE = re.compile(r"(?<![\w-])(не|нет|ни|без|not|no|never|without|none|nor)(?![\w-])|n't\b", re.I)

CAP_WORD = r"(?:[A-ZА-ЯЁ](?:[\w’'&-]|\.(?=\w))*)"
NAME_SEQ_RE = re.compile(r"(?<![\w-])" + CAP_WORD + r"(?:[ \t]+(?:" + CAP_WORD + r"|\d+(?:[\w-]|\.(?=\w))*))*")
QUOTED_NAME_RE = re.compile(r"«([^«»\n]{2,60})»")
SENT_START_RE = re.compile(r"(?:^|[.!?…]\s+|\n\s*(?:[-*+•#>]+\s*|\d+[.)]\s+)?|[:;]\s*\n)$")

RU_ENDINGS = sorted(["ами", "ями", "ого", "его", "ому", "ему", "ой", "ей", "ом", "ем", "ам", "ям",
                     "ах", "ях", "ов", "ев", "ую", "юю", "ая", "яя", "ые", "ие", "ый", "ий",
                     "а", "я", "у", "ю", "ы", "и", "е", "о"], key=len, reverse=True)


# ---------------------------------------------------------------- io


def read_input(path: str) -> str:
    if "\x00" in path or not os.path.isfile(path):
        raise ValueError(f"нет такого файла: {path!r}")
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"файл больше {MAX_BYTES} байт")
    with open(path, "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    if b"\x00" in data[:4096]:
        raise ValueError(f"похоже на бинарный файл: {path!r}")
    return data.decode("utf-8-sig", errors="replace")


def check_out_path(path: str) -> str:
    if "\x00" in path or not path.lower().endswith(".json"):
        raise ValueError("--out: нужен путь к файлу .json")
    ap = os.path.abspath(path)
    if os.path.islink(ap) or os.path.isdir(ap):
        raise ValueError("--out: путь — каталог или символическая ссылка")
    if not os.path.isdir(os.path.dirname(ap)):
        raise ValueError("--out: каталог для файла не существует")
    return ap


# ---------------------------------------------------------------- normalizers


def norm_space(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[    ]", " ", text)
    return re.sub(r"[\u200b-\u200d\u2060\ufeff\u00ad]", "", text)


def norm_number(n: str, mult: str | None = None) -> str:
    s = n.replace(" ", "").replace("−", "-").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return s
    if mult:
        m = mult.lower().rstrip(".")
        if m.startswith(("тыс", "thousand")) or m == "k":
            v *= 1_000
        elif m.startswith(("млн", "миллион", "million")) or m == "m":
            v *= 1_000_000
        elif m.startswith(("млрд", "миллиард", "billion")) or m == "bn":
            v *= 1_000_000_000
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return ("%.6f" % v).rstrip("0").rstrip(".")


def norm_currency(c: str) -> str:
    c = c.lower().rstrip(".")
    if c in ("₽",) or c.startswith(("руб", "рубл")):
        return "RUB"
    if c in ("$", "usd") or c.startswith("долл"):
        return "USD"
    if c in ("€", "eur", "евро"):
        return "EUR"
    if c == "£":
        return "GBP"
    if c in ("₸", "тенге"):
        return "KZT"
    if c in ("грн", "₴"):
        return "UAH"
    return c.upper()


def ru_month(word: str) -> int:
    w = word.lower()
    for k, v in MONTHS_RU.items():
        if w.startswith(k) and (k != "ма" or w in ("май", "мая", "мае")):
            return v
    return 0


def name_key(name: str) -> str:
    out = []
    for w in name.split():
        lw = w.lower().strip(".’'")
        if re.search(r"[а-яё]", lw) and len(lw) > 4 and not w.isupper():
            for e in RU_ENDINGS:
                if lw.endswith(e) and len(lw) - len(e) >= 3:
                    lw = lw[: -len(e)]
                    break
        out.append(lw)
    return " ".join(out)


# ---------------------------------------------------------------- extraction


def extract(text: str) -> dict:
    text = norm_space(text)
    taken = [False] * len(text)
    facts: dict[str, list[tuple[str, str]]] = {k: [] for k in
                                               ("urls", "emails", "dates", "money", "percents",
                                                "numbers", "names", "hedges", "hedged_numbers")}

    def free(a: int, b: int) -> bool:
        return not any(taken[a:b])

    def take(a: int, b: int) -> None:
        for i in range(a, b):
            taken[i] = True

    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,;:!?)»")
        facts["urls"].append((u.lower().rstrip("/"), u))
        take(m.start(), m.start() + len(u))
    for m in EMAIL_RE.finditer(text):
        if free(m.start(), m.end()):
            facts["emails"].append((m.group(0).lower(), m.group(0)))
            take(m.start(), m.end())

    for m in ISO_DATE_RE.finditer(text):
        if free(m.start(), m.end()):
            facts["dates"].append((f"{m.group(1)}-{m.group(2)}-{m.group(3)}", m.group(0)))
            take(m.start(), m.end())
    for m in DOT_DATE_RE.finditer(text):
        if free(m.start(), m.end()):
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            if 1 <= d <= 31 and 1 <= mo <= 12:
                y = ("20" + y) if len(y) == 2 else y
                facts["dates"].append((f"{y}-{mo:02d}-{d:02d}", m.group(0)))
                take(m.start(), m.end())
    for m in RU_DATE_RE.finditer(text):
        if free(m.start(), m.end()):
            mo = ru_month(m.group(2))
            if mo:
                y = m.group(3) or "----"
                facts["dates"].append((f"{y}-{mo:02d}-{int(m.group(1)):02d}", m.group(0)))
                take(m.start(), m.end())
    for rx, order in ((EN_DATE1_RE, "mdy"), (EN_DATE2_RE, "dmy")):
        for m in rx.finditer(text):
            if free(m.start(), m.end()):
                if order == "mdy":
                    mon, day, y = m.group(1), m.group(2), m.group(3)
                else:
                    day, mon, y = m.group(1), m.group(2), m.group(3)
                mo = MONTHS_EN.get(mon.lower()[:3], 0)
                if mo:
                    facts["dates"].append((f"{y}-{mo:02d}-{int(day):02d}", m.group(0)))
                    take(m.start(), m.end())

    # Оговорки ищем по тексту, где URL, почта и даты уже вырезаны: «от 01.02.2026» — не оговорка.
    blanked = "".join(" " if taken[i] else ch for i, ch in enumerate(text))
    for m in HEDGED_NUM_RE.finditer(blanked):
        facts["hedged_numbers"].append((f"{m.group(1).lower()} {norm_number(m.group(2))}", m.group(0)))
    for m in HEDGE_RE.finditer(blanked):
        facts["hedges"].append((m.group(1).lower(), m.group(1)))

    for m in MONEY_RE.finditer(text):
        if free(m.start(), m.end()):
            n = m.group("n1") or m.group("n2")
            mult = m.group("m1") or m.group("m2")
            cur = m.group("c1") or m.group("c2")
            facts["money"].append((f"{norm_number(n, mult)} {norm_currency(cur)}", m.group(0).strip()))
            take(m.start(), m.end())
    for m in PERCENT_RE.finditer(text):
        if free(m.start(), m.end()):
            facts["percents"].append((norm_number(m.group("n")) + "%", m.group(0)))
            take(m.start(), m.end())
    for m in NUMBER_RE.finditer(text):
        if free(m.start(), m.end()):
            facts["numbers"].append((norm_number(m.group("n"), m.group("m")), m.group(0).strip()))
            take(m.start(), m.end())

    return {"facts": facts, "text": text, "taken": taken}


def extract_names(text: str, taken: list[bool]) -> tuple[list[tuple], list]:
    """[(key, surface, sentence_initial, rest_key, rest_surface)] — имена; плюс названия в «ёлочках».

    rest_* — та же последовательность без первого слова: в начале фразы первое
    слово может быть обычным словом с заглавной («Смотрите Google Search Console»).
    """
    out = []
    for m in NAME_SEQ_RE.finditer(text):
        if any(taken[m.start():m.end()]):
            continue
        surface = m.group(0).strip(" .-")
        if not surface or not re.search(r"[^\W\d_]", surface):
            continue
        initial = bool(SENT_START_RE.search(text[max(0, m.start() - 6):m.start()]))
        parts = surface.split(None, 1)
        rest = parts[1] if len(parts) > 1 else ""
        out.append((name_key(surface), surface, initial, name_key(rest) if rest else "", rest))
    quoted = [(name_key(q), q) for q in QUOTED_NAME_RE.findall(text) if q[:1].isupper()]
    return out, quoted


def is_strong_name(surface: str) -> bool:
    """Аббревиатура, цифры или CamelCase в первом слове — имя и в начале фразы."""
    w = surface.split()[0]
    return (len(w) >= 2 and w.isupper()) or bool(re.search(r"\d|[a-z][A-Z]", w))


def multiset_diff(before: list[tuple[str, str]], after: list[tuple[str, str]]) -> dict:
    cb, ca = Counter(k for k, _ in before), Counter(k for k, _ in after)
    sb, sa = {}, {}
    for k, s in before:
        sb.setdefault(k, s)
    for k, s in after:
        sa.setdefault(k, s)
    lost = [{"key": k, "surface": sb[k], "count": n} for k, n in (cb - ca).items()]
    added = [{"key": k, "surface": sa[k], "count": n} for k, n in (ca - cb).items()]
    kept = sum((cb & ca).values())
    return {"lost": lost, "added": added, "kept": kept}


def compare(before_text: str, after_text: str) -> dict:
    eb, ea = extract(before_text), extract(after_text)
    nb, qb = extract_names(eb["text"], eb["taken"])
    na, qa = extract_names(ea["text"], ea["taken"])
    known = {it[0] for it in nb + na if not it[2]}

    def names(items):
        res = []
        for k, s, init, rk, rs in items:
            if not init or k in known or is_strong_name(s):
                res.append((k, s))
            elif rk:
                res.append((rk, rs))
        return res

    cats = {}
    for cat in ("numbers", "percents", "money", "dates", "urls", "emails", "hedged_numbers", "hedges"):
        cats[cat] = multiset_diff(eb["facts"][cat], ea["facts"][cat])
    cats["names"] = multiset_diff(names(nb) + qb, names(na) + qa)

    neg_b = len(NEG_RE.findall(eb["text"]))
    neg_a = len(NEG_RE.findall(ea["text"]))
    lost_total = sum(sum(x["count"] for x in c["lost"]) for c in cats.values())
    added_total = sum(sum(x["count"] for x in c["added"]) for c in cats.values())
    attention = []
    for item in cats["hedged_numbers"]["lost"]:
        attention.append(f"оговорка при числе пропала: «{item['surface']}»")
    for cat in ("numbers", "percents", "money", "dates"):
        if cats[cat]["lost"] and cats[cat]["added"]:
            attention.append(f"{cat}: часть значений заменена — сверить с источником")
    if neg_b != neg_a:
        attention.append(f"число отрицаний изменилось: {neg_b} → {neg_a} — проверить, не перевернулся ли смысл")
    return {
        "tool": "factdiff",
        "version": VERSION,
        "note": NOTE,
        "summary": {"lost": lost_total, "added": added_total,
                    "kept": sum(c["kept"] for c in cats.values()), "attention": attention},
        "categories": cats,
        "negations": {"before": neg_b, "after": neg_a},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Сравнение фактов до/после правки.")
    ap.add_argument("before", help="исходный файл")
    ap.add_argument("after", help="файл после правки")
    ap.add_argument("--out", help="полный отчёт в этот файл .json")
    args = ap.parse_args(argv)
    try:
        out = check_out_path(args.out) if args.out else None
        rep = compare(read_input(args.before), read_input(args.after))
        rep["before"], rep["after"] = os.path.basename(args.before), os.path.basename(args.after)
    except (ValueError, OSError) as exc:
        print(json.dumps({"tool": "factdiff", "ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        print(json.dumps({"tool": "factdiff", "summary": rep["summary"], "out": out}, ensure_ascii=False))
    else:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
