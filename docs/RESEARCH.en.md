# What papa-seo is built from

Research dated 2026-10-24, pack 0.1.1. The full Russian write-up is [RESEARCH.md](RESEARCH.md); attributions are in `THIRD_PARTY_NOTICES.md`, pinned commits in `source.lock.json`.

## Numbers

| What | How many |
|---|---|
| Repositories reviewed by code and text | 105 |
| Safety verdicts | 🟢 40 · 🟡 56 · 🔴 9 |
| Malicious payloads found (exfiltration, `base64→exec`, binaries, `postinstall`, reads of `~/.ssh`) | 0 |
| Fake network | 89 repositories on 89 accounts, reviewed by metadata only |
| Licenses across the original 94 | ✅ 71 · MIT in README only 10 · none/ARR/NC 9 · AGPL/CC BY-SA/fake 4 |
| Donors whose wording was adapted | 23 |
| Idea-only sources, nothing copied | 16 |
| Result | one skill: router, 29 modules, 9 stdlib scripts, 6 references, tests with attack fixtures |

## Method

Static review only: own stdlib scanners run with `python3 -I` from a separate directory. Checked auto-run surfaces (hooks, settings, `plugin.json`, `.mcp.json`, install and package scripts, CI, symlinks), network calls, secrets, deletion, persistence, invisible Unicode, archive listings without extraction, license files at any depth, GitHub API metadata for the fake network, primary sources for 2026 facts, vendor pricing pages.

Not done: no skill, script, installer or MCP server was run or installed; no antivirus or sandbox; no release binaries downloaded; stars not verified (the stargazers endpoint returns 404); npm/PyPI packages not matched to their repositories; remote files that skills ask to fetch not opened; third-party benchmark figures not re-run.

## Donors: wording adapted, header `Adapted from <owner>/<repo>@<sha7>` in each file

