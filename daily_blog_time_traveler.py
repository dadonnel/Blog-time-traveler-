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
HN_SEARCH_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"
DEFAULT_OUTPUT = "blog_time_travel_report.html"
USER_AGENT = "BlogTimeTraveler/1.0 (+https://web.archive.org)"


@dataclass(frozen=True)
class BlogSource:
    blog_name: str
    base_url: str
    subject: str
    popularity: str  # high | medium | low
    origin: str = "seed"  # seed | discovered | discovered-hn


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

IGNORED_DISCOVERY_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "medium.com",
    "pinterest.com",
    "reddit.com",
    "t.co",
    "twitter.com",
    "x.com",
    "youtube.com",
}

HREF_PATTERN = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", flags=re.IGNORECASE)


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


def fetch_json_url_params(base_url: str, params: dict[str, str], timeout: int = 30):
    query = urllib.parse.urlencode(params)
    return fetch_json(f"{base_url}?{query}", timeout=timeout)


def fetch_text(
    url: str,
    timeout: int = 30,
    retries: int = 2,
    max_bytes: int = 200_000,
    use_stream_read: bool = False,
):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if use_stream_read:
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in iter(lambda: response.read(8192), b""):
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= max_bytes:
                            break
                    body = b"".join(chunks)
                else:
                    body = response.read(max_bytes)
                return body.decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch text from {url}: {last_error}")


def canonical_source_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = parsed.netloc.lower().strip(".")
    if not host:
        return ""
    return f"https://{host}/"


def domain_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower().lstrip("www.")


def looks_like_blog_url(url: str) -> bool:
    domain = domain_from_url(url)
    if not domain:
        return False
    if any(domain == ignored or domain.endswith(f".{ignored}") for ignored in IGNORED_DISCOVERY_DOMAINS):
        return False
    lower = url.lower()
    return any(marker in lower for marker in ("blog", "news", "posts", "articles", "writing", "journal", "magazine"))


def make_blog_name(url: str) -> str:
    host = domain_from_url(url)
    if not host:
        return "Discovered Blog"
    base = host.split(".")[0]
    return base.replace("-", " ").replace("_", " ").title()


def extract_candidate_urls(document: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    for match in HREF_PATTERN.finditer(document):
        href = match.group(1).strip()
        if not href:
            continue
        resolved = urllib.parse.urljoin(base_url, href)
        if not looks_like_blog_url(resolved):
            continue
        canonical = canonical_source_url(resolved)
        if canonical:
            candidates.append(canonical)
    return candidates


def discover_sources_from_seeds(
    seeds: list[BlogSource],
    max_discovered_per_seed: int,
    pause_seconds: float,
) -> list[BlogSource]:
    discovered: list[BlogSource] = []
    seen_domains = {domain_from_url(src.base_url) for src in seeds}
    for src in seeds:
        try:
            document = fetch_text(src.base_url)
        except RuntimeError:
            continue
        candidates = extract_candidate_urls(document, src.base_url)
        random.shuffle(candidates)
        per_seed_count = 0
        for candidate in candidates:
            domain = domain_from_url(candidate)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            discovered.append(
                BlogSource(
                    blog_name=make_blog_name(candidate),
                    base_url=candidate,
                    subject=src.subject,
                    popularity="low",
                    origin="discovered",
                )
            )
            per_seed_count += 1
            if per_seed_count >= max_discovered_per_seed:
                break
        time.sleep(pause_seconds)
    return discovered


def discover_sources_from_hn(day: dt.date, max_sources: int) -> list[BlogSource]:
    start = int(dt.datetime(day.year, day.month, day.day, 0, 0, tzinfo=dt.timezone.utc).timestamp())
    end = int(dt.datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=dt.timezone.utc).timestamp())
    page = 0
    per_page = 100
    seen_domains: set[str] = set()
    discovered: list[BlogSource] = []

    while len(discovered) < max_sources:
        params = {
            "tags": "story",
            "numericFilters": f"created_at_i>={start},created_at_i<={end}",
            "hitsPerPage": str(per_page),
            "page": str(page),
        }
        payload = fetch_json_url_params(HN_SEARCH_ENDPOINT, params)
        hits = payload.get("hits", []) if isinstance(payload, dict) else []
        if not hits:
            break

        for item in hits:
            if len(discovered) >= max_sources:
                break
            if not isinstance(item, dict):
                continue
            raw_url = item.get("url")
            if not isinstance(raw_url, str) or not raw_url.strip():
                continue
            canonical = canonical_source_url(raw_url)
            if not canonical or not looks_like_blog_url(canonical):
                continue
            domain = domain_from_url(canonical)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            discovered.append(
                BlogSource(
                    blog_name=make_blog_name(canonical),
                    base_url=canonical,
                    subject="Technology",
                    popularity="low",
                    origin="discovered-hn",
                )
            )

        nb_pages = payload.get("nbPages", 0) if isinstance(payload, dict) else 0
        if page >= (nb_pages - 1):
            break
        page += 1

    return discovered


