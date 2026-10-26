# papa-seo — SEO skill for Claude Code and Codex

An SEO, GEO and content skill for Claude Code and OpenAI Codex: audits a page or a site for Google, Yandex and AI search, writes briefs and articles, and de-AIs text.

[Русская версия](README.md) · [Quick start (RU)](QUICKSTART.md) · [Security (RU)](SECURITY.md) · [Changelog (RU)](CHANGELOG.md) · [Project page](https://affpapa.org/papa-seo)

It isn't a hosted SEO tool. The skill runs inside your coding agent, reads the live HTML and the exports you give it, and attaches evidence to every claim it makes about your site.

- Audits one page or a sample of URLs: indexability, canonical, robots.txt, sitemaps, structured data, Core Web Vitals, internal links. Each finding quotes the HTML and carries a status: `confirmed`, `likely` or `hypothesis`.
- Has a separate Yandex track (YandexAdditional, Clean-param, Yandex Webmaster, commercial signals).
- For AI search, checks whether a page can show up in ChatGPT search, Perplexity, Google AI Overviews and Yandex Alice AI answers, which bots robots.txt lets in and whether a WAF blocks them. llms.txt is treated as optional.
- Writes content briefs and sourced articles, refreshes old pages, edits and de-AIs Russian and English text. `factdiff.py` shows which numbers, dates and links an edit dropped.
- Reads Google Search Console, Yandex Webmaster and GA4 exports: period comparison, traffic drops, striking-distance queries.
- Free and MIT-licensed. No paid APIs; the scripts use only the Python standard library. No crawling by default: one page, or up to 20 URLs fetched one by one with a pause.

The skill's own instructions are in Russian, with standard English terms. It works on English sites and texts too, but the Yandex track and the Russian style layer assume a Russian-language market.

## Install with one prompt

Copy the prompt as is and hand it to your agent: Claude Code, Codex, Cursor, Copilot, Gemini CLI or anything else that can touch files. It works out where it's running, puts the `papa-seo/` folder in the right place, verifies it and reports back. It deletes and overwrites nothing: if a folder with that name is already there, it stops and asks.

```text
Install the papa-seo skill for me: SEO audits, Yandex, AI search and SEO copy, MIT, https://github.com/AffPapa/papa-seo. Go step by step. Delete nothing, overwrite nothing.

1. Work out where you are running. By folders: ~/.claude means Claude Code; ~/.codex or ~/.agents means Codex; ~/.cursor or .cursor in the project means Cursor; ~/.codeium/windsurf or .windsurf means Windsurf; ~/.copilot or .github/skills means GitHub Copilot; ~/.gemini means Gemini CLI; ~/.openclaw means OpenClaw; ~/.hermes means Hermes. If you already know what you are, that beats the folders. If you have no file system (ChatGPT, claude.ai), stop and say so: those are set up differently, see the repository README.

2. Get the pack: git clone https://github.com/AffPapa/papa-seo.git into a temporary folder. No git? Download https://github.com/AffPapa/papa-seo/archive/refs/heads/main.zip and unpack it; inside the archive the skill folder is at papa-seo-main/papa-seo/. You need only the papa-seo/ folder (the one with SKILL.md); don't copy anything else from the clone.

3. Where it goes, so that the result is <path>/papa-seo/SKILL.md. Claude Code: ~/.claude/skills/ for all projects or <project>/.claude/skills/ for one. Codex: ~/.agents/skills/ or <project>/.agents/skills/. Cursor: <project>/.agents/skills/ or ~/.cursor/skills/. Windsurf: <project>/.windsurf/skills/ or ~/.codeium/windsurf/skills/. Copilot: <project>/.github/skills/ or ~/.copilot/skills/. Gemini CLI: ~/.gemini/skills/ or <project>/.gemini/skills/. OpenClaw: <workspace>/skills/ or ~/.openclaw/skills/. Hermes: ~/.hermes/skills/. If this machine has both ~/.claude and ~/.agents (or ~/.codex), put a copy in both ~/.claude/skills/papa-seo and ~/.agents/skills/papa-seo: Claude Code doesn't read .agents/skills and Codex doesn't read .claude/skills. If you can't tell the host but do have files, put two copies in the project: <project>/.agents/skills/papa-seo and <project>/.claude/skills/papa-seo. If I didn't say global or project, ask.

4. Before copying, check that papa-seo does not already exist at the target. If it does, stop and ask; touch nothing. Copy the whole folder (cp -R). Leave other files alone. Afterwards you may remove the temporary clone or archive, and only that.

5. Verify each location: test -f <path>/papa-seo/SKILL.md && python3 <path>/papa-seo/scripts/page_facts.py --help. Python 3.10 or newer, no third-party packages.

6. Triggering. Claude Code, Codex, Cursor, Windsurf, Copilot, OpenClaw and Hermes pick the skill up on their own from the description in SKILL.md; Gemini CLI proposes it and I confirm activation. If you are installing into a project whose root already has CLAUDE.md, AGENTS.md or an agent rules file, append one line without removing anything: "For SEO tasks, page checks and SEO copy, use the papa-seo skill (folder <path>/papa-seo)". Don't create a new file just for that line.

7. Finish with a report: where it went (full paths); how to call it (Claude Code, Cursor, Copilot and Hermes: /papa-seo; Codex and OpenClaw: $papa-seo; Windsurf: @papa-seo; or just ask "check the page https://…"); how to remove it (rm -rf <path>/papa-seo, plus delete the line you added to the rules; in Codex it can also be switched off with [[skills.config]] enabled = false in ~/.codex/config.toml, in Gemini CLI with gemini skills uninstall papa-seo). If anything doesn't add up at some step, say what exactly and don't do the next one.
```

For an agent with file access: Claude Code, Codex, Cursor, Copilot, Gemini CLI, Windsurf, OpenClaw, Hermes. Claude Code and Codex were checked by hand (2026-10-26); the other hosts follow their own documentation. ChatGPT and claude.ai work differently, see below.

If you know your host, the short versions:

<details>
<summary>Claude Code, all projects</summary>

```text
Install the papa-seo skill for all my projects. Run git clone https://github.com/AffPapa/papa-seo.git into a temporary folder and copy the papa-seo/ folder from the clone to ~/.claude/skills/papa-seo. If ~/.claude/skills/papa-seo already exists, stop and ask; delete or overwrite nothing else. Verify: test -f ~/.claude/skills/papa-seo/SKILL.md && python3 ~/.claude/skills/papa-seo/scripts/page_facts.py --help. Remove the temporary clone. Finish with the path, how to call it (/papa-seo or a plain SEO request) and how to remove it (rm -rf ~/.claude/skills/papa-seo).
```

Triggers on its own from the SKILL.md description: Claude Code keeps every skill's description in context. List them with /skills. No line in CLAUDE.md needed. Claude Code cloud sessions and Cowork don't read ~/.claude/skills; for those see claude.ai.

</details>

<details>
<summary>Claude Code, one project</summary>

```text
Install the papa-seo skill into this project only. Run git clone https://github.com/AffPapa/papa-seo.git into a temporary folder and copy the papa-seo/ folder from the clone to <repository root>/.claude/skills/papa-seo. If that folder already exists, stop and ask; leave other files alone. Verify: test -f .claude/skills/papa-seo/SKILL.md && python3 .claude/skills/papa-seo/scripts/page_facts.py --help. If the root has a CLAUDE.md, append the line "For SEO tasks, page checks and SEO copy, use the papa-seo skill (.claude/skills/papa-seo)" without removing anything. Remove the clone. Finish with the path, how to call it and how to remove it.
```

Claude Code finds .claude/skills from any folder up to the repository root and picks it up without a restart; a brand-new skills root needs /reload-skills. The CLAUDE.md line isn't required by the docs; it does no harm.

</details>

<details>
<summary>OpenAI Codex: CLI, IDE, desktop</summary>

```text
Install the papa-seo skill. Run git clone https://github.com/AffPapa/papa-seo.git into a temporary folder and copy the papa-seo/ folder from the clone to ~/.agents/skills/papa-seo (all projects) or <repository root>/.agents/skills/papa-seo (this one); if I didn't say which, ask. If the folder already exists, stop and ask; delete or overwrite nothing. Verify: test -f <path>/papa-seo/SKILL.md && python3 <path>/papa-seo/scripts/page_facts.py --help. If installing into a project that has an AGENTS.md at the root, append the line "For SEO tasks, page checks and SEO copy, use the papa-seo skill (.agents/skills/papa-seo)". Remove the clone. Finish with the path, how to call it ($papa-seo or /skills) and how to remove it.
```

Codex reads .agents/skills in the current folder and every parent up to the repository root; it does not read .claude/skills (checked 2026-10-26 with codex debug prompt-input). Triggers from the description; if it doesn't show up, restart Codex. Disable without deleting: [[skills.config]] path = ".../papa-seo/SKILL.md", enabled = false in ~/.codex/config.toml. Codex cloud (web) says nothing about skills in its docs.

</details>

<details>
<summary>Cursor</summary>

```text
Install the papa-seo skill. Run git clone https://github.com/AffPapa/papa-seo.git into a temporary folder and copy the papa-seo/ folder from the clone to <repository root>/.agents/skills/papa-seo (this project) or ~/.cursor/skills/papa-seo (all projects); if I didn't say which, ask. If the folder already exists, stop and ask; delete or overwrite nothing. Verify: test -f <path>/papa-seo/SKILL.md && python3 <path>/papa-seo/scripts/page_facts.py --help. Remove the clone. Finish with the path, how to call it (/papa-seo in the Agent chat) and how to remove it (rm -rf <path>/papa-seo).
```

Cursor reads .cursor/skills and .agents/skills in the project, ~/.cursor/skills and ~/.agents/skills globally, and .claude/skills for compatibility (Cursor docs, 2026-10-26). Skills are discovered at startup, so restart Cursor after copying.

</details>

<details>
<summary>Windsurf, GitHub Copilot, Gemini CLI, OpenClaw and other .agents/skills hosts</summary>

```text
Install the papa-seo skill. Run git clone https://github.com/AffPapa/papa-seo.git into a temporary folder and copy the papa-seo/ folder from the clone to <repository root>/.agents/skills/papa-seo. If you have a skills folder of your own, put a second copy there: Windsurf: .windsurf/skills/ or ~/.codeium/windsurf/skills/; GitHub Copilot: .github/skills/ (the only option for the cloud agent) or ~/.copilot/skills/; Gemini CLI: ~/.gemini/skills/ or .gemini/skills/; OpenClaw: <workspace>/skills/ or ~/.openclaw/skills/; Hermes: ~/.hermes/skills/. If a target folder already exists, stop and ask; delete or overwrite nothing. Verify: test -f <path>/papa-seo/SKILL.md && python3 <path>/papa-seo/scripts/page_facts.py --help. If the project root has an AGENTS.md or an agent rules file, append the line "For SEO tasks, page checks and SEO copy, use the papa-seo skill (<path>/papa-seo)". Remove the clone. Finish with the paths, how to call it and how to remove it.
```

Per their own docs, .agents/skills is read by Codex, Cursor, Windsurf, Copilot, Gemini CLI and OpenClaw; Hermes reads only ~/.hermes/skills. Calling it: Windsurf @papa-seo, Copilot /papa-seo (and /skills reload), OpenClaw $papa-seo, Hermes /papa-seo. Gemini CLI doesn't switch a skill on by itself: the model proposes, you confirm; remove with gemini skills uninstall papa-seo. Windsurf is now Devin Desktop and its docs call the .windsurf/skills paths legacy. The pack hasn't been hand-tested on these hosts.

</details>

<details>
<summary>ChatGPT: partial, no scripts</summary>

```text
You work by the papa-seo skill; its SKILL.md and policies are pasted below, follow them. The scripts in scripts/ are not available to you: where the skill says to run a script, do the same check by hand on the HTML, robots.txt or export I give you, and mark it as a manual check. Don't guess the contents of modules from modules/ that aren't pasted here; name the module you need and I'll paste it. Don't crawl sites. Don't invent anything: no data means say so. Every claim about a site gets a quoted piece of evidence and a status: confirmed, likely or hypothesis.
```

ChatGPT has no skills folder, so this text isn't a command: it's the opening of your Project instructions. By hand: Project → Instructions (or a custom GPT's Instructions), paste the text above, then the contents of papa-seo/SKILL.md and papa-seo/policies/security.md, evidence.md and actions.md from the repository. Modules from papa-seo/modules/ go in as project files; how many depends on your plan. Scripts don't run and nothing gets crawled, so this is a partial setup.

</details>

<details>
<summary>claude.ai</summary>

```text
Build a zip for uploading the papa-seo skill to claude.ai. Run git clone https://github.com/AffPapa/papa-seo.git into a temporary folder, copy the papa-seo/ folder to a separate directory, and in its SKILL.md replace the description value in the frontmatter with this line (all of it, on one line): "SEO, GEO and content skill for Google, Yandex and AI search: page and site audits with evidence, briefs, articles, de-AI editing in RU/EN. Use for SEO audits, robots, schema, titles, SEO texts.". Change nothing else in the files. Pack it so that papa-seo/ is the root of the archive: cd into the directory that holds papa-seo and run zip -r papa-seo.zip papa-seo. Tell me the archive path. Don't install anything into my skills folders.
```

This prompt is for an agent with files (Claude Code or similar); claude.ai itself won't build the zip. Then by hand: Customize → Skills → "+" → Upload a skill, with code execution on. claude.ai caps description at 200 characters and the pack's is 560, so the upload fails without the replacement. The skill triggers from its description; remove it with the toggle → "…" → Delete. With syncClaudeAiSkills on it also shows up in Claude Code under ~/.claude/skills/synced/.

</details>

<details>
<summary>Into your project: install plus .papa-seo/project.md</summary>

```text
Install the papa-seo skill into this repository and set up the project context.

1. git clone https://github.com/AffPapa/papa-seo.git into a temporary folder. Copy the papa-seo/ folder from the clone to <repository root>/.claude/skills/papa-seo if people here use Claude Code, and to <repository root>/.agents/skills/papa-seo if they use Codex, Cursor, Copilot, Gemini CLI, Windsurf or OpenClaw; if you don't know, both. If a folder already exists, stop and ask. Delete nothing, overwrite nothing.
2. Verify each copy: test -f <path>/papa-seo/SKILL.md && python3 <path>/papa-seo/scripts/page_facts.py --help.
3. Create .papa-seo/project.md from the template: mkdir -p .papa-seo && cp <path>/papa-seo/templates/project-context.md .papa-seo/project.md. If the file already exists, leave it and tell me.
4. Ask me five questions, one at a time: (1) market and language: countries, regions, site languages; (2) which search engines matter and in what shares, and whether AI search matters; (3) whether the site may be crawled, how many threads, what pause, when it's off limits; (4) where results go and who approves changes; (5) the voice of the texts and where facts come from. Write my answers into .papa-seo/project.md; delete the lines I didn't answer, the skill will use cautious defaults. No keys or passwords in the file.
5. If the root has CLAUDE.md or AGENTS.md, append: "For SEO tasks, page checks and SEO copy, use the papa-seo skill". Remove the clone. Report: paths, what project.md now contains, how to remove it all.
```

The skill reads .papa-seo/project.md before choosing a mode; its limits override the pack's defaults. Without the file it runs in its most cautious mode: one page, or up to 20 URLs one by one, no crawling, no publishing.

</details>

<details>
<summary>Without an agent: git clone, npx skills, zip</summary>

There is no installer. The pack is one folder, papa-seo/, copied into a skills directory; nothing else there changes, just check that no folder with that name exists already. The scripts need Python 3.10 or newer and no third-party packages.

Download:

```bash
git clone https://github.com/AffPapa/papa-seo.git && cd papa-seo
```

Claude Code:

```bash
cp -R papa-seo ~/.claude/skills/papa-seo           # all projects
cp -R papa-seo <project>/.claude/skills/papa-seo   # one project
```

Codex, Cursor, Copilot, Gemini CLI, OpenClaw:

```bash
cp -R papa-seo ~/.agents/skills/papa-seo           # all projects
cp -R papa-seo <repo>/.agents/skills/papa-seo      # one repository
```

With the skills CLI, Node.js 22.20 or newer:

```bash
npx skills add AffPapa/papa-seo -g                 # or without -g, into the current project
npx skills add AffPapa/papa-seo -g -a claude-code -a codex   # name the hosts
npx skills remove papa-seo -g -y                   # remove
```

From the archive:

```bash
curl -fL -o papa-seo-main.zip https://github.com/AffPapa/papa-seo/archive/refs/heads/main.zip
unzip papa-seo-main.zip && cp -R papa-seo-main/papa-seo ~/.claude/skills/papa-seo
```

npx skills add finds papa-seo/SKILL.md in the repository (checked 2026-10-26), puts a copy in ~/.agents/skills/papa-seo, makes ~/.claude/skills/papa-seo a symlink to it (a copy with --copy) and writes ~/.agents/.skill-lock.json. The CLI's telemetry is on by default; DISABLE_TELEMETRY=1 turns it off. Either way, removing the skill means deleting the folder.

</details>

<details>
<summary>Download</summary>

- [Download zip (main)](https://github.com/AffPapa/papa-seo/archive/refs/heads/main.zip)
- [Release v0.1.1](https://github.com/AffPapa/papa-seo/releases/tag/v0.1.1)

main.zip is the current main branch, always up to date; it unpacks to papa-seo-main/, with the skill at papa-seo-main/papa-seo/. Release v0.1.1 is papa-seo-0.1.1.zip with only the papa-seo/ folder, README, LICENSE and THIRD_PARTY_NOTICES, SHA-256 in the release notes; it appears once published. affpapa.org doesn't host a copy of the archive, so it can't drift from GitHub.

</details>

### Project context

If the project root has `.papa-seo/project.md`, the skill reads it before picking a mode: market and language, which search engines matter, whether crawling is allowed and at what load, where results go, who publishes changes, the voice of the texts. Templates: `papa-seo/templates/project-context.md` and `papa-seo/templates/voice-profile.md`. Without that file the skill sticks to its most cautious defaults. The "Into your project" prompt above creates the file and asks the five questions itself.

## Try it in a minute

### SEO audit of one page: does the markup match the text?

```text
papa-seo page https://affpapa.org/neevents/piterskie-razborki — compare dates and times in the JSON-LD with what the page says.
```

This is a real run from 2026-10-24 on affpapa.org, the site of the people who built the pack. The event's JSON-LD says `"startDate":"2026-10-25T19:00:00+00:00"`, while the page says the event starts at 19:00 in Saint Petersburg, which is UTC+3. Google would show it starting at 22:00 Moscow time and ending at 02:00 the next day.

What you get: a finding `schema.event_timezone_shift`, status `confirmed`, severity medium, with both HTML lines as evidence, a fix (output the city's offset, +03:00, instead of +00:00) and a check: `page_facts.py` on three events in different cities. Only one of ~670 events in the sitemap was checked, so "the bug is in the template" stays a hypothesis.

### robots.txt for AI bots and YandexAdditional

```text
look at https://example.com/robots.txt: which AI bots get in, which don't, and are we excluded from Yandex Alice answers
```

What you get: a bot × URL table (allowed or blocked) across search, training and user-triggered bots, findings tagged `engine: yandex` and, if you ask, a robots.txt diff.

A common mistake it catches: YandexAdditional obeys neither `User-agent: *` nor the `Yandex` group. It needs a group of its own, so blocking everyone with a wildcard doesn't block it.

## Modes

Ask in plain words ("check this page", "write a brief", "refresh this article") or name a mode: `papa-seo audit example.com`.

| Mode | What it does |
|---|---|
| `page` | one page, or an HTML file before it goes live: title, description, headings, canonical, structured data, indexability |
| `audit` | technical SEO audit from a URL sample: status codes, redirects, robots.txt, sitemap, markup, speed, internal links; ends with a report that states coverage |
| `yandex` | Yandex SEO: YandexAdditional, Clean-param, Webmaster, commercial signals, site moves |
| `geo` | AI search (GEO/AEO): eligibility for ChatGPT, Perplexity, AI Overviews and Alice AI answers, AI bots in robots.txt, WAF, llms.txt |
| `plan` | keyword research from your data: intents, clusters, query-to-page map, cannibalization |
| `brief` | content brief: intent, angle, outline, sourced facts, questions for an expert |
| `write` | article or page copy from a brief, then a fact check and a de-AI pass |
| `refresh` | update an old page using a Search Console export and the current SERP |
| `edit` | editing and rewriting that keeps every fact, removal of AI-writing tells |
| `landing` | landing or sales page with no invented testimonials, numbers or guarantees |
| `links` | internal linking: orphans, depth, the exact sentence for each new link; backlinks from free data |
| `fix` | a patch or draft for robots.txt, JSON-LD, titles, templates; shipped only after your yes |
| `measure` | Search Console, Yandex Webmaster, GA4, read-only: period comparison, drops, near-top queries |

Server logs, migrations, local SEO, e-commerce, hreflang, programmatic pages, backlinks and text metrics load when you ask about them.

## Example prompts

Paste a prompt into the agent's chat as is, with your own paths and URLs.

### Single page

<details>
<summary>Find out why a page is not indexed</summary>

```text
https://example.com/catalog/sofas/ has been out of Google's index for three weeks but Yandex has it. What's blocking it?
```

What you get: any blocking condition with its evidence. If everything is open, a list of what to check in Search Console (URL Inspection, the exclusion reason).

The agent can't see your Search Console report, so without a technical block it calls the cause a hypothesis, not a fact.

</details>

<details>
<summary>Validate JSON-LD against the visible page text</summary>

```text
papa-seo page https://example.com/blog/choosing-laminate/ — markup only: what's there, what's broken, what still earns a rich result
```

What you get: an inventory of type → format → JSON path → Google status → Yandex note, and findings with the snippet.

FAQPage isn't recommended for the SERP: Google stopped showing that rich result on 2026-05-07, and Yandex's help doesn't list the type.

</details>

<details>
<summary>Check whether crawlers see the text without JavaScript</summary>

```text
We're on a client-rendered SPA. Look at https://example.com/pricing — what is in the raw HTML?
```

What you get: how much of the main text is in the raw HTML, whether prices and answers exist without JavaScript, and a `rendered` finding if they don't.

There is no renderer in the pack. A before/after-JS comparison needs a saved rendered copy from you.

</details>

### Site audit

The first two come from the same affpapa.org audit on 2026-10-24: 15 pages fetched one by one with a pause, plus robots.txt and the sitemap index.

<details>
<summary>Check a generated review against the specs on the same page (affpapa.org case)</summary>

```text
papa-seo page https://affpapa.org/nepartners/1win-partners plus the English twin /en/nepartners/1win-partners. Check the review text against the Specs block on the same page: countries, payouts, anything verifiable.
```

What it found on 2026-10-24: the review names Germany, the USA and Ukraine as the program's markets, while the Specs block on the same page lists those countries under restricted GEOs. The English twin repeats the error. Finding status `confirmed`, severity high. The fix belongs in the review generator: pass only target GEOs into the prompt and block publishing when a country in the text is on the restricted list.

One RU/EN pair out of ~1,580 entity pages was checked, so the scale isn't visible from a single page.

</details>

<details>
<summary>Find parameter URLs that are open to crawling (affpapa.org case)</summary>

```text
papa-seo audit affpapa.org without crawling: the 15 URLs in urls.txt, one thread, 4-second pause. robots.txt and sitemap first, then pages. Look separately at parameter URLs linked from entity pages.
```

What it found: `/neblask/compare?brands=1win,stake` returns `index, follow`, 544,663 bytes of HTML and a canonical pointing to the `/neblask/compare` hub, which has different content. Brand pages link to such pairs, there are 2,555 brands, and each order of a pair is its own URL. robots.txt has no rule for `/neblask/compare?*`.

Status `likely`, not `confirmed`: without Webmaster data and logs there's no way to see how many of these URLs are indexed or crawled. Two fixes, the owner's choice: block the combinations from crawling, or keep an allowlist of pairs with their own title and a self-canonical.

</details>
<details>
<summary>Audit a site from a URL sample, no crawling</summary>

```text
papa-seo audit example.com. Do not crawl, the server is weak. 15 URLs in urls.txt: home plus two of each template. 3-second pause.
```

What you get: a report on `templates/report.md`: verdict, what to fix first, findings by severity, a coverage line "checked N of ~M URLs" and a Not checked section.

From a sample it won't write "the whole site lacks X", only "in the N pages checked".

</details>

<details>
<summary>Check a sitemap: limits, lastmod, foreign hosts</summary>

```text
check https://example.com/sitemap.xml — it's an index of 8 files generated on the fly, go easy
```

What you get: findings on file type, size limits, foreign hosts, http entries, duplicates and plausible lastmod. `children_warning` lists the shards it didn't open.

It opens two child sitemaps unless you ask for more, and it doesn't fetch the URLs listed inside.

</details>

<details>
<summary>Decide which templated pages deserve indexing</summary>

```text
We have 4,000 'service + city' pages built from one table. Records are in ./data/cities.csv, plus 10 sample URLs. Which ones should be indexed?
```

What you get: an indexing rule based on the record's fields, a sample table with a verdict per page and a plan to roll out in batches.

No "text uniqueness percentage": the pack lists that threshold as a myth in `references/folklore.md`.

</details>

### Yandex SEO

<details>
<summary>Review a service page for Google and Yandex</summary>

```text
check https://example.ru/uslugi/remont-kvartir/ — Moscow market, Yandex matters most
```

What you get: findings tagged `engine: google / yandex / both`, a page card (title, H1, description, first paragraph as is) and 2–3 draft titles.

No search volume unless you give it Webmaster, Wordstat or your own export.

</details>

<details>
<summary>Stop UTM duplicates in Yandex with Clean-param</summary>

```text
Yandex Webmaster shows duplicates with utm_ and ?ref=. Draft a Clean-param rule and check it won't break anything else. robots.txt attached.
```

What you get: a robots.txt diff with the new rule and an access table before and after for the same URLs.

Disallow wins over Clean-param: a blocked page isn't indexed even if the rule matches it.

</details>

<details>
<summary>Analyse excluded pages from Yandex Webmaster</summary>

```text
I exported Excluded pages from Yandex Webmaster for October: ./webmaster/excluded.csv. What matters here?
```

What you get: exclusion reasons grouped by URL pattern, with examples and a decision for each group.

"Low-value or low-demand" is about quality and demand. Recrawling won't fix it.

</details>

### AI search (GEO/AEO), AI bots, llms.txt

<details>
<summary>Check if a page can appear in ChatGPT, Perplexity and AI Overviews answers</summary>

```text
GEO check for https://example.com/guide/mortgage-2026/ — is it eligible for AI Overviews, ChatGPT search and Perplexity?
```

What you get: an eligibility table per engine (status 200, search bot allowed, no noindex, snippet directives, canonical) with evidence on every row, plus bot access by group.

Eligible doesn't mean cited. Search Console and Webmaster settings are visible only to the site owner.

</details>

<details>
<summary>Block AI training without leaving AI search</summary>

```text
We want to opt out of model training but stay in ChatGPT and Claude search. Draft the robots.txt change, don't deploy anything.
```

What you get: a robots.txt diff that explains what changes for each bot (GPTBot vs OAI-SearchBot, ClaudeBot vs Claude-SearchBot, Google-Extended vs Googlebot) and an access table before and after.

User-triggered fetchers such as ChatGPT-User and Claude-User don't always honour robots.txt. That isn't a defect of your site.

</details>

<details>
<summary>Build an llms.txt from your own page list</summary>

```text
Make an llms.txt from the section list in ./docs/sections.md. One-sentence descriptions.
```

What you get: a draft llms.txt built only from your list, and the entries it dropped with the reason. Every description goes through the hidden-instruction filter.

The file is optional. Google Search doesn't use it, and the skill doesn't report a missing llms.txt as a problem.

</details>

<details>
<summary>Check whether a CDN or WAF blocks AI crawlers</summary>

```text
Our robots.txt allows everyone, yet GPTBot gets only 403s in the logs. Fetch the home page with its User-Agent.
```

What you get: a `headers` finding if robots.txt allows the bot but a live request with its User-Agent gets a 403 or a challenge.

If the WAF lets bots through by IP, a request from your own address won't show it.

</details>

### Keywords and structure

<details>
<summary>Find keyword cannibalization in a Search Console export</summary>

```text
I think two laminate articles compete. Search Console query × page export for 3 months: ./gsc/query_page.csv
```

What you get: a table of query, competing URLs, the data and a proposed fix (split the intents, merge with a 301, relink), with `approval_required: true`.

Without a query × page export it won't claim cannibalization. A `site:` search is a hint, not proof.

</details>

### Briefs and articles

<details>
<summary>Write a content brief for a copywriter</summary>

```text
write a brief for an article on how to choose laminate flooring for a kitchen. Facts come from our price list and manufacturer sheets in ./sources/
```

What you get: a filled `templates/brief.md`, a separate list of `[NEED: …]` gaps with who to ask, and questions for an expert.

Whatever isn't in the brief's fact table is off limits for the writer. There's no word-count target.

</details>

<details>
<summary>Write an article from an existing brief, with sources</summary>

```text
papa-seo write from ./briefs/choosing-laminate.md — sources in ./sources/, save the draft to ./drafts/
```

What you get: a Markdown draft, the source list, open `[NEED: …]` markers and a short check report (claim → source → status, de-AI scan).

It doesn't add experience, stories or opinions the author didn't give. A number without a source stays a `[NEED]` marker.

</details>

<details>
<summary>Write a title, H1 and meta description</summary>

```text
write a title and description for https://example.com/washer-repair/ — the current snippet is junk
```

What you get: 2–3 title options with reasons, an H1, a description and a first paragraph, plus a before → after → why table.

Promises the page can't back up go into warnings instead of the title.

</details>

### Refresh, rewrite, de-AI

<details>
<summary>Refresh an old article using a Search Console export</summary>

```text
papa-seo refresh https://example.com/blog/laminate-2023/ — 16 months of Search Console data in ./gsc/laminate.csv
```

What you get: a plan first (sections, title options, meta, markup). After you agree: the new text, a `factdiff.py` report and what to compare in Search Console a few weeks later.

URL, anchors and verified facts stay. The "updated" date changes only when the content really changed.

</details>

<details>
<summary>Figure out why a page lost traffic</summary>

```text
Since September /services/windows/ lost half its clicks. Search Console exports for August and October are in ./gsc/. What happened?
```

What you get: a one- or two-sentence verdict, a change table with absolute and relative values, and causes split into demand, ranking, snippet CTR and indexing, each marked confirmed / likely / hypothesis.

Same timing isn't causation. A link to a Google update stays a hypothesis unless the update date is in `references/facts-2026.md`.

</details>

<details>
<summary>Strip AI tells from a text</summary>

```text
de-AI ./drafts/review.md, keep the meaning and every number
```

What you get: the edited text and at most two "check before sending" lines. The full change list on request.

No humanness score, no AI probability, no promise to beat detectors.

</details>

### Internal links

<details>
<summary>Find orphan pages from a link export</summary>

```text
Here's a crawler link export edges.csv (from,to,anchor) and the sitemap URL list sitemap_urls.txt. Find orphans and pages buried too deep.
```

What you get: a graph summary (source, pages, completeness, orphans, depth) and a table of problem pages.

A page is called an orphan only when the graph is complete. A folder of saved HTML works instead of CSV (`--html-dir`).

</details>

<details>
<summary>Plan internal links down to the exact sentence</summary>

```text
I want to boost /services/bathroom-renovation/. Pick 3–5 donor pages and show the exact sentence where each link goes.
```

What you get: a table of donor → target → anchor → the donor's exact sentence → the new sentence → region → priority.

Donor URLs come from your site, not from a pattern. Nothing goes into the CMS without your yes.

</details>

### Fixes and Search Console

<details>
<summary>Prepare a robots.txt patch with before/after checks</summary>

```text
Block internal search /search?q= and ?sort= from crawling. Give me a patch and prove product pages stay open. File: ./public/robots.txt
```

What you get: a robots.txt diff, an access table before and after, and a rollback command.

noindex and Disallow on the same URL don't work together: a crawler blocked by robots.txt never reads the noindex.

</details>

<details>
<summary>Find striking-distance queries</summary>

```text
find queries where we sit at positions 8–20 with real impressions. Export: ./gsc/queries_28d.csv
```

What you get: queries and pages with impressions, position and the next step (`edit` or `links`).

These are candidates for work, not a promise of page one.

</details>

### Logs and migrations

<details>
<summary>Tell a real Googlebot from a fake one</summary>

```text
Some 'Googlebot' hits /search?q= 20 times a second. Check if it's real; Caddy JSON log at ./logs/caddy.json
```

What you get: separate lines for "claims Googlebot, verified" and "claims Googlebot, not verified", plus draft countermeasures.

`bot_verify.py` makes DNS queries; cap unique IPs with `--max-ips`.

</details>

<details>
<summary>Build a 301 redirect map for a URL structure change</summary>

```text
We're moving the blog from /blog/2023/05/slug to /blog/slug. Old URLs in old_urls.txt, new ones from the new sitemap. Need a redirect map.
```

What you get: a redirect-map CSV with a `status_after` column, a launch checklist and a monitoring plan with dates.

A URL with no counterpart goes to 404/410, not to the home page. Rollback criteria are yours to set.

</details>

## Scripts without an agent

You can run the same checks by hand. Run them from the skill folder (for example `cd ~/.claude/skills/papa-seo`); output is JSON.

```bash
# robots.txt access table for search and AI bots
python3 scripts/robots_check.py https://example.com/robots.txt --url / --url /catalog/?utm_source=x \
  --bots Googlebot,YandexBot,YandexAdditional,OAI-SearchBot,GPTBot,ClaudeBot --out robots.json

# facts from one page; for an unpublished file use ./build/page.html --base-url https://example.com/services/
python3 scripts/page_facts.py https://example.com/services/ --out facts.json

# up to 20 pages one by one, pause of at least 2 seconds
python3 scripts/page_facts.py --urls-file urls.txt --delay 3 --out batch.json

# sitemap check without fetching the listed URLs
python3 scripts/sitemap_check.py https://example.com/sitemap.xml --site https://example.com \
  --follow-index --max-children 2 --out sitemap.json

# internal link graph: orphans, depth, PageRank
python3 scripts/link_graph.py edges.csv --pages sitemap_urls.txt --csv-out nodes.csv --out graph.json

# AI-writing tells: clichés, chatbot artifacts, invisible characters
python3 scripts/deai_scan.py article.md --genre expert --lang en --out scan.json

# what an edit lost or added: numbers, dates, money, URLs, names
python3 scripts/factdiff.py before.md after.md --out diff.json
```

Two more: `text_metrics.py` counts length, keyword stems and density (as an estimate), and `bot_verify.py` checks from a log whether Googlebot, YandexBot or Bingbot is real. Every script has `--help`.

## What's inside

```text
papa-seo/
  SKILL.md       router: request → mode → modules
  policies/      security, evidence rules, permission ladder
  modules/       29 modules, one file per function
  references/    dated facts with sources, myths, bot roster, Yandex, page types, Russian style
  templates/     finding schema, brief, report, project context, voice profile
  scripts/       9 scripts, Python 3.10+, standard library only
  tests/         python3 -m unittest discover
evals/           fixture site with planted defects and an answer key
```

Modules by group:

- audit: `tech-audit`, `indexing`, `on-page`, `schema`, `performance`, `eeat`, `report`;
- demand and SERP: `semantics`, `serp`, `measure`;
- Yandex and AI search: `yandex`, `geo`;
- links: `links`, `backlinks`;
- writing: `brief`, `write`, `factcheck`, `edit`, `deai`, `voice`, `headlines`, `landing`, `text-metrics`;
- site types and special cases: `local`, `ecommerce`, `international`, `programmatic`, `migration`, `logs`.

The router loads only the module a request needs. Thresholds and dates live in one file, `references/facts-2026.md`, each with a check date and a link to the primary source. Findings follow `templates/finding.schema.json`: where the fact came from, when, the evidence snippet, status, search engine, the fix and how to verify it. Before it says "add X", the agent checks the live HTML to confirm X is really missing.

[evals/](evals/README.md) holds a small site with ten planted defects, eight traps and two prompt-injection attacks, for comparing the same model with and without the skill. That comparison hasn't been run on models yet; what the scripts alone catch, without a model, is in [evals/RESULTS-scripts.md](evals/RESULTS-scripts.md) (Russian).

## Safety and limits

- No full-site crawl unless you ask. If you do, it crawls in a single thread and warns about the load.
- It doesn't publish anything. Work stops at a patch; you approve what ships.
- Fetched HTML, robots.txt, CSV files and competitor texts are data, not instructions. Hidden prompts in a page are reported as a finding. Scripts reach the network only through `http_safe.py`, which blocks private and internal addresses, re-checks every redirect hop and caps the response size.
- It doesn't make up search volume, rankings, DR or CTR. Missing data is reported as missing. Paid APIs (DataForSEO, Ahrefs, Semrush, Serpstat, SE Ranking, Wordstat API, Yandex Search API) may be suggested, always marked as paid.
- No promises of traffic or rankings, and no "humanness" scores for text.
- Page JavaScript isn't executed. The skill checks raw HTML and flags signs of client-side rendering.
- There has been no external security audit.

The threat model, what the tests cover and where protection ends: [SECURITY.md](SECURITY.md) (in Russian).

## Where it comes from

The pack was built after reviewing 105 open repositories with SEO, GEO and copywriting skills (2026-10-24): 94 in the first pass and 11 in the second. Methods and wording were adapted only where the license allows it, and from original projects rather than clones. Where there was no license, only ideas were used, restated in our own words. Sources, commits and licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [source.lock.json](source.lock.json) and [licenses/](licenses/).

What went into it, in numbers:

- 105 repositories reviewed statically; no skill or installer was ever run. Safety verdicts: 40 clean, 56 with reservations, 9 rejected; no malicious code in any of them.
- Another 89 repositories on 89 accounts turned out to be one fake network, reviewed by metadata only.
- 23 donors whose wording was adapted, with attribution and a pinned commit; 16 sources where only an idea was taken.
- Of the original 94, 71 have a proper license, 10 say "MIT" only in the README, 9 have none or a closed one, 4 are AGPL, CC BY-SA or fake.
- 17 de-AI editing implementations, nearly all tracing back to one Wikipedia page; Yandex covered by a single donor, YandexAdditional mentioned by none of the 105.
- Left out, by group: paid APIs and hosted MCPs, ads inside reports, CAPTCHA bypass, wildcard uninstallers, remote SKILL.md, auto-merge, browser cookies.

The full breakdown, who, what, under which license, what was dropped and why, and which "rules" from other skills failed a primary-source check: [docs/RESEARCH.en.md](docs/RESEARCH.en.md) (short) and [docs/RESEARCH.md](docs/RESEARCH.md) (full, Russian).

## Project page

Full instructions and the complete example library (in Russian): [affpapa.org/papa-seo](https://affpapa.org/papa-seo).

## License

MIT, © 2026 AFFPAPA. See [LICENSE](LICENSE). Adapted third-party material keeps its license; each such file names its source in a header.
