#!/usr/bin/env python3
"""Build a 'this day in blog history' report from the Wayback Machine.

The script looks for pages captured on this month/day in prior years and writes
an HTML report organized by year, subject, popularity tier, blog, and article.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WAYBACK_REPLAY_PREFIX = "https://web.archive.org/web"
DEFAULT_OUTPUT = "blog_time_travel_report.html"
USER_AGENT = "BlogTimeTraveler/1.0 (+https://web.archive.org)"


@dataclass(frozen=True)
class BlogSource:
    blog_name: str
    base_url: str
    subject: str
    popularity: str  # high | medium | low


@dataclass
class ArchiveEntry:
    year: int
    month_day: str
    subject: str
    popularity: str
    blog_name: str
    page_title: str
    original_url: str
    archive_url: str
    timestamp: str


# Broad list across domains/subjects with mixed popularity tiers.
SOURCES: list[BlogSource] = [
    # Technology
    BlogSource("The Verge", "https://www.theverge.com/", "Technology", "high"),
    BlogSource("TechCrunch", "https://techcrunch.com/", "Technology", "high"),
    BlogSource("Stratechery", "https://stratechery.com/", "Technology", "medium"),
    BlogSource("Coding Horror", "https://blog.codinghorror.com/", "Technology", "low"),
    # Science
    BlogSource("Scientific American Blog", "https://blogs.scientificamerican.com/", "Science", "high"),
    BlogSource("Nautilus", "https://nautil.us/", "Science", "medium"),
    BlogSource("Pharyngula", "https://freethoughtblogs.com/pharyngula/", "Science", "low"),
    # Business/Economics
    BlogSource("Harvard Business Review", "https://hbr.org/", "Business", "high"),
    BlogSource("Marginal Revolution", "https://marginalrevolution.com/", "Business", "medium"),
    BlogSource("A Wealth of Common Sense", "https://awealthofcommonsense.com/", "Business", "low"),
    # Design
    BlogSource("Smashing Magazine", "https://www.smashingmagazine.com/", "Design", "high"),
    BlogSource("A List Apart", "https://alistapart.com/", "Design", "medium"),
    BlogSource("CSS-Tricks", "https://css-tricks.com/", "Design", "low"),
    # Culture/Writing
    BlogSource("The Atlantic", "https://www.theatlantic.com/", "Culture", "high"),
    BlogSource("Longreads", "https://longreads.com/", "Culture", "medium"),
    BlogSource("Brain Pickings", "https://www.themarginalian.org/", "Culture", "low"),
]


def fetch_json(url: str, timeout: int = 30, retries: int = 3, sleep_base: float = 0.8):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(sleep_base * (attempt + 1))
    raise RuntimeError(f"Failed to fetch JSON from {url}: {last_error}")


def fetch_text(url: str, timeout: int = 30, retries: int = 2):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(160_000)
                return body.decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch text from {url}: {last_error}")


def cdx_query(base_url: str, day: dt.date, max_results: int) -> list[tuple[str, str]]:
    from_ts = day.strftime("%Y%m%d") + "000000"
    to_ts = day.strftime("%Y%m%d") + "235959"

    params = {
        "url": urllib.parse.urljoin(base_url, "*"),
        "from": from_ts,
        "to": to_ts,
        "filter": ["statuscode:200", "mimetype:text/html"],
        "fl": "timestamp,original",
        "output": "json",
        "collapse": "urlkey",
        "limit": str(max_results),
    }

    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{CDX_ENDPOINT}?{query}"
    payload = fetch_json(url)
    if not payload or len(payload) <= 1:
        return []

    rows = payload[1:]  # Skip header.
    cleaned: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        ts, original = row[0], row[1]
        cleaned.append((ts, original))
    return cleaned


def parse_title(document: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", document, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    text = re.sub(r"\s+", " ", match.group(1)).strip()
    return text[:220] if text else None


def choose_entries(captures: Iterable[tuple[str, str]], sample_size: int) -> list[tuple[str, str]]:
    items = list(captures)
    if len(items) <= sample_size:
        return items
    random.shuffle(items)
    return sorted(items[:sample_size], key=lambda x: x[0])


def collect_for_year(
    year: int,
    month: int,
    day: int,
    max_per_source_year: int,
    request_pause_seconds: float,
) -> list[ArchiveEntry]:
    target = dt.date(year, month, day)
    entries: list[ArchiveEntry] = []

    for src in SOURCES:
        try:
            captures = cdx_query(src.base_url, target, max_results=max(40, max_per_source_year * 5))
        except RuntimeError:
            continue

        sampled = choose_entries(captures, max_per_source_year)
        for timestamp, original in sampled:
            archive_url = f"{WAYBACK_REPLAY_PREFIX}/{timestamp}/{original}"
            title = "(title unavailable)"
            try:
                text = fetch_text(archive_url)
                extracted = parse_title(text)
                if extracted:
                    title = extracted
            except RuntimeError:
                pass

            entries.append(
                ArchiveEntry(
                    year=year,
                    month_day=target.strftime("%B %d"),
                    subject=src.subject,
                    popularity=src.popularity,
                    blog_name=src.blog_name,
                    page_title=title,
                    original_url=original,
                    archive_url=archive_url,
                    timestamp=timestamp,
                )
            )
            time.sleep(request_pause_seconds)
    return entries


def tier_sort_value(tier: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(tier, 99)


def render_html(entries: list[ArchiveEntry], report_date: dt.date, year_offsets: list[int]) -> str:
    grouped: dict[int, list[ArchiveEntry]] = {}
    for item in entries:
        grouped.setdefault(item.year, []).append(item)

    years = sorted(grouped.keys(), reverse=True)

    chunks: list[str] = []
    chunks.append("<!doctype html>")
    chunks.append("<html lang='en'><head><meta charset='utf-8'>")
    chunks.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    chunks.append("<title>Blog Time Traveler Report</title>")
    chunks.append(
        "<style>body{font-family:system-ui,-apple-system,sans-serif;margin:2rem;line-height:1.45;}"
        "h1,h2,h3{margin-bottom:.3rem;} .meta{color:#555;} .year{margin-top:2rem;padding-top:1rem;border-top:1px solid #ddd;}"
        "table{width:100%;border-collapse:collapse;margin-top:.6rem;}th,td{border:1px solid #ddd;padding:.5rem;text-align:left;vertical-align:top;}"
        "th{background:#f6f6f6;} .pill{display:inline-block;padding:.1rem .4rem;border-radius:999px;background:#eef;font-size:.78rem;}"
        "a{text-decoration:none;}a:hover{text-decoration:underline;}</style>"
    )
    chunks.append("</head><body>")
    chunks.append("<h1>Blog Time Traveler</h1>")
    chunks.append(
        f"<p class='meta'>Built on {html.escape(report_date.isoformat())}. "
        f"Looking back across offsets {html.escape(', '.join(str(o) for o in year_offsets))} years "
        f"for posts captured on {html.escape(report_date.strftime('%B %d'))}.</p>"
    )

    if not years:
        chunks.append("<p>No archive entries were found for the selected date range.</p>")
    for year in years:
        rows = sorted(
            grouped[year],
            key=lambda x: (x.subject.lower(), tier_sort_value(x.popularity), x.blog_name.lower(), x.timestamp),
        )
        chunks.append(f"<section class='year'><h2>{year}</h2>")
        chunks.append("<table><thead><tr><th>Subject</th><th>Popularity</th><th>Blog</th><th>Article Title</th><th>Archive</th></tr></thead><tbody>")
        for r in rows:
            chunks.append(
                "<tr>"
                f"<td>{html.escape(r.subject)}</td>"
                f"<td><span class='pill'>{html.escape(r.popularity)}</span></td>"
                f"<td><a href='{html.escape(r.original_url)}'>{html.escape(r.blog_name)}</a></td>"
                f"<td>{html.escape(r.page_title)}</td>"
                f"<td><a href='{html.escape(r.archive_url)}'>{html.escape(r.timestamp)}</a></td>"
                "</tr>"
            )
        chunks.append("</tbody></table></section>")

    chunks.append("</body></html>")
    return "\n".join(chunks)


def build_default_year_offsets() -> list[int]:
    """Return 1-5 years back, then 5-year increments through 35 years back."""
    return [1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 35]


def build_year_offsets(years_back: int | None) -> list[int]:
    if years_back is None:
        return build_default_year_offsets()

    if years_back < 1:
        raise ValueError("--years-back must be at least 1")

    return list(range(1, years_back + 1))



def main() -> None:
    today = dt.date.today()

    parser = argparse.ArgumentParser(description="Build a day-matched historical blog link report from the Wayback Machine.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output HTML file path (default: blog_time_travel_report.html)")
    parser.add_argument(
        "--years-back",
        type=int,
        default=None,
        help=(
            "How many years to look back contiguously (e.g., 30 for 1..30 years ago). "
            "Default uses 1-5 years ago, then 5-year increments through 35 years ago."
        ),
    )
    parser.add_argument("--max-per-source-year", type=int, default=2, help="Max pages to include per source per year (default: 2)")
    parser.add_argument("--month", type=int, default=today.month, help="Month to query (default: current month)")
    parser.add_argument("--day", type=int, default=today.day, help="Day to query (default: current day)")
    parser.add_argument("--pause", type=float, default=0.15, help="Seconds to pause between replay fetches (default: 0.15)")
    args = parser.parse_args()

    output_path = Path(args.output)
    all_entries: list[ArchiveEntry] = []

    current_year = today.year
    year_offsets = build_year_offsets(args.years_back)
    for delta in year_offsets:
        year = current_year - delta
        try:
            _ = dt.date(year, args.month, args.day)
        except ValueError:
            continue
        year_entries = collect_for_year(
            year=year,
            month=args.month,
            day=args.day,
            max_per_source_year=args.max_per_source_year,
            request_pause_seconds=args.pause,
        )
        all_entries.extend(year_entries)

    document = render_html(all_entries, report_date=today, year_offsets=year_offsets)
    output_path.write_text(document, encoding="utf-8")
    print(f"Wrote {len(all_entries)} entries to {output_path}")


if __name__ == "__main__":
    main()
