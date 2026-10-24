#!/usr/bin/env python3
"""Sitemap validator: urlset or sitemapindex, from a file (.xml / .xml.gz) or one URL.

    python3 scripts/sitemap_check.py sitemap.xml [--site https://site.ru] [--out report.json]
    python3 scripts/sitemap_check.py https://site.ru/sitemap.xml [--follow-index] [--sample 10]

Checks: root type and namespace, <= 50 000 URLs and <= 50 MB uncompressed per file, missing/relative
<loc>, http:// entries, foreign hosts (and www variants), duplicates (exact and after normalising
case/trailing slash), fragments, very long URLs, lastmod format and plausibility (future dates,
one date on >= 90 % of entries, everything within the last 24 h, implausibly old), nested indexes.

No crawling by default. --follow-index fetches up to 20 child sitemaps of the same host,
--sample N (<= 20) fetches N listed URLs, both sequentially with a >= 2 s pause via http_safe.
DTD/ENTITY declarations are refused (XXE / billion laughs); gzip is decompressed with a cap.
"""
from __future__ import annotations

import io
import os
import re
import sys
import zlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_safe  # noqa: E402

MAX_URLS = 50_000
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_CHILDREN_FETCH = 20       # hard ceiling for --max-children
DEFAULT_MAX_CHILDREN = 2      # child sitemaps are often built on the fly and are heavy
MAX_SAMPLE = 20
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
UNIFORM_SHARE = 0.90
EXAMPLES = 10

_W3C_RE = re.compile(
    r"^(\d{4})(?:-(\d{2})(?:-(\d{2})(?:[Tt](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?"
    r"(Z|z|[+-]\d{2}:?\d{2})?)?)?)?$")


class SitemapError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def parse_w3c(value: str) -> tuple[datetime | None, str | None]:
    """W3C Datetime -> aware UTC datetime. Returns (dt, problem)."""
    m = _W3C_RE.match(value.strip())
    if not m:
        return None, "invalid_format"
    y, mo, d, hh, mm, ss, tz = m.groups()
    if hh is not None and tz is None:
        return None, "time_without_timezone"
    try:
        dt = datetime(int(y), int(mo or 1), int(d or 1), int(hh or 0), int(mm or 0), int(ss or 0))
    except ValueError:
        return None, "invalid_date"
    if tz and tz.upper() != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        dt = dt - sign * offset
    return dt.replace(tzinfo=timezone.utc), None


def _decompress_gzip(data: bytes, limit: int) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(data, limit + 1)
    except zlib.error as exc:
        raise SitemapError("bad_gzip", f"gzip error: {exc}") from None
    if len(out) > limit or d.unconsumed_tail:
        raise SitemapError("too_large", f"uncompressed sitemap exceeds {limit} bytes")
    return out


def _local(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return None, tag


def _norm_variant(url: str) -> str:
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), (p.netloc or "").lower(), path, p.query, ""))


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _strip_www(h: str) -> str:
    return h[4:] if h.startswith("www.") else h


