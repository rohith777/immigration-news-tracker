# Visa Ledger — H-1B / F-1 / I-140 / PERM / Green Card news tracker

A self-updating static site that pulls immigration news from public sources
(USCIS Newsroom, the Federal Register, immigration law/policy blogs, and
community discussion), tags each item by category, and shows it with a
visible citation linking back to the original source. A scheduled GitHub
Action does the scraping; GitHub Pages hosts the result. No server to run,
no database, free to host.

**This is a personal news tracker, not legal advice.** Always confirm
anything that affects your case with an attorney or the official agency.

## How it works

```
sources.json              → list of feeds/APIs to pull from (edit freely)
scraper/scrape.py         → fetches, filters by keyword, dedupes, writes docs/data/news.json
.github/workflows/*.yml   → runs the scraper every 6 hours and commits the result
docs/                     → the static site itself (served by GitHub Pages)
```

Categories tracked out of the box: **H-1B**, **F-1 / OPT / CPT**, **I-140**,
**PERM**, **Green Card**. Matching is keyword/regex-based — see
`CATEGORY_PATTERNS` in `scraper/scrape.py` to adjust.

Sources currently configured:
- **USCIS Newsroom** (RSS) — official announcements, always included
- **Federal Register API** — official rules/notices from USCIS, DOL, and
  State Dept, always included
- **Immigration Impact** (American Immigration Council blog, RSS)
- **National Law Review – Immigration** (RSS)
- **r/immigration** and **r/h1b** (Reddit, public JSON endpoint)

Any single source failing (dead link, rate limit, site redesign) just gets
skipped with a warning in the Action logs — it won't break the whole run.
Check the logs occasionally and prune/replace sources in `sources.json` as
needed.

## One-time setup

1. **Create a GitHub repo** (public or private — private repos on GitHub
   Pages need GitHub Pro/Team/Enterprise to publish; public is simplest) and
   push everything in this folder to it.

2. **Let Actions write to the repo.** In your repo:
   `Settings → Actions → General → Workflow permissions` → select
   **"Read and write permissions"** → Save. (The workflow file already
   requests `contents: write`, but this repo setting has to allow it too.)

3. **Enable GitHub Pages.**
   `Settings → Pages → Build and deployment → Source` → **Deploy from a
   branch** → Branch: `main`, folder: **`/docs`** → Save. GitHub will give
   you a URL like `https://<your-username>.github.io/<repo-name>/`.

4. **Run the scraper once manually** so you're not staring at the
   placeholder: `Actions` tab → **"Update immigration news"** → **Run
   workflow**. After it finishes (~30–60s), refresh your Pages URL.

From then on it refreshes itself every 6 hours automatically (edit the
`cron` line in `.github/workflows/update-news.yml` to change that — cron
times are UTC).

## Running it locally (optional, for testing)

```bash
pip install -r requirements.txt
python scraper/scrape.py
# then open docs/index.html in a browser, or:
cd docs && python -m http.server 8000
```

## Customizing

- **Add/remove sources:** edit `sources.json`. RSS feeds just need a `url`;
  Reddit sources use the public `.json` endpoint of a subreddit; the
  Federal Register entry takes a list of agency slugs.
- **Tune what counts as "matching":** edit `CATEGORY_PATTERNS` in
  `scraper/scrape.py` — it's plain regex per category.
- **Change refresh frequency:** edit the `cron` schedule in
  `.github/workflows/update-news.yml`.
- **Look and feel:** `docs/style.css` (colors/type) and `docs/index.html`.
