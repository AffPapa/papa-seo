# Факты 2026: пороги, даты, правила поисковиков

Единственный источник цифр, порогов и дат для модулей. Модуль пишет `см. facts-2026 §N` и своих чисел не держит.
**Последняя проверка: 24.10.2026.** Пометки: ✅ — первоисточник открыт 24.10.2026, в скобках дата «Last updated» страницы; ◐ — проверено исследованием пакета (research/03, 24.10.2026), страница в этот заход не открывалась; ❓ — не перепроверено, правилом не считать.
Тексты Google Search Central — CC BY 4.0; здесь пересказ, короткие цитаты в кавычках. Справка Яндекса — только пересказ.
Боты AI — в `ai-bots.yaml`, Яндекс подробно — в `yandex.md`; здесь только то, на что ссылаются модули.

## §1. Сканирование и robots.txt (Google)

| Факт | Статус | Источник |
|---|---|---|
| Лимит robots.txt — 500 KiB, всё дальше игнорируется | ✅ (23.10.2026) | developers.google.com/search/docs/crawling-indexing/robots/robots_txt |
| 4xx на robots.txt, кроме 429, = файла нет, ограничений нет. 401/403 не годятся для снижения скорости обхода | ✅ | там же |
| 5xx на robots.txt: первые 12 ч обход стоит, затем до 30 дней берётся последняя удачная копия, дальше — по доступности сайта | ✅ | там же |
| Кэш robots.txt обычно до 24 ч (может дольше, учитывает `Cache-Control: max-age`) | ✅ | там же |
| Конфликт правил: побеждает самое длинное (специфичное) правило; при равенстве — наименее строгое (Allow) | ✅ | там же; RFC 9309 (rfc-editor.org/rfc/rfc9309) |
| Google поддерживает только `user-agent`, `allow`, `disallow`, `sitemap`; `crawl-delay` не поддерживается | ✅ | там же |
| Disallow не убирает URL из индекса: «may still index URLs that are disallowed… without their content» | ✅ (10.07.2026) | …/crawling-indexing/consolidate-duplicate-urls |
| Googlebot для Поиска читает первые **2 МБ** поддерживаемого файла (HTML) и **64 МБ** PDF, считая несжатые байты; хвост не индексируется. Уточнено 03.02.2026 | ✅ | developers.google.com/search/updates; блог «Inside Googlebot», 03.2026 |
| Краулеры и фетчеры Google по умолчанию читают первые 15 МБ файла; у отдельных продуктов лимиты свои | ✅ (12.06.2026) | developers.google.com/crawling/docs/crawlers-fetchers/overview-google-crawlers |
| Ссылки Google находит только в `<a>` с `href` | ✅ (04.03.2026) | …/crawling-indexing/javascript/javascript-seo-basics |
| Гайд по краулинговому бюджету — для сайтов от ~1 млн страниц с еженедельными изменениями или от ~10 тыс. с ежедневными; «rough estimate» | ✅ (22.07.2026) | …/crawling-indexing/large-site-managing-crawl-budget |
| `noindex` бюджет не экономит: страница всё равно запрашивается. Soft 404 продолжают сканироваться и тратят бюджет | ✅ | там же |
| Справочник по краулерам Google переехал на developers.google.com/crawling (2025) | ✅ | developers.google.com/search/updates |

## §2. Директивы индексации, JS-рендеринг

| Факт | Статус | Источник |
|---|---|---|
| Правила robots meta: `noindex, nofollow, none, nosnippet, max-snippet, max-image-preview, max-video-preview, notranslate, noimageindex, unavailable_after, indexifembedded` | ✅ (24.03.2026) | …/crawling-indexing/robots-meta-tag |
| Любое правило meta robots можно отдать заголовком `X-Robots-Tag` (нужно для PDF и картинок) | ✅ | там же |
| Если URL закрыт в robots.txt, Google не видит его meta robots и X-Robots-Tag | ✅ | там же |
| При конфликте правил применяется более строгое | ✅ | там же |
| 24.03.2026 задокументировано поведение meta robots вне `<head>` | ✅ | developers.google.com/search/updates |
| Страницы с 200 идут в очередь рендеринга; при не-200 рендеринг может быть пропущен | ✅ (04.03.2026) | …/javascript/javascript-seo-basics |
| Увидев `noindex` в исходном HTML, Google может не рендерить страницу: снимать noindex скриптом бесполезно | ✅ | там же |
| Canonical лучше задавать в HTML; внедрённый JS-ом Google подхватит при рендере, но не рекомендует | ✅ | там же |
| Dynamic rendering Google называет обходным решением, не рекомендуемым | ◐ | …/javascript/dynamic-rendering |

