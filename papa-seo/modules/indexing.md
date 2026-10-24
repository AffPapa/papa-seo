<!-- Adapted from seo-skills/geo-audit-skill@17fd0d2 (MIT, © 2026 SEOmator), mykpono/ultimate-seo-geo@c92fdba (MIT, © 2026 Myk Pono), Bhanunamikaze/Agentic-SEO-Skill@445c46c (MIT, © 2026 Bhanu Namikaze), kostja94/marketing-skills@b59bbde (MIT, © 2025 kostja94). Changes: rewritten in Russian; robots semantics from lib/robots.py, sitemap plausibility checks from scripts/sitemap_checker.py, reason classes and movement threshold from scripts/index_coverage_diff.py, per-URL verdict idea from indexability_matrix.py and noindex page-type table from skills/seo/technical/indexing restated as one matrix; Yandex directives moved to yandex.md; numbers moved to facts-2026. -->
# Индексация: robots.txt, sitemap, матрица, IndexNow

Решает, что поисковики могут сканировать и что должно попасть в индекс: разбор robots.txt по RFC 9309 и расширениям Яндекса, проверка sitemap, матрица «сканировать / индексировать / в sitemap» по группам URL, разбор выгрузок «Индексирование страниц», IndexNow. Статусы, canonical и рендер одной страницы — `tech-audit.md`.

**Когда грузить:** режимы `audit`, `fix`, `yandex`; «не индексируется», «index bloat», «что закрыть», «проверь robots/sitemap», «Обнаружена, не проиндексирована», «Crawled – currently not indexed».

**Входы:** robots.txt (URL или файл); sitemap или индекс sitemap (URL или файл); список URL или групп URL (шаблоны путей); опционально две выгрузки GSC «Индексирование страниц» за разные даты, выгрузка Вебмастера «Страницы в поиске», список выкладок/релизов с датами.

## Шаги

1. **robots.txt.** `python3 scripts/robots_check.py <origin>/robots.txt --urls-file urls.txt --out robots.json`. Скрипт: группы и склейка UA, longest match, `*` и `$`, равенство → Allow, 4xx/5xx-семантика, лимит размера (facts-2026 §1); Яндекс — `Clean-param`, пометки об игнорируемых `Host`/`Crawl-delay`, YandexAdditional вне `*` (references/yandex.md); таблица доступа для ботов из `references/ai-bots.yaml`. Статус ответа robots.txt — первая строка отчёта.
2. **Sitemap.** `python3 scripts/sitemap_check.py <URL|файл> --follow-index --max-children 2 --out sitemap.json` (дочерние карты часто собираются на лету и тяжёлые: больше 2 шардов — только по явной просьбе, пропущенные шарды скрипт пишет в `children_warning`): тип (индекс/urlset), лимиты файла, чужие хосты, http-записи, дубли, правдоподобие `lastmod` (будущие даты, одна дата почти у всех, расхождение с датой на странице). URL из sitemap не обходить; опциональная выборка `--sample 20 --delay 2`.
3. **Сверка четырёх источников по каждому URL выборки:** robots (можно ли сканировать) × meta robots/X-Robots-Tag (можно ли индексировать, `page_facts.py`) × canonical (на себя или нет) × присутствие в sitemap. Противоречия — главные находки (см. «Матрица»).
4. **Группы URL, а не отдельные адреса.** Разбить сайт на группы по шаблонам путей и параметров (карточки, категории, фильтры, поиск, пагинация, теги, служебные, UGC). Для каждой группы — одно правило из матрицы. Решение для группы проверить на 3–5 живых URL.
5. **Разница выгрузок индексации** (если даны две): по каждой причине — сколько URL пришло и ушло. Сообщать только о заметных движениях (порог задаётся явно в отчёте, например ≥ 50 URL или ≥ 5 % при ≥ 10), иначе «2 → 3» читается как «рост на 50 %». Класс причины: technical (robots, noindex, 4xx/5xx, ошибки редиректа) / quality (просканирована, не проиндексирована; дубли) / discovery (обнаружена, не проиндексирована) / expected (редиректы, намеренные canonical). Связать скачки с датами выкладок.
6. **IndexNow** — проверить, есть ли ключ-файл и отправка; Google его не использует, Яндекс и Bing — да (facts-2026 §4). Для Яндекса вариант без IndexNow — переобход в Вебмастере (references/yandex.md).
7. **Гейт доказательств.** «Группа закрыта noindex» — только после проверки живых URL группы, а не по шаблону в коде или чужому отчёту. «В sitemap нет X» — только по полному набору файлов индекса.
8. Находки по `templates/finding.schema.json`, правки robots.txt и sitemap — черновиком с диффом (policies/actions.md).

## Матрица решений по группе URL

