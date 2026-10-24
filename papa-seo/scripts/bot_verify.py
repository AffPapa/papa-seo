#!/usr/bin/env python3
"""Verify search-engine bots by reverse DNS + forward confirmation.

    python3 scripts/bot_verify.py 66.249.66.1 5.255.253.1 [--out v.json]
    python3 scripts/bot_verify.py --log access.log [--max-ips 200]

Log lines: Caddy JSON (request.remote_ip / client_ip, request.headers.User-Agent), combined/common
log format (IP first, User-Agent last quoted field) or bare IPs. A User-Agent that claims Googlebot,
YandexBot or Bingbot is checked against the vendor's rDNS domains:
  Google: googlebot.com, google.com   Yandex: yandex.ru, yandex.net, yandex.com   Bing: search.msn.com
Verified = PTR ends on a vendor domain (label boundary) AND that name resolves back to the same IP.
Bots that are verified by published IP ranges, not rDNS (GPTBot, ClaudeBot, PerplexityBot, ...),
are reported as `needs_ip_ranges` and not looked up. Private addresses are not looked up.
DNS goes through http_safe (timeouts, no other network).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import http_safe  # noqa: E402

VENDORS = {
    "google": {"domains": ("googlebot.com", "google.com"), "ua": re.compile(r"googlebot|google-inspectiontool|googleother|storebot-google", re.I)},
    "yandex": {"domains": ("yandex.ru", "yandex.net", "yandex.com"), "ua": re.compile(r"yandex", re.I)},
    "bing": {"domains": ("search.msn.com",), "ua": re.compile(r"bingbot|msnbot|bingpreview|adidxbot", re.I)},
}
IP_RANGE_BOTS = re.compile(r"gptbot|oai-searchbot|chatgpt-user|claudebot|claude-user|claude-searchbot|"
                           r"perplexitybot|perplexity-user|applebot|ccbot|bytespider|meta-externalagent", re.I)
MAX_IPS_DEFAULT = 200
MAX_LOG_BYTES = 1024 * 1024 * 1024
MAX_LINES = 5_000_000
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_LAST_QUOTED = re.compile(r'"([^"]*)"\s*$')


def domain_matches(host: str, domain: str) -> bool:
    host = host.rstrip(".").lower()
    return host == domain or host.endswith("." + domain)


def vendor_of_host(host: str | None) -> str | None:
    if not host:
        return None
    for name, v in VENDORS.items():
        if any(domain_matches(host, d) for d in v["domains"]):
            return name
    return None


def claimed_vendors(ua: str | None) -> list[str]:
    if not ua:
        return []
    return [name for name, v in VENDORS.items() if v["ua"].search(ua)]


def _canonical_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip().strip("[]")))
    except ValueError:
        return None


def parse_log_line(line: str) -> tuple[str | None, str | None]:
    """(ip, user_agent) from one log line, or (None, None)."""
    s = line.strip()
    if not s:
        return None, None
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except ValueError:
            return None, None
        req = obj.get("request") if isinstance(obj, dict) else None
        if not isinstance(req, dict):
            return None, None
        ip = req.get("client_ip") or req.get("remote_ip") or req.get("remote_addr")
        if isinstance(ip, str) and ip.count(":") == 1 and "." in ip:  # "1.2.3.4:5678"
            ip = ip.split(":")[0]
        ua = None
        headers = req.get("headers")
        if isinstance(headers, dict):
            for k, v in headers.items():
                if k.lower() == "user-agent":
                    ua = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)
        return (_canonical_ip(ip) if isinstance(ip, str) else None), ua
    first = s.split()[0]
    ip = _canonical_ip(first)
    if ip is None:
        m = _IPV4_RE.search(s)
        ip = _canonical_ip(m.group(0)) if m else None
    m = _LAST_QUOTED.search(s)
    ua = m.group(1) if m and m.group(1) not in ("-", "") else None
    return ip, ua


def verify_ip(ip: str, claimed: list[str], *, reverse=None, forward=None, ua_ip_range_bot: bool = False) -> dict:
    reverse = reverse or http_safe.reverse_dns
    forward = forward or http_safe.forward_dns
    row = {"ip": ip, "claimed": claimed, "ptr": None, "ptr_vendor": None, "forward_ips": [],
           "forward_confirmed": False, "verdict": None}
    if not http_safe.is_public_ip(ip):
        row["verdict"] = "private_ip"
        return row
    if ua_ip_range_bot and not claimed:
        row["verdict"] = "needs_ip_ranges"
        row["note"] = "Этот бот проверяется по опубликованным диапазонам IP вендора, не по rDNS"
        return row
    ptr = reverse(ip)
    row["ptr"] = ptr
    vendor = vendor_of_host(ptr)
    row["ptr_vendor"] = vendor
    if ptr and vendor:
        fwd = forward(ptr)
        row["forward_ips"] = fwd[:10]
        row["forward_confirmed"] = ip in fwd
    if vendor and row["forward_confirmed"]:
        row["verdict"] = "verified"
        if claimed and vendor not in claimed:
            row["note"] = f"PTR подтверждает {vendor}, а User-Agent заявляет {', '.join(claimed)}"
    elif claimed:
        row["verdict"] = "fake" if ptr else "unverified_no_ptr"
        if ptr and vendor and not row["forward_confirmed"]:
            row["note"] = "PTR похож на вендора, но прямой запрос не возвращает этот IP (подделка PTR)"
    elif ptr is None:
        row["verdict"] = "no_ptr"
    else:
        row["verdict"] = "not_a_known_bot"
    return row


def main(argv: list[str] | None = None) -> int:
    def body() -> int:
        p = http_safe.JsonArgumentParser(prog="bot_verify.py", description="rDNS bot verification")
        p.add_argument("ips", nargs="*", help="IP addresses")
        p.add_argument("--log", help="access log (Caddy JSON, combined, or one IP per line)")
        p.add_argument("--max-ips", type=int, default=MAX_IPS_DEFAULT)
        p.add_argument("--only-claimed", action="store_true", help="look up only IPs whose UA claims a bot")
        p.add_argument("--out")
        args = p.parse_args(argv)
        if args.out:
            http_safe.safe_out_path(args.out)
        if not args.ips and not args.log:
            raise http_safe.CliError("give IP addresses or --log", "bad_arguments")
        if not 1 <= args.max_ips <= 5000:
            raise http_safe.CliError("--max-ips must be 1..5000", "bad_arguments")
        claims: dict[str, set] = {}
        range_bots: set[str] = set()
        hits = Counter()
        bad = 0
        for raw in args.ips:
            ip = _canonical_ip(raw)
            if ip is None:
                bad += 1
                continue
            claims.setdefault(ip, set())
        lines = 0
        if args.log:
            http_safe.read_input_file(args.log, 0)
            if os.path.getsize(args.log) > MAX_LOG_BYTES:
                raise http_safe.CliError("log larger than 1 GB: cut it first", "bad_input")
            with open(args.log, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    lines += 1
                    if lines > MAX_LINES:
                        break
                    ip, ua = parse_log_line(line)
                    if ip is None:
                        continue
                    vendors = claimed_vendors(ua)
                    if args.only_claimed and not vendors:
                        continue
                    claims.setdefault(ip, set()).update(vendors)
                    hits[ip] += 1
                    if ua and IP_RANGE_BOTS.search(ua):
                        range_bots.add(ip)
        ordered = sorted(claims, key=lambda i: (-len(claims[i]), -hits[i], i))
        skipped = max(0, len(ordered) - args.max_ips)
        rows = []
        for ip in ordered[:args.max_ips]:
            row = verify_ip(ip, sorted(claims[ip]), ua_ip_range_bot=ip in range_bots)
            if hits[ip]:
                row["hits"] = hits[ip]
            rows.append(row)
        verdicts = Counter(r["verdict"] for r in rows)
        report = {"checked": len(rows), "skipped_over_limit": skipped, "bad_inputs": bad,
                  "log_lines": lines, "verdicts": dict(verdicts), "results": rows,
                  "rules": {k: list(v["domains"]) for k, v in VENDORS.items()},
                  "note": "Google: пользовательские загрузчики (google.com / googleusercontent.com) этой проверкой "
                          "не покрыты полностью; ИИ-боты сверяются по диапазонам IP вендора"}
        return http_safe.emit(report, args.out, {"checked": len(rows), "verdicts": dict(verdicts)})

    return http_safe.run_cli(body)


if __name__ == "__main__":
    sys.exit(main())