def parse_sitemap(data: bytes, *, max_bytes: int = MAX_UNCOMPRESSED, max_urls: int = MAX_URLS) -> dict:
    """Stream-parse sitemap XML bytes. Returns raw entries (bounded) and structural facts."""
    if data[:2] == b"\x1f\x8b":
        data = _decompress_gzip(data, max_bytes)
        gz = True
    else:
        gz = False
    if len(data) > max_bytes:
        raise SitemapError("too_large", f"sitemap exceeds {max_bytes} bytes uncompressed")
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise SitemapError("dtd_refused", "DOCTYPE/ENTITY declarations are refused (XXE, entity expansion)")
    root_name, root_ns = None, None
    entries: list[dict] = []
    children: list[dict] = []
    count = 0
    over_limit = False
    extras = Counter()
    try:
        ctx = ET.iterparse(io.BytesIO(data), events=("start", "end"))
        depth = 0
        cur: dict | None = None
        for event, el in ctx:
            ns, name = _local(el.tag)
            if event == "start":
                depth += 1
                if depth == 1:
                    root_name, root_ns = name, ns
                elif depth == 2 and name in ("url", "sitemap"):
                    cur = {"kind": name}
                elif depth == 3 and cur is not None and name == "link" and ns == "http://www.w3.org/1999/xhtml":
                    extras["hreflang_links"] += 1
                elif depth == 3 and cur is not None and name == "image":
                    extras["images"] += 1
                elif depth == 3 and cur is not None and name == "video":
                    extras["videos"] += 1
                elif depth == 3 and cur is not None and name == "news":
                    extras["news"] += 1
                continue
            # end
            if depth == 3 and cur is not None and name in ("loc", "lastmod", "changefreq", "priority"):
                cur[name] = (el.text or "").strip()
            elif depth == 2 and cur is not None:
                count += 1
                if cur["kind"] == "sitemap":
                    if len(children) < 50_000:
                        children.append(cur)
                else:
                    if count > max_urls:
                        over_limit = True
                    if len(entries) < max_urls + 1:
                        entries.append(cur)
                cur = None
                el.clear()
            elif depth == 1:
                el.clear()
            depth -= 1
    except ET.ParseError as exc:
        raise SitemapError("xml_invalid", f"XML parse error: {exc}") from None
    return {"root": root_name, "namespace": root_ns, "gzip": gz, "bytes_uncompressed": len(data),
            "entries": entries, "children": children, "count": count, "over_limit": over_limit,
            "extensions": dict(extras)}


