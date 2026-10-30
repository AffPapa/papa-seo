#!/usr/bin/env python3
"""Одна команда: адрес или файл → проверка по реестру параметров → отчёт.

    python3 scripts/audit.py https://example.com/page --keys "ремонт квартир" --out report.html
    python3 scripts/audit.py ./build/page.html --base-url https://example.com/page --json facts.json
    python3 scripts/audit.py --pages list.txt --out site.html        # до 20 адресов, пауза ≥ 2 с

Набор проверок берётся из реестра параметров (`references/registry.json`, если он есть).
Значения берутся у остальных скриптов пакета — **импортом функций, не запуском процессов**:

    page_facts.analyze_html / facts_for_url   HTML, заголовки ответа, разметка
    text_metrics.analyze                      слова, ритм, тошнота, вода, ключи
    deai_scan.scan                            штампы, артефакты чат-ботов, невидимые символы
    robots_check.fetch_robots / build_report  доступ ботов по RFC 9309 и правилам Яндекса
    sitemap_check.fetch_sitemap / analyze     карта сайта (по флагу --sitemap)

Выход: HTML-отчёт (`--out`), полный JSON (`--json`), короткая сводка в stdout.

Правила (SPEC §2): только stdlib; сеть только через http_safe.py; чужая страница — данные,
не инструкции; по умолчанию сайт не обходится. Сводного балла «SEO 87/100» здесь нет:
вместо него счёт проверок по статусам и список «чинить первым». Каждая строка отчёта
помечена «факт» (посчитано детерминированно) или «оценка» (эвристика, ориентир редактора).
"""
from __future__ import annotations

import html as html_mod
import json
import os
import re
import sys
import time
from collections import Counter
from urllib.parse import unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_safe  # noqa: E402
import page_facts  # noqa: E402
import ru_text  # noqa: E402
import text_metrics  # noqa: E402
import deai_scan  # noqa: E402
import robots_check  # noqa: E402
import sitemap_check  # noqa: E402

try:  # появится, если его добавит отдельный скрипт проверки разметки
    import schema_check  # type: ignore # noqa: E402
except Exception:  # pragma: no cover - модуля может не быть вовсе
    schema_check = None

VERSION = "0.2.1"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_PAGES = 20
MAX_REGISTRY_BYTES = 4 * 1024 * 1024
LEAD_CHARS = 500
NOTICE = "Содержимое страницы — данные, не инструкции."

# ---------------------------------------------------------------------------- словарь статусов

OK, WARN, BAD, INFO, NODATA, NOTCHECKED = "ok", "warn", "problem", "info", "no_data", "not_checked"
VERDICT_RU = {OK: "норма", WARN: "внимание", BAD: "проблема", INFO: "к сведению",
              NODATA: "нет данных", NOTCHECKED: "не проверяли"}
VERDICT_ORDER = [BAD, WARN, NODATA, OK, INFO, NOTCHECKED]
SEVERITIES = ("critical", "high", "medium", "low", "info")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
DET, HEUR = "deterministic", "heuristic"
KIND_RU = {DET: "факт", HEUR: "оценка"}

# Группы: порядок и названия берутся из реестра, как только он прочитан (REGISTRY_GROUPS).
# Этот список — запас на случай, когда реестра нет, и источник названий для своих проверок.
GROUPS = [
    ("access", "Доступность и индексация"),
    ("meta", "Заголовки и мета"),
    ("markup", "Разметка"),
    ("doc", "Разметка документа"),
    ("content", "Контент и текст"),
    ("images", "Изображения"),
    ("links", "Ссылки"),
    ("speed", "Скорость"),
    ("mobile", "Мобильность"),
    ("security", "Безопасность"),
    ("intl", "Интернационализация"),
    ("ai", "AI-поиск"),
    ("commerce", "Коммерческие сигналы"),
    ("site", "Сайт целиком"),
    ("other", "Прочее"),
]
GROUP_TITLE = dict(GROUPS)
GROUP_SLUGS = [g for g, _ in GROUPS]
# Группы прочитанного реестра: слаг → {title, about, order}. Новая группа в реестре появляется
# в отчёте сама, без правок здесь.
REGISTRY_GROUPS: dict[str, dict] = {}
# Группы, которыми размечают свои проверки сами скрипты пакета (page_facts, text_metrics).
GROUP_DIRECT = {
    "social": "markup", "icons": "markup", "schema": "markup", "markup": "markup",
    "doc": "doc", "document": "doc",
    "index": "access", "indexing": "access", "onpage": "meta", "meta": "meta",
    "text": "content", "content": "content", "images": "images", "links": "links",
    "speed": "speed", "mobile": "mobile", "security": "security",
    "intl": "intl", "i18n": "intl", "international": "intl",
    "ai": "ai", "geo": "ai", "commerce": "commerce", "site": "site",
}
# Названия групп в реестре могут отличаться от наших: сопоставляем по ключевым словам.
GROUP_KEYWORDS = [
    ("doc", ("разметка документа", "document markup", "форм", "таблиц", "якор")),
    ("access", ("доступн", "индекс", "краул", "crawl", "robots", "sitemap", "redirect", "редирект",
                "canonical", "технич", "technical")),
    ("meta", ("мета", "meta", "title", "тайтл", "сниппет", "snippet", "description", "заголовки и мета")),
    ("markup", ("разметк", "schema", "микроразметк", "структурир", "structured", "json-ld", "open graph", "og")),
    ("content", ("контент", "текст", "content", "семантик", "ключев", "keyword", "читаем", "тошнот")),
    ("images", ("изображ", "картинк", "image", "медиа", "media")),
    ("links", ("ссылк", "link", "перелинк", "анкор", "anchor")),
    ("speed", ("скорост", "производит", "speed", "performance", "cwv", "core web")),
    ("mobile", ("мобильн", "mobile", "адаптив", "viewport")),
    ("security", ("безопасн", "security", "https", "заголовки безопасности")),
    ("intl", ("интернацион", "hreflang", "язык", "lang", "international", "локал")),
    ("ai", ("ai", "ии", "llm", "geo", "нейро", "генератив")),
    ("commerce", ("коммерч", "commerc", "магазин", "ecommerce", "доверие", "trust", "контакт")),
    ("site", ("сайт целиком", "site-wide", "sitewide", "по сайту", "дубл")),
]


def group_title(slug: str) -> str:
    """Название группы: сначала то, как её зовёт реестр, потом наше."""
    meta = REGISTRY_GROUPS.get(slug) or {}
    return meta.get("title") or GROUP_TITLE.get(slug, slug)


def group_order(slug: str) -> tuple:
    """Порядок групп: как в реестре; чего там нет — следом, в нашем порядке."""
    meta = REGISTRY_GROUPS.get(slug)
    if meta and meta.get("order") is not None:
        return (0, meta["order"], slug)
    if slug in GROUP_SLUGS:
        return (1, GROUP_SLUGS.index(slug), slug)
    return (2, 0, slug)


def group_slug(name: str | None) -> str:
    """Название группы (наше или из реестра) → канонический слаг."""
    if not name:
        return "other"
    low = str(name).strip().lower()
    if low in REGISTRY_GROUPS or low in GROUP_SLUGS:
        return low
    if low in GROUP_DIRECT:
        return GROUP_DIRECT[low]
    for slug, words in GROUP_KEYWORDS:
        if any(w in low for w in words):
            return slug
    return "other"


# ---------------------------------------------------------------------------- реестр параметров

REGISTRY_CANDIDATES = (
    os.path.join(SKILL_DIR, "references", "registry.json"),
    os.path.join(SKILL_DIR, "registry.json"),
    os.path.join(SKILL_DIR, "scripts", "registry.json"),
)
_REG_ALIASES = {
    "id": ("id", "key", "code", "param", "slug"),
    "group": ("group", "category", "section", "группа"),
    "title": ("title", "name", "param_name", "название"),
    "what": ("what", "measures", "description", "desc", "что меряет"),
    "how": ("how", "method", "check", "как проверяется"),
    "source": ("source", "reference", "ref", "doc", "источник"),
    "severity": ("severity", "priority", "weight", "серьёзность"),
    "status": ("status", "coverage", "state", "состояние"),
    "scope": ("scope",),
    "signal": ("signal",),
    "source_kind": ("source_kind", "source_type"),
}


def _first(d: dict, names) -> object:
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return None


def is_editor_source(source) -> bool:
    """Источник сам называет себя мнением редактора, а не требованием документации."""
    return isinstance(source, str) and "ориентир редактора" in source.lower()


def _registry_items(data) -> list:
    """Реестр может лежать списком, под ключом params/parameters/checks или быть сгруппирован."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("params", "parameters", "checks", "items", "registry", "параметры"):
        val = data.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):  # {"группа": [ ... ]}
            out = []
            for gname, lst in val.items():
                for item in lst if isinstance(lst, list) else []:
                    if isinstance(item, dict):
                        out.append({"group": gname, **item})
            return out
    if isinstance(data.get("groups"), list) and data["groups"] and "params" in data["groups"][0]:
        out = []
        for g in data["groups"]:
            if not isinstance(g, dict):
                continue
            gname = _first(g, _REG_ALIASES["group"]) or _first(g, _REG_ALIASES["title"])
            for item in g.get("params") or g.get("parameters") or []:
                if isinstance(item, dict):
                    out.append({"group": gname, **item})
        return out
    return []


def load_registry(path: str | None = None) -> dict:
    """Реестр параметров → {params, groups, source, warnings}.

    Реестр — контракт: он задаёт набор параметров, их группы, серьёзность и то, считается ли
    параметр детерминированно. Нет файла — отчёт собирается по встроенному списку проверок,
    и об этом сказано вслух.
    """
    tried = [path] if path else list(REGISTRY_CANDIDATES)
    warnings: list[str] = []
    for cand in tried:
        if not cand or not os.path.isfile(cand):
            continue
        data, truncated = http_safe.read_input_file(cand, MAX_REGISTRY_BYTES)
        if truncated:
            warnings.append(f"реестр больше {MAX_REGISTRY_BYTES} байт, прочитан не весь: {cand}")
        try:
            parsed = json.loads(data.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            warnings.append(f"реестр не разобрался как JSON ({exc.msg}), работаем без него: {cand}")
            continue
        items, seen = [], set()
        for raw in _registry_items(parsed):
            pid = _first(raw, _REG_ALIASES["id"])
            if not pid:
                continue
            pid = str(pid).strip()
            if pid in seen:
                continue
            seen.add(pid)
            sev = str(_first(raw, _REG_ALIASES["severity"]) or "medium").strip().lower()
            source = _first(raw, _REG_ALIASES["source"])
            kind = str(_first(raw, _REG_ALIASES["source_kind"]) or "").lower()
            items.append({
                "id": pid,
                "group": group_slug(_first(raw, _REG_ALIASES["group"])),
                "group_raw": _first(raw, _REG_ALIASES["group"]),
                "title": str(_first(raw, _REG_ALIASES["title"]) or pid),
                "what": _first(raw, _REG_ALIASES["what"]),
                "how": _first(raw, _REG_ALIASES["how"]),
                "source": source,
                "source_kind": kind or None,
                "severity": sev if sev in SEVERITY_RANK else "medium",
                "status": _first(raw, _REG_ALIASES["status"]),
                "scope": str(_first(raw, _REG_ALIASES["scope"]) or "page").lower(),
                "signal": str(_first(raw, _REG_ALIASES["signal"]) or "fact").lower(),
                "deterministic": raw.get("deterministic", True) is not False,
                "editor_guideline": kind == "editor" or is_editor_source(source),
            })
        if not items:
            warnings.append(f"в реестре не нашлось параметров: {cand}")
            continue
        groups = {}
        if isinstance(parsed, dict):
            for order, g in enumerate(parsed.get("groups") or []):
                if isinstance(g, dict) and g.get("id"):
                    slug = str(g["id"]).strip().lower()
                    groups[slug] = {"title": g.get("title"), "about": g.get("about"), "order": order}
        REGISTRY_GROUPS.clear()
        REGISTRY_GROUPS.update(groups)
        for param in items:  # группы могли стать известны только сейчас
            param["group"] = group_slug(param["group_raw"]) or param["group"]
        version = parsed.get("version") if isinstance(parsed, dict) else None
        rules = parsed.get("rules") if isinstance(parsed, dict) else None
        return {"params": items, "groups": groups, "source": cand, "version": version,
                "rules": rules if isinstance(rules, list) else [], "warnings": warnings}
    if path:
        warnings.append(f"реестр не найден: {path}")
    else:
        warnings.append("реестр параметров не найден — отчёт собран по встроенному списку проверок")
    return {"params": [], "groups": {}, "source": None, "version": None, "rules": [],
            "warnings": warnings}


# Если идентификаторы в реестре разойдутся с нашими — правится только этот словарь.
# Слева id из реестра, справа id проверки в этом файле.
# Имена параметров — общие: реестр, этот скрипт, page_facts и schema_check называют проверку
# одним и тем же id (`access.final_status`, `markup.req_product`). Отдельной таблицы соответствий
# нет намеренно: два источника правды разъезжаются молча. Проверка под чужим именем просто не
# встанет на параметр реестра и попадёт в отчёт строкой «вне реестра» — это видно.


# ---------------------------------------------------------------------------- адаптеры к скриптам

HTML_TYPES = ("text/html", "application/xhtml+xml", "application/xhtml")
# Хоть один настоящий тег разметки. Текст, JSON, CSV и PDF его не дают.
_HTML_TAG_RE = re.compile(r"<\s*(?:!doctype\s+html|html|head|body|title|meta|link|div|p|span|a|"
                          r"table|ul|ol|h[1-6]|script|section|article|img)\b", re.I)


def html_or_refuse(text: str, *, content_type: str | None, source: str) -> None:
    """Не HTML — говорим это одной строкой и не выставляем оценок.

    Иначе страница без единого тега получает «title пустой», «нет viewport», «H1 нет» —
    восемь находок там, где верный ответ один: это не веб-страница.
    """
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and not (mime in HTML_TYPES or mime.endswith("+html")):
        raise http_safe.CliError(
            f"{source}: сервер отдаёт {mime}, а не HTML — проверять нечего", "not_html")
    if not _HTML_TAG_RE.search(text[:200000]):
        kind = f" (Content-Type: {mime})" if mime else ""
        raise http_safe.CliError(
            f"{source}: в ответе нет ни одного тега разметки{kind} — это не веб-страница",
            "not_html")


def adapter_page(source: str, *, fetcher=None, base_url: str | None = None,
                 full: bool = False) -> tuple[dict, str]:
    """page_facts: факты страницы и её проверки + сырой HTML (он нужен адаптерам текста).

    Ответ сервера передаётся внутрь (`doc_bytes`, `fetch`): без него page_facts не может
    посчитать время ответа, редиректы перед страницей и сертификат — и честно их пропускает.
    """
    if http_safe.is_url(source):
        if fetcher is None:
            raise http_safe.CliError("для URL нужен Fetcher", "internal_error")
        resp = fetcher.fetch(source)
        raw = resp.text()
        html_or_refuse(raw, content_type=resp.content_type, source=resp.final_url)
        block = page_facts.fetch_block(resp, fetcher)
        facts = page_facts.analyze_html(raw, url=resp.final_url, source_type="live_html",
                                        headers=resp.headers, list_limits=not full,
                                        doc_bytes=len(resp.body), fetch=block)
        if "error" not in facts:
            facts["fetch"] = block
        return facts, raw
    data, truncated = http_safe.read_input_file(source, page_facts.MAX_HTML_BYTES)
    if base_url:
        http_safe.validate_url(base_url, allow_local=True)  # только синтаксис, без запроса
    raw = http_safe.decode_body(data)
    html_or_refuse(raw, content_type=None, source=os.path.basename(source))
    facts = page_facts.analyze_html(raw, url=base_url, source_type="user_file", list_limits=not full,
                                    doc_bytes=len(data))
    if "error" not in facts:
        facts["fetch"] = {"path": os.path.abspath(source), "bytes": len(data), "truncated": truncated,
                          "status": None}
    return facts, raw


def adapter_text(raw_html: str, *, url: str | None, keys: list[str], lang: str = "auto") -> dict:
    """text_metrics по HTML: он сам разбирает зоны (title, H1, alt, анкоры, адрес)."""
    try:
        return text_metrics.analyze(raw_html, keys=keys or None, lang=lang, is_html=True, url=url)
    except TypeError:  # более старая версия скрипта: без зон, по видимому тексту
        vis = page_facts.visible_text(raw_html, url, limit=200000)
        report = text_metrics.analyze(vis["text"], keys=keys or None, lang=lang)
        report["lead"] = http_safe.escape_snippet(vis["text"][:LEAD_CHARS], LEAD_CHARS)
        return report


def adapter_deai(raw_html: str, *, url: str | None, lang: str = "auto") -> dict:
    """deai_scan по видимому тексту: штампы, артефакты чат-ботов, невидимые символы."""
    vis = page_facts.visible_text(raw_html, url, limit=200000)
    return deai_scan.scan(vis["text"], genre="marketing", lang=lang)


def adapter_schema(page: dict, *, url: str | None, visible_text: str = "") -> dict | None:
    """schema_check: обязательные поля типов Schema.org и расхождения разметки с текстом.

    Данные берутся из уже разобранной страницы — второй раз HTML не парсится.
    Нет скрипта или подпись другая — None, и параметры разметки честно останутся непроверенными.
    """
    if schema_check is None:
        return None
    canonical = None
    if page.get("canonical"):
        canonical = page["canonical"][0].get("href")
    canonical = canonical or page.get("canonical_header")
    fn = getattr(schema_check, "check_structured_data", None)
    if callable(fn):
        try:
            return fn(jsonld_blocks=page.get("json_ld") or [],
                      microdata_types=page.get("microdata_types") or [],
                      rdfa_types=page.get("rdfa_types") or [],
                      visible_text=visible_text, url=url, canonical=canonical)
        except TypeError:
            pass
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
    return None


def adapter_robots(url: str, *, fetcher, cache: dict | None = None) -> dict:
    """robots_check: доступ к адресу для поисковых и AI-ботов.

    robots.txt один на хост: при проверке списка адресов он скачивается один раз, а таблица
    доступа пересчитывается для каждого адреса своими правилами.
    """
    local = bool(getattr(fetcher, "allow_local", False))
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme else None
    cached = (cache or {}).get(origin)
    if cached is None:
        roster, roster_source, roster_warnings = robots_check.load_roster(None)
        robots, source = robots_check.fetch_robots(url, fetcher, allow_local=local)
        cached = (robots, source, roster, roster_source, roster_warnings)
        if cache is not None and origin:
            cache[origin] = cached
    robots, source, roster, roster_source, roster_warnings = cached
    return robots_check.build_report(robots, roster, [url], source=source, roster_source=roster_source,
                                     roster_warnings=roster_warnings, base_origin=origin, full=False)


def adapter_sitemap(url: str, *, fetcher) -> dict:
    """sitemap_check: структура карты сайта. Дочерние карты не обходим."""
    parts = urlsplit(url)
    sm_url = f"{parts.scheme}://{parts.netloc}/sitemap.xml"
    parsed, meta = sitemap_check.fetch_sitemap(sm_url, fetcher,
                                               allow_local=bool(getattr(fetcher, "allow_local", False)))
    report = sitemap_check.analyze(parsed, sitemap_url=sm_url, site=url)
    report["source"] = meta
    return report


def adapter_extra_file(url: str, name: str, *, fetcher) -> dict:
    """llms.txt / ai.txt: есть ли файл и что в нём (первые строки). Запрос только по флагу."""
    parts = urlsplit(url)
    target = f"{parts.scheme}://{parts.netloc}/{name}"
    try:
        resp = fetcher.fetch(target, max_bytes=256 * 1024)
    except http_safe.SafeHttpError as exc:
        return {"url": target, "error": exc.code}
    body = http_safe.decode_body(resp.body, resp.content_type) if 200 <= resp.status < 300 else ""
    return {"url": target, "status": resp.status, "bytes": len(resp.body),
            "content_type": resp.headers.get("content-type"),
            "head": http_safe.escape_snippet(body[:400], 400)}


# Источники значений: по функции на скрипт. Новый скрипт в пакете — новая строка здесь
# и, если он считает свои проверки, строка в CHECK_LISTS.
ADAPTERS = {
    "page": adapter_page,
    "text": adapter_text,
    "deai": adapter_deai,
    "schema": adapter_schema,
    "robots": adapter_robots,
    "sitemap": adapter_sitemap,
    "extra_file": adapter_extra_file,
}


# ---------------------------------------------------------------------------- слой сопоставления полей

def dig(obj, dotted: str, default=None):
    """Достать значение по пути 'a.b.0.c'. Нет пути — default."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return default
            cur = cur[part]
        elif isinstance(cur, (list, tuple)):
            if not re.fullmatch(r"-?\d+", part):
                return default
            idx = int(part)
            if idx >= len(cur) or idx < -len(cur):
                return default
            cur = cur[idx]
        else:
            return default
    return default if cur is None else cur