## §3. Каноникализация, редиректы, переезды

| Факт | Статус | Источник |
|---|---|---|
| Сигналы canonical: редирект — сильный; `rel=canonical` (тег или HTTP-заголовок) — сильный; попадание в sitemap — слабый. Сигналы складываются, обязательных нет | ✅ (10.07.2026) | …/consolidate-duplicate-urls |
| robots.txt для каноникализации не использовать | ✅ | там же |
| При hreflang canonical указывать на страницу того же языка | ✅ | там же |
| После исправления Google может держать страницы в кластере дублей до двух недель | ✅ (21.08.2026) | …/canonicalization-troubleshooting |
| Частые причины «Google выбрал другой canonical»: ошибки CMS в canonical/3xx, языковые версии без hreflang, сервер отдаёт чужой домен или одинаковые soft 404, взлом, синдикация, копипаст | ✅ | там же |
| Постоянные: 301, 308, meta refresh 0 с, JS `location` (последний вариант). Временные: 302, 303, 307, meta refresh > 0 с | ✅ (14.04.2026) | …/crawling-indexing/301-redirects |
| Переезд: редиректы держать «as long as possible, generally at least 1 year» | ✅ (20.08.2026) | …/crawling-indexing/site-move-with-url-changes |
| Цепочки: вести сразу на финальный URL; Googlebot проходит до 10 переходов, держать цепочку желательно < 3 и всегда < 5 | ✅ | там же |
| Инструмент смены адреса — только при смене домена или поддомена; не для HTTP→HTTPS и смены путей. С 17.06.2026 — для всех вариантов поддомена, включая www/без www | ✅ | там же; …/search/updates |
| Средний сайт: новые URL проявляются в выдаче за несколько недель и дольше | ✅ | там же |
| Пагинация: у каждой страницы свой self-canonical, не на первую; ссылки на следующую — `<a href>`; `rel=next/prev` Google не использует (другие поисковики могут) | ✅ (10.12.2025) | …/specialty/ecommerce/pagination-and-incremental-page-loading |
| Фасеты: лишнее закрывать в robots.txt или выносить во фрагмент `#`; порядок параметров постоянный, без дублей; пустая комбинация — настоящий 404; разделитель `&`; canonical снижает обход медленнее, чем блок; nofollow работает, только если стоит на всех ссылках | ✅ (18.12.2025) | …/crawling-indexing/crawling-managing-faceted-navigation |

## §4. Sitemap и IndexNow

| Факт | Статус | Источник |
|---|---|---|
| Один файл: ≤ 50 000 URL и ≤ 50 МБ без сжатия; больше — индекс sitemap | ✅ (08.07.2026) | …/crawling-indexing/sitemaps/build-sitemap |
| `<priority>` и `<changefreq>` Google игнорирует | ✅ | там же |
| `<lastmod>` учитывается, только если «consistently and verifiably» точен; смена года в копирайте — не изменение | ✅ | там же |
| Абсолютные URL, UTF-8; без Search Console sitemap действует только на свою папку и ниже; кросс-хост — через robots.txt каждого сайта | ✅ | там же |
| IndexNow: эндпоинты Amazon, Bing, Naver, Seznam, Yandex, Yep; отправка в один расходится по всем; Google в FAQ не значится | ✅ | indexnow.org/faq |
| IndexNow: ≤ 10 000 URL на POST; ключ-файл на том же хосте, `keyLocation` при нестандартном пути | ✅ | там же |
| Яндекс поддерживает IndexNow с 18.10.2021 | ◐ | yandex.ru/support/webmaster/ru/indexing-options/index-now |

## §5. Title, сниппет, URL, картинки

