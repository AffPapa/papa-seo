# Из чего собран papa-seo

Исследование 24.10.2026, пакет 0.1.1. Здесь то, что стоит за `THIRD_PARTY_NOTICES.md`: как искали, у кого что взяли, что отложили и почему, какие «нормы» из чужих скилов не прошли проверку по первоисточникам. Подробные отчёты лежат у авторов пакета; в репозитории — выжимка.

Коммит донора — тот, на котором проверяли код (`source.lock.json`). Пометка «HEAD клона» — коммит записан по локальной копии; «не запинен» — снимок без git-метаданных.

## 1. Числа

| Что | Сколько |
|---|---|
| Репозиториев с кодом и текстами проверено | 105 (94 исходных + 11 из второго захода) |
| Вердикт безопасности | 🟢 40 · 🟡 56 · 🔴 9 (ещё один 🔴 по метаданным, без скачивания) |
| Вредоносного кода (эксфильтрация, `base64→exec`, бинарники, `postinstall`, чтение `~/.ssh`) | 0 |
| Фейковая сеть | 89 репозиториев на 89 аккаунтах, из них 17 с темой SEO; разобраны по метаданным |
| Ещё разобрано только по README | около 35 |
| Лицензии по 94 исходным | ✅ 71 · MIT только в README 10 · без лицензии/ARR/NC 9 · AGPL/CC BY-SA/фейк 4 |
| Доноров, чьи формулировки адаптированы | 23 |
| Источников идей без копирования | 16 |
| Де-AI редактура | 17 реализаций, почти все восходят к одной странице Wikipedia |
| Яндекс | закрыт у одного донора; `YandexAdditional` не упомянут ни в одном из 105 |
| Итог | один скил: роутер, 29 модулей, 9 скриптов на stdlib, 6 справочников, тесты с атаками |

## 2. Как проверяли

Только статический разбор. Свои сканеры на стандартной библиотеке, запуск `python3 -I` из отдельного каталога.

| Проверяли | Как |
|---|---|
| Автозапуск | hooks, settings, `plugin.json`, `.mcp.json`, install-скрипты, package-скрипты, Makefile, Docker, CI, симлинки (1 651, все внутри корня) |
| Сеть, секреты, окружение | вызовы сети, `os.environ`, удаление файлов, persistence, `exec`/`base64`, `curl \| sh`, обход разрешений, телеметрия |
| Невидимый Unicode | теги `U+E0000–E007F` и bidi-управление: нет нигде; ZWSP/ZWJ/BOM объяснены по контексту |
| Архивы | список содержимого без распаковки |
| Лицензии | LICENSE/NOTICE любой глубины, манифесты, поле `license` во frontmatter (460 SKILL.md) |
| Фейковая сеть | GitHub API: метаданные аккаунтов, деревья, коммиты, релизы |
| Факты 2026 | первоисточники: Google Search Central, web.dev, справка Яндекса, документация вендоров ботов, arXiv |
| Цены | страницы тарифов, 24.10.2026 |

Чего не делали:

- ни один скил, скрипт, установщик и MCP-сервер не запускался и не ставился; «лучший донор» значит лучший по устройству и фактам, а не по результату прогона;
- антивирус и песочницу не гоняли; релизы и бинарники не скачивали;
- звёзды не проверяли: эндпоинт старгейзеров отдаёт 404; накрутка — только по косвенным признакам;
- пакеты npm и PyPI, которые ставят скилы, с репозиториями не сверяли;
- файлы, которые скилы велят загрузить с чужих доменов, не открывали;
- цифры из чужих бенчмарков не перепроверяли.

## 3. Доноры: что взято

Формулировки адаптированы, в каждом файле шапка `Adapted from <owner>/<repo>@<sha7>`. Полные тексты лицензий — `licenses/`.

