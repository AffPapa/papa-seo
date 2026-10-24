# Third-party notices

papa-seo
Copyright (c) 2026 AFFPAPA (https://affpapa.org)
Licensed under the MIT License (see LICENSE).

> **Draft for 0.1.0.** This file lists the donor projects named in the build
> specification. The final list keeps only sources that were actually used and
> is assembled from the per-file attribution logs of the build
> (`.build/B*-attributions.md`). Until then, a donor listed here is a planned
> source, not a confirmed one.

This pack contains original work and material adapted from the open-source
projects listed below. Each adapted file carries a header naming its source,
the upstream commit and what was changed:

```
<!-- Adapted from <owner>/<repo>@<sha7> (<License>, © <holder>). Changes: <summary>. -->
```

Upstream copyright and permission notices are reproduced in full in
`licenses/<owner>__<repo>.txt`, together with the upstream NOTICE file where
one exists. Commits are pinned in `source.lock.json`.

Third-party material keeps its original license. Where that license is not
MIT, the file header says so.

## Apache License 2.0 material

The following NOTICE text is reproduced as required by Section 4(d) of the
Apache License 2.0:

    SuperSEO Skills
    Copyright 2026 InhouseSEO

    This product includes prompt-engineering and documentation content
    developed by InhouseSEO (https://inhouseseo.ai).

Full license text: `licenses/inhouseseo__superseo-skills.txt`.

iannuttall/seo is also Apache-2.0 and has no NOTICE file. Full license text:
`licenses/iannuttall__seo.txt`.

## Sources: adapted material

One line per source. `used in` is filled from the build logs.

| Source | Commit | License | Copyright holder (from LICENSE) | Planned for | Notes |
|---|---|---|---|---|---|
| [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) | 6be93f4 | MIT | 2026 agricidaniel | tech-audit, on-page, schema, performance, geo, semantics, serp, backlinks, ecommerce, international, programmatic, measure | `skills/seo-flow` and `agents/seo-flow.md` are CC BY 4.0 (Daniel Agrici) and are not used |
| [calm-north/seojuice-skills](https://github.com/calm-north/seojuice-skills) | c1f633b | MIT | 2026 SEOJuice, Calm North Labs UAB | tech-audit, serp, migration | |
| [seo-skills/seo-audit-skill](https://github.com/seo-skills/seo-audit-skill) | fac4b75 | MIT | 2024-present SEOmator | tech-audit, indexing | |
| [seo-skills/geo-audit-skill](https://github.com/seo-skills/geo-audit-skill) | 17fd0d2 | MIT | 2026 SEOmator | indexing, geo | |
| [mykpono/ultimate-seo-geo](https://github.com/mykpono/ultimate-seo-geo) | c92fdba | MIT | 2026 Myk Pono | indexing, links, logs | |
| [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill) | 445c46c | MIT | 2026 Bhanu Namikaze; 2026 agricidaniel | indexing, links, international, logs | LICENSE names two holders |
| [kostja94/marketing-skills](https://github.com/kostja94/marketing-skills) | b59bbde | MIT | 2025 kostja94 | indexing, yandex, eeat | |
| [iannuttall/seo-graph](https://github.com/iannuttall/seo-graph) | not pinned | MIT | 2026 Ian Nuttall | schema | Its NOTICE credits code derived from [jdevalk/seo-graph](https://github.com/jdevalk/seo-graph) (MIT, Joost de Valk); both are credited |
| [iannuttall/seo](https://github.com/iannuttall/seo) | 69a8ea2 | Apache-2.0 | 2026 Ian Nuttall | measure | Project name, slogan and logo are trademarks of the author and are not used |
| [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) | afa8da9 | MIT | 2026 Addy Osmani | performance | |
| [lionkiii/claude-seo-skills](https://github.com/lionkiii/claude-seo-skills) | e8347fc | MIT | 2026 Aashish | geo, eeat | Partly derived from claude-seo; only original parts are used |
| [artwist-polyakov/polyakov-claude-skills](https://github.com/artwist-polyakov/polyakov-claude-skills) | 197190a | MIT | 2025 Aleksandr Poliakov | yandex | |
| [inhouseseo/superseo-skills](https://github.com/inhouseseo/superseo-skills) | 9cf22cc | Apache-2.0 | 2026 InhouseSEO | eeat, brief, write, deai, factcheck | NOTICE reproduced above |
| [nowork-studio/notfair-plugin](https://github.com/nowork-studio/notfair-plugin) | ed835f2 | MIT | 2026 Toprank Contributors | backlinks | |
| [garrettjsmith/localseoskills](https://github.com/garrettjsmith/localseoskills) | 405ce20 | MIT | 2026 Garrett Smith / GMB Gorilla | local | |
| [AgriciDaniel/claude-blog](https://github.com/AgriciDaniel/claude-blog) | 3544423 | MIT | 2025-2026 AgriciDaniel | write, voice, factcheck | `brain/` is all rights reserved and is not used. Files it adapted from pbakaus/impeccable (Apache-2.0) or FLOW (CC BY 4.0) are used only with those attributions; its NOTICE is in `licenses/` |
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | e85f3cb | MIT | 2025 Corey Haines | edit, landing | Original source; copies in other repositories are not used |
| [coleschaffer/copywritingskills-rmbc](https://github.com/coleschaffer/copywritingskills-rmbc) | 8327d49 | MIT | 2026 Stefan Georgi | edit | |
| [Nanako0129/sepia](https://github.com/Nanako0129/sepia) | fb06be7 | MIT | 2026 Nanako Tsai | deai, voice | |
| [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) | 3621b1c | MIT | 2026 Ilya Utov | deai, text-metrics | Fonts in `docs/` (OFL) are not used |
| [blader/humanizer](https://github.com/blader/humanizer) | 8c307f3 | MIT | 2025 Siqi Chen | deai | Pattern list traces back to Wikipedia (see below); its wording and examples are not used |
| [robpalmer99/claude-code-copywriting-skills](https://github.com/robpalmer99/claude-code-copywriting-skills) | 7dbfd61 | CC BY 4.0 | 2026 Rob Palmer | landing | Credit: Rob Palmer, https://robpalmer.com/blog/claude-code-copywriting-skills. License: https://creativecommons.org/licenses/by/4.0/. Adapted files are marked as changed |
| [every-app/open-seo](https://github.com/every-app/open-seo) | 2d8236a | MIT | 2026 Ben Senescu | report | `web/content/legal/*` is all rights reserved and is not used |

## Inspired by: ideas only

No text or code was taken from these projects. Ideas were restated in our own
words.

| Source | Commit | License status | Idea used for |
|---|---|---|---|
| [Horosheff/google-yandex-seo-skill](https://github.com/Horosheff/google-yandex-seo-skill) | bdd76f9 | MIT, © 2026 Ertugrul Akben | separate Google and Yandex findings |
| [MYehia565/google-seo-agent-skills](https://github.com/MYehia565/google-seo-agent-skills) | 5336bcb | MIT, © 2026 MYehia565 | e-commerce checks |
| [Illyism/seo-skills](https://github.com/Illyism/seo-skills) | a47acc9 | MIT declared in README, no LICENSE file (Ilias Ism) | headlines |
| [yabasha/copywrite-skill](https://github.com/yabasha/copywrite-skill) | not pinned | MIT declared in README, no LICENSE file | headlines |
| [Yaroslavle/seo-content-writer-claude-skill](https://github.com/Yaroslavle/seo-content-writer-claude-skill) | not pinned | MIT declared in README, no LICENSE file | brief |
| [alenazaharovaux/share](https://github.com/alenazaharovaux/share) | not pinned | no root license; per-skill licenses | brief |
| [milcheliquids-ship-it/seo-text-skill](https://github.com/milcheliquids-ship-it/seo-text-skill) | not pinned | no license | brief, text metrics |
| [mazamaka/seo-skills-claude-code](https://github.com/mazamaka/seo-skills-claude-code) | 5cec59e | no license | clustering |
| [affilino/ecommerce-seo-audit-skill](https://github.com/affilino/ecommerce-seo-audit-skill) | 76f313d | all rights reserved | e-commerce checks |
| Wikipedia, "Signs of AI writing" (WikiProject AI Cleanup) | — | CC BY-SA 4.0 | signs of machine-written text as a topic; our pattern list, wording and examples are our own |

## Not used

Reviewed and deliberately left out because their licenses do not mix with an
MIT package or authorship could not be established: ilien-dev/quiron
(AGPL-3.0), yaojingang/GEOHub (AGPL-3.0), jaredrhod/ai-marketing-skills
(CC BY-SA 4.0), and one repository cloned from another project without a
traceable author.

## Public documentation

Facts and thresholds from Google Search Central and web.dev (content under
CC BY 4.0, code samples under Apache 2.0), schema.org and Yandex Webmaster Help
are restated in our own words with links to the source pages. Schema.org type
and property names are used as an interface; vocabulary descriptions are not
copied.

## Detailed attribution by file

Per-file record of what each module, reference or script took from which upstream project. Texts are rewritten; rows list structure, checks or ideas taken. Commits are the pinned versions in `source.lock.json`. Script attributions for `scripts/` also appear as header comments in the files themselves.

### Technical SEO modules, facts-2026, folklore

| Наш файл | Донор @ sha7 | Лицензия, © | Что взято |
|---|---|---|---|
| modules/tech-audit.md | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | категории skills/seo-technical (crawl/index/security/URL/mobile/JS-рендеринг) → чек-лист с гейтом |
| | seo-skills/seo-audit-skill@fac4b75 | MIT, © 2024-present SEOmator | идея потолков балла src/score-caps.ts (noindex, пустая страница, закрыт бот; кап по стартовой странице) |
| | calm-north/seojuice-skills@c1f633b | MIT, © 2026 SEOJuice, Calm North Labs UAB | порядок дерева диагностики skills/diagnose-seo (без «ожидаемых эффектов») |
| modules/indexing.md | seo-skills/geo-audit-skill@17fd0d2 | MIT, © 2026 SEOmator | семантика robots по RFC 9309 и 4xx/5xx (lib/robots.py) |
| | mykpono/ultimate-seo-geo@c92fdba | MIT, © 2026 Myk Pono | проверки правдоподобия lastmod (scripts/sitemap_checker.py); классы причин и порог движения (scripts/index_coverage_diff.py) |
| | Bhanunamikaze/Agentic-SEO-Skill@445c46c | MIT, © 2026 Bhanu Namikaze | идея вердикта по каждому URL robots × meta × canonical × sitemap (indexability_matrix.py) |
| | kostja94/marketing-skills@b59bbde | MIT, © 2025 kostja94 | таблица типов страниц под noindex, разбор «Crawled – not indexed» (skills/seo/technical/indexing) |
| modules/on-page.md | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | перечень on-page и image-проверок skills/seo-page, skills/seo-images (без норм символов, слов, веса файлов) |
| modules/schema.md | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | шаги обнаружения/валидации/генерации skills/seo-schema; карта выведенных типов — только как подсказка, перепроверена по Google |
| | iannuttall/seo-graph (sha не записан: нет в donor-shas.tsv и нет .git; снимок с пушем 2026-10-23) | MIT, © 2026 Ian Nuttall; код графа производен от jdevalk/seo-graph, MIT, © Joost de Valk | правила устойчивых `@id`, дедупликации и проверки висячих ссылок @graph (packages/core/src/schema: ids.ts, dedupe.ts, assemble.ts) |
| modules/performance.md | addyosmani/web-quality-skills@afa8da9 | MIT, © 2026 Addy Osmani | порядок «сначала поле, потом трасса», правила preload/fetchpriority, «не заявлять улучшение поля сразу» (skills/core-web-vitals) |
| | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | списки узких мест по LCP/INP/CLS (skills/seo/references/cwv-thresholds.md), перегруппированы по подчастям LCP |
| modules/international.md | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | 8 проверок и согласование с canonical (skills/seo-hreflang) |
| | Bhanunamikaze/Agentic-SEO-Skill@445c46c | MIT, © 2026 Bhanu Namikaze | проверки hreflang в sitemap (hreflang_sitemap_validator.py, hreflang_checker.py) |
| modules/programmatic.md | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | оценка источника данных, статика/динамика шаблона, URL, canonical, sitemap, index bloat (skills/seo-programmatic); пороги уникальности выброшены как фольклор |
| modules/migration.md | calm-north/seojuice-skills@c1f633b | MIT, © 2026 SEOJuice, Calm North Labs UAB | фазы и чек-листы skills/migrate-site (инвентарь, карта 301, стенд, выкладка, наблюдение, откат) без процентов просадки |
| modules/logs.md | Bhanunamikaze/Agentic-SEO-Skill@445c46c | MIT, © 2026 Bhanu Namikaze | разрезы по ботам/путям/статусам (log_file_analyzer.py) |
| | mykpono/ultimate-seo-geo@c92fdba | MIT, © 2026 Myk Pono | оговорки: кэш CDN, «не найден ≠ не ходит», IP не печатать (scripts/ai_bot_logs.py) |
| modules/ecommerce.md | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | чек-лист карточки и правила валидации Product (skills/seo-ecommerce) без скоринга полноты и DataForSEO |
| | Bhanunamikaze/Agentic-SEO-Skill@445c46c | MIT, © 2026 Bhanu Namikaze | идеи проверок фасетов и листингов (faceted_nav_audit.py, collection_page_checker.py) |
| modules/local.md | garrettjsmith/localseoskills@405ce20 | MIT, © 2026 Garrett Smith / GMB Gorilla | порядок аудита и чек-листы skills/local-seo-audit (профиль, категории, дубли, NAP, справочники, отзывы, страницы точек) без вендоров и кредитов |
| modules/backlinks.md | nowork-studio/notfair-plugin@ed835f2 | MIT, © 2026 Toprank Contributors | порядок источников данных, фазы доноры/анкоры/цели, осторожный disavow (seo/backlink-audit/WORKFLOW.md) |
| | AgriciDaniel/claude-seo@6be93f4 | MIT, © 2026 agricidaniel | бесплатные источники и их перекосы (skills/seo/references/free-backlink-sources.md) без процентов покрытия и весов |
| references/facts-2026.md | — | — | своё; первоисточники: Google Search Central, web.dev, indexnow.org, Google Business Profile Help (открыты 24.10.2026), OpenAI/Anthropic/Perplexity и Яндекс — по research/03. Пересказ CC BY 4.0-документации Google с короткими цитатами |
| references/folklore.md | — | — | своё; список мифов из research/03 §4–4.1 и SPEC §2.7, опровержения по первоисточникам |

### GEO, Yandex, strategy modules; ai-bots; yandex reference

| Файл | Донор @sha7 | Лицензия, правообладатель | Что взято |
|---|---|---|---|
| modules/geo.md | lionkiii/claude-seo-skills@e8347fc `skills/seo-ai-optimization` | MIT, © 2026 Aashish | гейт допуска «проиндексирована + допущена к сниппету», проход по мифам Google (llms.txt, дробление, переписывание под AI, неестественные упоминания) |
| modules/geo.md | AgriciDaniel/claude-seo@6be93f4 `skills/seo-geo` (+ references) | MIT, © 2026 agricidaniel | таблица «утверждение → свой бот», раздельный отчёт по ботам поиска и обучения, llms.txt как необязательный |
| modules/geo.md | seo-skills/geo-audit-skill@17fd0d2 `src/geo_audit/lib/safety.py` | MIT, © 2026 SEOmator | правило: текст, обращённый к модели, не попадает в генерируемый llms.txt, а уходит в отчёт |
| modules/yandex.md | artwist-polyakov/polyakov-claude-skills@197190a `plugins/yandex-webmaster`, `plugins/yandex-wordstat` | MIT, © 2025 Aleksandr Poliakov | порядок работы с Вебмастером только на чтение, проверка интента перед пометкой запроса целевым; cookie-скрейпинг Алисы сознательно не взят |
| modules/yandex.md | Horosheff/google-yandex-seo-skill (sha нет в donor-shas.tsv) | MIT, © 2026 Ertugrul Akben | идея: раздельные находки Google / Яндекс, категории юридических сигналов (оферта, персданные, оплата, доставка, гарантия, реквизиты) — своими словами; эвристики «поведенческих прокси» отвергнуты |
| modules/eeat.md | kostja94/marketing-skills@b59bbde `skills/seo/entity-seo` | MIT, © 2025 kostja94 | сигналы сущности, Organization/Person со стабильным `@id`, согласованность имени/логотипа/описания; убраны «~3,2×» и sitelinks searchbox |
| modules/eeat.md | lionkiii/claude-seo-skills@e8347fc `skills/seo-helpful-content` | MIT, © 2026 Aashish | вопросы самооценки people-first и тревожные признаки search-engine-first (сжато) |
| modules/semantics.md | AgriciDaniel/claude-seo@6be93f4 `skills/seo-cluster/references/serp-overlap-methodology.md` | MIT, © 2026 agricidaniel | пороги общих URL 7–10 / 4–6 / 2–3 / 0–1, пре-группировка по интенту, антипаттерны, фильтр вездесущих доменов |
| modules/semantics.md | artwist-polyakov/polyakov-claude-skills@197190a `plugins/yandex-wordstat` | MIT, © 2025 Aleksandr Poliakov | ловушки интента («для X», «своими руками», ремонт) |
| modules/semantics.md | mazamaka/seo-skills-claude-code (лицензии нет) | — | идея: файл `page_map.csv` и порог ≥ 3 общих URL; ни строки текста |
| modules/serp.md | AgriciDaniel/claude-seo@6be93f4 `skills/seo-sxo`, `skills/seo-competitor-pages` | MIT, © 2026 agricidaniel | чтение выдачи «с конца», консенсус типа страницы, таблица несовпадения типа; правила честных сравнений |
| modules/serp.md | calm-north/seojuice-skills@c1f633b `skills/target-serp` | MIT, © 2026 SEOJuice, Calm North Labs UAB | таблица «блок выдачи — кто держит — наша страница — реально ли»; устаревшие советы (FAQ/HowTo, нормы длины ответа) отброшены |
| modules/links.md | mykpono/ultimate-seo-geo@c92fdba `scripts/site_graph.py` | MIT, © 2026 Myk Pono | регион ссылки nav/footer/main, правило полноты для «нет на сайте», PageRank как внутренняя метрика |
| modules/links.md | Bhanunamikaze/Agentic-SEO-Skill@445c46c `scripts/orphan_pages_from_sitemap.py`, `scripts/anchor_text_audit.py` | MIT, © 2026 Bhanu Namikaze | сироты = URL sitemap без входящих в графе; список общих анкоров |
| modules/links.md | calm-north/seojuice-skills@c1f633b `skills/fix-linking` | MIT, © 2026 SEOJuice, Calm North Labs UAB | дерево решений для сироты, таблица вставок донор → цель → анкор → место; «ожидаемый ROI» и квоты анкоров отброшены |
| modules/measure.md | AgriciDaniel/claude-seo@6be93f4 `skills/seo-drift/references/comparison-rules.md` | MIT, © 2026 agricidaniel | поля снимка и уровни CRITICAL/WARNING/INFO для дрейфа после релиза (сжато, без SQLite и Lighthouse) |
| modules/measure.md | iannuttall/seo@69a8ea2 `skills/seo/SKILL.md`, `evals/striking-distance.json` | Apache-2.0, © 2026 Ian Nuttall | идея: сравнение индексации неделя к неделе по URL и причине, «средняя позиция — среднее, а не место», следующий шаг в конце ответа; своими словами, без текста |
| modules/report.md | every-app/open-seo@2d8236a `.agents/skills/seo-report/SKILL.md` | MIT, © 2026 Ben Senescu | одна самодостаточная страница, вердикт первым, находка тремя строками, раздел «как сделан отчёт», HTML без внешних ресурсов и скриптов; брендовый футер, ссылки на вендора и «expected effect» убраны |
| references/ai-bots.yaml, .json | tigerless-labs/seo-ops `references/ai-crawlers.yaml` (лицензии нет; по research/03, файл не открывался) | — | идея: ростер как данные, группы search_classic / search / training / user_fetch, раздел «не включено и почему» |
| references/ai-bots.yaml, .json | — | — | данные — из первоисточников, проверено 24.10.2026: developers.openai.com/api/docs/bots; support.claude.com/en/articles/8896518; docs.perplexity.ai/guides/bots; developers.google.com …/google-common-crawlers, …/google-user-triggered-fetchers; support.apple.com/en-us/119829; commoncrawl.org/ccbot; developers.facebook.com/docs/sharing/webmasters/web-crawlers; developer.amazon.com/amazonbot; yandex.ru/support/webmaster/ru/robot-workings/check-yandex-robots, …/adding-site/indexing-prohibition. Bing — страница не прочиталась, помечено в записи |
| references/yandex.md | — | справка Яндекса — обычное авторское право, только пересказ | пересказ справки Вебмастера (ревизия r21762422): robots-txt, user-agent, allow-disallow, clean-param, crawl-delay, check-yandex-robots, metatags, schema-org, supported-schemas/*, open-graph, alice, service/alice-answers, epos, indexing-prohibition, indexnow/key и reference, moving-site, crawl-rate, rendering; цены — aistudio.yandex.ru/docs/ru/search-api/pricing |
| references/yandex.md | artwist-polyakov/polyakov-claude-skills@197190a `plugins/yandex-webmaster/references/ALICE_EFFICIENCY.md` | MIT, © 2025 Aleksandr Poliakov | факт: у раздела «Видимость в Алисе» нет публичного API (проверено автором 03.09.2026); со ссылкой |

### Content modules, ru-style, page-types, text scripts

| Наш файл | Донор @ sha7 | Лицензия, © | Что взято |
|---|---|---|---|
| modules/brief.md | inhouseseo/superseo-skills@9cf22cc | Apache-2.0, © 2026 InhouseSEO (NOTICE обязателен) | skills/content-brief (бриф от прочитанной выдачи, «не выводить содержание непрочитанной страницы»), skills/expert-interview (2–4 вопроса по одному: ошибки новичков, пример с цифрой, что удивило, кому не подходит) |
| modules/write.md | inhouseseo/superseo-skills@9cf22cc | Apache-2.0, © 2026 InhouseSEO | skills/write-content: фазы бриф → тип → текст → проверки, «настоящая конкретика или вопрос», ответ на первом экране |
| | AgriciDaniel/claude-blog@3544423 | MIT, © 2025-2026 AgriciDaniel | skills/blog-write: «публичные утверждения — проверенный источник или качественная формулировка», без квот на длину и статистику |
| modules/edit.md | coreyhaines31/marketingskills@e85f3cb | MIT, © 2025 Corey Haines | skills/copy-editing: режимы (пусто/живой голос/точечная), точечная правка без полного прохода, проходы ясность → голос → «и что?» → доказательства → конкретика → действие, тест «лучше или просто иначе», references/content-refresh.md (сетка разрыва с выдачей, план Keep/Revise/New до правки, сохранить URL и якоря) |
| | coleschaffer/copywritingskills-rmbc@8327d49 | MIT, © 2026 Stefan Georgi | skills/copy-rewrite: «сначала аудит, потом правка по разделам, до/после» (без RMBC-баллов) |
| | Nanako0129/sepia@fb06be7 | MIT, © 2026 Nanako Tsai | операция recreate: голый список фактов → проверка «ничего не добавлено» → текст заново; не добавлять позицию, которой нет в источнике |
| modules/deai.md | Nanako0129/sepia@fb06be7 | MIT, © 2026 Nanako Tsai | SKILL.md (операции, калибровка «полоса, а не полюс», hard guardrails), references/professional-pass.md (10 проверок, по одной за проход, whitelist), style-pass.md §4 (тест удаления и тест отката) |
| | ilyautov/humanizer-ru@3621b1c | MIT, © 2026 Ilya Utov | «удаляй, не дописывай», матрица регистров, факт-замок, холодное перечитывание вторым агентом, стоп после второго круга |
| | blader/humanizer@8c307f3 | MIT, © 2025 Siqi Chen | только структура: сила признака (сильные — с одного попадания, слабые — кластером), раздел «когда не действовать». Текст каталога (линия Wikipedia) не переносился |
| | inhouseseo/superseo-skills@9cf22cc | Apache-2.0, © 2026 InhouseSEO | идея теста «мог бы этот абзац стоять где угодно» (write-content/references/anti-slop-ruleset.md; сам superseo приписывает её aplaceforallmystuff/the-antislop — не проверено) |
| modules/landing.md | coreyhaines31/marketingskills@e85f3cb | MIT, © 2025 Corey Haines | skills/copywriting: диагноз ситуации, три вопроса к строке, `[NEED: …]` вместо пруфа, «утверждения должны подтверждаться, отказ — с ключом», блоки страницы, «акцент на одном-двух местах» |
| | robpalmer99/claude-code-copywriting-skills@7dbfd61 | CC BY 4.0, © 2026 Rob Palmer (https://creativecommons.org/licenses/by/4.0/) | copychief: порядок ревью от стратегии к строке (классификация → главная мысль → первый экран → доказательства → оффер → действие → строки). Изменения указаны в шапке, как требует CC BY |
| modules/voice.md | Nanako0129/sepia@fb06be7 | MIT, © 2026 Nanako Tsai | references/voice-skills.md и voices/PERSONA-TEMPLATE.md: голос внутри регистра площадки, конфликт — пользователю, 3–5 приёмов на текст, проза вместо квот, «не выдумывать» не уступает голосу |
| | AgriciDaniel/claude-blog@3544423 | MIT, © 2025-2026 AgriciDaniel | skills/blog-style: мерить образцы, а не угадывать; профиль описательный, не определение авторства; только образцы, на которые есть права |
| modules/factcheck.md | AgriciDaniel/claude-blog@3544423 | MIT, © 2025-2026 AgriciDaniel | skills/blog-factcheck: нагруженные утверждения, проверка URL до загрузки, уровни источника T1–T5, эхо-кластеры, «подтверждено — только если загружено в этом прогоне», соответствие источнику ≠ истина (баллы 1.0/0.7 заменены статусами) |
| | inhouseseo/superseo-skills@9cf22cc | Apache-2.0, © 2026 InhouseSEO | write-content/references/fact-checking.md: оригинал, а не перепост; свежесть; точное совпадение числа; замена размытых атрибуций (неподтверждённая цифра «5–15 % выдуманной статистики» не перенесена) |
| | ilyautov/humanizer-ru@3621b1c | MIT, © 2026 Ilya Utov | факт-замок для части «сохранность» |
| references/ru-style.md | ilyautov/humanizer-ru@3621b1c | MIT, © 2026 Ilya Utov | матрица регистров, пять действий редактора, факт-замок и список оговорок, «не маркеры», сверка сдвигов усиления. Запрет «—» вне диапазонов **не** взят: раздел о тире написан заново по русской грамматике |
| references/page-types.md | inhouseseo/superseo-skills@9cf22cc | Apache-2.0, © 2026 InhouseSEO | идея таблицы «тип → интент → первый экран/H2 → разметка» (content-brief/references/content-types-overview.md); без объёмов слов, с типами карточки сущности, события, вакансии |

| Где | Источник | Статус лицензии (research/06) | Идея |
|---|---|---|---|
| scripts/deai_scan.py | smixs/humanizer-ru@ff990df | ✅ MIT, © 2026 Serge Shima (сам ссылается на Vladimir-Human/humanizer-ru) | ловить следы разметки ассистентов (oaicite, turnNsearchN, utm_source чат-ботов, сноски 【†】); регулярки написаны заново, отмечено комментарием в скрипте |
| scripts/factdiff.py | ilyautov/humanizer-ru@3621b1c (`scan.py --before`, facts.py), Aboudjem/humanizer-skill@a58df06 (cli/lib/facts.js) | ✅ MIT | сравнение фактов до/после правки; код свой, файлы доноров не копировались (Aboudjem — по описанию в research/04) |
| scripts/text_metrics.py, modules/text-metrics.md | milcheliquids-ship-it/seo-text-skill | ⚠️ лицензии нет | метрики рунета: тошнота, вода, знаки без пробелов, «формулы сервисов не публичны — это оценка»; формулы описаны и реализованы своими словами, файлы донора не открывались |
| modules/headlines.md | Illyism/seo-skills@a47acc9 (seo-title-optimization) | ✅ˣ MIT только в README | «выдача как бриф», title/H1/slug/description об одном, slug не менять ради года |
| | yabasha/copywrite-skill | ✅ˣ MIT только в README | уровни осведомлённости → тип заголовка (сама схема — классика копирайтинга, Юджин Шварц) |
| modules/brief.md | Yaroslavle/seo-content-writer-claude-skill | ✅ˣ MIT только в README | сформулировать задачу читателя до ключа |
| | flaqai/Awesome_SEO_Writing_Skill@7d30056 | ✅ MIT | карточка задачи с явными допущениями |
| | alenazaharovaux/share (writing-guru) | ⚠️ лицензия неизвестна | выбрать угол подачи до текста |
| | milcheliquids-ship-it/seo-text-skill | ⚠️ лицензии нет | русские поля ТЗ (объём в знаках без пробелов, требования заказчика к метрикам); «нет фактов — нет блоков» |
| modules/voice.md | BrianRWagner/ai-marketing-claude-code-skills@f36b34f (voice-extractor) | ✅ˣ MIT только в README | 3–5 образцов или около 500 слов; сырые образцы ценнее вылизанных |
| modules/landing.md | coleschaffer/dtc-copywriting-skills (scarcity-urgency) | ✅ MIT, код ⛔ (исполняемые преамбулы) | дефицит и срочность только настоящие; файл не открывался, идея по research/04 |

## Trademarks

Product and project names are the property of their owners and are used only
to identify sources. No endorsement is implied.