| Факт | Статус | Источник |
|---|---|---|
| Лимита длины `<title>` нет; ссылка-заголовок в выдаче обрезается под ширину устройства | ✅ (10.12.2025) | …/search/docs/appearance/title-link |
| Источники title link: `<title>`, главный видимый заголовок, H1 и др. заголовки, `og:title`, крупный текст, анкоры ссылок на страницу, WebSite structured data | ✅ | там же |
| Правила title: у каждой страницы свой, описательный, без набивки и шаблонных повторов, бренд коротко через разделитель, язык как у контента | ✅ | там же |
| Лимита длины meta description нет; Google берёт её, когда она точнее текста страницы | ✅ (20.04.2026) | …/appearance/snippet |
| Управление сниппетом: `nosnippet`, `max-snippet`, `data-nosnippet` | ✅ | там же |
| 20.04.2026 — раздел о «read more» deep links в сниппетах | ✅ | …/search/updates |
| 02.03.2026 — для миниатюр Google использует schema.org и `og:image` | ✅ | там же |
| 23.10.2026 — обновлено руководство по структуре URL (дефис против подчёркивания) | ✅ | там же; …/crawling-indexing/url-structure |

## §6. Структурированные данные (Google)

| Факт | Статус | Источник |
|---|---|---|
| Форматы: JSON-LD (рекомендован), Microdata, RDFa | ✅ (10.07.2026) | …/structured-data/sd-policies |
| Размечать только видимое пользователю; скрытое не размечать | ✅ | там же |
| Валидная разметка не гарантирует rich result | ✅ | там же |
| Ручная мера за спам-разметку снимает право на rich results, на ранжирование в веб-поиске не влияет | ✅ | там же |
| Галерея на 16.10.2026 (25 функций): Article, Breadcrumb, Carousel, Course list, Dataset, Discussion forum, Education Q&A, Employer aggregate rating, Event, Image metadata, Job posting, Local business, Math solver, Movie carousel, Organization, Product, Profile page, Q&A, Recipe, Review snippet, Software app, Speakable, Subscription/paywalled content, Vacation rental, Video | ✅ | …/structured-data/search-gallery |
| FAQ rich result: объявлено 08.05.2026, не показывается с 07.05.2026; документация снята 15.06.2026. С 2023 был только у авторитетных гос- и медсайтов | ✅ | …/structured-data/faqpage; …/search/updates |
| HowTo: 08.08.2023 только десктоп, с 13.09.2023 не показывается | ◐ | developers.google.com/search/blog/2023/08/howto-faq-changes |
| 12.06.2025 объявлен вывод Course Info, ClaimReview, Estimated Salary, Learning Video, Special Announcement, Vehicle Listing (и Book Actions); с 09.09.2025 сняты из отчётов SC и Rich Results Test | ◐ | developers.google.com/search/blog/2025/06/simplifying-search-results |
| Book Actions на 24.10.2026 без пометки о выводе, но только для партнёров-поставщиков книг | ✅ (10.12.2025) | …/structured-data/book |
| Practice problem: уведомление 05.11.2025, документация снята 06.01.2026. Dataset жив только для Dataset Search | ✅ / ◐ | …/search/updates; …/search/blog/2025/11/update-on-our-efforts |
| Отзывы о себе: страницы с `LocalBusiness`/`Organization`, где сущность сама контролирует отзывы (включая виджеты на своём сайте), не получают звёзды | ✅ (08.09.2026) | …/structured-data/review-snippet |
| Запрет фейковых и нераскрытых стимулированных отзывов в контенте и разметке (правило добавлено 24.07.2026) | ✅ | там же; …/search/updates |
| Product: product snippets — страницы без прямой покупки (обзоры); merchant listings — страницы продажи. Разметка + фид Merchant Center вместе дают максимум | ✅ (10.12.2025) | …/structured-data/product |
| Merchant listing: обязательны `name`, `image`, `offers`; в Offer цена и валюта; цена > 0; `AggregateOffer` не поддерживается (в product snippets — да) | ✅ | …/structured-data/merchant-listing |
| 07.07.2026: `Product.category` (Text или CategoryCode); раздел о сроках скидки (`validFrom`, `validThrough`, `priceValidUntil`). 20.05.2026: `hasAdultConsideration` | ✅ | …/search/updates |
| LocalBusiness: обязательны `name`, `address`; каждая точка — свой LocalBusiness со своим URL; отделы — через `department` | ✅ (08.09.2026) | …/structured-data/local-business |
| 24.03.2026 — свойства Discussion Forum и QAPage уточнены; 24.09.2026 — `creator` в VideoObject | ✅ | …/search/updates |
| **У части типов раздела Required в документации Google нет.** Article: «There are no required properties; instead, add the properties that apply to your content» — `author`, `author.name`, `author.url`, `dateModified`, `datePublished`, `headline`, `image` стоят под Recommended. Organization: «There are no required properties» — `name`, `url`, `logo`, `sameAs`, `address`, `contactPoint` тоже Recommended. Называть их обязательными нельзя | ✅ (30.10.2026) | …/structured-data/article; …/structured-data/organization |
| Sitelinks search box: документация снята 29.11.2024, причина — «The sitelinks search box feature is no longer available in Google Search results», правило `nositelinkssearchbox` в архиве. Требований к `WebSite` + `SearchAction` у Google больше нет | ✅ (30.10.2026) | …/search/updates (29.11.2024) |
| Где Required есть: Product snippet (`name` + одно из review/aggregateRating/offers), merchant listing (`name`, `image`, `offers`; в Offer цена и валюта), Event (`name`, `startDate`, `location`, `location.address`), JobPosting (`title`, `description`, `datePosted`, `hiringOrganization`, `jobLocation` — последний не нужен при `applicantLocationRequirements`), LocalBusiness (`name`, `address`), Recipe (`name`, `image`), VideoObject (`name`, `thumbnailUrl`, `uploadDate`), BreadcrumbList (`itemListElement`, в ListItem `item`), ItemList/Carousel (`itemListElement`; в ListItem `position` и `url` либо `item`), QAPage (`mainEntity`; в Question `name`, `answerCount` и один из ответов; в Answer `text`), Review (`author`, `reviewRating.ratingValue`, `itemReviewed` у невложенного), AggregateRating (`ratingValue` и `ratingCount` либо `reviewCount`), SoftwareApplication (`name`, `offers.price`, одно из aggregateRating/review), DiscussionForumPosting (`author.name`, `datePublished`, одно из text/image/video), Dataset (`name`, `description`), ImageObject-лицензия (`contentUrl` + одно из creator/creditText/copyrightNotice/license), paywall (`isAccessibleForFree`), speakable (`cssSelector` либо `xPath`), ProfilePage (`mainEntity`, у Person `name`) | ✅ (30.10.2026) | …/structured-data/* — страница каждого типа |
| Описания словаря schema.org — CC BY-SA 3.0: имена типов и свойств использовать можно, описания не копировать | ◐ | schema.org/docs/terms.html |

## §7. Скорость и Core Web Vitals

| Факт | Статус | Источник |
|---|---|---|
| LCP ≤ 2,5 с хорошо, > 4 с плохо; INP ≤ 200 мс / > 500 мс; CLS ≤ 0,1 / > 0,25 | ✅ / ◐ (плохие пороги) | web.dev/articles/vitals (31.10.2024); web.dev/articles/defining-core-web-vitals-thresholds |
| Оценка по 75-му перцентилю загрузок, мобайл и десктоп отдельно | ✅ | web.dev/articles/vitals |
| INP заменил FID 12.03.2024; FID убран из CrUX API и PSI 09.09.2024 | ◐ | web.dev/blog/inp-cwv-march-12 |
| Google: хорошие CWV «aligns with what our core ranking systems seek to reward»; гарантии позиций нет | ✅ (10.12.2025) | …/search/docs/appearance/core-web-vitals |
| TTFB не входит в CWV; ориентир ≤ 0,8 с хорошо, > 1,8 с плохо | ✅ (28.11.2025) | web.dev/articles/ttfb |
| Подчасти LCP: TTFB ~40 %, задержка загрузки ресурса < 10 %, длительность загрузки ~40 %, задержка отрисовки < 10 % — ориентиры, не нормы в мс | ✅ (31.03.2025) | web.dev/articles/optimize-lcp |
| LCP-картинку никогда не ставить на lazy-load; `fetchpriority="high"` — одной-двум картинкам, не больше | ✅ | там же |
| Поле (CrUX, отчёт CWV в Search Console) — то, что видит Google; лаборатория (Lighthouse) — для отладки | ◐ | web.dev/articles/lab-and-field-data-differences |
| Отдельного отчёта Page Experience в Search Console больше нет | ❓ | по claude-seo, не перепроверено |

## §8. Языковые версии (hreflang)

| Факт | Статус | Источник |
|---|---|---|
| Три равноценных способа: `<link>` в head, HTTP-заголовок, sitemap; смешивать смысла нет | ✅ (21.09.2026) | …/specialty/international/localized-versions |
| Без взаимной ссылки пара игнорируется; каждая версия перечисляет себя и все остальные | ✅ | там же |
| `x-default` — запасной вариант, задуман для страниц выбора языка и автоперенаправления | ✅ | там же |
| Коды: язык ISO 639-1, регион ISO 3166-1 Alpha-2; только регион нельзя; `es-419` не поддерживается | ✅ | там же |
| Язык страницы Google определяет сам, не по `hreflang` и не по `lang` | ✅ | там же |
| Локализованные версии — дубли, только если основной контент не переведён | ✅ | там же |
| Отчёт «Международное таргетирование» в Search Console убран в 2022 | ❓ | по claude-seo, не перепроверено |

## §9. Спам-политики, AI-контент, ссылки

| Факт | Статус | Источник |
|---|---|---|
| Политики: cloaking, doorway abuse, expired domain abuse, hacked content, hidden text and link abuse, keyword stuffing, link spam, machine-generated traffic, malicious practices, misleading functionality, scaled content abuse, scraping, site reputation policy, sneaky redirects, thin affiliation, UGC spam | ✅ (28.08.2026) | …/search/docs/essentials/spam-policies |
| Scaled content abuse — «many pages are generated for the primary purpose of manipulating search rankings», способ генерации не важен | ✅ | там же |
| Back button hijacking (подмена истории браузера) — с 13.04.2026 в malicious practices | ✅ | там же; …/search/updates |
| С 15.05.2026 спам-политики распространяются и на AI-ответы Поиска | ✅ | …/search/updates |
| Site reputation policy: 28.08.2026 изменён подход в ЕЭЗ | ✅ | там же |
| AI-контент не запрещён; массовая генерация страниц без ценности может нарушать scaled content abuse; title, description, разметку и alt после генерации проверять вручную; AI-данные товаров помечать (обновлено 01.10.2026) | ✅ | …/fundamentals/using-gen-ai-content |
| Оценки асессоров «don't directly influence ranking» | ✅ | там же |
| `rel="sponsored"` — реклама и платные размещения (nofollow тоже допустим), `ugc` — пользовательский контент, `nofollow` — прочее; можно сочетать | ✅ (10.12.2025) | …/crawling-indexing/qualify-outbound-links |
| Disavow: Google обычно сам решает, каким ссылкам доверять; инструмент — только при большом объёме спам-ссылок, которые привели или вероятно приведут к ручной мере, и после попытки снять их | ◐ | support.google.com/webmasters/answer/2648487 |

## §10. AI-поиск Google и другие AI-системы

| Факт | Статус | Источник |
|---|---|---|
| Условие для AI Overviews / AI Mode: страница проиндексирована и может показываться со сниппетом; дополнительных технических требований нет | ✅ (10.12.2025) | …/search/docs/appearance/ai-features |
| Ограничение показа: `nosnippet`, `data-nosnippet`, `max-snippet`, `noindex`; доступ — правилами robots.txt для Googlebot | ✅ | там же |
| Google-Extended — только токен robots.txt; управляет обучением и grounding в других системах Google, на AI-функции Поиска не влияет | ✅ / ◐ | там же; …/crawling-indexing/google-common-crawlers |
| Гайд по generative AI (15.05.2026, обновлён 10.07.2026): «no requirement to break your content into tiny pieces», «There's no ideal page length», structured data «isn't required», llms.txt Поиск игнорирует («will neither harm nor help») | ✅ | …/search/docs/fundamentals/ai-optimization-guide |
| Search generative AI control в Search Console: с 31.08.2026 раскатан на все сайты; варианты include (по умолчанию) / exclude / inherit; действует на AI Overviews, AI Mode и генеративные функции Discover, на обучение не влияет; исключение вступает за 1–2 дня | ✅ | support.google.com/webmasters/answer/16908024; …/crawling-indexing/control-what-you-share |
| OpenAI: OAI-SearchBot — ChatGPT search, GPTBot — обучение, ChatGPT-User — по запросу пользователя (robots.txt может не применяться) | ◐ | developers.openai.com/api/docs/bots |
| Anthropic: ClaudeBot — обучение, Claude-SearchBot — поиск, Claude-User — по запросу; все соблюдают robots.txt | ◐ | support.claude.com/en/articles/8896518 |
| Perplexity: PerplexityBot — индекс, не обучение; Perplexity-User robots.txt в целом не соблюдает | ◐ | docs.perplexity.ai/guides/bots |
| Полный ростер ботов, уровни search / training / user_fetch и Яндекс — `ai-bots.yaml` | — | — |

## §11. Проверка подлинности ботов

| Факт | Статус | Источник |
|---|---|---|
| Google: обратный DNS → домен `googlebot.com`, `google.com` или `googleusercontent.com` → прямой DNS → тот же IP | ✅ (20.03.2026) | …/crawling-indexing/verifying-googlebot |
| Диапазоны IP Google: `/static/crawling/ipranges/` — `common-crawlers.json`, `special-crawlers.json`, `user-triggered-fetchers.json`, `user-triggered-fetchers-google.json`, `user-triggered-agents.json`; общий `gstatic.com/ipranges/goog.json` | ✅ | там же |
| Яндекс: обратный DNS на `yandex.ru`, `yandex.net`, `yandex.com` + прямая проверка | ◐ | см. `yandex.md` |
| Bing: обратный DNS на `search.msn.com` | ❓ | bing.com/webmasters/help/how-to-verify-bingbot-3905dc26 |
| Списки IP публикуют OpenAI, Anthropic, Perplexity (по их страницам ботов) | ◐ | §10 |

## §12. Локальный поиск (Google)

| Факт | Статус | Источник |
|---|---|---|
| Локальная выдача — по релевантности, расстоянию и известности (prominence: ссылки, отзывы и др.); купить позицию нельзя | ✅ | support.google.com/business/answer/7091 |
| Отзывы: больше отзывов и хороших оценок может помочь; ответы на отзывы рекомендованы | ✅ | там же |
| Название — как в реальном мире, без слоганов, кодов, часов, телефонов; нарушение может привести к блокировке профиля | ✅ | support.google.com/business/answer/3038177 |
| Абонентские ящики и виртуальные офисы не допускаются; сервисный бизнес скрывает адрес | ✅ | там же |
| Один профиль на бизнес и на точку; категорий — минимум, достаточный для описания основного бизнеса | ✅ | там же |
| 18.09.2026 — локальные запросы в aggregator и supplier units (ЕЭЗ); 08.09.2026 — региональные различия выдачи | ✅ | …/search/updates |
| Яндекс Бизнес, Карты, 2ГИС — см. `yandex.md` | — | — |

## §13. Яндекс: только то, на что ссылаются модули

| Факт | Статус | Источник |
|---|---|---|
| YandexAdditional / YandexAdditionalBot — токены robots.txt для показа в ответах с YandexGPT и в Поиске с Алисой; `User-agent: *` на них не действует | ◐ | yandex.ru/support/webmaster/ru/robot-workings/check-yandex-robots |
| `Clean-param` поддерживается; `Host` не учитывается с 2018 (нужен 301); `Crawl-delay` игнорируется с 22.02.2018 — скорость обхода в Вебмастере | ◐ | yandex.ru/support/webmaster/ru/controlling-robot/robots-txt |
| Разметка: schema.org (JSON-LD, microdata), Open Graph; поддерживаются не все типы (список — references/yandex.md §4); FAQPage в справке не найден; `nosnippet`/`max-snippet` Яндекс не поддерживает, показ в Алисе AI управляется YandexAdditional(Bot) | ◐ | yandex.ru/support/webmaster/ — раздел о поддерживаемых схемах |
| llms.txt: упоминаний у Яндекса не найдено | ◐ | research/03 |
| Wordstat API платный: GetTop и GetDynamics — 20 ₽ за 1 000 запросов | ◐ | aistudio.yandex.ru/docs/ru/search-api/pricing |

## §14. Снято, скоропортящееся, не подтверждено

| Утверждение | Почему не правило |
|---|---|
| «55,6 % origin проходят CWV» (CrUX, август 2026) | Меняется ежемесячно; перед цитированием открыть developer.chrome.com/docs/crux/release-notes |
| Soft Navigations в Chrome 151 | ❓ Не перепроверено; на CrUX и ранжирование пока не влияет (по claude-seo) |
| «AMP даёт преимущество» | Нет. С 01.07.2026 Google ведёт пользователей прямо на AMP-страницы издателя, AMP Cache и Viewer из документации убраны (…/search/updates) |
| Сроки снятия типов из Rich Results Test | Есть только у сторонних сайтов |
| Цифры Ahrefs/seoClarity о цитировании в AIO | Исследования третьих сторон на выборках США, не правила; см. `folklore.md` |

Как обновлять: открыть первоисточник, сверить дату «Last updated», поменять статус и дату проверки в шапке. Факт без первоисточника сюда не вносить.