| Ценность группы для поиска | Сканирование | Индексация | sitemap | Типичные группы |
|---|---|---|---|---|
| Целевые страницы | разрешить | index, self-canonical | да | карточки, категории, статьи |
| Дубли целевых (параметры сортировки, UTM, слэш) | разрешить, если нужен canonical; иначе закрыть | canonical на основную | нет | `?sort=`, `?utm_` |
| Фильтры без спроса, комбинации фасетов | закрыть в robots.txt или вынести в `#` (facts-2026 §3) | — | нет | многофасетные URL |
| Фильтры со спросом | разрешить | index, свой title/H1/текст | да | «бренд + категория» |
| Внутренний поиск, пустые выдачи | закрыть или noindex | noindex; пустая выдача — 404 | нет | `/search?q=` |
| Пагинация | разрешить | index, self-canonical | первая — да, остальные по выбору | `?page=2` |
| Служебные (вход, корзина, кабинет, спасибо) | по ситуации | noindex | нет | `/login`, `/cart` |
| Устаревшее без замены | — | 404/410 | нет | снятые товары без аналога |
| Устаревшее с заменой | — | 301 на замену | нет (в sitemap — цель) | переименованные страницы |

Правило: чтобы поисковик увидел `noindex`, URL нельзя закрывать в robots.txt (facts-2026 §2). Чтобы сэкономить обход, `noindex` не помогает (facts-2026 §1).

## Проверки

| Что | Как проверить | Severity | Движок |
|---|---|---|---|
| robots.txt отдаёт 5xx или таймаут | `robots_check.py`: статус | critical | both |
| Googlebot/YandexBot закрыт целиком (`Disallow: /` в своей группе или в `*` без своей группы) | `robots_check.py`: доступ к главной | critical | both |
| Закрыты CSS/JS, нужные для рендера | доступ к ресурсам из `page_facts` | high | google |
| Важный URL закрыт robots.txt | таблица доступа | high | both |
| robots.txt больше лимита или содержит мусор после лимита | размер | medium | both |
| Своя группа `User-agent: Yandex`/`Googlebot` молча отменяет правила `*` | сравнение групп | medium | both |
| `Crawl-delay`, `Host`, `Noindex:` в robots.txt как будто работают | список директив + facts-2026 §1, §13 | low | both |
| Нет `Clean-param` для параметров-дублей при ориентире на Яндекс | параметры в ссылках/логах + robots | medium | yandex |
| YandexAdditional ожидаемо закрыт через `*` | группы robots (правило в references/yandex.md) | medium | yandex |
| sitemap не найден ни в robots.txt, ни по стандартному пути | `sitemap_check.py` | medium | both |
| В sitemap URL с noindex, 3xx, 4xx, чужой canonical | выборка ≤ 20 + `page_facts` | high | both |
| В sitemap http-URL, чужой хост, дубли | `sitemap_check.py` | medium | both |
| Файл sitemap сверх лимита, ошибка XML, не UTF-8 | `sitemap_check.py` | high | both |
| `lastmod` в будущем, одинаковый почти у всех, отстаёт от страницы | `sitemap_check.py` | low | google |
| Целевые страницы не в sitemap | группы × sitemap | medium | both |
| Рост «Просканирована, не проиндексирована» после релиза | разница выгрузок; класс quality — переотправка не поможет | high | google |
| Рост «Обнаружена, не проиндексирована» | класс discovery: внутренние ссылки, скорость сервера, бюджет | medium | google |
| Индексируются служебные или поисковые страницы | `site:` не годится как доказательство; выгрузки GSC/Вебмастера | medium | both |
| Фасеты порождают бесконечные комбинации | параметры в ссылках `page_facts`, логи (`logs.md`) | high | both |
| IndexNow-ключ не совпадает с хостом / не отдаётся 200 | `http_safe.py fetch <host>/<key>.txt` | low | yandex |

## Чего не делать

- Не удалять страницы из индекса через `Disallow` — URL может остаться без контента.
- Не ставить одновременно `Disallow` и `noindex` на одну группу, если цель — убрать из индекса.
- Не переотправлять в индекс страницы класса quality в надежде, что «Google передумает».
- Не править robots.txt и sitemap на сервере самому — только дифф и `approval_required: true`.
- Не открывать «всех AI-ботов» и не закрывать их скопом: решение по уровням из `references/ai-bots.yaml` и задаче владельца (`geo.md`).
- Не опираться на `site:` как на счётчик индекса.
- Не выдумывать число проиндексированных страниц: нет выгрузки — `null` и «нет данных».

## Выход

Находки по `templates/finding.schema.json` (`module: "indexing"`, `source_type`: robots / sitemap / gsc / webmaster / live_html). Плюс: таблица доступа ботов из `robots_check.py`, матрица групп URL с правилом и 3–5 проверенными примерами на группу, разница выгрузок по причинам с классами, черновик правок robots.txt/sitemap диффом.