def load_source_registry(path: Path) -> dict[str, dict[str, str | int]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, dict[str, str | int]] = {}
    for domain, record in payload.items():
        if not isinstance(domain, str) or not isinstance(record, dict):
            continue
        base_url = record.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            continue
        cleaned[domain] = {
            "blog_name": str(record.get("blog_name", make_blog_name(base_url))),
            "base_url": base_url,
            "subject": str(record.get("subject", "Technology")),
            "popularity": str(record.get("popularity", "low")),
            "origin": str(record.get("origin", "discovered")),
            "success_count": int(record.get("success_count", 0)),
            "last_seen": str(record.get("last_seen", "")),
        }
    return cleaned


def registry_to_sources(registry: dict[str, dict[str, str | int]], max_sources: int) -> list[BlogSource]:
    ranked = sorted(
        registry.values(),
        key=lambda x: (int(x.get("success_count", 0)), str(x.get("last_seen", ""))),
        reverse=True,
    )
    selected: list[BlogSource] = []
    for record in ranked[:max_sources]:
        base_url = str(record.get("base_url", ""))
        if not base_url:
            continue
        selected.append(
            BlogSource(
                blog_name=str(record.get("blog_name", make_blog_name(base_url))),
                base_url=base_url,
                subject=str(record.get("subject", "Technology")),
                popularity=str(record.get("popularity", "low")),
                origin=str(record.get("origin", "discovered")),
            )
        )
    return selected


def update_source_registry(
    registry: dict[str, dict[str, str | int]],
    run_sources: list[BlogSource],
    entries: list[ArchiveEntry],
    seen_date: dt.date,
) -> dict[str, dict[str, str | int]]:
    captures_by_domain: dict[str, int] = {}
    for entry in entries:
        domain = domain_from_url(entry.original_url)
        if not domain:
            continue
        captures_by_domain[domain] = captures_by_domain.get(domain, 0) + 1

    for src in run_sources:
        domain = domain_from_url(src.base_url)
        if not domain:
            continue
        existing = registry.get(domain, {})
        registry[domain] = {
            "blog_name": src.blog_name,
            "base_url": src.base_url,
            "subject": src.subject,
            "popularity": src.popularity,
            "origin": src.origin,
            "success_count": int(existing.get("success_count", 0)) + captures_by_domain.get(domain, 0),
            "last_seen": seen_date.isoformat(),
        }
    return registry