def analyze(parsed: dict, *, sitemap_url: str | None = None, site: str | None = None,
            now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    issues: list[dict] = []
    root = parsed["root"]
    kind = {"urlset": "urlset", "sitemapindex": "sitemapindex"}.get(root or "", "unknown")
    if kind == "unknown":
        issues.append({"code": "unknown_root", "severity": "critical",
                       "note": f"Корневой элемент {root!r}: не urlset и не sitemapindex"})
    if parsed["namespace"] != SITEMAP_NS:
        issues.append({"code": "namespace", "severity": "medium",
                       "note": f"Пространство имён {parsed['namespace']!r}, ожидалось {SITEMAP_NS}"})
    if parsed["over_limit"] or parsed["count"] > MAX_URLS:
        issues.append({"code": "over_50000", "severity": "high",
                       "note": f"Записей {parsed['count']}, лимит протокола — {MAX_URLS} на файл"})
    items = parsed["children"] if kind == "sitemapindex" else parsed["entries"]
    if kind == "sitemapindex" and parsed["entries"]:
        issues.append({"code": "mixed_index", "severity": "high", "note": "В индексе есть <url>-записи"})

    ref_host = None
    ref_source = None
    if site:
        ref_host, ref_source = _host(site), "site"
    elif sitemap_url:
        ref_host, ref_source = _host(sitemap_url), "sitemap_url"
    hosts = Counter(_host(it.get("loc", "")) for it in items if it.get("loc"))
    if not ref_host and hosts:
        ref_host, ref_source = hosts.most_common(1)[0][0], "inferred_majority"

    ex: dict[str, list] = {}

    def add(code: str, value):
        lst = ex.setdefault(code, [])
        if len(lst) < EXAMPLES:
            lst.append(value)

    counters = Counter()
    seen: set[str] = set()
    seen_variant: dict[str, str] = {}
    lastmods: list[tuple[str, datetime]] = []
    for it in items:
        loc = it.get("loc")
        if not loc:
            counters["missing_loc"] += 1
            continue
        if not http_safe.is_url(loc):
            counters["not_absolute"] += 1
            add("not_absolute", loc)
            continue
        if loc.lower().startswith("http://"):
            counters["http_url"] += 1
            add("http_url", loc)
        h = _host(loc)
        if ref_host and h != ref_host:
            if _strip_www(h) == _strip_www(ref_host):
                counters["www_variant"] += 1
                add("www_variant", loc)
            else:
                counters["foreign_host"] += 1
                add("foreign_host", loc)
        if "#" in loc:
            counters["fragment"] += 1
            add("fragment", loc)
        if len(loc) > 2048:
            counters["too_long"] += 1
            add("too_long", loc[:120] + "…")
        if re.search(r"\s", loc):
            counters["whitespace_in_loc"] += 1
            add("whitespace_in_loc", loc)
        if loc in seen:
            counters["duplicate"] += 1
            add("duplicate", loc)
        else:
            seen.add(loc)
            var = _norm_variant(loc)
            if var in seen_variant and seen_variant[var] != loc:
                counters["near_duplicate"] += 1
                add("near_duplicate", [seen_variant[var], loc])
            else:
                seen_variant.setdefault(var, loc)
        lm = it.get("lastmod")
        if lm is None:
            counters["no_lastmod"] += 1
        elif lm:
            dt, problem = parse_w3c(lm)
            if problem:
                counters["lastmod_" + problem] += 1
                add("lastmod_" + problem, f"{loc} → {lm}")
            else:
                lastmods.append((lm, dt))
                if dt > now + timedelta(days=1):
                    counters["lastmod_future"] += 1
                    add("lastmod_future", f"{loc} → {lm}")
                if dt.year < 1995:
                    counters["lastmod_implausibly_old"] += 1
                    add("lastmod_implausibly_old", f"{loc} → {lm}")
        if it.get("changefreq"):
            counters["has_changefreq"] += 1
        if it.get("priority"):
            counters["has_priority"] += 1
            try:
                pv = float(it["priority"])
                if not 0.0 <= pv <= 1.0:
                    counters["priority_out_of_range"] += 1
            except ValueError:
                counters["priority_out_of_range"] += 1
        if kind == "sitemapindex" and not loc.lower().split("?")[0].endswith((".xml", ".xml.gz", ".gz")):
            counters["child_not_xml_like"] += 1

    lastmod_stats = {"with_lastmod": len(lastmods), "total": len(items)}
    if len(lastmods) >= 10:
        top_value, top_n = Counter(v[:10] for v, _ in lastmods).most_common(1)[0]
        share = top_n / len(lastmods)
        lastmod_stats.update(top_date=top_value, top_share=round(share, 3))
        if share >= UNIFORM_SHARE:
            issues.append({"code": "lastmod_uniform", "severity": "medium", "status": "likely",
                           "note": f"{share:.0%} записей с одной датой {top_value}: похоже на время сборки, "
                                   f"а не на дату изменения"})
        if all(now - dt < timedelta(hours=24) for _, dt in lastmods):
            issues.append({"code": "lastmod_all_recent", "severity": "low", "status": "hypothesis",
                           "note": "Все lastmod за последние 24 часа: возможно, перегенерируются при каждой сборке"})
    severities = {"missing_loc": "high", "not_absolute": "high", "http_url": "medium", "foreign_host": "high",
                  "www_variant": "medium", "fragment": "low", "too_long": "medium", "whitespace_in_loc": "medium",
                  "duplicate": "medium", "near_duplicate": "low", "lastmod_invalid_format": "medium",
                  "lastmod_time_without_timezone": "low", "lastmod_invalid_date": "medium",
                  "lastmod_future": "medium", "lastmod_implausibly_old": "low",
                  "priority_out_of_range": "low", "child_not_xml_like": "info"}
    for code, sev in severities.items():
        if counters.get(code):
            issues.append({"code": code, "severity": sev, "count": counters[code], "examples": ex.get(code, [])})
    info = {k: counters[k] for k in ("no_lastmod", "has_changefreq", "has_priority") if counters.get(k)}
    if info.get("has_changefreq") or info.get("has_priority"):
        info["note"] = "changefreq и priority Google не использует"
    return {
        "type": kind, "namespace": parsed["namespace"], "gzip": parsed["gzip"],
        "bytes_uncompressed": parsed["bytes_uncompressed"], "entries": parsed["count"],
        "reference_host": ref_host, "reference_host_source": ref_source,
        "hosts": dict(hosts.most_common(10)), "extensions": parsed["extensions"],
        "lastmod": lastmod_stats, "info": info, "issues": issues,
        "children": [{"loc": c.get("loc"), "lastmod": c.get("lastmod")} for c in parsed["children"][:200]]
        if kind == "sitemapindex" else [],
        "children_total": len(parsed["children"]),
    }


def children_skip_report(report: dict, max_children: int) -> dict:
    checked = len([c for c in report.get("children_checked", []) if "skipped" not in c])
    skipped = max(0, report["children_total"] - len(report.get("children_checked", [])))
    out = {"children_not_checked": skipped}
    if skipped:
        out["children_warning"] = (f"Проверено шардов: {checked} из {report['children_total']}, пропущено {skipped} "
                                   f"(--max-children {max_children}). Остальные не запрашивались, выводы — только "
                                   f"по проверенным")
    return out


def _same_site(a: str, b: str) -> bool:
    return _strip_www(_host(a)) == _strip_www(_host(b)) and _host(a) != ""


def fetch_sitemap(url: str, fetcher: http_safe.Fetcher, *, allow_local: bool = False) -> tuple[dict, dict]:
    resp = fetcher.fetch(url, max_bytes=MAX_UNCOMPRESSED, allow_local=allow_local)
    meta = {"url": url, "final_url": resp.final_url, "status": resp.status, "chain": resp.chain,
            "bytes": len(resp.body), "truncated": resp.truncated, "fetched_at": resp.fetched_at}
    if resp.status != 200:
        raise SitemapError("http_status", f"sitemap returned HTTP {resp.status}")
    if resp.truncated:
        raise SitemapError("too_large", "sitemap body exceeds the size limit")
    return parse_sitemap(resp.body), meta


def follow_index(report: dict, index_url: str, fetcher: http_safe.Fetcher, *, allow_local: bool = False,
                 limit: int = DEFAULT_MAX_CHILDREN) -> list[dict]:
    limit = max(0, min(int(limit), MAX_CHILDREN_FETCH))
    out = []
    fetched = 0
    for child in report["children"]:
        if fetched >= limit:
            break
        loc = child.get("loc") or ""
        if not http_safe.is_url(loc):
            out.append({"loc": loc, "skipped": "not_absolute"})
            continue
        if not _same_site(loc, index_url):
            out.append({"loc": loc, "skipped": "other_host", "note": "чужой хост не запрашивается"})
            continue
        fetched += 1
        try:
            parsed, meta = fetch_sitemap(loc, fetcher, allow_local=allow_local)
            sub = analyze(parsed, sitemap_url=meta["final_url"])
            if sub["type"] == "sitemapindex":
                sub["issues"].append({"code": "nested_index", "severity": "high",
                                      "note": "Индекс внутри индекса протоколом не допускается"})
            out.append({"loc": loc, "status": meta["status"], "type": sub["type"], "entries": sub["entries"],
                        "issues": sub["issues"], "lastmod": sub["lastmod"]})
        except (SitemapError, http_safe.SafeHttpError) as exc:
            out.append({"loc": loc, "error": exc.message, "code": exc.code})
    return out


_NOINDEX_META = re.compile(rb"<meta[^>]+name=[\"']?(?:robots|googlebot|yandex)[\"']?[^>]*noindex", re.I)


def sample_urls(entries: list[dict], n: int, fetcher: http_safe.Fetcher, *, ref: str,
                allow_local: bool = False) -> list[dict]:
    locs = [e["loc"] for e in entries if e.get("loc") and http_safe.is_url(e["loc"]) and _same_site(e["loc"], ref)]
    if not locs or n <= 0:
        return []
    n = min(n, MAX_SAMPLE, len(locs))
    step = len(locs) / n
    picked = [locs[int(i * step)] for i in range(n)]
    out = []
    for loc in picked:
        try:
            r = fetcher.fetch(loc, max_bytes=256 * 1024, allow_local=allow_local)
            xr = r.headers.get("x-robots-tag", "")
            out.append({"loc": loc, "status": r.status, "final_url": r.final_url,
                        "redirected": r.final_url != http_safe.validate_url(loc, allow_local=True).url,
                        "noindex_header": "noindex" in xr.lower(),
                        "noindex_meta": bool(_NOINDEX_META.search(r.body))})
        except http_safe.SafeHttpError as exc:
            out.append({"loc": loc, "error": exc.message, "code": exc.code})
    return out


def main(argv: list[str] | None = None) -> int:
    def body() -> int:
        p = http_safe.JsonArgumentParser(prog="sitemap_check.py", description="Sitemap validator")
        p.add_argument("source", help="sitemap file (.xml/.gz) or URL")
        p.add_argument("--site", help="expected site URL (host check)")
        p.add_argument("--follow-index", action="store_true", help="fetch child sitemaps (URL mode), see --max-children")
        p.add_argument("--max-children", type=int, default=DEFAULT_MAX_CHILDREN,
                       help=f"child sitemaps to fetch with --follow-index (default {DEFAULT_MAX_CHILDREN}, max {MAX_CHILDREN_FETCH})")
        p.add_argument("--sample", type=int, default=0, help="fetch N listed URLs (<= 20, URL mode)")
        http_safe.add_pace_args(p)
        p.add_argument("--out")
        args = p.parse_args(argv)
        if args.out:
            http_safe.safe_out_path(args.out)
        http_safe.check_delay(args.delay)
        if not 1 <= args.max_children <= MAX_CHILDREN_FETCH:
            raise http_safe.CliError(f"--max-children must be 1..{MAX_CHILDREN_FETCH}", "bad_arguments")
        if not 0 <= args.sample <= MAX_SAMPLE:
            raise http_safe.CliError(f"--sample must be 0..{MAX_SAMPLE}", "bad_arguments")
        fetcher = http_safe.Fetcher(delay=args.delay, state_dir=http_safe.check_state_dir(args.state_dir))
        try:
            if http_safe.is_url(args.source):
                parsed, meta = fetch_sitemap(args.source, fetcher)
                report = analyze(parsed, sitemap_url=meta["final_url"], site=args.site)
                report["source"] = {"type": "url", **meta}
                if args.follow_index and report["type"] == "sitemapindex":
                    report["children_checked"] = follow_index(report, meta["final_url"], fetcher,
                                                              limit=args.max_children)
                    report.update(children_skip_report(report, args.max_children))
                if args.sample and report["type"] == "urlset":
                    report["sample"] = sample_urls(parsed["entries"], args.sample, fetcher, ref=meta["final_url"])
            else:
                if args.follow_index or args.sample:
                    raise http_safe.CliError("--follow-index and --sample need a sitemap URL", "bad_arguments")
                data, truncated = http_safe.read_input_file(args.source, MAX_UNCOMPRESSED)
                if truncated:
                    raise SitemapError("too_large", f"file exceeds {MAX_UNCOMPRESSED} bytes")
                parsed = parse_sitemap(data)
                report = analyze(parsed, site=args.site)
                report["source"] = {"type": "file", "path": os.path.abspath(args.source), "bytes": len(data)}
        except SitemapError as exc:
            raise http_safe.CliError(exc.message, exc.code) from None
        summary = {"type": report["type"], "entries": report["entries"],
                   "issues": [i["code"] for i in report["issues"]]}
        return http_safe.emit(report, args.out, summary)

    return http_safe.run_cli(body)


if __name__ == "__main__":
    sys.exit(main())