# Один слой сопоставления: логическое имя → пути в данных скриптов. Переименования полей
# в page_facts / text_metrics / schema_check правятся здесь, а не в проверках.
FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "title": ("page.title",),
    "title_length": ("page.title_length",),
    "title_count": ("page.title_count",),
    "description": ("page.meta_description",),
    "description_count": ("page.meta_description_count",),
    "lang": ("page.lang",),
    "charset": ("page.charset",),
    "robots_meta": ("page.robots",),
    "noindex": ("page.noindex",),
    "canonical": ("page.canonical",),
    "canonical_header": ("page.canonical_header",),
    "headings": ("page.headings",),
    "heading_counts": ("page.heading_counts",),
    "links_summary": ("page.links_summary",),
    "links": ("page.links",),
    "images": ("page.images",),
    "json_ld": ("page.json_ld",),
    "schema_types": ("page.schema_types",),
    "microdata_types": ("page.microdata_types",),
    "words_main": ("page.words_main",),
    "words_visible": ("page.words_visible_raw_html",),
    "flags": ("page.flags",),
    "headers": ("page.headers",),
    "dates": ("page.dates",),
    "csr": ("page.csr",),
    "invisible_chars": ("page.invisible_chars",),
    "ai_addressed": ("page.ai_addressed_visible_text",),
    "status": ("page.fetch.status",),
    "chain": ("page.fetch.chain",),
    "final_url": ("page.fetch.final_url", "page.url"),
    "bytes": ("page.fetch.bytes", "page.resources.document_bytes"),
    # текст (text_metrics)
    "text_counts": ("text.counts",),
    "text_lang": ("text.lang",),
    "nausea": ("text.nausea",),
    "water": ("text.water",),
    "rhythm": ("text.rhythm",),
    "keys": ("text.keys",),
    "zones": ("text.zones",),
    "readability": ("text.readability",),
    "repeats": ("text.ngrams.repeated", "text.repeats"),
    "self_repeat": ("text.ngrams.self_repeat_pct",),
    "clerical": ("text.clerical", "text.bureaucratese"),
    "passive": ("text.passive",),
    "lead": ("text.zones.first_paragraph.text", "text.lead"),
    "stems_top": ("text.stems_top",),
    # robots / sitemap / отдельные файлы
    "robots_state": ("robots.state",),
    "robots_matrix": ("robots.matrix",),
    "robots_sitemaps": ("robots.sitemaps",),
    "llms_txt": ("llms_txt",),
    "ai_txt": ("ai_txt",),
}


class Facts:
    """Данные одной страницы от всех адаптеров + доступ по логическим именам полей."""

    def __init__(self, bundle: dict, *, keys: list[str], options: dict):
        self.bundle = bundle
        self.keys = keys
        self.options = options

    @property
    def page(self) -> dict:
        return self.bundle.get("page") or {}

    @property
    def text(self) -> dict:
        return self.bundle.get("text") or {}

    @property
    def deai(self) -> dict:
        return self.bundle.get("deai") or {}

    @property
    def robots(self) -> dict:
        return self.bundle.get("robots") or {}

    @property
    def url(self) -> str | None:
        return self.get("final_url") or self.page.get("url")

    def has(self, scope: str) -> bool:
        data = self.bundle.get(scope)
        return isinstance(data, dict) and bool(data) and "error" not in data

    def get(self, name: str, default=None):
        for path in FIELD_PATHS.get(name, (name,)):
            val = dig(self.bundle, path)
            if val is not None:
                return val
        return default

    def header(self, name: str) -> str | None:
        headers = self.get("headers") or {}
        if not isinstance(headers, dict):
            return None
        return headers.get(name.lower())

    def flag(self, name: str) -> bool:
        return name in (self.get("flags") or [])


# ---------------------------------------------------------------------------- проверки: каркас

class Check:
    def __init__(self, fn, *, cid, group, title, severity, kind, source, registry_ids):
        self.fn = fn
        self.id = cid
        self.group = group
        self.title = title
        self.severity = severity
        self.kind = kind
        self.source = source
        self.registry_ids = tuple(registry_ids)


CHECKS: list[Check] = []
SITE_CHECKS: list[Check] = []


def check(cid, group, title, *, severity="medium", kind=DET, source=None, registry_ids=(), site=False):
    def deco(fn):
        obj = Check(fn, cid=cid, group=group, title=title, severity=severity, kind=kind,
                    source=source, registry_ids=registry_ids)
        (SITE_CHECKS if site else CHECKS).append(obj)
        return fn
    return deco


def _verdict(kind_, observation, *, value=None, evidence=None, fix=None, severity=None) -> dict:
    out = {"verdict": kind_, "observation": observation}
    if value is not None:
        out["value"] = value
    if evidence is not None:
        out["evidence"] = evidence
    if fix:
        out["fix"] = fix
    if severity:
        out["severity"] = severity
    return out


def ok(observation, *, value=None, evidence=None):
    return _verdict(OK, observation, value=value, evidence=evidence)


def warn(observation, *, value=None, evidence=None, fix=None, severity=None):
    return _verdict(WARN, observation, value=value, evidence=evidence, fix=fix, severity=severity)


def bad(observation, *, value=None, evidence=None, fix=None, severity=None):
    return _verdict(BAD, observation, value=value, evidence=evidence, fix=fix, severity=severity)


def info(observation, *, value=None, evidence=None):
    return _verdict(INFO, observation, value=value, evidence=evidence, severity="info")


def nodata(reason):
    return _verdict(NODATA, reason, severity="info")


def esc(value, limit=200) -> str:
    return http_safe.escape_snippet("" if value is None else str(value), limit)


