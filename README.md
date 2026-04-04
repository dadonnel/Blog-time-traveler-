# Blog Time Traveler

`daily_blog_time_traveler.py` builds a daily HTML report of archived blog posts that were captured on this calendar day in prior years (1-5 years back, then every 5 years up to 35 years back by default), using the Internet Archive Wayback Machine CDX API.

## What it does

- Queries many blog sources across multiple subjects (technology, science, business, design, culture).
- Uses mixed popularity tiers (`high`, `medium`, `low`) for each subject.
- Pulls archived page titles and writes a single organized HTML file with links.

## Run

```bash
python3 daily_blog_time_traveler.py
```

Options:

```bash
python3 daily_blog_time_traveler.py --help
```

Useful flags:

- `--output blog_time_travel_report.html`
- `--years-back 30` (optional contiguous range override: 1..30 years ago)
- `--max-per-source-year 2`
- `--month 4 --day 2` (override today)
- `--discover-sources --max-discovered-per-seed 3` (discover additional blogs from seed pages each run)
- `--discover-hn --max-hn-sources 25` (discover blog-like sources from Hacker News links for the selected month/day)
- `--source-registry .blog_source_registry.json --max-registry-sources 100` (reuse previously successful discovered sources)

## Dynamic source discovery

By default, the script uses a curated seed list of blogs. If you pass `--discover-sources`, it will also:

- Crawl each seed blog's homepage.
- Extract outbound links that look blog-like (e.g., `blog`, `news`, `posts`, `articles`).
- Add a capped number of newly discovered domains per seed (`--max-discovered-per-seed`).

This helps diversify the set of blogs queried for each date while preserving the stable seed list.

## Hacker News-assisted discovery

If you pass `--discover-hn`, the script queries the HN Algolia API for story links posted on the selected month/day (current year), filters them to blog-like domains, and adds them as low-popularity discovered sources.

## Source registry (learning over time)

By default, the script maintains a source registry JSON file (`.blog_source_registry.json`) that tracks discovered domains, success counts, and last-seen date.

- Loads prior high-performing discovered sources at startup.
- Updates success counts based on captures found in the current run.
- Lets source variety improve over time without hard-coding domains.

Use `--disable-registry` to turn this behavior off.

## Daily schedule (cron)

Example cron entry (runs every day at 6:10 AM UTC):

```cron
10 6 * * * cd /workspace/Blog-time-traveler- && /usr/bin/python3 daily_blog_time_traveler.py --output blog_time_travel_report.html >> /tmp/blog_time_traveler.log 2>&1
```

The report is regenerated each run.
