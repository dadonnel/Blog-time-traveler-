# Blog Time Traveler

`daily_blog_time_traveler.py` builds a daily HTML report of archived blog posts that were captured on this calendar day in prior years (1..30 years back by default), using the Internet Archive Wayback Machine CDX API.

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
- `--years-back 30`
- `--max-per-source-year 2`
- `--month 4 --day 2` (override today)

## Daily schedule (cron)

Example cron entry (runs every day at 6:10 AM UTC):

```cron
10 6 * * * cd /workspace/Blog-time-traveler- && /usr/bin/python3 daily_blog_time_traveler.py --output blog_time_travel_report.html >> /tmp/blog_time_traveler.log 2>&1
```

The report is regenerated each run.