| Донор | Коммит | Лицензия | Что взято | Что не взято |
|---|---|---|---|---|
| [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) | 6be93f4 | MIT | `tech-audit`, `on-page`, `schema`, `performance`, `geo`, `semantics`, `serp`, `backlinks`, `ecommerce`, `international`, `programmatic`, `measure`; устройство `url_safety.py` → `http_safe.py` | `seo-flow` (CC BY 4.0), футер сообщества, `uninstall.sh` по маске `seo-*`, расширения с платными API |
| [calm-north/seojuice-skills](https://github.com/calm-north/seojuice-skills) | c1f633b | MIT | дерево диагностики → `tech-audit`; `migrate-site` → `migration`; `target-serp` → `serp`; `fix-linking` → `links` | «Pro Tip» с рекламой, «+15–30 % трафика» |
| [seo-skills/seo-audit-skill](https://github.com/seo-skills/seo-audit-skill) | fac4b75 | MIT | потолки балла при блокирующих условиях → `tech-audit` | npm CLI, ссылка на вендора в отчёте |
| [seo-skills/geo-audit-skill](https://github.com/seo-skills/geo-audit-skill) | 17fd0d2 | MIT | семантика robots по RFC 9309 → `indexing`, `robots_check.py`; фильтр инъекций в llms.txt → `geo` | `uv tool install` из PyPI |
| [mykpono/ultimate-seo-geo](https://github.com/mykpono/ultimate-seo-geo) | c92fdba | MIT | правдоподобие `lastmod`, классы причин → `indexing`; регион ссылки, PageRank → `links`; оговорки по логам → `logs` | тексты с «134–167 слов»; запись пароля в `~/.zshrc` |
| [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill) | 445c46c | MIT (два правообладателя) | вердикт по URL robots × meta × canonical × sitemap → `indexing`; hreflang в sitemap → `international`; разрезы логов → `logs`; сироты, анкоры → `links`; фасеты → `ecommerce` | `curl \| bash`, `--force` с `rm -rf` |
| [kostja94/marketing-skills](https://github.com/kostja94/marketing-skills) | b59bbde | MIT | типы страниц под noindex, «Crawled – not indexed» → `indexing`; сигналы сущности → `eeat` | `parasite-seo`, устаревшая schema, «~3,2×» |
| [iannuttall/seo-graph](https://github.com/iannuttall/seo-graph) | не запинен | MIT (код восходит к [jdevalk/seo-graph](https://github.com/jdevalk/seo-graph), MIT) | устойчивые `@id`, дедупликация, висячие ссылки `@graph` → `schema` | — |
| [iannuttall/seo](https://github.com/iannuttall/seo) | 69a8ea2 | Apache-2.0 | недельный diff индексации по URL и причине, «средняя позиция — среднее» → `measure` | имя, слоган, лого (товарные знаки); телеметрия по умолчанию |
| [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) | afa8da9 | MIT | «сначала поле, потом трасса», preload/fetchpriority → `performance` | — |
| [lionkiii/claude-seo-skills](https://github.com/lionkiii/claude-seo-skills) | e8347fc | MIT | гейт «проиндексирована + допущена к сниппету» → `geo`; вопросы people-first → `eeat` | 12 клонов claude-seo, `install.sh` поверх чужих каталогов, TLS выключен |
| [artwist-polyakov/polyakov-claude-skills](https://github.com/artwist-polyakov/polyakov-claude-skills) | 197190a | MIT | Вебмастер только на чтение, проверка интента → `yandex`, `semantics`; факт об отсутствии API «Видимости в Алисе» → `references/yandex` | скрейпинг Алисы по cookie; плагин `codex-review` |
| [inhouseseo/superseo-skills](https://github.com/inhouseseo/superseo-skills) | 9cf22cc | Apache-2.0 + NOTICE | `content-brief`, `expert-interview` → `brief`; `write-content` → `write`; тест «абзац мог бы стоять где угодно» → `deai`; свежесть и оригинал источника → `factcheck`; типы страниц → `references/page-types` | плотность 1–2 %, «5–15 % выдуманной статистики», объёмы слов |
| [nowork-studio/notfair-plugin](https://github.com/nowork-studio/notfair-plugin) | ed835f2 | MIT | порядок источников и фазы аудита ссылок → `backlinks` | облачный MCP, правка кампаний |
| [garrettjsmith/localseoskills](https://github.com/garrettjsmith/localseoskills) | 405ce20 | MIT | порядок локального аудита: профиль, NAP, справочники, отзывы → `local` | вендоры и ключи в URL, `curl \| bash` |
| [AgriciDaniel/claude-blog](https://github.com/AgriciDaniel/claude-blog) | 3544423 | MIT | «утверждение — проверенный источник или качественная формулировка» → `write`; профиль голоса по образцам → `voice`; уровни источника, эхо-кластеры → `factcheck` | `brain/` (все права защищены), `blog-notebooklm` (обход бот-детекции), платные Gemini-функции |
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | e85f3cb | MIT | режимы правки, проходы, тест «лучше или просто иначе» → `edit`; `[NEED: …]`, блоки страницы → `landing` | 66 JS-клиентов, `google-ads.js` с записью в кабинет, платные партнёры, удалённая инструкция |
| [coleschaffer/copywritingskills-rmbc](https://github.com/coleschaffer/copywritingskills-rmbc) | 8327d49 | MIT | «сначала аудит, потом правка по разделам» → `edit` | блок «Attribution» с партнёрской ссылкой, RMBC-баллы |
| [Nanako0129/sepia](https://github.com/Nanako0129/sepia) | fb06be7 | MIT | операции, калибровка, тест удаления и отката → `deai`; операция recreate → `edit`; голос внутри регистра → `voice` | — |
| [ilyautov/humanizer-ru](https://github.com/ilyautov/humanizer-ru) | 3621b1c | MIT | «удаляй, не дописывай», матрица регистров, факт-замок → `deai`, `factcheck`, `references/ru-style`; сравнение фактов до/после → `factdiff.py` | запрет тире; шрифты OFL; `uvx` из PyPI |
| [blader/humanizer](https://github.com/blader/humanizer) | 8c307f3 | MIT | только структура: сила признака, «когда не действовать» → `deai` | текст каталога (линия Wikipedia, CC BY-SA), примеры |
| [robpalmer99/claude-code-copywriting-skills](https://github.com/robpalmer99/claude-code-copywriting-skills) | 7dbfd61 | CC BY 4.0 | порядок ревью от стратегии к строке → `landing`; изменения помечены | — |
| [every-app/open-seo](https://github.com/every-app/open-seo) | 2d8236a | MIT | одна самодостаточная HTML, вердикт первым → `report` | облачный MCP, партнёрская ссылка DataForSEO, брендовый футер |

## 4. Только идеи, ни строки текста

Лицензия не позволяет копировать, или код донора не открывали, или брали одно наблюдение.

| Источник | Коммит | Лицензия | Идея | Где |
|---|---|---|---|---|
| [Horosheff/google-yandex-seo-skill](https://github.com/Horosheff/google-yandex-seo-skill) | bdd76f9 (HEAD клона) | MIT, правообладатель не владелец репо | раздельные находки Google и Яндекс, категории юридических сигналов; «поведенческие прокси» отвергнуты | `yandex` |
| [MYehia565/google-seo-agent-skills](https://github.com/MYehia565/google-seo-agent-skills) | 5336bcb (HEAD клона) | MIT | формат модуля, проверки магазина | `ecommerce` |
| [Illyism/seo-skills](https://github.com/Illyism/seo-skills) | a47acc9 (HEAD клона) | MIT только в README | «выдача как бриф», title/H1/slug об одном | `headlines` |
| [yabasha/copywrite-skill](https://github.com/yabasha/copywrite-skill) | не запинен | MIT только в README | уровни осведомлённости → тип заголовка | `headlines` |
| [Yaroslavle/seo-content-writer-claude-skill](https://github.com/Yaroslavle/seo-content-writer-claude-skill) | не запинен | MIT только в README | задача читателя до ключа | `brief` |
| [alenazaharovaux/share](https://github.com/alenazaharovaux/share) | не запинен | корневой нет | выбрать угол подачи до текста | `brief` |
| [milcheliquids-ship-it/seo-text-skill](https://github.com/milcheliquids-ship-it/seo-text-skill) | не запинен | нет | русские поля ТЗ; метрики рунета как оценка, не как факт | `brief`, `text-metrics`, `text_metrics.py` |
| [mazamaka/seo-skills-claude-code](https://github.com/mazamaka/seo-skills-claude-code) | 5cec59e (HEAD клона) | нет | `page_map.csv`, порог ≥ 3 общих URL | `semantics` |
| [affilino/ecommerce-seo-audit-skill](https://github.com/affilino/ecommerce-seo-audit-skill) | 76f313d (HEAD клона) | все права защищены | фасеты и логи | `ecommerce` |
| [Aboudjem/humanizer-skill](https://github.com/Aboudjem/humanizer-skill) | a58df06 | MIT | diff фактов после правки; формула балла не взята | `factdiff.py` |
| [flaqai/Awesome_SEO_Writing_Skill](https://github.com/flaqai/Awesome_SEO_Writing_Skill) | 7d30056 | MIT | карточка задачи с явными допущениями | `brief` |
| [smixs/humanizer-ru](https://github.com/smixs/humanizer-ru) | ff990df | MIT | ловить следы разметки ассистентов; регулярки написаны заново | `deai_scan.py` |
| [BrianRWagner/ai-marketing-claude-code-skills](https://github.com/BrianRWagner/ai-marketing-claude-code-skills) | не запинен | MIT только в README | 3–5 сырых образцов для голоса | `voice` |
| [tigerless-labs/seo-ops](https://github.com/tigerless-labs/seo-ops) | не открывался | нет | ростер ботов как данные с обоснованием; сами данные — из документации вендоров | `references/ai-bots` |
| [coleschaffer/dtc-copywriting-skills](https://github.com/coleschaffer/dtc-copywriting-skills) | не открывался | MIT, код с преамбулами не брать | дефицит и срочность только настоящие | `landing` |
| Wikipedia, «Signs of AI writing» | — | CC BY-SA 4.0 | признаки машинного текста как тема; каталог, формулировки и примеры свои | `deai` |

## 5. Не взяли и почему

Группы по причине. Одна строка — один репозиторий; если у репозитория несколько причин, он в первой подходящей группе.

### 5.1. Платные API и облачные MCP

Данные уходят через чужой сервер или без платного ключа скил не работает.

| Репозиторий | Что именно |
|---|---|
| [Ryze-AI-Adgent/open-seo-mcp-skills](https://github.com/Ryze-AI-Adgent/open-seo-mcp-skills) | плагин сам подключает удалённый MCP с OAuth к GSC/GA4/Ads; тарифы $89–1 499/мес |
| [irinabuht12-oss/marketing-skills](https://github.com/irinabuht12-oss/marketing-skills) | то же, над Ryze |
| [hyperfx-ai/marketing-skills](https://github.com/hyperfx-ai/marketing-skills) | облачный MCP, $49/мес; сценарий запуска рекламы на $300 в день |
| [seranking/seo-skills](https://github.com/seranking/seo-skills) | MCP SE Ranking; дописывает `settings.json`, `curl \| bash` с main |
| [cognyai/claude-code-marketing-skills](https://github.com/cognyai/claude-code-marketing-skills) | премиум отдаёт учётки GA4/GSC/Ads шлюзу |
| [sherotree/seo-agent-skills](https://github.com/sherotree/seo-agent-skills) | без DataForSEO не работает |
| [TheMattBerman/seo-kit](https://github.com/TheMattBerman/seo-kit) | DataForSEO, картинки через Replicate |
| [AgriciDaniel/jev-seo](https://github.com/AgriciDaniel/jev-seo) | содержимое страниц уходит в платный LLM-API |
| [mangollc/claude-seo-skill](https://github.com/mangollc/claude-seo-skill) | весь обход через Firecrawl, вход через браузер |
| [Bomx/distribb-skill](https://github.com/Bomx/distribb-skill) | $97/$495 в месяц; обмен ссылками в каждой статье; лицензии нет |
| [dageno-agents/seo-geo-content-engine](https://github.com/dageno-agents/seo-geo-content-engine) | SerpAPI; квота «5 цитируемых фраз с данными» |
| [weipanux/seo-geo-blog-writer](https://github.com/weipanux/seo-geo-blog-writer) | DataForSEO; без ключа выдаёт эвристические объёмы как данные; просит пароль в чат; CC BY-NC-SA |
| [TheCraigHewitt/seomachine](https://github.com/TheCraigHewitt/seomachine) | ключевые команды на DataForSEO; 25 скилов — копии coreyhaines31 |
| [ericosiu/ai-marketing-skills](https://github.com/ericosiu/ai-marketing-skills) | почти всё на платных API; outbound-скрипты шлют письма |
| [AminForou/mcp-gsc](https://github.com/AminForou/mcp-gsc) | `submit_sitemap` пишет в GSC без флага, полный scope `webmasters` |

### 5.2. Реклама и CTA внутри выдачи

| Репозиторий | Что именно |
|---|---|
| [OranAi-Ltd/orangeo-ai-visibility-skill](https://github.com/OranAi-Ltd/orangeo-ai-visibility-skill) | CTA с UTM в каждом отчёте |
| [zubair-trabzada/ai-marketing-claude](https://github.com/zubair-trabzada/ai-marketing-claude) | реклама сообщества; `curl \| bash` без пина |
| [NulightJens/humanizer-stack](https://github.com/NulightJens/humanizer-stack) | реклама сообщества; файл humanizer под CC BY-SA; покрыто sepia |
| [dageno-agents/seo-geo-audit](https://github.com/dageno-agents/seo-geo-audit) | реклама в README, своего мало |
| [nowork-studio/notfair-plugin](https://github.com/nowork-studio/notfair-plugin) (48 скилов) | в основном реклама; взят только порядок аудита ссылок |

У доноров из §3 футеры сообществ, «Pro Tip», партнёрские ссылки и платные партнёры вырезаны.

### 5.3. Обход CAPTCHA и бот-защиты

| Репозиторий | Что именно |
|---|---|
| [halilertekin/advanced-seo-mcp](https://github.com/halilertekin/advanced-seo-mcp) | Cloudflare Turnstile Ahrefs через платный CapSolver; файла лицензии нет |
| [mrgoonie/seo-insights-mcp-server](https://github.com/mrgoonie/seo-insights-mcp-server) | то же |
| [cnych/seo-mcp](https://github.com/cnych/seo-mcp), [egebese/dataseo-mcp](https://github.com/egebese/dataseo-mcp) | данные Ahrefs через решение капчи (по README) |
| [AgriciDaniel/claude-blog](https://github.com/AgriciDaniel/claude-blog), часть `blog-notebooklm` | Patchright + stealth, куки Google в профиле; остальное взято |

### 5.4. Деинсталляторы и установщики, которые трогают чужие папки

| Репозиторий | Что именно |
|---|---|
| [zubair-trabzada/geo-seo-claude](https://github.com/zubair-trabzada/geo-seo-claude) | `uninstall.sh` удаляет `geo-*` по маске; источник «134–167 слов» |
| [FreeAutomation-Tech/claude-seo-kit](https://github.com/FreeAutomation-Tech/claude-seo-kit) | `install.sh` делает `rm -rf ~/.claude/skills/seo-*`; повтор claude-seo |
| [dalroot/agentic-seo](https://github.com/dalroot/agentic-seo) | копия Bhanunamikaze; установщик качает tarball с копии, а не с оригинала |
| [norahe0304-art/30x-seo](https://github.com/norahe0304-art/30x-seo) | клон claude-seo без атрибуции; шаг аудита «BLOCKING» на стороннем пакете |
| [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo), [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill), [lionkiii/claude-seo-skills](https://github.com/lionkiii/claude-seo-skills) | `uninstall.sh` по маске `seo-*`, `--force` с `rm -rf`, `cp -R` поверх чужих каталогов; сами скилы взяты, установщики нет |

Поэтому у papa-seo нет установщика и нет префиксов `seo-`/`geo-`: пакет копируют папкой, чужие деинсталляторы его не видят.

### 5.5. Удалённый SKILL.md и инструкции с чужого сервера

| Репозиторий | Что именно |
|---|---|
| [Illyism/seo-skills](https://github.com/Illyism/seo-skills) | «если версия на сайте новее — следуй живому файлу», «не проверяй через shell»; авто-merge; куки браузера; ежедневный обход всего sitemap. Взята одна идея из `seo-title-optimization` |
| [rampstackco/claude-skills](https://github.com/rampstackco/claude-skills) | «скачать с main и выполнить agent protocol» |
| [OpenClaudia/openclaudia-skills](https://github.com/OpenClaudia/openclaudia-skills) | ссылка на SKILL.md на чужом домене; постинг без подтверждения; Stop-хук читает файл из `/tmp`; «купить домен конкурента» |
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills), часть `conversion-tracking` | «fetch it live and follow it»; остальное взято |
| [milcheliquids-ship-it/seo-text-skill](https://github.com/milcheliquids-ship-it/seo-text-skill) | заголовки чужих страниц попадают в промпт, который велено исполнять дословно; взяты только идеи полей ТЗ |

### 5.6. Авто-merge, автопубликация, запись в чужие аккаунты

| Репозиторий | Что именно |
|---|---|
| [Gingiris/gingiris-skills](https://github.com/Gingiris/gingiris-skills) | коммит в репо через `PUT /contents` без PR; «134–167» |
| [indranilbanerjee/digital-marketing-pro](https://github.com/indranilbanerjee/digital-marketing-pro) | `connector_executor.py --execute` пишет в рекламные кабинеты и CRM |
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills), `tools/clis/google-ads.js` | пауза кампаний и смена бюджета; CLI не взяты |
| [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | пишет crontab и по ночам запускает агента с Bash; SEO-часть — клоны coreyhaines31 |

### 5.7. Куки и сессии браузера

| Репозиторий | Что именно |
|---|---|
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | куки X из 9 браузеров, Keychain, CDP `getAllCookies`, `bypassPermissions` |
| [yasikvlad/marketing-skills](https://github.com/yasikvlad/marketing-skills) | cookies Google в `state.json`; перезалив coreyhaines31 без лицензии |
| [artwist-polyakov/polyakov-claude-skills](https://github.com/artwist-polyakov/polyakov-claude-skills), `alice.sh` | cookie `Session_id` Яндекса; плагин `codex-review` исполняет `config.env` из любого репо; остальное взято |

### 5.8. Хуки на каждый вызов, правка настроек

| Репозиторий | Что именно |
|---|---|
| [aaron-he-zhu/aaron-marketing-skills](https://github.com/aaron-he-zhu/aaron-marketing-skills) | хук на 7 событий, fail-closed; идея veto-проверок пересказана |
| [agencia-conversion/agentic-seo-skills](https://github.com/agencia-conversion/agentic-seo-skills) | сторонний JS на странице ввода ключей; «не показывать пользователю команды» |
| [imgompanda/fireauto](https://github.com/imgompanda/fireauto) | хуки SessionStart/PostToolUse/Stop, ~17 МБ wasm; про SEO один скил |
| [Aluxads/claude-skills](https://github.com/Aluxads/claude-skills) | хук UserPromptSubmit; организации 18 дней, 0 ★ |
| [aleclindz/seo-skill-bench](https://github.com/aleclindz/seo-skill-bench) | харнесс с `acceptEdits` и Bash; идея фикстуры с ловушками взята в `evals/` |

### 5.9. Фейковая сеть

89 репозиториев на 89 аккаунтах. Нагрузки сегодня нет; отдельные аккаунты сети отрабатывали атаки на GitHub Actions и выложили бинарник под чужим именем. Признаки, по которым сеть видна без имён:

- аккаунты созданы в один день за два часа, у каждого в тот же день пустой репозиторий со случайным именем из 8 букв;
- репозитории созданы за четыре минуты, два коммита: «Initial commit» и косметический через ~55 минут;
- имя `<аккаунт>/rNN-<известный-репо>-<домен>`: 20 известных репозиториев × 5 тем (security, ecommerce, seo, devops, datascience);
- звёзды 37–73 при нуле watchers; подписчиков 0 у 87 из 89;
- 18 файлов, ~71 КБ, только markdown; бейдж «License MIT» без файла LICENSE; `name` в SKILL.md не совпадает с именем репо;
- команды велят модели рисовать прогресс и цифры, которых не было;
- релизов и тегов нет.

Чек-лист для любого чужого скила, по той же проверке:

1. Аккаунт создан пачкой с другими, 0 подписчиков, рядом пустой репозиторий со случайным именем.
2. Много звёзд при 0 watchers и 0 issues; у живых проектов 100–300 звёзд на одного watcher.
3. Имя = номер + чужое имя, описание «derived from <awesome-list>»; бейдж лицензии без файла.
4. В README ZIP, `releases/latest/download`, installer, «скопируйте команду в Terminal».
5. Велит загрузить удалённый SKILL.md или «агентский протокол» и предпочесть его локальному; просит не проверять и не сообщать пользователю.
6. `curl … | bash` с main, `npm i -g`, `pip install` без пина, `--cookies-from-browser`, ключи в чат.
7. `plugin.json` или `.mcp.json` подключает удалённый MCP с OAuth к вашим аккаунтам.
8. Теги `U+E0000–E007F` и bidi-управление в файлах.
9. «merge when the build passes», автопостинг, рекламный бюджет без подтверждения.
10. Прогресс-бары и метрики без источника; `uninstall.sh` по маске; байткод и минифицированный JS без исходника.

### 5.10. Лицензия не позволяет или её нет

| Репозиторий | Что именно |
|---|---|
| [ilien-dev/quiron](https://github.com/ilien-dev/quiron) | AGPL-3.0 + условие 7(b) |
| [yaojingang/GEOHub](https://github.com/yaojingang/GEOHub) | AGPL-3.0, включая инструкции скилов |
| [jaredrhod/ai-marketing-skills](https://github.com/jaredrhod/ai-marketing-skills) | CC BY-SA 4.0 |
| [WordPress/agent-skills](https://github.com/WordPress/agent-skills) | GPL-2.0+, другой стек |
| [g-battaglia/mcp-seo](https://github.com/g-battaglia/mcp-seo) | MIT и AGPL в одном коммите; TLS выключен |
| [ccforseo/seo-claude-code-skills](https://github.com/ccforseo/seo-claude-code-skills) | лицензии нет; `curl \| bash`; FAQ/HowTo как rich results |
| [SNLabat/SEO-GEO-AEO-Skill](https://github.com/SNLabat/SEO-GEO-AEO-Skill) | лицензии нет |
| anthropics/skills: docx, pdf, pptx, xlsx | проприетарные; формат SKILL.md — открытый стандарт |
| один репозиторий фейковой сети | бейдж MIT без файла, автор не установлен |

### 5.11. Клоны и устаревшие факты

| Репозиторий | Что именно |
|---|---|
| [boraoztunc/skills](https://github.com/boraoztunc/skills), [davidpc007/openclaw-marketing-skills](https://github.com/davidpc007/openclaw-marketing-skills) | копии coreyhaines31; у второго 1 129 форков при 171 ★ |
| [seoskillsai/seo-skills-ai](https://github.com/seoskillsai/seo-skills-ai), [hmzainjamil/geo-seo-claude](https://github.com/hmzainjamil/geo-seo-claude), [ninryt/seo-analysis-skill](https://github.com/ninryt/seo-analysis-skill), [borghei/Claude-Skills](https://github.com/borghei/Claude-Skills) | ребрендинг без форка |
| [aaron-he-zhu/seo-geo-claude-skills](https://github.com/aaron-he-zhu/seo-geo-claude-skills) | 20 заглушек «has moved» |
| [AgriciDaniel/chatgpt-seo](https://github.com/AgriciDaniel/chatgpt-seo) | порт claude-seo тем же автором; методики не дублировали |
| [huifer/claude-code-seo](https://github.com/huifer/claude-code-seo) | FID и FAQ как нормы |
| [metawhisp/best-aeo-skill](https://github.com/metawhisp/best-aeo-skill) | FAQPage как «главная поверхность AI», открывает 27 ботов разом |
| [199-biotechnologies/claude-skill-seo-geo-optimizer](https://github.com/199-biotechnologies/claude-skill-seo-geo-optimizer) | «40–60 слов»; идея эндпоинтов IndexNow пересказана |
| [numen-tech/slopornot](https://github.com/numen-tech/slopornot) | переписывание до нужной оценки детектора |
| [Auriti-Labs/geo-optimizer-skill](https://github.com/Auriti-Labs/geo-optimizer-skill) | `pip install` без пина; имена — товарные знаки; идея уровней ботов пересказана |
| [JeffLi1993/seo-audit-skill](https://github.com/JeffLi1993/seo-audit-skill) | SSRF-защита пропускает при ошибке DNS |
| [Thibaultbm/claude-seo-geo](https://github.com/Thibaultbm/claude-seo-geo) | TLS выключен, полный обход сайта; идеи в 0.1.x не вошли |
| [jdevalk/skills](https://github.com/jdevalk/skills), [gaguero/seo-agent-skills](https://github.com/gaguero/seo-agent-skills), [muryulia/google-search-console-mcp](https://github.com/muryulia/google-search-console-mcp) | чистые, рекомендованы вторым заходом; в 0.1.x не вошли, вопрос открыт |

## 6. Мифы, которые не взяли

Проверено по первоисточникам 24.10.2026.

| Утверждение в скилах | Вердикт | Первоисточник |
|---|---|---|
| «Окно цитируемости 134–167 слов» (Princeton, «Bortolato 2025») | ❌ первоисточника нет; в статье Princeton длины пассажа нет; у Ahrefs корреляция длины с цитированием в AIO 0,04; Google: «no ideal page length» | [arxiv.org/abs/2311.09735](https://arxiv.org/abs/2311.09735), [ahrefs.com/blog/short-vs-long-content-in-ai-overviews](https://ahrefs.com/blog/short-vs-long-content-in-ai-overviews), [ai-optimization-guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide) |
| «Прямой ответ 40–60 слов под H2» | ❌ эвристика старых разборов featured snippets, в 21 репозитории; как правило редактуры годится, как метрика нет | первоисточника нет |
| FAQ rich results | ✅ не показываются с 07.05.2026; в 2023 ограничены гос- и медсайтами; разметка не вредит | [faqpage](https://developers.google.com/search/docs/appearance/structured-data/faqpage), [search/updates](https://developers.google.com/search/updates) |
| HowTo rich results | ✅ убраны 13.09.2023 | [howto-faq-changes](https://developers.google.com/search/blog/2023/08/howto-faq-changes) |
| llms.txt влияет на Google | ❌ «Google Search itself doesn't use them», «will neither harm nor help»; у Яндекса упоминаний нет | [ai-optimization-guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide) |
| «FID < 100 мс» | ❌ INP с 12.03.2024: LCP ≤ 2,5 с, INP ≤ 200 мс, CLS ≤ 0,1, 75-й перцентиль | [inp-cwv-march-12](https://web.dev/blog/inp-cwv-march-12), [defining-core-web-vitals-thresholds](https://web.dev/articles/defining-core-web-vitals-thresholds) |
| «≥ 30–40 % уникального текста» для шаблонных страниц | ❌ у Google такой цифры нет, есть политика scaled content abuse | Google Search Central, спам-политики |
| Плотность ключа 1–2 % как фактор | ❌ ориентир рунет-сервисов; в пакете только отчёт, не гейт | — |
| Flesch 60–70 для русского | ❌ формула на английских слогах | — |
| Princeton GEO «+30–115 %» | ◐ в аннотации «до 40 %»; 115 % — частный случай на синтетическом движке 2023 | [arxiv.org/abs/2311.09735](https://arxiv.org/abs/2311.09735) |
| «92 % ссылок AIO из топ-10» | ◐ у Ahrefs 76 %; 13,7 % совпадений по URL верно | [ai-overviews-vs-ai-mode](https://ahrefs.com/blog/ai-overviews-vs-ai-mode), [search-rankings-ai-citations](https://ahrefs.com/blog/search-rankings-ai-citations) |
| «Монолитные скилы хуже атомарных» (бенчмарк) | ✅ цифры, ❌ вывод: одна фикстура, 3 прогона, разброс ±8, лидер — продукт автора бенча | [aleclindz/seo-skill-bench](https://github.com/aleclindz/seo-skill-bench) |
| Google-Extended имеет User-Agent и влияет на AI Overviews | ❌ только токен robots.txt; на Search не влияет; AIO подчиняются Googlebot и snippet-директивам | [google-common-crawlers](https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers), [ai-features](https://developers.google.com/search/docs/appearance/ai-features) |
| «Applebot-Extended — только обучение» | ◐ сам не краулит; обычный Applebot тоже связан с AI-функциями | [support.apple.com/en-us/119829](https://support.apple.com/en-us/119829) |
| `User-agent: *` закрывает YandexAdditional | ❌ не действует, нужна своя группа; токены ограничивают показ в ответах YandexGPT и Алисы | [check-yandex-robots](https://yandex.ru/support/webmaster/ru/robot-workings/check-yandex-robots) |
| Host и Crawl-delay у Яндекса | ❌ Host не учитывается с марта 2018, Crawl-delay с 22.02.2018; Clean-param работает | [robots-txt](https://yandex.ru/support/webmaster/ru/controlling-robot/robots-txt) |
| Wordstat API бесплатный | ❌ GetTop и GetDynamics — 20 ₽ за 1 000 запросов | [search-api/pricing](https://aistudio.yandex.ru/docs/ru/search-api/pricing) |
| «Поведенческие прокси Яндекса» по TTFB и размеру HTML | ❌ это технические эвристики, не поведенческие факторы | — |

Не проверялись: «Soft Navigations в Chrome 151», «55,6 % origin проходят CWV», корреляции Ahrefs «YouTube 0,737 против DR 0,266» — их автор сам пометил неперепроверенными.

## 7. Чего нет у доноров

| Пробел | Почему | Где в papa-seo |
|---|---|---|
| YandexAdditional / YandexAdditionalBot | 0 упоминаний в 105 репозиториях; `*` на них не действует | `references/ai-bots.yaml`, `robots_check.py`, `modules/yandex.md` |
| Robots с семантикой Яндекса | RFC-парсеры не знают Clean-param и игнор Host/Crawl-delay | `robots_check.py` |
| Вебмастер в одной модели с GSC | недельный diff есть только для GSC | `modules/measure.md`, `modules/yandex.md` |
| Разметка, которую понимает Яндекс | модули schema написаны под Google | `modules/schema.md`, `references/yandex.md` |
| Коммерческие и юридические сигналы рунета | только эвристики одного донора | `modules/yandex.md` |
| Цитирование в Нейро и Алисе | скилов нет | `modules/geo.md`: ручной протокол, без cookie |
| Подлинность ботов в логах | нет ни для Google, ни для Яндекса | `bot_verify.py`, `modules/logs.md` |
| Аудит без обхода сайта | массовый обход ежедневно из sitemap, 5 параллельных запросов, полный краул | одна страница, до 20 URL с паузой, корпус или CSV краулера |
| Русские метрики текста локально | только клиенты платных API | `text_metrics.py` |
| Русский слой де-AI | у sepia нет русского файла | `references/ru-style.md` |
| Гейт «проверь, что дефект есть» | главная ловушка бенчмарка у всех участников | `policies/evidence.md`, `templates/finding.schema.json` |
| Переезд с сохранением склейки в Яндексе | нет ни у кого | `modules/migration.md` |

## 8. Что осталось открытым

- Скилы доноров ни разу не запускались; сравнение «модель без скила / со скилом» на `evals/` не прогонялось.
- Накрутка звёзд не проверена напрямую.
- npm- и PyPI-пакеты, которые ставят чужие скилы, с репозиториями не сверены.
- Четыре чистых репозитория второго захода (гейты качества, read-only GSC, спецификации типов страниц, чек-листы) в 0.1.x не вошли.
- Эффект llms.txt у Яндекса неизвестен.