def save_source_registry(path: Path, registry: dict[str, dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def cdx_query(base_url: str, day: dt.date, max_results: int) -> list[tuple[str, str]]:
    from_ts = day.strftime("%Y%m%d") + "000000"
    to_ts = day.strftime("%Y%m%d") + "235959"

    common_params = {
        "url": urllib.parse.urljoin(base_url, "*"),
        "from": from_ts,
        "to": to_ts,
        "filter": ["statuscode:200", "mimetype:text/html"],
        "fl": "timestamp,original",
        "collapse": "urlkey",
        "limit": str(max_results),
    }

    # Primary path: JSON output.
    json_params = dict(common_params)
    json_params["output"] = "json"
    json_query = urllib.parse.urlencode(json_params, doseq=True)
    json_url = f"{CDX_ENDPOINT}?{json_query}"

    cleaned: list[tuple[str, str]] = []
    try:
        payload = fetch_json(json_url)
        if payload and len(payload) > 1:
            rows = payload[1:]  # Skip header.
            for row in rows:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                ts, original = row[0], row[1]
                cleaned.append((ts, original))
    except RuntimeError:
        # Fall back to text mode; some environments/proxies intermittently
        # reject or mangle JSON responses for this endpoint.
        pass

    if cleaned:
        return cleaned

    # Fallback path: plain-text output where each row is:
    # "<timestamp> <original-url>"
    text_params = dict(common_params)
    text_params["output"] = "txt"
    text_query = urllib.parse.urlencode(text_params, doseq=True)
    text_url = f"{CDX_ENDPOINT}?{text_query}"
    text_payload = fetch_text(
        text_url,
        timeout=20,
        retries=2,
        max_bytes=120_000,
        use_stream_read=True,
    )

    for line in text_payload.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        ts, original = parts[0].strip(), parts[1].strip()
        if ts and original:
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


def log_step(message: str) -> None:
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}")


def collect_for_year(
    year: int,
    month: int,
    day: int,
    max_per_source_year: int,
    request_pause_seconds: float,
    sources: list[BlogSource],
) -> list[ArchiveEntry]:
    target = dt.date(year, month, day)
    entries: list[ArchiveEntry] = []
    log_step(f"Year {year}: collecting captures for {target.strftime('%B %d')} across {len(sources)} sources")

    for index, src in enumerate(sources, start=1):
        log_step(f"Year {year}: [{index}/{len(sources)}] querying {src.blog_name} ({src.origin})")
        try:
            captures = cdx_query(src.base_url, target, max_results=max(40, max_per_source_year * 5))
        except RuntimeError as exc:
            log_step(f"Year {year}: {src.blog_name} query failed ({exc})")
            continue

        sampled = choose_entries(captures, max_per_source_year)
        log_step(f"Year {year}: {src.blog_name} returned {len(captures)} captures, keeping {len(sampled)}")
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
        if sampled:
            log_step(f"Year {year}: completed {src.blog_name}")
    log_step(f"Year {year}: done, collected {len(entries)} entries")
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
    parser.add_argument(
        "--discover-sources",
        action="store_true",
        help="Discover additional blog sources from seed pages to increase variety.",
    )
    parser.add_argument(
        "--max-discovered-per-seed",
        type=int,
        default=2,
        help="Max additional sources discovered from each seed source (default: 2).",
    )
    parser.add_argument(
        "--discover-hn",
        action="store_true",
        help="Discover additional sources from Hacker News story links for the selected month/day in the current year.",
    )
    parser.add_argument(
        "--max-hn-sources",
        type=int,
        default=20,
        help="Max sources to add from Hacker News discovery (default: 20).",
    )
    parser.add_argument(
        "--source-registry",
        default=".blog_source_registry.json",
        help="JSON file used to persist discovered sources and prior success counts.",
    )
    parser.add_argument(
        "--max-registry-sources",
        type=int,
        default=50,
        help="Max sources to load from the source registry (default: 50).",
    )
    parser.add_argument(
        "--disable-registry",
        action="store_true",
        help="Disable loading/saving of discovered source registry data.",
    )
    args = parser.parse_args()
    log_step("Starting Blog Time Traveler run")

    output_path = Path(args.output)
    all_entries: list[ArchiveEntry] = []
    run_sources = list(SOURCES)
    registry_path = Path(args.source_registry)
    registry: dict[str, dict[str, str | int]] = {}

    if not args.disable_registry:
        registry = load_source_registry(registry_path)
        registry_sources = registry_to_sources(registry, max_sources=max(0, args.max_registry_sources))
        existing_domains = {domain_from_url(src.base_url) for src in run_sources}
        new_registry_sources = [src for src in registry_sources if domain_from_url(src.base_url) not in existing_domains]
        run_sources.extend(new_registry_sources)
        if new_registry_sources:
            log_step(f"Loaded {len(new_registry_sources)} sources from registry {registry_path}")

    if args.discover_sources:
        log_step("Discovering additional sources from seed blogs")
        discovered = discover_sources_from_seeds(
            run_sources,
            max_discovered_per_seed=max(0, args.max_discovered_per_seed),
            pause_seconds=max(0.0, args.pause),
        )
        if discovered:
            run_sources.extend(discovered)
            log_step(f"Discovered {len(discovered)} additional sources; total source count is {len(run_sources)}")
        else:
            log_step("No additional sources discovered; continuing with seed list")
    if args.discover_hn:
        hn_day = dt.date(today.year, args.month, args.day)
        try:
            log_step(f"Discovering sources from Hacker News for {hn_day.isoformat()}")
            hn_sources = discover_sources_from_hn(hn_day, max_sources=max(0, args.max_hn_sources))
            existing_domains = {domain_from_url(src.base_url) for src in run_sources}
            new_hn_sources = [src for src in hn_sources if domain_from_url(src.base_url) not in existing_domains]
            run_sources.extend(new_hn_sources)
            log_step(f"Discovered {len(new_hn_sources)} Hacker News sources; total source count is {len(run_sources)}")
        except RuntimeError as exc:
            log_step(f"Hacker News discovery failed ({exc}); continuing without HN-discovered sources")

    current_year = today.year
    year_offsets = build_year_offsets(args.years_back)
    log_step(f"Using date {args.month:02d}-{args.day:02d} and year offsets: {', '.join(str(v) for v in year_offsets)}")
    for delta in year_offsets:
        year = current_year - delta
        try:
            _ = dt.date(year, args.month, args.day)
        except ValueError:
            log_step(f"Skipping year {year}: invalid date {args.month:02d}-{args.day:02d}")
            continue
        log_step(f"Processing year {year} ({delta} year(s) back)")
        year_entries = collect_for_year(
            year=year,
            month=args.month,
            day=args.day,
            max_per_source_year=args.max_per_source_year,
            request_pause_seconds=args.pause,
            sources=run_sources,
        )
        all_entries.extend(year_entries)
        log_step(f"Year {year} complete: running total is {len(all_entries)} entries")

    log_step("Rendering HTML report")
    document = render_html(all_entries, report_date=today, year_offsets=year_offsets)
    output_path.write_text(document, encoding="utf-8")
    log_step(f"Wrote {len(all_entries)} entries to {output_path}")
    if not args.disable_registry:
        updated = update_source_registry(registry, run_sources, all_entries, seen_date=today)
        save_source_registry(registry_path, updated)
        log_step(f"Updated source registry at {registry_path} with {len(updated)} domains")


if __name__ == "__main__":
    main()