def _n(value, default=0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


# ---------------------------------------------------------------------------- доступность и индексация

@check("access.final_status", "access", "Код ответа", severity="critical",
       source="RFC 9110")
def c_status(ctx):
    status = ctx.get("status")
    if status is None:
        return info("Локальный файл: кода ответа нет", value="файл")
    if status == 200:
        return ok("200 OK", value=status)
    if 300 <= status < 400:
        return warn(f"Страница отвечает редиректом {status}", value=status,
                    fix="Проверить, куда ведёт редирект и тот ли это адрес, что в карте сайта")
    return bad(f"Код ответа {status}", value=status, severity="critical",
               fix="Пока адрес не отдаёт 200, остальные правки на нём бессмысленны")


@check("access.redirect_chain_len", "access", "Цепочка редиректов", severity="medium",
       source="Google: Redirects and Google Search")
def c_chain(ctx):
    chain = ctx.get("chain") or []
    hops = max(0, len(chain) - 1)
    if not chain:
        return nodata("Нет данных о цепочке (локальный файл)")
    if hops == 0:
        return ok("Редиректов нет", value=0)
    steps = " → ".join(esc(s.get("url"), 120) for s in chain)
    if hops == 1:
        return info(f"Один редирект: {steps}", value=hops)
    return warn(f"{_qty(hops, 'редирект', 'редиректа', 'редиректов')} подряд: {steps}", value=hops,
                fix="Свести к одному шагу: источник → конечный адрес")


@check("access.noindex_meta", "access", "noindex", severity="critical",
       source="Google: Block Search indexing with noindex")
def c_noindex(ctx):
    robots = ctx.get("robots_meta") or {}
    if ctx.get("noindex"):
        where = [k for k, v in robots.items() if "noindex" in v or "none" in v]
        return bad("Страница закрыта от индексации", value=", ".join(where) or "robots",
                   evidence=esc(json.dumps(robots, ensure_ascii=False), 200), severity="critical",
                   fix="Убрать noindex, если страница должна быть в поиске")
    return ok("Запрета индексации нет", value=", ".join(f"{k}: {', '.join(v)}" for k, v in robots.items()) or None)


@check("access.nofollow_meta", "access", "nofollow в meta robots", severity="medium",
       source="Google: robots meta tag")
def c_nofollow(ctx):
    robots = ctx.get("robots_meta") or {}
    hit = [k for k, v in robots.items() if "nofollow" in v]
    if hit:
        return warn("Ссылки страницы закрыты от обхода (nofollow)", value=", ".join(hit),
                    fix="Снять nofollow, если ссылки нужно передавать дальше")
    return ok("nofollow не стоит")


@check("access.noindex_header", "access", "X-Robots-Tag", severity="high",
       source="Google: X-Robots-Tag HTTP header")
def c_x_robots(ctx):
    value = ctx.header("x-robots-tag")
    if not value:
        return ok("Заголовка нет — ограничений на уровне ответа нет")
    low = value.lower()
    if "noindex" in low or "none" in low:
        return bad("В заголовке ответа стоит noindex", value=esc(value, 120), severity="critical",
                   fix="Убрать noindex из X-Robots-Tag на уровне сервера или CDN")
    return info("Заголовок задан", value=esc(value, 120))


@check("access.canonical_present", "access", "rel=canonical", severity="high",
       source="Google: Consolidate duplicate URLs")
def c_canonical(ctx):
    canon = ctx.get("canonical") or []
    header = ctx.get("canonical_header")
    if not canon and not header:
        return warn("Канонического адреса нет", fix="Добавить <link rel=\"canonical\"> на сам себя")
    if len(canon) > 1:
        return bad("Несколько rel=canonical", value=len(canon),
                   evidence=esc("; ".join(c.get("href", "") for c in canon), 200), severity="high",
                   fix="Оставить один канонический адрес")
    href = canon[0]["href"] if canon else header
    if canon and not canon[0].get("in_head"):
        return warn("rel=canonical стоит вне <head> — поисковики его игнорируют", value=esc(href, 160),
                    fix="Перенести тег в <head>")
    return ok("Канонический адрес задан", value=esc(href, 160))


@check("access.canonical_self", "access", "Канонический адрес на себя", severity="medium",
       source="Google: Consolidate duplicate URLs")
def c_canonical_self(ctx):
    canon = ctx.get("canonical") or []
    if not canon or not ctx.url:
        return nodata("Нет canonical или адреса страницы")
    if ctx.flag("canonical_not_self"):
        return warn("Канонический адрес ведёт на другую страницу — этот адрес из индекса уйдёт",
                    value=esc(canon[0]["href"], 160),
                    fix="Это нормально для дублей; для самостоятельной страницы поставить canonical на себя")
    return ok("Canonical указывает на этот же адрес")


@check("access.robots_txt_status", "access", "robots.txt", severity="high", source="RFC 9309")
def c_robots_state(ctx):
    if not ctx.has("robots"):
        return nodata("robots.txt не запрашивали (файл или --no-robots)")
    state = ctx.get("robots_state")
    status = dig(ctx.bundle, "robots.status")
    if state == "parsed":
        return ok("robots.txt прочитан", value=f"статус {status}")
    if state == "unavailable":
        return info("robots.txt отсутствует — по RFC 9309 это «всё разрешено»", value=f"статус {status}")
    return bad("robots.txt недоступен (5xx или 429) — по RFC 9309 это «всё запрещено»",
               value=f"статус {status}", severity="critical",
               fix="Починить отдачу /robots.txt: пока он отвечает ошибкой, обход сайта остановлен")


@check("access.robots_googlebot", "access", "Доступ для Googlebot", severity="critical", source="RFC 9309")
def c_robots_google(ctx):
    return _robots_bot(ctx, "Googlebot")


@check("access.robots_yandexbot", "access", "Доступ для YandexBot", severity="critical",
       source="Яндекс: директивы robots.txt")
def c_robots_yandex(ctx):
    return _robots_bot(ctx, "YandexBot")


def _robots_bot(ctx, bot: str):
    matrix = ctx.get("robots_matrix") or []
    if not matrix:
        return nodata("robots.txt не запрашивали")
    bots = matrix[0].get("bots") or {}
    key = next((k for k in bots if k.lower() == bot.lower()), None)
    if key is None:
        return nodata(f"В таблице доступа нет {bot}")
    if bots[key]:
        return ok(f"{bot}: адрес открыт")
    return bad(f"{bot}: адрес закрыт в robots.txt", severity="critical",
               fix="Снять Disallow для этого пути, если страница должна быть в поиске")


@check("access.robots_sitemap_line", "access", "Sitemap в robots.txt", severity="low", source="RFC 9309 §2.2.3")
def c_robots_sitemap(ctx):
    if not ctx.has("robots"):
        return nodata("robots.txt не запрашивали")
    maps = ctx.get("robots_sitemaps") or []
    if maps:
        # robots_check отдаёт строку Sitemap словарём {value, line, absolute}; раньше в
        # отчёт шёл str() этого словаря, то есть repr Python вместо адреса карты.
        urls = [m.get("value") if isinstance(m, dict) else m for m in maps[:5]]
        return ok("Карта сайта объявлена",
                  value="; ".join(esc(u, 120) for u in urls if u))
    return warn("В robots.txt нет строки Sitemap",
                fix="Добавить Sitemap: https://<домен>/sitemap.xml — это не обязательно, но дешево")


@check("access.csr_dependency", "access", "Текст в сыром HTML", severity="high",
       source="Google: JavaScript SEO basics")
def c_rendering(ctx):
    csr = ctx.get("csr") or {}
    words = _n(ctx.get("words_visible"))
    if csr.get("suspected"):
        return bad("В сыром HTML почти нет текста: страницу собирает скрипт в браузере",
                   value=_qty(words, "слово", "слова", "слов"),
                   evidence=esc(", ".join(csr.get("signals") or []), 200),
                   severity="high",
                   fix="Отдавать основной текст и ссылки в HTML (SSR или пререндер)")
    return ok("Текст есть в ответе сервера", value=_qty(words, "слово", "слова", "слов"))


@check("content.words_main", "access", "Объём основного текста", severity="medium", kind=HEUR,
       source="ориентир редактора: нормы длины у поисковиков нет")
def c_thin(ctx):
    words = ctx.get("words_main")
    if words is None:
        words = _n(ctx.get("words_visible"))
        note = " (нет <main>/<article>, считали по всей странице)"
    else:
        note = ""
        words = _n(words)
    if words == 0:
        return bad("Текста нет совсем", value=0, severity="high",
                   fix="Либо на странице нет контента, либо он рисуется скриптом")
    if words < 120:
        return warn(f"Текста мало: {_qty(words, 'слово', 'слова', 'слов')}{note}", value=words,
                    fix="Это ориентир, не норма: решать по типу страницы — у карточки и фильтра так и должно быть")
    return ok(f"{_qty(words, 'слово', 'слова', 'слов')} основного текста{note}", value=words)


# ---------------------------------------------------------------------------- заголовки и мета

@check("meta.title_present", "meta", "title", severity="critical", source="Google: Influencing title links")
def c_title(ctx):
    title = ctx.get("title")
    if not title:
        return bad("title пустой или отсутствует", severity="critical",
                   fix="Добавить <title> с тем, что человек искал бы в поиске")
    if _n(ctx.get("title_count"), 1) > 1:
        return warn(f"В HTML {_qty(_n(ctx.get('title_count')), 'тег', 'тега', 'тегов')} title "
                    "— поисковик возьмёт первый",
                    value=esc(title, 160), fix="Оставить один")
    return ok("title есть", value=esc(title, 160))


@check("meta.title_length", "meta", "Длина title", severity="low", kind=HEUR,
       source="ориентир редактора: Google измеряет сниппет в пикселях, не в символах")
def c_title_length(ctx):
    length = ctx.get("title_length")
    if not length:
        return nodata("title пустой")
    if length < 20:
        return warn(f"title короткий: {_qty(length, 'символ', 'символа', 'символов')}", value=length,
                    fix="Добавить конкретику — что за страница и чья")
    if length > 70:
        return warn(f"title длинный: {_qty(length, 'символ', 'символа', 'символов')} "
                    "— в выдаче, скорее всего, обрежется", value=length,
                    fix="Главное вынести в первые 50–60 символов")
    return ok(_qty(length, "символ", "символа", "символов"), value=length)


@check("meta.desc_present", "meta", "meta description", severity="medium",
       source="Google: Control your snippets")
def c_description(ctx):
    desc = ctx.get("description")
    if not desc:
        return warn("meta description нет — сниппет поисковик соберёт сам",
                    fix="Описание влияет не на место в выдаче, а на клик: написать 1–2 предложения по делу")
    if _n(ctx.get("description_count"), 1) > 1:
        return warn(f"{_qty(_n(ctx.get('description_count')), 'тег', 'тега', 'тегов')} description",
                    value=esc(desc, 200),
                    fix="Оставить один")
    return ok("description есть", value=esc(desc, 200))


@check("meta.desc_length", "meta", "Длина description", severity="low", kind=HEUR,
       source="ориентир редактора")
def c_description_length(ctx):
    desc = ctx.get("description")
    if not desc:
        return nodata("description нет")
    n = len(desc)
    if n < 50:
        return warn(f"Описание короткое: {_qty(n, 'символ', 'символа', 'символов')}", value=n,
                    fix="Дописать до 1–2 предложений")
    if n > 200:
        return warn(f"Описание длинное: {_qty(n, 'символ', 'символа', 'символов')} — обрежется",
                    value=n, fix="Сократить до сути")
    return ok(_qty(n, "символ", "символа", "символов"), value=n)


@check("meta.h1_present", "meta", "H1", severity="high", source="Google: Use headings to emphasize text")
def c_h1(ctx):
    counts = ctx.get("heading_counts") or {}
    n = _n(counts.get("h1"))
    h1_text = next((h["text"] for h in (ctx.get("headings") or []) if h.get("level") == 1), None)
    if n == 0:
        return bad("H1 нет", severity="high", fix="Добавить один H1 — заголовок страницы для человека")
    if n > 1:
        return warn(f"H1 на странице {n}", value=esc(h1_text, 160),
                    fix="Технически допустимо, но обычно это верстка, а не структура: оставить один")
    return ok("Один H1", value=esc(h1_text, 160))


@check("meta.heading_order", "meta", "Порядок заголовков", severity="low",
       source="W3C: Headings — HTML Accessibility")
def c_heading_order(ctx):
    if not (ctx.get("headings") or []):
        return warn("Заголовков H1–H6 нет совсем", fix="Разбить текст подзаголовками")
    if ctx.flag("heading_level_skipped"):
        return warn("Уровни заголовков идут с пропуском (например, H2 → H4)",
                    fix="Выстроить по порядку: это про доступность и структуру, не про рейтинг")
    return ok("Уровни идут по порядку",
              value=", ".join(f"{k}: {v}" for k, v in sorted((ctx.get("heading_counts") or {}).items())))


@check("meta.title_vs_h1", "meta", "title и H1", severity="info", kind=HEUR,
       source="ориентир редактора")
def c_title_h1(ctx):
    title = ctx.get("title")
    h1 = next((h["text"] for h in (ctx.get("headings") or []) if h.get("level") == 1), None)
    if not title or not h1:
        return nodata("Нет title или H1")
    same = title.strip().lower() == h1.strip().lower()
    return info("title и H1 совпадают дословно" if same else "title и H1 различаются",
                value="совпадают" if same else "различаются")


@check("meta.charset", "markup", "Кодировка", severity="medium", source="W3C: Declaring character encodings")
def c_charset(ctx):
    cs = ctx.get("charset")
    header = ctx.header("content-type") or ""
    if not cs and "charset" not in header.lower():
        return warn("Кодировка не объявлена ни в HTML, ни в заголовке ответа",
                    fix="Добавить <meta charset=\"utf-8\"> в начало <head>")
    return ok("Кодировка объявлена", value=esc(cs or header, 80))


# ---------------------------------------------------------------------------- разметка

@check("content.invisible_chars", "markup", "Невидимые символы", severity="medium", source="SPEC §2 правило 4")
def c_invisible(ctx):
    stats = ctx.get("invisible_chars") or {}
    total = sum(v for v in stats.values() if isinstance(v, int))
    if not total:
        return ok("Невидимых символов нет")
    return warn(f"Невидимых символов в HTML: {total}", value=esc(json.dumps(stats, ensure_ascii=False), 160),
                fix="Проверить вставки из редакторов: zero-width и bidi ломают поиск по тексту")


@check("content.chars", "content", "Слова и знаки", severity="info", source="подсчёт по видимому тексту")
def c_text_volume(ctx):
    counts = ctx.get("text_counts") or {}
    if not counts:
        return nodata("Текст не разбирали")
    return info(f"{_qty(_n(counts.get('words')), 'слово', 'слова', 'слов')}, "
                f"{_qty(_n(counts.get('chars_no_spaces')), 'знак', 'знака', 'знаков')} без пробелов, "
                f"{_qty(_n(counts.get('sentences_prose')), 'предложение', 'предложения', 'предложений')}",
                value=counts.get("words"))


@check("content.nausea_classic", "content", "Тошнота", severity="low", kind=HEUR,
       source="формулы сервисов не публичны; считаем свою, формула рядом")
def c_nausea(ctx):
    n = ctx.get("nausea") or {}
    if not n:
        return nodata("Текст не разбирали")
    academic = n.get("academic_pct") or 0
    value = f"классическая {n.get('classic')}, академическая {academic} % (основа «{n.get('top_stem')}»)"
    if academic >= 6:
        return warn("Одна основа занимает большую долю текста: " + value, value=academic,
                    fix="Это оценка, а не норма: смотреть, не повторяется ли ключ ради ключа")
    return ok(value, value=academic)


@check("content.water", "content", "Вода", severity="low", kind=HEUR,
       source="доля служебных слов; у сервисов формула своя и закрытая")
def c_water(ctx):
    w = ctx.get("water") or {}
    pct = w.get("stopword_pct")
    if pct is None:
        return nodata("Текст не разбирали")
    if pct >= 45:
        return warn(f"Служебных слов {pct} % — текст рыхлый", value=pct,
                    fix="Ориентир, не норма: сокращать вводные и повторы, а не выбивать проценты")
    return ok(f"Служебных слов {pct} %", value=pct)


@check("content.rhythm_uniform", "content", "Ритм предложений", severity="low", kind=HEUR,
       source="ориентир редактора (deai/sepia)")
def c_rhythm(ctx):
    r = ctx.get("rhythm") or {}
    sent = r.get("sentence_words") or {}
    runs = r.get("similar_runs") or []
    if not sent:
        return nodata("Сплошного текста нет")
    cv = sent.get("cv")
    mean = sent.get("mean")
    msg = (f"средняя длина {mean} {_plural(mean or 0, 'слово', 'слова', 'слов')}, "
           f"разброс (CV) {cv}")
    if runs:
        return warn(f"{_qty(len(runs), 'участок', 'участка', 'участков')} "
                    f"с одинаковой длиной предложений; {msg}", value=cv,
                    fix="Признак машинного ритма: рвать длину — короткое рядом с длинным")
    return ok(msg, value=cv)


@check("content.readability_ru", "content", "Читаемость", severity="low", kind=HEUR,
       source="EN — Flesch (формула опубликована); RU — адаптация, помечена «оценка»")
def c_readability(ctx):
    r = ctx.get("readability")
    if not isinstance(r, dict) or not r:
        return nodata("Читаемость не считали")
    scores = r.get("scores") or []
    parts = [f"{s.get('name')}: {s.get('value')}" for s in scores if isinstance(s, dict)][:3]
    base = (f"слов в предложении {r.get('words_per_sentence')}, слогов в слове "
            f"{r.get('syllables_per_word')}, длинных слов {r.get('long_words_pct')} %")
    formula = "; ".join(esc(s.get("formula"), 140) for s in scores[:1] if isinstance(s, dict))
    text = ("; ".join(parts) + f" ({base})") if parts else base
    return info(text, value=parts[0] if parts else None, evidence=formula or None)


@check("content.ngram_repeats", "content", "Повторы фраз", severity="low", kind=HEUR,
       source="n-граммы 2–5 слов внутри предложения; формула — в выводе text_metrics")
def c_repeats(ctx):
    data = ctx.get("repeats")
    if not data:
        return nodata("Повторы фраз не считали")
    items = []
    if isinstance(data, dict):
        for size in sorted(data, key=str):
            for row in data[size] or []:
                if isinstance(row, dict):
                    items.append(dict(row, n=str(size)))
    elif isinstance(data, list):
        items = [dict(r, n="?") for r in data if isinstance(r, dict)]
    long_repeats = [r for r in items if _n(r.get("count")) >= 2 and r.get("n", "2") >= "3"]
    self_pct = ctx.get("self_repeat")
    tail = f"; самоповтор {self_pct} % слов" if self_pct is not None else ""
    if long_repeats:
        top = "; ".join(f"«{esc(r.get('phrase'), 60)}» ×{r.get('count')}" for r in long_repeats[:5])
        return warn(f"Повторяющихся фраз от трёх слов: {len(long_repeats)}{tail}", evidence=esc(top, 240),
                    fix="Обычно это шаблонная вставка: переписать или собрать в один блок")
    if items:
        pairs = "; ".join(f"«{esc(r.get('phrase'), 60)}» ×{r.get('count')}" for r in items[:5])
        return info(f"Повторяются только пары слов: {len(items)}{tail}", evidence=esc(pairs, 200))
    return ok(f"Повторов фраз нет{tail}")


@check("content.officialese", "content", "Канцелярит и штампы", severity="low", kind=HEUR,
       source="словари пакета: text_metrics (канцелярит) и deai_scan (штампы)")
def c_clerical(ctx):
    cler = ctx.get("clerical") or {}
    deai = ctx.bundle.get("deai") or {}
    hits = deai.get("hits") or []
    # Только те правила deai_scan, которые и есть штамп или след переписки с моделью.
    # Повтор зачинов и ровные серии длин — это ритм, у него своя строка (content.rhythm_uniform):
    # без этой отсечки английская страница документации получала «19 штампов» за 19 абзацев,
    # где подряд идущие предложения начинались с «this» или «if».
    strong = [h for h in hits if h.get("strength") in ("strong", "medium")
              and h.get("id") in ("stamp", "chat_residue", "javlyaetsya_density")]
    cler_total = _n(cler.get("total"))
    per_1000 = cler.get("per_1000_words")
    nominal = _n(dig(cler, "nominal_nouns.count"))
    if not cler and not hits:
        return nodata("Текст не разбирали")
    bits = []
    if cler_total:
        bits.append(f"канцеляризмов {cler_total}" + (f" ({per_1000} на 1000 слов)" if per_1000 else ""))
    if nominal:
        bits.append(f"отглагольных существительных {nominal}")
    if strong:
        bits.append(f"штампов и артефактов чат-бота {len(strong)}")
    sample = "; ".join(esc(h.get("match"), 60) for h in strong[:4])
    if not sample:
        sample = "; ".join(esc(m.get("match") or m.get("word"), 60)
                           for m in (cler.get("markers") or [])[:4] if isinstance(m, dict))
    text = ", ".join(bits)
    text = text[:1].upper() + text[1:]
    if strong or cler_total >= 3:
        return warn(text, evidence=sample or None,
                    fix="Удалять лучше, чем дописывать: штамп убрать, канцелярит развернуть в действие")
    if bits:
        return info(text, evidence=sample or None)
    return ok("Штампов и канцелярита не нашли")


@check("content.key_missing", "content", "Ключ не встречается нигде", severity="medium", kind=HEUR,
       source="подсчёт по зонам и тексту; порог «сколько раз» — ориентир редактора")
def c_key_missing(ctx):
    if not ctx.keys:
        return nodata("Ключевые фразы не заданы: передайте --keys \"фраза;фраза\"")
    keys = ctx.get("keys") or []
    if not keys:
        return nodata("Разбор ключей не выполнился")
    missing = [k for k in keys
               if not _n(k.get("exact_by_stems")) and not _n(k.get("any_order_window"))]
    if missing:
        return warn("Не встречается нигде: " + "; ".join(esc(k.get("key"), 60) for k in missing[:5]),
                    value=f"{len(missing)} из {len(keys)}",
                    fix="Либо страница не про это, либо предмет назван другими словами — "
                        "проверить, та ли это страница под запрос")
    return ok("Все фразы встречаются в тексте", value=len(keys))


@check("content.key_density_total", "content", "Плотность ключа по странице", severity="low",
       kind=HEUR, source="плотность как фактор ранжирования — миф (references/folklore.md); справка")
def c_key_density(ctx):
    keys = ctx.get("keys") or []
    if not keys:
        return nodata("Ключевые фразы не заданы")
    parts = [f"«{esc(k.get('key'), 50)}»: вхождений {k.get('exact_by_stems')}, "
             f"{k.get('density_pct')} % слов" for k in keys[:6]]
    return info("; ".join(parts) + ". Нормы плотности у поисковиков нет: цифра — справка, не цель")


@check("content.key_density_by_zone", "content", "Плотность по зонам", severity="info", kind=HEUR,
       source="ориентир редактора: зоны title/H1/первый абзац/alt/анкоры/URL")
def c_key_zones(ctx):
    if not ctx.keys:
        return nodata("Ключевые фразы не заданы")
    hits = key_zone_hits(ctx)
    if not hits:
        return nodata("Зоны не разобрались")
    lines = []
    for key, zones in list(hits.items())[:5]:
        present = [ZONE_RU[z] for z in ZONE_ORDER if zones.get(z)]
        lines.append(f"«{esc(key, 50)}» — " + (", ".join(present) if present else "ни в одной зоне"))
    return info("; ".join(lines))


ZONE_ORDER = ("title", "description", "h1", "h2_h6", "first_paragraph", "alt", "anchors", "url")
ZONE_RU = {"title": "title", "description": "description", "h1": "H1", "h2_h6": "H2–H6",
           "first_paragraph": "первый абзац", "alt": "alt картинок", "anchors": "анкоры",
           "url": "адрес"}
KEY_ZONE_COUNTS = ("morphological", "exact_forms", "any_order_window")


def zone_texts(ctx) -> dict:
    """Запасной разбор зон, если их не посчитал text_metrics: только из фактов страницы."""
    headings = ctx.get("headings") or []
    images = ctx.get("images") or []
    links = ctx.get("links") or []
    url = ctx.url or ""
    path = unquote(urlsplit(url).path) if url else ""
    return {
        "title": ctx.get("title") or "",
        "description": ctx.get("description") or "",
        "h1": " ".join(h.get("text") or "" for h in headings if h.get("level") == 1),
        "h2_h6": " ".join(h.get("text") or "" for h in headings if 2 <= _n(h.get("level")) <= 6),
        "first_paragraph": ctx.get("lead") or "",
        "alt": " ".join(i.get("alt") or "" for i in images),
        "anchors": " ".join(l.get("text") or "" for l in links if l.get("internal")),
        "url": re.sub(r"[\W_]+", " ", path, flags=re.UNICODE),
    }


def _zone_count(cell) -> int:
    """Ячейка зоны у text_metrics — словарь со способами совпадения; берём первый, что есть."""
    if isinstance(cell, dict):
        for name in KEY_ZONE_COUNTS:
            if _n(cell.get(name)):
                return _n(cell.get(name))
        return 1 if cell.get("present") else 0
    return _n(cell)


def key_zone_hits(ctx) -> dict:
    """{фраза: {зона: вхождений}}. Если зоны посчитал text_metrics — берём его цифры."""
    ready_list = ctx.get("keys") or []
    if ready_list and any(isinstance(k.get("zones"), dict) for k in ready_list):
        return {k["key"]: {z: _zone_count((k.get("zones") or {}).get(z)) for z in ZONE_ORDER}
                for k in ready_list if k.get("key")}
    texts = zone_texts(ctx)
    if not any(texts.values()):
        return {}
    out: dict[str, dict] = {}
    for key in ctx.keys:
        words = text_metrics.letter_words(key)
        stems = [text_metrics.stem(w) for w in words if not text_metrics.is_stop(w)]
        stems = stems or [text_metrics.stem(w) for w in words]
        if not stems:
            continue
        hits = {}
        for zone, raw in texts.items():
            seq = [text_metrics.stem(w) for w in text_metrics.letter_words(raw)
                   if not text_metrics.is_stop(w)]
            hits[zone] = text_metrics.find_seq(seq, stems) if seq else 0
        out[key] = hits
    return out


# Изображения, безопасность, мобильность и интернационализация считаются в page_facts: его
# проверки приходят сюда через imported_rows(), дублировать их здесь нечем и незачем.

# ---------------------------------------------------------------------------- ссылки

@check("links.main_region_internal", "links", "Внутренние ссылки", severity="medium",
       source="Google: Links best practices")
def c_internal_links(ctx):
    summary = ctx.get("links_summary") or {}
    internal = _n(summary.get("internal"))
    external = _n(summary.get("external"))
    unknown = _n(summary.get("unknown_host"))
    if not summary:
        return nodata("Ссылки не разбирали")
    if internal == 0 and unknown == 0:
        return bad("Внутренних ссылок нет: страница — тупик для обхода", severity="high",
                   fix="Поставить ссылки на родительский раздел и смежные страницы")
    by_region = summary.get("by_region") or {}
    contextual = _n(by_region.get("main")) + _n(by_region.get("body"))
    msg = f"внутренних {internal}, внешних {external}, в основном тексте {contextual}"
    if internal and contextual == 0:
        return warn("Все внутренние ссылки — в меню и подвале, в тексте ни одной: " + msg, value=internal,
                    fix="Ссылки из текста работают заметно лучше шаблонных")
    return ok(msg, value=internal)


@check("links.empty_anchor", "links", "Пустые анкоры", severity="low",
       source="W3C: Link text; Google: Links best practices")
def c_empty_anchors(ctx):
    summary = ctx.get("links_summary") or {}
    empty = _n(summary.get("empty_anchor"))
    if not summary:
        return nodata("Ссылки не разбирали")
    if empty:
        return warn(f"Ссылок без текста и без aria-label: {empty}", value=empty,
                    fix="Дать текст или aria-label — иначе непонятно ни человеку, ни поисковику")
    return ok("У всех ссылок есть текст или aria-label")


@check("links.generic_anchor", "links", "Безликие анкоры", severity="low", kind=HEUR,
       source="ориентир редактора")
def c_vague_anchors(ctx):
    links = ctx.get("links") or []
    if not links:
        return nodata("Ссылок нет")
    vague_re = re.compile(r"^(здесь|тут|подробнее|читать далее|далее|ссылка|перейти|click here|here|"
                          r"read more|more|link|learn more)[.!…]*$", re.I)
    hits = [l for l in links if l.get("text") and vague_re.match(l["text"].strip())]
    if hits:
        return warn(f"Анкоров вида «подробнее» и «здесь»: {len(hits)}",
                    evidence=esc("; ".join(l["text"] for l in hits[:5]), 200),
                    fix="Написать в анкоре, что на той странице")
    return ok("Безликих анкоров нет")


@check("links.javascript_links", "links", "Ссылки через javascript:", severity="medium",
       source="Google: Links best practices (href обязателен)")
def c_js_links(ctx):
    summary = ctx.get("links_summary") or {}
    n = _n(summary.get("javascript"))
    if n:
        return warn(f"Ссылок на javascript: {n} — поисковик по ним не пойдёт", value=n,
                    fix="Использовать <a href=\"/адрес\">")
    return ok("Ссылок-заглушек нет")


@check("links.nofollow_internal", "links", "nofollow на своих ссылках", severity="low",
       source="Google: Qualify your outbound links")
def c_nofollow_internal(ctx):
    links = ctx.get("links") or []
    hits = [l for l in links if l.get("internal") and set(l.get("rel") or []) & {"nofollow", "ugc", "sponsored"}]
    if not links:
        return nodata("Ссылки не разбирали")
    if hits:
        return warn(f"Внутренних ссылок с nofollow/ugc/sponsored: {len(hits)}",
                    evidence=esc("; ".join(l.get("href", "") for l in hits[:5]), 240),
                    fix="На своих страницах эти атрибуты обычно лишние")
    return ok("На внутренних ссылках атрибутов nofollow нет")


# ---------------------------------------------------------------------------- AI-поиск

@check("ai.search_bots_access", "ai", "Доступ для AI-ботов", severity="medium",
       source="references/ai-bots.yaml (документация вендоров)")
def c_ai_bots(ctx):
    matrix = ctx.get("robots_matrix") or []
    if not matrix:
        return nodata("robots.txt не запрашивали")
    bots = matrix[0].get("bots") or {}
    blocked_extra = matrix[0].get("others_blocked") or []
    rows = {k: v for k, v in bots.items() if k in AI_BOTS}
    closed = sorted([k for k, v in rows.items() if not v] + [b for b in blocked_extra if b in AI_BOTS])
    if not rows and not blocked_extra:
        return nodata("В таблице доступа нет AI-ботов")
    if closed:
        return info("Закрыты: " + ", ".join(closed) + ". Это решение владельца, а не дефект",
                    value=", ".join(closed))
    return ok("Открыто всем AI-ботам из ростера", value=", ".join(sorted(rows)) or None)


@check("ai.llms_txt", "ai", "llms.txt", severity="info", kind=HEUR,
       source="предложение llmstxt.org; обязательным его не считает ни один поисковик")
def c_llms(ctx):
    data = ctx.get("llms_txt")
    if not data:
        return nodata("Файл не запрашивали (флаг --ai-files)")
    if data.get("error"):
        return info("Файл получить не удалось", value=esc(data.get("error"), 60))
    if 200 <= _n(data.get("status")) < 300:
        return info(f"llms.txt есть ({_qty(_n(data.get('bytes')), 'байт', 'байта', 'байт')})",
                    evidence=esc(data.get("head"), 200))
    return info(f"llms.txt нет (статус {data.get('status')}) — это не дефект", value=data.get("status"))


@check("ai.text_addressed_to_model", "ai", "Текст, обращённый к ИИ", severity="medium",
       source="SPEC §2 правило 4")
def c_ai_text(ctx):
    found = ctx.get("ai_addressed")
    if not found:
        return ok("Видимый текст к моделям не обращается")
    return warn("Видимый текст обращается к ИИ или агенту",
                evidence=esc(json.dumps(found.get("matched"), ensure_ascii=False), 200),
                fix="Такой текст воспринимается как попытка повлиять на ассистента, а не как контент")


@check("ai.answer_first", "ai", "Ответ в начале текста", severity="low", kind=HEUR,
       source="ориентир редактора: самодостаточность начала, без норм длины")
def c_answer_first(ctx):
    lead = ctx.get("lead")
    if not lead:
        return nodata("Текст не разбирали")
    words = len(text_metrics.letter_words(lead))
    if words < 15:
        return warn("Первые строки почти без текста: модели и люди не увидят ответа сразу", value=words,
                    fix="Начать с ответа на главный вопрос страницы")
    return ok(f"В начале текста {_qty(words, 'слово', 'слова', 'слов')}", evidence=esc(lead, 200))


# ---------------------------------------------------------------------------- коммерческие сигналы

_PHONE_RE = re.compile(r"(?:\+7|\b8)[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"
                       r"|\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{2,4}[\s-]?\d{2,4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LEGAL_RE = re.compile(r"\b(ИНН|ОГРН|ОГРНИП|КПП|VAT|Reg\.?\s?No)\b[\s:]*\d{5,}", re.I)
_ADDRESS_RE = re.compile(r"\b(ул\.|улица|пр-?т|проспект|шоссе|д\.\s?\d|офис|оф\.|стр\.\s?\d"
                         r"|street|avenue|suite|floor)\b", re.I)


_PRICE_RE = re.compile(r"(?:\d[\d\s  ]{2,}|\d+)\s?(?:₽|руб\.?|р\.|\$|€|USD|EUR|RUB)"
                       r"|(?:от|from)\s+\d[\d\s]{2,}", re.I)
_BUY_RE = re.compile(r"\b(купить|заказать|в корзину|оформить заказ|оставить заявку|записаться|"
                     r"add to cart|buy now|order now|checkout)\b", re.I)


def is_commercial(ctx) -> bool:
    """Похожа ли страница на коммерческую: цена, призыв к покупке, форма заказа или Offer."""
    text = _visible(ctx)
    if _PRICE_RE.search(text) or _BUY_RE.search(text):
        return True
    types = {t.lower() for t in (ctx.get("schema_types") or [])}
    if types & {"offer", "aggregateoffer", "product", "localbusiness", "service", "order"}:
        return True
    # Сама по себе форма признаком продажи не считается: поиск по сайту есть почти везде,
    # и раньше из-за него коммерческими объявлялись страницы документации. GET-форма по
    # RFC 9110 §9.2.1 безопасна и ничего не меняет — заказ отправляют методом POST.
    forms = dig(ctx.bundle, "page.markup.form_list") or []
    return any((f.get("method") or "").lower() not in ("", "get") for f in forms)


def _visible(ctx) -> str:
    text = dig(ctx.bundle, "text.lead") or ""
    full = ctx.bundle.get("visible_text") or ""
    return full or text


@check("commerce.contacts_visible", "commerce", "Контакты на странице", severity="medium", kind=HEUR,
       source="references/yandex.md: коммерческие факторы")
def c_contacts(ctx):
    text = _visible(ctx)
    links = ctx.get("links") or []
    if not text and not links:
        return nodata("Текст не разбирали")
    has_phone = bool(_PHONE_RE.search(text)) or any(l.get("kind") == "tel" for l in links)
    has_mail = bool(_EMAIL_RE.search(text)) or any(l.get("kind") == "mailto" for l in links)
    has_addr = bool(_ADDRESS_RE.search(text))
    found = [n for n, v in (("телефон", has_phone), ("почта", has_mail), ("адрес", has_addr)) if v]
    if found:
        return ok("Нашли: " + ", ".join(found), value=", ".join(found))
    if not is_commercial(ctx):
        return info("Контактов нет, но и признаков продажи на странице нет: для информационной "
                    "страницы это не дефект")
    return warn("Контактов на странице не нашли",
                fix="На странице есть цены или форма заказа: телефон, почта и адрес должны быть "
                    "на видном месте, иначе доверия не будет ни у человека, ни у Яндекса")


@check("commerce.legal_entity", "commerce", "Реквизиты", severity="low", kind=HEUR,
       source="references/yandex.md: юридические сигналы")
def c_legal(ctx):
    text = _visible(ctx)
    if not text:
        return nodata("Текст не разбирали")
    m = _LEGAL_RE.search(text)
    if m:
        return ok("Реквизиты есть", value=esc(m.group(0), 60))
    return info("Реквизитов (ИНН/ОГРН/VAT) на странице нет — обычно они в подвале или на отдельной странице")


@check("commerce.address_markup", "commerce", "Разметка организации", severity="low",
       source="Google: Organization structured data")
def c_org(ctx):
    types = [t.lower() for t in (ctx.get("schema_types") or [])]
    orgs = [t for t in types if t in ("organization", "localbusiness", "store", "restaurant",
                                      "corporation", "onlinebusiness")]
    if orgs:
        return ok("Организация размечена", value=", ".join(orgs))
    if types:
        return info("Разметки организации нет", value=", ".join(esc(t, 30) for t in types[:8]))
    return info("Разметки организации нет")


# ---------------------------------------------------------------------------- параметры реестра,
# которые закрываются уже собранными данными: по одной проверке на параметр, без новых запросов

@check("access.initial_status", "access", "Статус до редиректов", severity="info", source="RFC 9110")
def c_initial_status(ctx):
    chain = ctx.get("chain") or []
    if not chain:
        return nodata("Нет данных о запросе")
    first = chain[0]
    return info(f"Первый ответ: {first.get('status')}", value=first.get("status"))


@check("access.redirect_loop", "access", "Петля редиректов", severity="critical", source="RFC 9110")
def c_redirect_loop(ctx):
    chain = ctx.get("chain") or []
    if len(chain) < 2:
        return ok("Петли нет") if chain else nodata("Нет данных о запросе")
    urls = [s.get("url") for s in chain]
    if len(set(urls)) < len(urls):
        return bad("Адреса в цепочке повторяются — это петля", severity="critical",
                   evidence=esc(" → ".join(map(str, urls)), 240),
                   fix="Разорвать цикл редиректов: страница недостижима ни для людей, ни для поиска")
    return ok("Петли нет", value=len(chain) - 1)


@check("access.doc_size_limit", "access", "Размер документа", severity="medium",
       source="Google: Googlebot читает первые 15 МБ HTML")
def c_doc_size(ctx):
    size = _n(ctx.get("bytes"))
    if not size:
        return nodata("Размер неизвестен")
    human = f"{round(size / 1024)} КБ" if size < 1048576 else f"{round(size / 1048576, 1)} МБ"
    if size > 15 * 1048576:
        return bad(f"HTML больше 15 МБ ({human}): остальное Googlebot не прочитает", value=human,
                   severity="high", fix="Разгрузить документ: лишнее — в отдельные файлы")
    if size > 10 * 1048576:
        return warn(f"HTML близок к лимиту чтения: {human} из 15 МБ", value=human,
                    fix="Смотреть, что весит: инлайн-данные, повторы шаблона")
    return ok(f"{human} при лимите чтения 15 МБ", value=human)


@check("access.nav_without_href", "access", "Навигация без a href", severity="medium",
       source="Google: Links best practices (нужен <a href>)")
def c_nav_without_href(ctx):
    links = ctx.get("links") or []
    if not links:
        return nodata("Ссылок нет")
    nav_regions = {"nav", "header", "footer"}
    # kind == "fragment" — обычная ссылка на якорь той же страницы (оглавление, «наверх»,
    # аккордеон). Поисковик по ней ходит, адрес у неё есть; в находку идут только те,
    # у которых адреса нет вообще или переход сделан скриптом.
    broken = [l for l in links if l.get("region") in nav_regions
              and l.get("kind") in ("none", "javascript")]
    if broken:
        return warn(f"В меню и подвале {_qty(len(broken), '«ссылка»', '«ссылки»', '«ссылок»')} "
                    "без настоящего адреса",
                    evidence=esc("; ".join((l.get("text") or l.get("kind") or "") for l in broken[:5]), 200),
                    fix="Переходы делать через <a href>: иначе раздел не обойдут")
    return ok("Навигация на обычных ссылках")


@check("access.canonical_count", "access", "Несколько canonical", severity="high",
       source="Google: Consolidate duplicate URLs")
def c_canonical_count(ctx):
    canon = ctx.get("canonical") or []
    if not canon:
        return nodata("canonical нет")
    if len(canon) > 1:
        return bad(f"rel=canonical объявлен {_qty(len(canon), 'раз', 'раза', 'раз')} "
                   "— Google проигнорирует все", severity="high",
                   evidence=esc("; ".join(c.get("href", "") for c in canon), 240),
                   fix="Оставить один тег")
    return ok("Один canonical")


@check("access.canonical_in_head", "access", "canonical внутри head", severity="medium",
       source="Google: Consolidate duplicate URLs")
def c_canonical_in_head(ctx):
    canon = ctx.get("canonical") or []
    if not canon:
        return nodata("canonical нет")
    outside = [c for c in canon if not c.get("in_head")]
    if outside:
        return bad("canonical стоит вне <head> — он не действует", severity="medium",
                   evidence=esc("; ".join(f"строка {c.get('line')}" for c in outside), 120),
                   fix="Перенести в <head>")
    return ok("canonical в <head>")


@check("access.canonical_absolute", "access", "canonical абсолютный", severity="low",
       source="Google: Consolidate duplicate URLs")
def c_canonical_absolute(ctx):
    canon = ctx.get("canonical") or []
    if not canon:
        return nodata("canonical нет")
    rel = [c for c in canon if not http_safe.is_url(str(c.get("href") or ""))]
    if rel:
        return warn("canonical задан относительным адресом", evidence=esc(rel[0].get("href"), 160),
                    fix="Писать полный адрес со схемой и доменом")
    return ok("Адрес абсолютный")


URL_CHECKS = (
    ("access.url_underscore", "Подчёркивания в пути", "low",
     lambda path, parts: ("_" in path, "в пути есть подчёркивания", "В пути подчёркиваний нет",
                          "Дефис читается поисковиком как разделитель слов, подчёркивание — нет")),
    ("access.url_length", "Длина URL", "info",
     lambda path, parts: (False, "", _qty(len(parts.geturl()), "символ", "символа", "символов"),
                          None)),
    ("access.url_depth", "Глубина пути", "info",
     lambda path, parts: (False, "", _qty(len([s for s in path.split("/") if s]),
                                          "уровень", "уровня", "уровней"), None)),
    ("access.url_case", "Верхний регистр в пути", "low",
     lambda path, parts: (bool(re.search(r"[A-ZА-Я]", path)), "в пути есть заглавные буквы",
                          "В пути только строчные буквы",
                          "Адреса чувствительны к регистру: разный регистр — разные страницы")),
    ("access.url_encoding", "Кодирование не-ASCII", "info",
     lambda path, parts: (bool(re.search(r"%[0-9A-Fa-f]{2}", parts.path or "")),
                          "путь закодирован процентами — так и должно быть для кириллицы, "
                          "но в логах и отчётах адрес будет нечитаемым",
                          "Путь в ASCII, процентного кодирования нет", None)),
    ("access.url_session_params", "Параметры сессии", "low",
     lambda path, parts: (bool(re.search(r"(?:^|&)(?:sid|sessionid|phpsessid|jsessionid)=", parts.query, re.I)),
                          "в адресе параметр сессии", "Параметров сессии в адресе нет",
                          "Параметр сессии в ссылках плодит дубли: убрать или закрыть Clean-param")),
)


def _make_url_check(cid, title, severity, fn):
    @check(cid, "access", title, severity=severity,
           source="ориентир редактора: требований к виду URL у Google нет")
    def _fn(ctx, _fn=fn, _sev=severity):
        url = ctx.url
        if not url:
            return nodata("Адрес не задан")
        parts = urlsplit(url)
        raw = parts.path or "/"
        hit, hit_text, ok_text, fix = _fn(unquote(raw) if "%" in raw else raw, parts)
        shown = esc(parts.path, 120)
        if _sev == "info":
            return info(hit_text if hit else ok_text, value=shown)
        if hit:
            return warn(hit_text, value=shown, fix=fix)
        return ok(ok_text, value=shown)
    return _fn


for _spec in URL_CHECKS:
    _make_url_check(*_spec)


@check("meta.title_count", "meta", "Один тег title", severity="medium",
       source="HTML Standard: в документе один <title>")
def c_title_count(ctx):
    n = _n(ctx.get("title_count"))
    if n == 0:
        return nodata("title нет")
    if n > 1:
        return warn(f"Тегов title: {n} — поисковик возьмёт первый", value=n, fix="Оставить один")
    return ok("Один", value=1)


@check("meta.desc_count", "meta", "Один тег description", severity="low",
       source="Google: Control your snippets")
def c_desc_count(ctx):
    n = _n(ctx.get("description_count"))
    if n == 0:
        return nodata("description нет")
    if n > 1:
        return warn(f"Тегов description: {n}", value=n, fix="Оставить один")
    return ok("Один", value=1)


@check("meta.desc_equals_title", "meta", "description повторяет title", severity="low",
       source="ориентир редактора")
def c_desc_equals_title(ctx):
    title, desc = ctx.get("title"), ctx.get("description")
    if not title or not desc:
        return nodata("Нет title или description")
    if title.strip().lower() == desc.strip().lower():
        return warn("description дословно повторяет title — в сниппете это пустая строка",
                    fix="Описание должно добавлять то, чего нет в заголовке")
    return ok("Описание не дублирует заголовок")


@check("meta.h1_count", "meta", "Число H1", severity="low",
       source="Google: несколько H1 допустимы, но структура от этого не выигрывает")
def c_h1_count(ctx):
    n = _n((ctx.get("heading_counts") or {}).get("h1"))
    if n == 0:
        return nodata("H1 нет")
    if n > 1:
        return warn(f"H1 на странице: {n}", value=n, fix="Обычно это вёрстка, а не структура: оставить один")
    return ok("Один H1", value=1)


@check("meta.heading_count_total", "meta", "Сколько заголовков всего", severity="info",
       source="подсчёт по HTML")
def c_heading_total(ctx):
    counts = ctx.get("heading_counts") or {}
    if not counts:
        return warn("Заголовков H1–H6 нет совсем", fix="Разбить текст подзаголовками")
    return info(", ".join(f"{k}: {v}" for k, v in sorted(counts.items())),
                value=sum(_n(v) for v in counts.values()))


@check("meta.heading_empty", "meta", "Пустые заголовки", severity="low",
       source="W3C: Headings")
def c_heading_empty(ctx):
    headings = ctx.get("headings") or []
    if not headings:
        return nodata("Заголовков нет")
    empty = [h for h in headings if not (h.get("text") or "").strip()]
    if empty:
        return warn(f"Заголовков без текста: {len(empty)}",
                    evidence=esc("; ".join(f"h{h.get('level')} строка {h.get('line')}" for h in empty[:5]), 160),
                    fix="Либо дать текст, либо не использовать тег заголовка для отступа")
    return ok("Все заголовки с текстом")


@check("meta.heading_hidden", "meta", "Скрытые заголовки", severity="medium",
       source="Google: Hidden text and links")
def c_heading_hidden(ctx):
    headings = ctx.get("headings") or []
    if not headings:
        return nodata("Заголовков нет")
    hidden = [h for h in headings if h.get("hidden")]
    if hidden:
        return warn(f"Заголовков в скрытых блоках: {len(hidden)}",
                    evidence=esc("; ".join(f"h{h.get('level')}: {h.get('text')}" for h in hidden[:4]), 200),
                    fix="Скрытый заголовок для поиска — риск; для доступности есть sr-only, "
                        "и такой текст должен совпадать с видимым смыслом")
    return ok("Скрытых заголовков нет")


@check("content.sentences", "content", "Предложения", severity="info", source="подсчёт по тексту")
def c_sentences(ctx):
    counts = ctx.get("text_counts") or {}
    sent = ctx.get("rhythm") or {}
    if not counts:
        return nodata("Текст не разбирали")
    desc = (sent.get("sentence_words") or {})
    mean = desc.get("mean")
    return info(f"{_qty(_n(counts.get('sentences_prose')), 'предложение', 'предложения', 'предложений')}"
                f", в среднем {mean} {_plural(mean or 0, 'слово', 'слова', 'слов')} "
                f"(от {desc.get('min')} до {desc.get('max')})",
                value=counts.get("sentences_prose"))


@check("content.paragraphs", "content", "Абзацы", severity="info", source="подсчёт по тексту")
def c_paragraphs(ctx):
    counts = ctx.get("text_counts") or {}
    if not counts:
        return nodata("Текст не разбирали")
    para = dig(ctx.bundle, "text.rhythm.paragraph_words") or {}
    mean = para.get("mean")
    return info(f"{_qty(_n(counts.get('paragraphs_prose')), 'абзац', 'абзаца', 'абзацев')}, в среднем "
                f"{mean} {_plural(mean or 0, 'слово', 'слова', 'слов')}",
                value=counts.get("paragraphs_prose"))


@check("content.stems_top", "content", "Частые основы", severity="info", kind=HEUR,
       source="стеммер пакета (RU/EN), не морфологический словарь")
def c_stems_top(ctx):
    top = ctx.get("stems_top") or []
    if not top:
        return nodata("Текст не разбирали")
    return info("; ".join(f"{esc(s.get('stem'), 30)} ×{s.get('count')} ({s.get('share_pct')} %)"
                          for s in top[:8]), value=top[0].get("stem"))


@check("content.nausea_academic", "content", "Тошнота академическая", severity="low", kind=HEUR,
       source="формула сервисов не публична; считаем свою и подписываем")
def c_nausea_academic(ctx):
    n = ctx.get("nausea") or {}
    pct = n.get("academic_pct")
    if pct is None:
        return nodata("Текст не разбирали")
    text = f"{pct} % — доля самой частой значимой основы «{n.get('top_stem')}» среди всех слов"
    if pct >= 8:
        return warn(text, value=pct, fix="Ориентир редактора: смотреть, не повторяется ли ключ ради ключа")
    return ok(text, value=pct)


@check("content.passive_share", "content", "Доля пассива", severity="low", kind=HEUR,
       source="эвристика по маркерам RU/EN, не разбор грамматики")
def c_passive(ctx):
    p = ctx.get("passive") or {}
    pct = p.get("pct")
    if pct is None:
        return nodata("Пассив не считали")
    text = f"{pct} % предложений с маркерами пассива ({p.get('sentences_with_marker')} из {p.get('sentences_prose')})"
    if pct >= 35:
        return warn(text, value=pct, evidence=esc("; ".join(map(str, p.get("markers_top") or [])), 160),
                    fix="Пассив прячет, кто действует: переписать на действующее лицо")
    return ok(text, value=pct)


@check("content.readability_en", "content", "Читаемость EN", severity="info", kind=HEUR,
       source="Flesch Reading Ease — формула опубликована")
def c_readability_en(ctx):
    if (ctx.get("text_lang") or "") != "en":
        return nodata("Текст не английский")
    scores = dig(ctx.bundle, "text.readability.scores") or []
    if not scores:
        return nodata("Читаемость не считали")
    first = scores[0]
    return info(f"{first.get('name')}: {first.get('value')}", value=first.get("value"),
                evidence=esc(first.get("formula"), 140))


@check("content.chat_artifacts", "content", "Артефакты чат-бота", severity="medium", kind=HEUR,
       source="словарь deai_scan (свой)")
def c_chat_artifacts(ctx):
    hits = [h for h in (dig(ctx.bundle, "deai.hits") or []) if h.get("id") == "chat_residue"]
    if not (ctx.bundle.get("deai") or {}):
        return nodata("Текст не разбирали")
    if hits:
        return bad(f"Следы переписки с ассистентом: {len(hits)}", severity="medium",
                   evidence=esc("; ".join(esc(h.get("match"), 60) for h in hits[:4]), 200),
                   fix="Удалить: это не текст страницы, а ответ модели")
    return ok("Артефактов чат-бота нет")


@check("content.cliche", "content", "Штампы и слоп-лексика", severity="low", kind=HEUR,
       source="словарь deai_scan (свой)")
def c_cliche(ctx):
    deai = ctx.bundle.get("deai") or {}
    if not deai:
        return nodata("Текст не разбирали")
    hits = [h for h in (deai.get("hits") or []) if h.get("id") == "stamp"]
    if len(hits) >= 3:
        return warn(f"Штампов: {len(hits)}",
                    evidence=esc("; ".join(esc(h.get("match"), 50) for h in hits[:5]), 220),
                    fix="Удалять лучше, чем заменять: штамп обычно ничего не сообщает")
    if hits:
        return info(f"Штампов: {len(hits)}",
                    evidence=esc("; ".join(esc(h.get("match"), 50) for h in hits), 200))
    return ok("Штампов не нашли")


@check("content.dates_visible", "content", "Даты на странице", severity="low",
       source="подсчёт по видимому тексту")
def c_dates_visible(ctx):
    dates = ctx.get("dates") or {}
    text_dates = dates.get("text_dates") or []
    if not dates:
        return nodata("Текст не разбирали")
    if not text_dates:
        return info("Дат в тексте нет: для части страниц это нормально, для новости и обзора — нет")
    return ok(f"Дат в тексте: {len(text_dates)}", value=", ".join(map(str, text_dates[:6])))


@check("content.key_exact_vs_morph", "content", "Точное и морфологическое вхождение",
       severity="info", source="подсчёт text_metrics, правила совпадения — в его выводе")
def c_key_forms(ctx):
    keys = ctx.get("keys") or []
    if not keys:
        return nodata("Ключевые фразы не заданы")
    parts = []
    for k in keys[:6]:
        parts.append(f"«{esc(k.get('key'), 50)}»: словоформами {k.get('exact_forms')}, "
                     f"по основам {k.get('exact_by_stems')}, в окне {k.get('any_order_window')}")
    return info("; ".join(parts))


@check("links.total", "links", "Сколько ссылок на странице", severity="info", source="подсчёт по HTML")
def c_links_total(ctx):
    summary = ctx.get("links_summary") or {}
    if not summary:
        return nodata("Ссылки не разбирали")
    return info(f"всего {summary.get('total')}, внутренних {_n(summary.get('internal'))}, "
                f"внешних {_n(summary.get('external'))}", value=summary.get("total"))


@check("links.by_region", "links", "Ссылки по зонам", severity="info", source="подсчёт по HTML")
def c_links_by_region(ctx):
    by_region = (ctx.get("links_summary") or {}).get("by_region") or {}
    if not by_region:
        return nodata("Ссылки не разбирали")
    return info(", ".join(f"{k}: {v}" for k, v in sorted(by_region.items(), key=lambda x: -x[1])),
                value=sum(by_region.values()))


@check("links.external_hosts", "links", "Внешние домены", severity="info", source="подсчёт по HTML")
def c_external_hosts(ctx):
    links = ctx.get("links") or []
    hosts = Counter()
    for l in links:
        if l.get("internal") is False and http_safe.is_url(str(l.get("href") or "")):
            hosts[urlsplit(l["href"]).hostname or "?"] += 1
    if not links:
        return nodata("Ссылки не разбирали")
    if not hosts:
        return info("Внешних ссылок нет")
    return info(f"Внешних доменов: {len(hosts)} — "
                + ", ".join(f"{esc(h, 40)} ×{n}" for h, n in hosts.most_common(6)), value=len(hosts))


@check("links.target_blank_noopener", "links", "target=_blank без noopener", severity="low",
       source="MDN: rel=noopener (современные браузеры ставят его сами)")
def c_target_blank(ctx):
    links = ctx.get("links") or []
    if not links:
        return nodata("Ссылки не разбирали")
    if not any("target" in l for l in links):
        return nodata("В фактах страницы нет атрибута target — проверить нечем")
    risky = [l for l in links if (l.get("target") or "") == "_blank"
             and "noopener" not in (l.get("rel") or [])]
    if risky:
        return info(f"Ссылок в новое окно без rel=noopener: {len(risky)}",
                    value=len(risky))
    return ok("Таких ссылок нет")


AI_BOT_GROUPS = (
    ("ai.training_bots_access", "Боты обучения", "medium",
     ("GPTBot", "Google-Extended", "Applebot-Extended", "ClaudeBot", "CCBot"),
     "Закрыть или открыть обучение — решение владельца, а не дефект"),
    ("ai.user_fetch_bots", "Боты по запросу пользователя", "info",
     ("ChatGPT-User", "Claude-User", "PerplexityBot"),
     "Эти боты ходят, когда человек просит ассистента открыть страницу"),
)


def _make_ai_group_check(cid, title, severity, bots, note):
    @check(cid, "ai", title, severity=severity, source="references/ai-bots.yaml (документация вендоров)")
    def _fn(ctx, _bots=bots, _note=note):
        matrix = ctx.get("robots_matrix") or []
        if not matrix:
            return nodata("robots.txt не запрашивали")
        rows = matrix[0].get("bots") or {}
        others = matrix[0].get("others_blocked") or []
        known = {k: v for k, v in rows.items() if k in _bots}
        closed = sorted([k for k, v in known.items() if not v] + [b for b in others if b in _bots])
        if not known and not closed:
            return nodata("В таблице доступа этих ботов нет")
        if closed:
            return info("Закрыты: " + ", ".join(closed) + ". " + _note, value=", ".join(closed))
        return ok("Открыты: " + ", ".join(sorted(known)), value=len(known))
    return _fn


for _spec in AI_BOT_GROUPS:
    _make_ai_group_check(*_spec)


@check("ai.google_extended", "ai", "Google-Extended в robots.txt", severity="info",
       source="Google: Google-Extended управляет обучением, а не показом в поиске")
def c_google_extended(ctx):
    matrix = ctx.get("robots_matrix") or []
    if not matrix:
        return nodata("robots.txt не запрашивали")
    rows = matrix[0].get("bots") or {}
    key = next((k for k in rows if k.lower() == "google-extended"), None)
    if key is None:
        return info("Группы Google-Extended в robots.txt нет: обучение не ограничено")
    return info("Google-Extended " + ("открыт" if rows[key] else "закрыт")
                + " — на показ страницы в поиске и в AI Overviews это не влияет",
                value="открыт" if rows[key] else "закрыт")


@check("ai.yandex_additional", "ai", "YandexAdditional", severity="high",
       source="Яндекс: YandexAdditional не подчиняется группе User-agent: *")
def c_yandex_additional(ctx):
    matrix = ctx.get("robots_matrix") or []
    if not matrix:
        return nodata("robots.txt не запрашивали")
    rows = matrix[0].get("bots") or {}
    notes = dig(ctx.bundle, "robots.bot_notes") or {}
    key = next((k for k in rows if k.lower().startswith("yandexadditional")), None)
    if key is None:
        return nodata("В таблице доступа нет YandexAdditional")
    hint = "; ".join(notes.get(key) or [])
    if rows[key]:
        return ok("Открыт", value="открыт", evidence=esc(hint, 200) or None)
    return info("Закрыт: Нейро и Алиса страницу не используют", value="закрыт",
                evidence=esc(hint, 200) or None)


@check("ai.csr_for_ai", "ai", "Текст только после JS", severity="high",
       source="AI-боты не исполняют скрипты")
def c_csr_for_ai(ctx):
    csr = ctx.get("csr") or {}
    if csr.get("suspected"):
        return bad("Текст появляется только после скрипта: AI-боты его не увидят вовсе",
                   severity="high", evidence=esc(", ".join(csr.get("signals") or []), 200),
                   fix="Отдавать текст в HTML: для AI-поиска это не «медленнее», а «нет текста»")
    return ok("Текст есть в ответе сервера")


@check("ai.ai_txt", "ai", "ai.txt", severity="info", kind=HEUR,
       source="частное предложение, ни один поисковик его не требует")
def c_ai_txt(ctx):
    data = ctx.get("ai_txt")
    if not data:
        return nodata("Файл не запрашивали (флаг --ai-files)")
    if data.get("error"):
        return info("Файл получить не удалось", value=esc(data.get("error"), 60))
    if 200 <= _n(data.get("status")) < 300:
        return info(f"ai.txt есть ({_qty(_n(data.get('bytes')), 'байт', 'байта', 'байт')})",
                    evidence=esc(data.get("head"), 200))
    return info(f"ai.txt нет (статус {data.get('status')}) — это не дефект", value=data.get("status"))


@check("ai.nosnippet", "ai", "nosnippet", severity="high",
       source="Google: nosnippet убирает страницу из сниппетов и из AI-ответов")
def c_nosnippet(ctx):
    robots = ctx.get("robots_meta") or {}
    hit = [k for k, v in robots.items() if "nosnippet" in v]
    if hit:
        return bad("Стоит nosnippet: ни сниппета, ни цитаты в AI-ответе не будет", severity="high",
                   value=", ".join(hit), fix="Убрать, если страница должна цитироваться")
    return ok("nosnippet не стоит")


@check("ai.max_snippet", "ai", "max-snippet", severity="high",
       source="Google: max-snippet ограничивает длину текста в выдаче")
def c_max_snippet(ctx):
    robots = ctx.get("robots_meta") or {}
    for key, values in robots.items():
        for v in values:
            m = re.fullmatch(r"max-snippet:\s*(-?\d+)", v.strip())
            if m:
                n = int(m.group(1))
                if n == 0:
                    return bad("max-snippet:0 — сниппета не будет", severity="high", value=v,
                               fix="Снять ограничение, если страница должна показываться с текстом")
                if n > 0:
                    return info(f"Сниппет ограничен "
                                f"{_qty(n, 'символом', 'символами', 'символами')} ({key})", value=v)
                return ok("max-snippet:-1 — ограничения нет", value=v)
    return ok("Ограничения длины сниппета нет")


ZONE_CHECK_IDS = (
    ("content.key_in_title", "title", "medium"),
    ("content.key_in_description", "description", "low"),
    ("content.key_in_h1", "h1", "medium"),
    ("content.key_in_h2h6", "h2_h6", "low"),
    ("content.key_in_first_para", "first_paragraph", "low"),
    ("content.key_in_alt", "alt", "low"),
    ("content.key_in_anchors", "anchors", "low"),
    ("content.key_in_url", "url", "low"),
)


def _make_zone_check(cid, zone, severity):
    @check(cid, "content", f"Ключ в зоне: {ZONE_RU[zone]}", severity=severity, kind=HEUR,
           source="ориентир редактора: зоны вхождения; нормы плотности у поисковиков нет")
    def _fn(ctx, _zone=zone):
        if not ctx.keys:
            return nodata("Ключевые фразы не заданы")
        zone_words = _n(dig(ctx.bundle, f"text.zones.{_zone}.words"))
        hits = key_zone_hits(ctx)
        if not hits:
            return nodata("Зоны не разобрались")
        present = [k for k, z in hits.items() if _n(z.get(_zone))]
        absent = [k for k in hits if k not in present]
        if zone_words == 0 and not present:
            return nodata(f"Зона «{ZONE_RU[_zone]}» на странице пустая")
        if not present:
            return warn("Ни одной фразы: " + "; ".join(esc(k, 50) for k in absent[:5]),
                        value=f"слов в зоне: {zone_words}",
                        fix="Не вставлять ключ ради ключа: если страница про это, предмет называют своими словами")
        text = "есть: " + "; ".join(esc(k, 50) for k in present[:4])
        if absent:
            text += "; нет: " + "; ".join(esc(k, 50) for k in absent[:4])
        return ok(text, value=f"слов в зоне: {zone_words}")
    return _fn


for _spec in ZONE_CHECK_IDS:
    _make_zone_check(*_spec)


# ---------------------------------------------------------------------------- проверки по сайту

@check("meta.title_duplicate_site", "site", "Дубли title", severity="high",
       source="Google: Consolidate duplicate URLs", site=True)
def s_dup_titles(pages):
    return _dup(pages, "title", "title")


@check("meta.desc_duplicate_site", "site", "Дубли description", severity="medium",
       source="Google: Control your snippets", site=True)
def s_dup_desc(pages):
    return _dup(pages, "description", "meta description")


@check("site.duplicate_h1", "site", "Дубли H1", severity="low", source="ориентир редактора", site=True)
def s_dup_h1(pages):
    values = {}
    for p in pages:
        h1 = next((h.get("text") for h in (dig(p["facts"], "page.headings") or [])
                   if h.get("level") == 1), None)
        if h1:
            values.setdefault(h1.strip().lower(), []).append(p["target"])
    return _dup_verdict(values, "H1", len(pages))


def _dup(pages, field, label):
    values = {}
    for p in pages:
        val = dig(p["facts"], FIELD_PATHS[field][0])
        if val:
            values.setdefault(str(val).strip().lower(), []).append(p["target"])
    return _dup_verdict(values, label, len(pages))


def _dup_verdict(values: dict, label: str, total: int):
    if not values:
        return nodata(f"Ни на одной странице нет {label}")
    dupes = {k: v for k, v in values.items() if len(v) > 1}
    if dupes:
        lines = [f"«{esc(k, 80)}» — {_qty(len(v), 'страница', 'страницы', 'страниц')}"
                 for k, v in list(dupes.items())[:5]]
        return warn(f"Повторяющихся {label}: {len(dupes)} на "
                    f"{_qty(total, 'проверенной странице', 'проверенных страницах', 'проверенных страницах')}",
                    evidence=esc("; ".join(lines), 300),
                    fix=f"Переписать {label} так, чтобы по нему было понятно, какая это страница")
    return ok("Проверена одна страница: сравнивать не с чем" if total == 1
              else f"{label} у всех {_qty(total, 'страницы', 'страниц', 'страниц')} разные")


@check("site.pages_noindex", "site", "Страницы, закрытые от индексации", severity="high",
       source="Google: noindex", site=True)
def s_blocked(pages):
    closed = [p["target"] for p in pages if dig(p["facts"], "page.noindex")]
    if closed:
        return bad(f"Закрыты от индексации: {len(closed)} из {len(pages)}", severity="high",
                   evidence=esc("; ".join(closed[:5]), 300),
                   fix="Проверить, намеренно ли это")
    return ok("Единственная страница открыта для индексации" if len(pages) == 1
              else f"Все {_qty(len(pages), 'страница', 'страницы', 'страниц')} "
                   "открыты для индексации")


@check("site.pages_status", "site", "Коды ответа по списку", severity="critical",
       source="RFC 9110", site=True)
def s_status(pages):
    bad_rows = [(p["target"], dig(p["facts"], "page.fetch.status")) for p in pages
                if dig(p["facts"], "page.fetch.status") not in (200, None)]
    if bad_rows:
        return bad(f"Не отвечают 200: {len(bad_rows)} из {len(pages)}", severity="critical",
                   evidence=esc("; ".join(f"{u} → {s}" for u, s in bad_rows[:5]), 300),
                   fix="Разобраться с кодами ответа до остальных правок")
    return ok("Единственная страница отвечает 200" if len(pages) == 1
              else f"Все {_qty(len(pages), 'страница', 'страницы', 'страниц')} отвечают 200")


# ---------------------------------------------------------------------------- сборка отчёта

def run_checks(ctx: Facts, checks: list[Check], arg) -> list[dict]:
    rows = []
    for chk in checks:
        try:
            result = chk.fn(arg)
        except Exception as exc:  # одна упавшая проверка не должна ронять отчёт
            result = {"verdict": NODATA, "observation": f"проверка не выполнилась: {type(exc).__name__}",
                      "severity": "info"}
        if not isinstance(result, dict):
            result = {"verdict": NODATA, "observation": "проверка ничего не вернула", "severity": "info"}
        row = {
            "id": chk.id, "group": chk.group, "group_title": group_title(chk.group),
            "title": chk.title, "kind": chk.kind, "kind_label": KIND_RU[chk.kind],
            "source": chk.source, "severity": chk.severity, "in_registry": False,
        }
        row.update(result)
        if row["verdict"] in (OK, INFO, NODATA):
            row["severity"] = "info"
        row["verdict_label"] = VERDICT_RU[row["verdict"]]
        rows.append(row)
    return rows


SCRIPT_NAMES = {"page": "page_facts", "text": "text_metrics", "schema": "schema_check",
                "robots": "robots_check", "sitemap": "sitemap_check"}
SCRIPT_STATUS = {"pass": OK, "ok": OK, "fail": BAD, "problem": BAD, "warn": WARN, "warning": WARN,
                 "info": INFO, "skip": NODATA, "no_data": NODATA, "unknown": NODATA}
CHECK_LISTS = ("page", "text", "schema", "robots", "sitemap")


def imported_rows(bundle: dict) -> list[dict]:
    """Проверки, которые посчитали сами скрипты пакета (`checks` в их выводе).

    Второй слой сопоставления: статусы, группы и серьёзность приводятся к нашим.
    Если скрипт поменяет названия статусов — правится только SCRIPT_STATUS.
    """
    rows: list[dict] = []
    for scope in CHECK_LISTS:
        data = bundle.get(scope)
        if not isinstance(data, dict):
            continue
        for item in data.get("checks") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            verdict = SCRIPT_STATUS.get(str(item.get("status", "")).lower(), INFO)
            severity = str(item.get("severity") or "info").lower()
            if verdict in (OK, INFO, NODATA) or severity not in SEVERITY_RANK:
                severity = "info"
            source = item.get("source") or ""
            kind = HEUR if "ориентир" in source or "эвристик" in source or "оценка" in source else DET
            rows.append({
                "id": str(item["id"]), "group": group_slug(item.get("group")),
                "group_title": group_title(group_slug(item.get("group"))),
                "title": str(item.get("title") or item["id"]),
                "verdict": verdict, "verdict_label": VERDICT_RU[verdict], "severity": severity,
                "kind": kind, "kind_label": KIND_RU[kind], "source": source or None,
                "observation": item.get("observation"),
                "value": item.get("value"), "evidence": item.get("evidence"),
                "fix": item.get("note") or item.get("fix"),
                "from_script": SCRIPT_NAMES.get(scope, scope), "in_registry": False,
            })
    return rows


def _check_index(checks: list[Check]) -> dict:
    index = {}
    for chk in checks:
        index[chk.id] = chk
        for rid in chk.registry_ids:
            index[rid] = chk
    return index


def _row_for(pid: str, by_id: dict, index: dict) -> dict | None:
    """Строка под параметр реестра: по его id. Имена общие, подбирать ничего не нужно."""
    row = by_id.get(pid)
    if row is not None:
        return row
    chk = index.get(pid)
    return by_id.get(chk.id) if chk is not None else None


def merge_registry(rows: list[dict], registry: dict, checks: list[Check], *, pages: int = 1,
                   scope: str = "page") -> list[dict]:
    """Строки реестра + результаты проверок.

    Параметр, которого не считает ни один скрипт, попадает в отчёт со статусом «не проверяли»
    (одно состояние — одно слово), а причина стоит в строке: проверки нет, нужен браузер или
    выгрузка, нужен обход сайта.
    """
    index = _check_index(checks)
    by_id = {r["id"]: r for r in rows}
    out: list[dict] = []
    used: set[str] = set()
    for param in registry.get("params") or []:
        if param["scope"] != scope:
            continue
        pid = param["id"]
        row = _row_for(pid, by_id, index)
        base = {
            "registry_id": pid, "group": param["group"],
            "group_title": group_title(param["group"]),
            "title": param["title"], "registry_what": param["what"],
            "registry_how": param["how"], "registry_severity": param["severity"],
            "registry_status": param["status"], "scope": param["scope"],
            "editor_guideline": param["editor_guideline"], "in_registry": True,
        }
        if row is not None:
            merged = dict(row, **base)
            merged["id"] = row["id"]
            if merged["verdict"] in (BAD, WARN):
                merged["severity"] = param["severity"] or merged["severity"]
            merged["source"] = row.get("source") or param["source"]
            # Источник в строке берётся у скрипта, а пометка приходила из реестра — и они
            # расходились: строка с источником «… ориентир редактора» выходила без пометки,
            # то есть мнение подавалось как требование. Пометка считается по тому источнику,
            # который человек видит, плюс флаг реестра.
            merged["editor_guideline"] = bool(param["editor_guideline"]) or is_editor_source(
                merged.get("source"))
            if param["signal"] == "estimate":
                merged["kind"] = HEUR
                merged["kind_label"] = KIND_RU[HEUR]
            used.add(row["id"])
            out.append(merged)
            continue
        if not param["deterministic"]:
            reason = "нужен браузер, выгрузка данных или решение владельца"
            why = reason + " — автоматически это не проверить"
        elif param["scope"] == "site" and pages < 2:
            reason = "нужен обход сайта"
            why = f"{reason}, а проверено страниц: {pages}"
        else:
            reason = "проверки нет в скрипте"
            why = reason + (f": {param['how']}" if param.get("how") else "")
        out.append({**base, "id": pid, "verdict": NOTCHECKED,
                    "verdict_label": VERDICT_RU[NOTCHECKED], "reason": reason,
                    "observation": why, "severity": "info",
                    "kind": DET if param["signal"] == "fact" else HEUR,
                    "kind_label": "—", "source": param["source"]})
    for row in rows:
        if row["id"] not in used:
            out.append(dict(row, off_registry=True,
                            editor_guideline=bool(row.get("editor_guideline"))
                            or is_editor_source(row.get("source"))))
    return out


def group_rows(rows: list[dict], registry: dict | None = None) -> list[dict]:
    """Строки по группам: сначала проверенное, отдельно — то, что не проверяли."""
    groups_meta = (registry or {}).get("groups") or {}
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["group"], []).append(row)
    out = []
    for slug in sorted(buckets, key=group_order):
        items = sorted(buckets[slug], key=lambda r: (VERDICT_ORDER.index(r["verdict"]),
                                                     SEVERITY_RANK.get(r["severity"], 9), r["title"]))
        meta = groups_meta.get(slug) or {}
        out.append({"group": slug, "title": meta.get("title") or group_title(slug),
                    "about": meta.get("about"), "totals": totals_of(items),
                    "params": [r for r in items if r["verdict"] != NOTCHECKED],
                    "not_checked": [r for r in items if r["verdict"] == NOTCHECKED]})
    return out


def totals_of(rows: list[dict]) -> dict:
    counts = Counter(r["verdict"] for r in rows)
    return {v: counts.get(v, 0) for v in VERDICT_ORDER} | {"all": len(rows)}


def fix_first(rows: list[dict], *, page: str | None = None, limit: int = 15,
              registry: dict | None = None) -> list[dict]:
    """Очередь починки. Если сработало блокирующее условие, в ней только оно: пока страница
    не отвечает 200 или закрыта от индексации, советы про og:description — шум."""
    # Название группы берём там же, где его берут заголовки разделов (group_rows): иначе
    # в «чинить первым» стоит «Прочее», а раздел ниже называется иначе, и находку не найти.
    groups_meta = (registry or {}).get("groups") or {}
    blocking = blocking_rows(rows)
    hits = blocking or [r for r in rows if r["verdict"] in (BAD, WARN)]
    hits.sort(key=lambda r: (SEVERITY_RANK.get(r["severity"], 9), VERDICT_ORDER.index(r["verdict"])))
    out = []
    for row in hits[:limit]:
        meta = groups_meta.get(row["group"]) or {}
        item = {"id": row["id"], "title": row["title"],
                "group_title": meta.get("title") or row["group_title"],
                "severity": row["severity"], "verdict": row["verdict"],
                "observation": row.get("observation"), "fix": row.get("fix")}
        if row.get("blocking_text"):
            item["blocking"] = True
        if page:
            item["page"] = page
        out.append(item)
    return out


def other_findings(rows: list[dict]) -> int:
    """Сколько находок отложено блокирующим условием — число, а не молчание."""
    if not blocking_rows(rows):
        return 0
    blocked = {r["id"] for r in blocking_rows(rows)}
    return sum(1 for r in rows if r["verdict"] in (BAD, WARN) and r["id"] not in blocked)


# Условия, при которых остальные правки не имеют смысла (SPEC §3: потолки балла).
BLOCKING = (
    ("access.final_status", "страница не отвечает 200"),
    ("access.noindex_meta", "страница закрыта от индексации"),
    ("access.noindex_header", "noindex в заголовке ответа"),
    ("access.robots_googlebot", "адрес закрыт для Googlebot"),
    ("access.robots_yandexbot", "адрес закрыт для YandexBot"),
    ("access.csr_dependency", "основного текста нет в ответе сервера"),
    ("content.words_main", "текста на странице нет"),
)


def blocking_rows(rows: list[dict]) -> list[dict]:
    ids = {r["id"]: r for r in rows}
    out = []
    for cid, text in BLOCKING:
        row = ids.get(cid)
        if row and row["verdict"] == BAD:
            out.append(dict(row, blocking_text=text))
    return out


def blocking_of(rows: list[dict]) -> list[str]:
    return [r["blocking_text"] for r in blocking_rows(rows)]


def audit_page(source: str, *, fetcher=None, keys: list[str], options: dict) -> dict:
    """Один адрес или файл → данные адаптеров + строки проверок."""
    bundle: dict = {}
    page, raw = adapter_page(source, fetcher=fetcher, base_url=options.get("base_url"),
                             full=options.get("full", False))
    bundle["page"] = page
    if "error" in page:
        return {"target": source, "error": page["error"], "code": page.get("code", "parse_failed"),
                "facts": bundle}
    url = page.get("url") or options.get("base_url")
    lang = options.get("lang", "auto")
    try:
        bundle["text"] = adapter_text(raw, url=url, keys=keys, lang=lang)
    except Exception as exc:
        bundle["text"] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        bundle["deai"] = adapter_deai(raw, url=url, lang=lang)
    except Exception as exc:
        bundle["deai"] = {"error": f"{type(exc).__name__}: {exc}"}
    vis = page_facts.visible_text(raw, url, limit=100000)
    bundle["visible_text"] = vis["text"]
    schema = adapter_schema(page, url=url, visible_text=vis["text"])
    if schema is not None:
        bundle["schema"] = schema
    if options.get("robots") and fetcher is not None and http_safe.is_url(source):
        try:
            bundle["robots"] = adapter_robots(page.get("url") or source, fetcher=fetcher,
                                              cache=options.get("robots_cache"))
        except http_safe.SafeHttpError as exc:
            bundle["robots"] = {"error": exc.code}
        except Exception as exc:
            bundle["robots"] = {"error": f"{type(exc).__name__}: {exc}"}
    if options.get("sitemap") and fetcher is not None and http_safe.is_url(source):
        try:
            bundle["sitemap"] = adapter_sitemap(page.get("url") or source, fetcher=fetcher)
        except Exception as exc:
            bundle["sitemap"] = {"error": f"{type(exc).__name__}: {exc}"}
    if options.get("ai_files") and fetcher is not None and http_safe.is_url(source):
        for name, key in (("llms.txt", "llms_txt"), ("ai.txt", "ai_txt")):
            try:
                bundle[key] = adapter_extra_file(page.get("url") or source, name, fetcher=fetcher)
            except Exception as exc:
                bundle[key] = {"error": f"{type(exc).__name__}: {exc}"}
    ctx = Facts(bundle, keys=keys, options=options)
    rows = imported_rows(bundle) + run_checks(ctx, CHECKS, ctx)
    return {"target": source, "url": url, "status": page.get("fetch", {}).get("status"),
            "title": page.get("title"), "rows": rows, "facts": bundle}


def build_report(pages: list[dict], *, registry: dict, keys: list[str], options: dict,
                 requests_made: int) -> dict:
    page_reports = []
    all_rows: list[dict] = []
    fixes: list[dict] = []
    ok_pages = [p for p in pages if not p.get("error")]
    many = len(pages) > 1
    for p in pages:
        if p.get("error"):
            page_reports.append({"target": p["target"], "error": p["error"], "code": p.get("code")})
            continue
        merged = merge_registry(p["rows"], registry, CHECKS, pages=len(ok_pages), scope="page")
        label = p.get("url") or p["target"]
        page_reports.append({
            "target": p["target"], "url": p.get("url"), "status": p.get("status"),
            "title": esc(p.get("title"), 160), "totals": totals_of(merged),
            "blocking": blocking_of(merged), "groups": group_rows(merged, registry),
            "fix_first": fix_first(merged, page=label if many else None, registry=registry),
            "postponed": other_findings(merged),
        })
        all_rows.extend(merged)
        fixes.extend(fix_first(merged, page=label if many else None, registry=registry))
    site_raw = run_checks(None, SITE_CHECKS, ok_pages) if len(ok_pages) > 1 else []
    site_rows = merge_registry(site_raw, registry, SITE_CHECKS, pages=len(ok_pages), scope="site")
    site = None
    if site_rows:
        site = {"pages": len(ok_pages), "totals": totals_of(site_rows),
                "groups": group_rows(site_rows, registry),
                "fix_first": fix_first(site_rows, registry=registry)}
        all_rows.extend(site_rows)
        fixes = site["fix_first"] + fixes
    checked_ids = {r.get("registry_id") for r in all_rows
                   if r.get("in_registry") and r["verdict"] != NOTCHECKED}
    reg_total = len(registry.get("params") or [])
    reg_rows = [r for r in all_rows if r.get("in_registry")]
    coverage = {
        "registry_source": registry.get("source"),
        "registry_version": registry.get("version"),
        "registry_params": reg_total,
        "registry_checked": len(checked_ids),
        "registry_not_checked": max(0, reg_total - len(checked_ids)),
        "not_checked_reasons": dict(Counter(r.get("reason", "не названа") for r in reg_rows
                                            if r["verdict"] == NOTCHECKED)),
        "editor_guidelines": sum(1 for r in reg_rows if r.get("editor_guideline")),
        "checks_in_script": len(CHECKS) + len(SITE_CHECKS),
        "rows_from_scripts": sum(1 for r in all_rows if r.get("from_script")),
        "off_registry": sum(1 for r in all_rows if r.get("off_registry")),
    }
    fixes.sort(key=lambda r: (SEVERITY_RANK.get(r["severity"], 9), VERDICT_ORDER.index(r["verdict"])))
    report = {
        "tool": "audit", "version": VERSION, "notice": NOTICE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {"keys": keys, "pages": len(pages), "delay_s": options.get("delay"),
                   "robots": bool(options.get("robots")), "sitemap": bool(options.get("sitemap")),
                   "ai_files": bool(options.get("ai_files")), "lang": options.get("lang")},
        "requests": {"count": requests_made},
        "coverage": coverage,
        "totals": totals_of(all_rows),
        "scoring": ("Сводного балла нет: один балл из разных по природе проверок складывается только "
                    "выдуманными весами. Вместо него — счёт по статусам, список «чинить первым» "
                    "и блокирующие условия."),
        "pages": page_reports,
        "site": site,
        "fix_first": fixes[:25],
        "registry_rules": list(registry.get("rules") or []),
        "warnings": list(registry.get("warnings") or []),
    }
    if options.get("full"):
        report["facts"] = {p.get("url") or p["target"]: p.get("facts") for p in pages}
    return report


# ---------------------------------------------------------------------------- HTML-отчёт

CSS = """
:root{color-scheme:light dark;
--bg:#ffffff;--fg:#17191c;--muted:#5d646d;--line:#e2e5ea;--panel:#f6f7f9;
--ok:#1f7a45;--warn:#8a5a00;--bad:#a52020;--info:#3b5bdb;--none:#6b7280;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
@media (prefers-color-scheme:dark){:root{
--bg:#15171a;--fg:#e8eaed;--muted:#a0a7b0;--line:#2b2f35;--panel:#1c1f23;
--ok:#5be49b;--warn:#f0b429;--bad:#ff7b72;--info:#8ab4f8;--none:#9aa0a6}}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 64px;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:21px;margin:40px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:26px 0 4px;scroll-margin-top:12px}
p{margin:8px 0}
a{color:var(--info)}
.sub{color:var(--muted);font-size:14px;margin:0 0 18px}
.sub.small{font-size:13px;margin:2px 0 8px}
.nav{font-size:13px;color:var(--muted);line-height:2}
.counts{font-size:12px;color:var(--muted);margin:2px 0 6px;font-family:var(--mono)}
code,.mono,.ev{font-family:var(--mono)}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 8px}
.card{flex:1 1 130px;border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel)}
.card.wide{flex:1 1 220px}
.card b{display:block;font-family:var(--mono);font-size:22px;font-variant-numeric:tabular-nums;line-height:1.2}
.card span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;margin:8px 0 4px;font-size:14px;table-layout:fixed}
th,td{text-align:left;vertical-align:top;padding:7px 9px;border-bottom:1px solid var(--line);
overflow-wrap:break-word}
th:nth-child(1),td:nth-child(1){width:24%}
th:nth-child(2),td:nth-child(2){width:11%}
th:nth-child(4),td:nth-child(4){width:30%}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
tr.problem td:first-child{box-shadow:inset 3px 0 0 var(--bad)}
tr.warn td:first-child{box-shadow:inset 3px 0 0 var(--warn)}
tr.ok td:first-child{box-shadow:inset 3px 0 0 var(--ok)}
tr.info td:first-child{box-shadow:inset 3px 0 0 var(--info)}
tr.no_data td:first-child,tr.not_checked td:first-child{box-shadow:inset 3px 0 0 var(--none)}
.st{font-weight:600;white-space:nowrap;font-size:13px}
.st.problem{color:var(--bad)}.st.warn{color:var(--warn)}.st.ok{color:var(--ok)}
.st.info{color:var(--info)}.st.no_data,.st.not_checked{color:var(--none)}
.ev{font-size:12px;color:var(--muted);word-break:break-word}
.ev.id{opacity:.7}
.tags{margin-top:5px;line-height:1.9}
.tag{display:inline-block;font-size:11px;border:1px solid var(--line);border-radius:999px;
padding:1px 7px;color:var(--muted);white-space:nowrap;font-family:var(--mono)}
.tag.src{white-space:normal;font-family:inherit;overflow-wrap:anywhere}
.tag.sev{border-color:var(--warn);color:var(--warn)}
.tag.edit{border-style:dashed;border-color:var(--info);color:var(--info)}
ol.fix{padding-left:22px}ol.fix li{margin:9px 0}
ol.fix .what{color:var(--muted);font-size:14px;display:block;margin-top:2px}
details{border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:10px 0;background:var(--panel)}
summary{cursor:pointer;font-weight:600;font-size:14px}
.note{border-left:3px solid var(--info);background:var(--panel);padding:8px 12px;margin:12px 0;
color:var(--muted);font-size:14px;border-radius:0 8px 8px 0}
.note.bad{border-left-color:var(--bad);color:var(--fg)}
ul li{margin:6px 0}
footer{margin-top:40px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
@media (max-width:720px){
body{padding:20px 14px 48px}
table{display:block;table-layout:auto;font-size:13px}
thead{display:none}
tbody,tr,td{display:block;width:auto}
th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2),th:nth-child(4),td:nth-child(4){width:auto}
tr{border:1px solid var(--line);border-radius:10px;margin:10px 0;padding:8px 10px}
td{border:0;padding:3px 0}
tr.problem{border-left:3px solid var(--bad)}
tr.warn{border-left:3px solid var(--warn)}
tr.ok{border-left:3px solid var(--ok)}
tr.info{border-left:3px solid var(--info)}
tr.no_data,tr.not_checked{border-left:3px solid var(--none)}
td:first-child{box-shadow:none !important}
.card{flex:1 1 100%}
}
@media print{
body{padding:0;background:#fff;color:#000;font-size:10pt}
.card,details,.note{background:none}
.nav{display:none}
h2{page-break-after:avoid}tr,details,h3{page-break-inside:avoid}
details{border:none;padding:0}summary{display:none}
details .after-summary{display:block}
a{color:#000;text-decoration:none}
.tag{border-color:#bbb;color:#444}
}
"""


_plural = ru_text.plural  # «1 проблема», «2 проблемы», «5 проблем»
_qty = ru_text.num


def _h(value) -> str:
    return html_mod.escape("" if value is None else str(value), quote=True)


def value_text(value, depth: int = 0) -> str:
    """Значение для человека, а не repr Python.

    В колонку «значение» приходят и числа, и словари, и списки словарей. str() на словаре
    даёт `{'has_title': True, ...}` — в отчёт, который читает владелец сайта, такое попадать
    не должно.
    """
    if value is None or value is True or value is False:
        return {None: "", True: "да", False: "нет"}[value]
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return value
    if depth >= 3:
        return "…"
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if val is None or (isinstance(val, (list, tuple, dict, str)) and len(val) == 0):
                continue
            parts.append(f"{key}: {value_text(val, depth + 1)}")
        return " · ".join(parts)
    if isinstance(value, (list, tuple, set)):
        items = [value_text(v, depth + 1) for v in value]
        items = [i for i in items if i]
        sep = "; " if any(isinstance(v, (dict, list, tuple, set)) for v in value) else ", "
        return sep.join(items)
    return str(value)


def _tags(row: dict) -> str:
    tags = []
    label = row.get("kind_label")
    if label and label != "—":
        tags.append(f'<span class="tag">{_h(label)}</span>')
    if row.get("editor_guideline"):
        tags.append('<span class="tag edit">ориентир редактора</span>')
    sev = row.get("severity")
    if sev and sev != "info":
        tags.append(f'<span class="tag sev">{_h(sev)}</span>')
    if row.get("from_script"):
        tags.append(f'<span class="tag">{_h(row["from_script"])}</span>')
    if row.get("off_registry"):
        tags.append('<span class="tag">вне реестра</span>')
    if row.get("source"):
        tags.append(f'<span class="tag src">{_h(row["source"])}</span>')
    return " ".join(tags)


def _row_html(row: dict) -> str:
    verdict = row["verdict"]
    cell = []
    if row.get("value") not in (None, ""):
        shown = value_text(row["value"])
        if shown:
            cell.append(f'<span class="mono">{_h(shown)}</span>')
    if row.get("observation"):
        cell.append(f'<div>{_h(row["observation"])}</div>')
    if row.get("evidence"):
        cell.append(f'<div class="ev">{_h(row["evidence"])}</div>')
    what = row.get("registry_what")
    name = (f'<b>{_h(row["title"])}</b>'
            + (f'<div class="ev">{_h(what)}</div>' if what else "")
            + f'<div class="ev id">{_h(row.get("registry_id") or row["id"])}</div>')
    return (f'<tr class="{_h(verdict)}">'
            f"<td>{name}</td>"
            f'<td class="st {_h(verdict)}">{_h(row["verdict_label"])}</td>'
            f'<td>{"".join(cell) or "—"}</td>'
            f'<td>{_h(row.get("fix") or "")}<div class="tags">{_tags(row)}</div></td>'
            "</tr>")


TABLE_HEAD = ('<table><thead><tr><th>Параметр</th><th>Статус</th>'
              '<th>Значение и доказательство</th><th>Что делать</th></tr></thead><tbody>')


def _groups_html(groups: list[dict], *, prefix: str = "") -> str:
    out = []
    for grp in groups:
        t = grp["totals"]
        counts = " · ".join(f"{VERDICT_RU[v]}: {t[v]}" for v in VERDICT_ORDER if t.get(v))
        gid = _h(prefix + grp["group"])
        out.append(f'<h3 id="{gid}">{_h(grp["title"])}</h3>')
        if grp.get("about"):
            out.append(f'<p class="sub small">{_h(grp["about"])}</p>')
        out.append(f'<p class="counts">{_h(counts)}</p>')
        if grp["params"]:
            out.append(TABLE_HEAD)
            out.extend(_row_html(r) for r in grp["params"])
            out.append("</tbody></table>")
        if grp["not_checked"]:
            n = len(grp["not_checked"])
            out.append(f'<details><summary>Не проверяли: {n} '
                       f'{_plural(n, "параметр", "параметра", "параметров")} реестра</summary>'
                       '<div class="after-summary">' + TABLE_HEAD)
            out.extend(_row_html(r) for r in grp["not_checked"])
            out.append("</tbody></table></div></details>")
    return "\n".join(out)


def _fix_html(items: list[dict]) -> str:
    if not items:
        return "<p>Проблем и предупреждений нет.</p>"
    rows = []
    for item in items:
        where = f' <span class="tag">{_h(item["page"])}</span>' if item.get("page") else ""
        rows.append(f'<li><b>{_h(item["title"])}</b> <span class="tag sev">{_h(item["severity"])}</span>'
                    f' <span class="tag">{_h(item["group_title"])}</span>{where}'
                    f'<span class="what">{_h(item.get("observation"))}'
                    + (f' → {_h(item["fix"])}' if item.get("fix") else "") + "</span></li>")
    return '<ol class="fix">' + "".join(rows) + "</ol>"


def _nav_html(groups: list[dict], prefix: str = "") -> str:
    if not groups:
        return ""
    links = " · ".join(f'<a href="#{_h(prefix + g["group"])}">{_h(g["title"])}</a>' for g in groups)
    return f'<p class="nav">{links}</p>'


def render_html(report: dict) -> str:
    t = report["totals"]
    cov = report["coverage"]
    first = report["pages"][0] if report["pages"] else {}
    target = first.get("url") or first.get("target") or "—"
    many = len(report["pages"]) > 1
    head_title = "Проверка сайта" if many else "Проверка страницы"
    cards = [(t[BAD], _plural(t[BAD], "проблема", "проблемы", "проблем")),
             (t[WARN], _plural(t[WARN], "предупреждение", "предупреждения", "предупреждений")),
             (t[OK], "в норме"),
             (t[NODATA], "нет данных"), (t[NOTCHECKED], "не проверяли")]
    parts = [
        "<!doctype html>", '<html lang="ru"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex">',
        f"<title>{_h(head_title)}: {_h(target)}</title>",
        f"<style>{CSS}</style></head><body><div class=\"wrap\">",
        f"<h1>{_h(head_title)}</h1>",
        f'<p class="sub"><code>{_h(target)}</code><br>'
        f'papa-seo audit {_h(report["version"])} · {_h(report["generated_at"])} UTC · '
        f'страниц: {len(report["pages"])} · запросов к сайту: '
        f'{_h(report["requests"]["count"])}</p>',
        '<div class="cards">',
    ]
    for num, label in cards:
        parts.append(f'<div class="card"><b>{num}</b><span>{_h(label)}</span></div>')
    if cov["registry_params"]:
        parts.append(f'<div class="card wide"><b>{cov["registry_checked"]} / '
                     f'{cov["registry_params"]}</b><span>параметров реестра проверено</span></div>')
    else:
        parts.append(f'<div class="card wide"><b>{cov["checks_in_script"]}</b>'
                     "<span>проверок в скрипте (реестр не найден)</span></div>")
    parts.append("</div>")
    if first.get("blocking"):
        parts.append('<div class="note bad"><b>Блокирует всё остальное:</b> '
                     + _h("; ".join(first["blocking"]))
                     + ". Пока это так, другие правки на результат не повлияют.</div>")
    for w in report.get("warnings") or []:
        parts.append(f'<div class="note">{_h(w)}</div>')
    parts.append("<h2>Чинить первым</h2>")
    postponed = sum(_n(p.get("postponed")) for p in report["pages"] if not p.get("error"))
    if any(p.get("blocking") for p in report["pages"] if not p.get("error")):
        parts.append('<p class="sub small">Пока держится блокирующее условие, остальное '
                     "подождёт: "
                     + (f"ещё {_qty(postponed, 'находка', 'находки', 'находок')} "
                        f"{_plural(postponed, 'ждёт', 'ждут', 'ждут')} своей очереди в таблицах ниже."
                        if postponed else "других находок нет."))
    else:
        parts.append('<p class="sub small">Порядок — по серьёзности из реестра параметров, '
                     "а не по нашему ощущению важности.</p>")
    parts.append(_fix_html(report["fix_first"]))
    if not many:
        groups = first.get("groups") or []
        if first.get("error"):
            parts.append(f'<div class="note bad">{_h(first["error"])}</div>')
        else:
            parts.append("<h2>Параметры по группам</h2>")
            parts.append(_nav_html(groups))
            parts.append(_groups_html(groups))
    else:
        parts.append("<h2>Страницы</h2>")
        for n, page in enumerate(report["pages"], 1):
            if page.get("error"):
                parts.append(f'<div class="note bad">{_h(page["target"])}: {_h(page["error"])}</div>')
                continue
            pt = page["totals"]
            head = (f'{_h(page.get("url") or page["target"])} — проблем {pt[BAD]}, '
                    f"предупреждений {pt[WARN]}")
            parts.append(f'<details><summary>{head}</summary><div class="after-summary">'
                         + _groups_html(page["groups"], prefix=f"p{n}-") + "</div></details>")
    if report.get("site"):
        site = report["site"]
        parts.append('<h2 id="site">Сайт целиком</h2>')
        if site["pages"] < 2:
            # По одной странице о сайте сказать нечего: раздел сворачивается в строку,
            # а не рисует семь пустых таблиц.
            waiting = site["totals"][NOTCHECKED]
            parts.append('<details><summary>Проверена одна страница: '
                         f"{_qty(waiting, 'параметр', 'параметра', 'параметров')} о сайте целиком "
                         f"{_plural(waiting, 'ждёт', 'ждут', 'ждут')} обхода</summary>"
                         '<div class="after-summary">'
                         '<p class="sub small">Дубли title и description, сироты, глубина клика '
                         "и прочее считается по нескольким адресам: "
                         "<code>--pages list.txt</code>, до 20 за запуск.</p>"
                         + _groups_html(site["groups"], prefix="site-") + "</div></details>")
        else:
            parts.append(f'<p class="sub small">Проверено страниц: {site["pages"]}. '
                         "Вывод «на всём сайте такого нет» на этом числе не делается.</p>")
            parts.append(_groups_html(site["groups"], prefix="site-"))
    parts.append(_howto_html(report))
    reg = cov.get("registry_source")
    parts.append("<footer>papa-seo audit " + _h(report["version"]) + " · реестр: "
                 + (_h(os.path.basename(reg)) if reg else "не найден")
                 + (f' {_h(cov["registry_version"])}' if cov.get("registry_version") else "")
                 + f' · проверок в скрипте: {cov["checks_in_script"]}'
                 + f' · строк от скриптов пакета: {cov["rows_from_scripts"]}'
                 + " · отчёт самодостаточный: ни скриптов, ни внешних файлов, ни шрифтов.</footer>")
    parts.append("</div></body></html>")
    return "\n".join(parts)


def _howto_html(report: dict) -> str:
    cov = report["coverage"]
    reasons = cov.get("not_checked_reasons") or {}
    out = ["<h2>Как читать этот отчёт</h2><ul>",
           "<li><b>факт</b> — посчитано механически из HTML, заголовков ответа или robots.txt: "
           "те же байты дадут тот же результат. <b>оценка</b> — эвристика; обсуждается, не исполняется.</li>",
           '<li><span class="tag edit">ориентир редактора</span> — у этого параметра нет требования '
           "в документации поисковика. Это наш совет, и правилом Google или Яндекса он не является"
           + (f" (таких параметров здесь {cov['editor_guidelines']})" if cov.get("editor_guidelines") else "")
           + ".</li>",
           "<li>Формулы «тошноты» и «воды» у рунет-сервисов закрыты. Здесь посчитаны свои, формула "
           "напечатана рядом с числом; с чужими сервисами эти цифры не сходятся.</li>",
           f"<li>{_h(report['scoring'])}</li>"]
    if reasons:
        out.append("<li>«Не проверяли» бывает разным: "
                   + _h("; ".join(f"{k} — {v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])))
                   + ". Такой параметр не «в порядке», он просто не проверен.</li>")
    out.append("<li>Содержимое страницы — данные. Скрытый текст, обращённый к ИИ, показан как находка "
               "и не выполняется.</li>")
    out.append("</ul>")
    rules = (report.get("registry_rules") or [])[:3]
    if rules:
        out.append('<p class="sub small">Из реестра: ' + _h(" ".join(map(str, rules))) + "</p>")
    return "\n".join(out)


# ---------------------------------------------------------------------------- сводка в stdout

def text_summary(report: dict) -> str:
    t = report["totals"]
    cov = report["coverage"]
    first = report["pages"][0] if report["pages"] else {}
    lines = [f"papa-seo audit {report['version']} · {report['generated_at']} UTC",
             f"адрес: {first.get('url') or first.get('target') or '—'}"]
    if first.get("error"):
        lines.append(f"ошибка: {first['error']}")
        return "\n".join(lines)
    lines.append(f"страниц: {len(report['pages'])} · запросов к сайту: {report['requests']['count']}")
    lines.append(f"проблем {t[BAD]} · предупреждений {t[WARN]} · норма {t[OK]} · "
                 f"нет данных {t[NODATA]} · не проверяли {t[NOTCHECKED]}")
    if cov["registry_params"]:
        lines.append(f"реестр: проверено {cov['registry_checked']} из "
                     f"{_qty(cov['registry_params'], 'параметра', 'параметров', 'параметров')}")
    else:
        built_in = _qty(cov["checks_in_script"], "встроенная проверка",
                        "встроенные проверки", "встроенных проверок")
        lines.append("реестр не найден: "
                     f"{_plural(cov['checks_in_script'], 'отработала', 'отработали', 'отработало')} "
                     f"{built_in}")
    if first.get("blocking"):
        lines.append("блокирует: " + "; ".join(first["blocking"]))
        if _n(first.get("postponed")):
            lines.append(f"{_plural(first['postponed'], 'остальная', 'остальные', 'остальные')} "
                         f"{_qty(first['postponed'], 'находка', 'находки', 'находок')} "
                         "— после того, как это починят")
    if report["fix_first"]:
        lines.append("чинить первым:")
        for item in report["fix_first"][:5]:
            where = f" [{item['page']}]" if item.get("page") else ""
            lines.append(f"  {item['severity']}: {item['title']}{where} — {item.get('observation') or ''}")
    else:
        lines.append("проблем и предупреждений нет")
    for w in report.get("warnings") or []:
        lines.append(f"примечание: {w}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- CLI

def list_checks() -> dict:
    rows = [{"id": c.id, "group": c.group, "group_title": group_title(c.group),
             "title": c.title, "severity": c.severity, "kind": c.kind, "source": c.source,
             "scope": "site" if c in SITE_CHECKS else "page"}
            for c in CHECKS + SITE_CHECKS]
    return {"tool": "audit", "version": VERSION, "count": len(rows),
            "adapters": sorted(ADAPTERS), "registry": load_registry().get("source"),
            "checks": rows}


def read_pages_file(path: str) -> list[str]:
    data, _ = http_safe.read_input_file(path, 1024 * 1024)
    urls = [ln.strip() for ln in data.decode("utf-8", "replace").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    if not urls:
        raise http_safe.CliError("--pages: список пуст", "bad_input")
    if len(urls) > MAX_PAGES:
        raise http_safe.CliError(f"{_qty(len(urls), 'адрес', 'адреса', 'адресов')}: "
                                 f"предел {MAX_PAGES} за один запуск "
                                 "(сайт по умолчанию не обходится)", "too_many_urls")
    return urls


def main(argv: list[str] | None = None) -> int:
    def body() -> int:
        p = http_safe.JsonArgumentParser(prog="audit.py",
                                         description="Проверка страницы или списка страниц по реестру параметров")
        p.add_argument("source", nargs="?", help="URL или HTML-файл")
        p.add_argument("--pages", help=f"файл со списком адресов, до {MAX_PAGES}")
        p.add_argument("--keys", action="append", default=[],
                       help="ключевые фразы через ; (можно повторять флаг)")
        p.add_argument("--base-url", help="адрес страницы для локального файла")
        p.add_argument("--out", help="файл HTML-отчёта")
        p.add_argument("--json", dest="json_out", help="файл полного JSON ('-' — в stdout)")
        p.add_argument("--registry", help="путь к registry.json (по умолчанию references/registry.json)")
        p.add_argument("--lang", default="auto", choices=("auto", "ru", "en"))
        p.add_argument("--no-robots", dest="robots", action="store_false",
                       help="не запрашивать robots.txt (на один запрос меньше)")
        p.add_argument("--sitemap", action="store_true", help="запросить /sitemap.xml")
        p.add_argument("--ai-files", action="store_true", help="запросить llms.txt и ai.txt")
        p.add_argument("--full", action="store_true", help="не ужимать списки и вложить сырые факты в JSON")
        p.add_argument("--quiet", action="store_true", help="без сводки в stdout")
        p.add_argument("--list-checks", action="store_true", help="показать каталог проверок и выйти")
        http_safe.add_pace_args(p)
        args = p.parse_args(argv)

        if args.list_checks:
            print(http_safe.dump_json(list_checks()))
            return 0
        if bool(args.source) == bool(args.pages):
            raise http_safe.CliError("нужен адрес/файл или --pages (но не оба)", "bad_arguments")
        if args.out:
            if args.out.lower().endswith(".json"):
                raise http_safe.CliError("--out — это HTML-отчёт; для JSON есть --json", "bad_arguments")
            http_safe.safe_out_path(args.out)
        if args.json_out and args.json_out != "-":
            http_safe.safe_out_path(args.json_out)
        delay = http_safe.check_delay(args.delay)
        state_dir = http_safe.check_state_dir(args.state_dir)
        keys = text_metrics.parse_keys(args.keys)

        sources = [args.source] if args.source else read_pages_file(args.pages)
        need_net = any(http_safe.is_url(s) for s in sources)
        fetcher = http_safe.Fetcher(delay=delay, state_dir=state_dir) if need_net else None
        options = {"base_url": args.base_url, "full": args.full, "lang": args.lang,
                   "robots": args.robots, "sitemap": args.sitemap, "ai_files": args.ai_files,
                   "delay": delay, "robots_cache": {}}
        if args.registry and not os.path.isfile(args.registry):
            # Молча уйти на встроенный список нельзя: опечатка в пути превращала «проверено
            # 222 из 415» в 99 проверок и «не проверяли 0», то есть отчёт выглядел полным.
            raise http_safe.CliError(
                f"реестра нет по этому пути: {args.registry}", "bad_registry_path")
        registry = load_registry(args.registry)

        pages = []
        for src in sources:
            try:
                page = audit_page(src, fetcher=fetcher, keys=keys, options=options)
                if page.get("error") and len(sources) == 1:
                    raise http_safe.CliError(page["error"], page.get("code", "page_failed"))
                pages.append(page)
            except http_safe.SafeHttpError as exc:
                if len(sources) == 1:
                    raise
                pages.append({"target": src, **exc.to_json(), "facts": {}})
            except http_safe.CliError as exc:
                if len(sources) == 1:
                    raise
                pages.append({"target": src, "error": exc.message, "code": exc.code, "facts": {}})
            # карту сайта и llms.txt хватит запросить один раз: они общие для хоста
            options = dict(options, sitemap=False, ai_files=False)

        report = build_report(pages, registry=registry, keys=keys, options=options,
                              requests_made=fetcher.requests_made if fetcher else 0)
        if args.out:
            http_safe.write_atomic(args.out, render_html(report))
            report["out_html"] = os.path.abspath(args.out)
        if args.json_out == "-":
            print(http_safe.dump_json(report))
            return 0
        if args.json_out:
            http_safe.write_atomic(args.json_out, http_safe.dump_json(report) + "\n")
            report["out_json"] = os.path.abspath(args.json_out)
        if not args.quiet:
            print(text_summary(report))
            if args.out:
                print(f"HTML-отчёт: {report['out_html']}")
            if report.get("out_json"):
                print(f"JSON: {report['out_json']}")
        return 0

    return http_safe.run_cli(body)


if __name__ == "__main__":
    sys.exit(main())
