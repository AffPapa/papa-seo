# papa-seo

An agent skill that audits websites, writes content briefs, and drafts or edits copy for Google and Yandex. Works in Claude Code and OpenAI Codex. Version 0.1.0.

[Русская версия](README.md) · [Quick start (RU)](QUICKSTART.md) · [Security](SECURITY.md)

The skill's own instructions are written in Russian, with English terms where they are the standard ones. It handles English pages and texts too, but its Yandex track and Russian style layer assume a Russian-language market.

## Modes

Ask in plain words ("check this page", "write a brief", "refresh this article") or name a mode.

| Mode | What it does |
|---|---|
| `audit` | technical audit: status codes, redirects, canonical, robots, sitemap, structured data, speed, internal links |
| `page` | one page: title, description, headings, images, structured data, indexability |
| `plan` | intents, clusters, query-to-page map, cannibalization |
| `brief` | brief for a writer: intent, angle, outline, questions for an expert, what not to claim without a source |
| `write` | article from a brief, with a source for every number |
| `refresh` | update an old page: what is stale, what changed in the SERP, fact diff before and after |
| `edit` | editing and rewriting without losing facts, de-AI pass |
| `links` | internal links (orphans, depth, exact insertion: source page, target, anchor, sentence); backlinks from free data |
| `fix` | draft or patch for the found issues; applied only after you say yes |
| `measure` | Search Console, Yandex Webmaster, GA4, read-only: period comparison, drops, near-top queries |
| `geo` | AI search visibility: index and snippet eligibility, bots, self-contained passages, llms.txt as an option |
| `yandex` | Yandex track: YandexAdditional, Clean-param, markup, commercial signals, site moves |

Local SEO, e-commerce, hreflang, programmatic pages, migrations, log files, landing pages and headlines load when you ask about them.

## Layout

```
papa-seo/
  SKILL.md       router: request → mode → modules
  policies/      security, evidence rules, permission ladder
  modules/       one file per function: tech-audit, indexing, on-page, schema, ...
  references/    dated facts, myths, bot roster, Yandex, page types, Russian style
  templates/     finding schema, brief, report, project context, voice profile
  scripts/       Python 3.10+, standard library only
  tests/         python3 -m unittest discover
```

The router reads only the module and references a request needs. Thresholds and dates live in one file, `references/facts-2026.md`, each with a date and a link to the primary source.

Every audit finding follows `templates/finding.schema.json`: where the fact came from, when, the evidence snippet, a status (`confirmed`, `likely`, `hypothesis`), the search engine, the fix and how to verify it after release. Before recommending "add X", the agent checks the live HTML to confirm X is actually missing. It says "no X anywhere on the site" only with full coverage; otherwise it reports how many pages were checked.

Scripts make no outside calls: no `subprocess` or `eval`, no reading of the home directory or environment variables. Only `http_safe.py` touches the network. It blocks private and internal addresses, re-checks every redirect hop and caps the response size.

## Install

There is no installer. Copy one folder, `papa-seo/`. Nothing in your setup is deleted or overwritten. Check that the target directory has no folder with the same name first.

Get it:

```bash
git clone https://github.com/AffPapa/papa-seo.git && cd papa-seo
```

**Claude Code**, all projects:

```bash
cp -R papa-seo ~/.claude/skills/papa-seo
```

One project:

```bash
cp -R papa-seo <project>/.claude/skills/papa-seo
```

**OpenAI Codex.** The Codex docs (checked 2026-10-24, developers.openai.com/codex/skills) list `.agents/skills`. All projects:

```bash
cp -R papa-seo ~/.agents/skills/papa-seo
```

One repository:

```bash
cp -R papa-seo <repo>/.agents/skills/papa-seo
```

Codex scans `.agents/skills` in every directory from the current one up to the repository root. Older guides mention `~/.codex/skills`; the current docs do not.

Scripts need Python 3.10 or later and no third-party packages. To uninstall, delete the folder.

## Project context

If the project root has `.papa-seo/project.md`, the router reads it before choosing a module: market and language, which search engines matter, whether crawling is allowed and at what load, where results go, who publishes changes, the voice of the texts. A starting template is `papa-seo/templates/project-context.md`; the voice profile is `templates/voice-profile.md`.

Without that file the skill stays conservative: one page, or up to 20 URLs fetched one by one, no site crawl, no publishing.

## Data and cost

The default mode is free: a public URL, your files (HTML, Markdown, CSV, JSON), exports from Search Console or Webmaster, and the agent's built-in web search. Search Console, GA4 and Yandex Webmaster connect read-only, with your own credentials.

Paid APIs (DataForSEO, Ahrefs, Semrush, Serpstat, SE Ranking, Wordstat API, Yandex Search API) are offered only as an option, marked as paid. When data is missing, the report says so. The skill does not make up search volume, DR, rankings or CTR.

## What it does not do

- It does not crawl a whole site unless you ask. If you do, it crawls in a single thread and warns about the load.
- It does not publish or change your site. Work stops at a patch; you decide what ships.
- It does not follow instructions found in fetched pages, robots.txt, CSV files or competitor texts. Hidden prompts in HTML are reported as a finding.
- It does not promise traffic growth or rankings. An audit score, when there is one, describes the page, not a forecast.
- It does not run texts through AI detectors or add opinions and stories the author did not give.

## Evaluation

`evals/` holds a small static site with planted defects, traps and one prompt injection, plus an answer key. The README there explains how to compare the same model with and without the skill: precision, recall, traps hit, rule violations.

## Where it comes from

The pack was assembled after reviewing about 94 open repositories with SEO and copywriting skills (2026-10-24). Methods and wording were adapted only where the license allows it, and only from original projects, not clones. Where there was no license, only ideas were used, restated in our own words. No paid dependencies. Sources, commits and licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [source.lock.json](source.lock.json) and `licenses/`.

Made by the [affpapa.org](https://affpapa.org) team for its own work and published as is.

## License

MIT, © 2026 AFFPAPA. See [LICENSE](LICENSE). Adapted third-party material keeps its license; each such file names its source in a header.