| Donor | Commit | License | Taken for |
|---|---|---|---|
| [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) | 6be93f4 | MIT | tech-audit, on-page, schema, performance, geo, semantics, serp, backlinks, ecommerce, international, programmatic, measure; `http_safe.py` design |
| [calm-north/seojuice-skills](https://github.com/calm-north/seojuice-skills) | c1f633b | MIT | tech-audit, migration, serp, links |
| [seo-skills/seo-audit-skill](https://github.com/seo-skills/seo-audit-skill) | fac4b75 | MIT | score caps in tech-audit |
| [seo-skills/geo-audit-skill](https://github.com/seo-skills/geo-audit-skill) | 17fd0d2 | MIT | robots per RFC 9309 (indexing, `robots_check.py`), llms.txt injection filter (geo) |
| [mykpono/ultimate-seo-geo](https://github.com/mykpono/ultimate-seo-geo) | c92fdba | MIT | indexing, links, logs |
| [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill) | 445c46c | MIT | indexing, international, logs, links, ecommerce |
| [kostja94/marketing-skills](https://github.com/kostja94/marketing-skills) | b59bbde | MIT | indexing, eeat |
| [iannuttall/seo-graph](https://github.com/iannuttall/seo-graph) | not pinned | MIT (code from [jdevalk/seo-graph](https://github.com/jdevalk/seo-graph)) | stable `@id` and `@graph` rules in schema |
| [iannuttall/seo](https://github.com/iannuttall/seo) | 69a8ea2 | Apache-2.0 | measure |
| [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) | afa8da9 | MIT | performance |
| [lionkiii/claude-seo-skills](https://github.com/lionkiii/claude-seo-skills) | e8347fc | MIT | geo, eeat (original parts only) |
| [artwist-polyakov/polyakov-claude-skills](https://github.com/artwist-polyakov/polyakov-claude-skills) | 197190a | MIT | yandex, semantics, `references/yandex` |
| [inhouseseo/superseo-skills](https://github.com/inhouseseo/superseo-skills) | 9cf22cc | Apache-2.0 + NOTICE | brief, write, deai, factcheck, `references/page-types` |
| [nowork-studio/notfair-plugin](https://github.com/nowork-studio/notfair-plugin) | ed835f2 | MIT | backlinks |
| [garrettjsmith/localseoskills](https://github.com/garrettjsmith/localseoskills) | 405ce20 | MIT | local |
| [AgriciDaniel/claude-blog](https://github.com/AgriciDaniel/claude-blog) | 3544423 | MIT | write, voice, factcheck |
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | e85f3cb | MIT | edit, landing |
| [coleschaffer/copywritingskills-rmbc](https://github.com/coleschaffer/copywritingskills-rmbc) | 8327d49 | MIT | edit |
| [Nanako0129/sepia](https://github.com/Nanako0129/sepia) | fb06be7 | MIT | deai, edit, voice |
| [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) | 3621b1c | MIT | deai, factcheck, `references/ru-style`, `factdiff.py` |
| [blader/humanizer](https://github.com/blader/humanizer) | 8c307f3 | MIT | deai: structure only, no catalogue text |
| [robpalmer99/claude-code-copywriting-skills](https://github.com/robpalmer99/claude-code-copywriting-skills) | 7dbfd61 | CC BY 4.0 | landing, changes marked |
| [every-app/open-seo](https://github.com/every-app/open-seo) | 2d8236a | MIT | report |

Idea-only sources (no text or code taken): Horosheff/google-yandex-seo-skill, MYehia565/google-seo-agent-skills, Illyism/seo-skills, yabasha/copywrite-skill, Yaroslavle/seo-content-writer-claude-skill, alenazaharovaux/share, milcheliquids-ship-it/seo-text-skill, mazamaka/seo-skills-claude-code, affilino/ecommerce-seo-audit-skill, Aboudjem/humanizer-skill, flaqai/Awesome_SEO_Writing_Skill, smixs/humanizer-ru, BrianRWagner/ai-marketing-claude-code-skills, tigerless-labs/seo-ops, coleschaffer/dtc-copywriting-skills, Wikipedia "Signs of AI writing" (topic only).

## Left out, by reason

| Reason | Examples |
|---|---|
| Paid APIs or cloud MCP that receives your GSC/GA4/Ads access | Ryze-AI-Adgent, irinabuht12-oss, hyperfx-ai, seranking, cognyai, sherotree, TheMattBerman/seo-kit, jev-seo, mangollc, Bomx/distribb-skill, dageno content-engine, weipanux, seomachine, ericosiu; AminForou/mcp-gsc writes to GSC without a flag |
| Ads and CTAs inside the output | OranAi-Ltd, zubair-trabzada/ai-marketing-claude, NulightJens, dageno/seo-geo-audit; community footers and partner links stripped from donors |
| CAPTCHA and bot-detection bypass | halilertekin/advanced-seo-mcp, mrgoonie/seo-insights-mcp-server, cnych/seo-mcp, egebese/dataseo-mcp; `blog-notebooklm` part of claude-blog |
| Uninstallers and installers that delete by prefix (`seo-*`, `geo-*`) or copy over your folders | zubair-trabzada/geo-seo-claude, FreeAutomation-Tech/claude-seo-kit, dalroot/agentic-seo, norahe0304-art/30x-seo; installers of claude-seo, Bhanunamikaze, lionkiii |
| Remote SKILL.md or instructions fetched from someone else's server | Illyism/seo-skills, rampstackco, OpenClaudia; `conversion-tracking` part of marketingskills; seo-text-skill feeds third-party page titles into an instruction executed verbatim |
| Auto-merge, auto-posting, writes to ad accounts and CRM | Gingiris, indranilbanerjee, `google-ads.js` in marketingskills, alirezarezvani (crontab + Bash at night) |
| Browser cookies and sessions | mvanhorn/last30days-skill, yasikvlad, `alice.sh` and `codex-review` in polyakov |
| Hooks on every tool call, settings edits | aaron-he-zhu/aaron-marketing-skills, agencia-conversion, imgompanda/fireauto, Aluxads, aleclindz harness |
| Fake network | 89 repositories: accounts created within two hours of one day, repos within four minutes, two commits each, 37–73 stars at zero watchers, MIT badge without a LICENSE file, instructions to fabricate progress and numbers |
| License does not mix with MIT or is missing | ilien-dev/quiron (AGPL), yaojingang/GEOHub (AGPL), jaredrhod (CC BY-SA), WordPress/agent-skills (GPL), g-battaglia/mcp-seo (MIT and AGPL in one commit), ccforseo, SNLabat |
| Clones and outdated facts | boraoztunc, davidpc007, seoskillsai, hmzainjamil, ninryt, borghei; huifer (FID, FAQ), metawhisp (FAQPage as "the AI surface"), 199-biotechnologies ("40–60 words"), numen-tech/slopornot (rewriting until a detector score drops) |

This is why papa-seo has no installer and no `seo-`/`geo-` prefix: it is copied as one folder, and other projects' uninstallers do not see it.

## Myths we did not adopt

| Claim | Verdict | Primary source |
|---|---|---|
| "Citation window of 134–167 words" | No primary source; the Princeton paper has no passage length; Ahrefs: length-to-AIO-citation correlation 0.04 | [arxiv.org/abs/2311.09735](https://arxiv.org/abs/2311.09735), [ahrefs.com](https://ahrefs.com/blog/short-vs-long-content-in-ai-overviews) |
| "Direct answer of 40–60 words under an H2" | No primary source; fine as an editing rule, not as a metric | — |
| FAQ rich results | Not shown since 2026-05-07; restricted to government and health sites in 2023 | [faqpage](https://developers.google.com/search/docs/appearance/structured-data/faqpage) |
| HowTo rich results | Removed 2023-09-13 | [howto-faq-changes](https://developers.google.com/search/blog/2023/08/howto-faq-changes) |
| llms.txt affects Google | "Google Search itself doesn't use them", "will neither harm nor help" | [ai-optimization-guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide) |
| "FID < 100 ms" | INP since 2024-03-12: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at the 75th percentile | [web.dev](https://web.dev/blog/inp-cwv-march-12) |
| "≥ 30–40 % unique text" for templated pages | No such figure at Google; the scaled content abuse policy applies | Google Search Central spam policies |
| Keyword density 1–2 % as a ranking factor | A Runet tooling heuristic; reported, never gated | — |
| Google-Extended has a User-Agent and affects AI Overviews | robots.txt token only; AI Overviews follow Googlebot and snippet directives | [google-common-crawlers](https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers) |
| `User-agent: *` closes YandexAdditional | It does not; the token needs its own group | [check-yandex-robots](https://yandex.ru/support/webmaster/ru/robot-workings/check-yandex-robots) |
| Host and Crawl-delay for Yandex | Host ignored since March 2018, Crawl-delay since 2018-02-22; Clean-param works | [robots-txt](https://yandex.ru/support/webmaster/ru/controlling-robot/robots-txt) |
| Wordstat API is free | GetTop and GetDynamics cost 20 ₽ per 1,000 requests | [search-api/pricing](https://aistudio.yandex.ru/docs/ru/search-api/pricing) |
| "Monolithic skills lose to atomic ones" (benchmark) | Numbers hold, conclusion does not: one fixture, 3 runs, ±8 spread, the leader is the benchmark author's product | [aleclindz/seo-skill-bench](https://github.com/aleclindz/seo-skill-bench) |

## What no donor had

YandexAdditional (0 mentions in 105 repositories), robots.txt with Yandex semantics (Clean-param, ignored Host and Crawl-delay), Yandex Webmaster alongside GSC in one measurement model, markup Yandex understands, commercial and legal signals of the Russian market, bot authenticity checks in logs (`bot_verify.py`), audits without crawling (one page, up to 20 URLs with a pause, or a crawler export), local Russian text metrics, a Russian de-AI layer, an evidence gate before "add X" (`policies/evidence.md`, `templates/finding.schema.json`), site moves that keep Yandex mirror glue.

## Still open

No donor skill was ever run; the "model without / with the skill" comparison on `evals/` has not been run; stars were not verified directly; four clean repositories from the second pass (quality gates, read-only GSC, page-type specs, checklists) are not in 0.1.x.
