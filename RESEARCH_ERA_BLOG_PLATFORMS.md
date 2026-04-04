# Era-based blogging platform research (1991–2026)

This guide is optimized for **high-variety blog discovery by date**. It picks one or two dominant blogging services per era (5-year windows across the last 35 years), then documents practical date-search methods you can automate.

> Note: “Most popular” is estimated from widely cited launch/adoption history and currently available platform usage reporting. Popularity in early eras is less precisely measured than modern web analytics.

## Quick strategy for date-driven variety

1. Build an era-weighted source pool (older and newer platforms).
2. For each platform, use native archive URLs first.
3. If native archives are weak, use search-engine date constraints (`site:` + year/month tokens).
4. For dead/declined platforms, use Wayback capture queries.

---

## Era map: dominant blogging services + how to find posts by date

| Era | Most popular services in era (representative) | Why this era pick | Date discovery method (automation-friendly) |
|---|---|---|---|
| 1991–1995 | **Personal homepages (GeoCities/Tripod/independent diaries)** | Pre-platform blogging era; personal web journals dominated. | Use Wayback CDX by domain/path and calendar day. Pattern: `web.archive.org/cdx/search/cdx?url=<domain>/*&from=1991&to=1995&output=json` then filter timestamps by month/day. |
| 1996–2000 | **Open Diary, LiveJournal, Blogger (late 1999)** | First mainstream hosted diary/blog systems. | **LiveJournal:** date URLs commonly follow `/YYYY/MM/DD/` on user journals; enumerate by date path and fallback to Wayback. **Blogger:** post permalinks include `/YYYY/MM/slug.html`; probe year/month and extract posts. |
| 2001–2005 | **Blogger, LiveJournal, TypePad/Movable Type** | Blogging breakout period; hosted + self-publish tools exploded. | **Blogger:** crawl archive widgets (`/search?updated-max=` patterns or archive links) and direct `YYYY/MM`. **TypePad/MT blogs:** often `/YYYY/MM/post-title.html`; discover from homepage archive links then paginate month pages. |
| 2006–2010 | **WordPress, Blogger, Tumblr (from 2007)** | WordPress became core publishing stack; Tumblr popularized microblogging. | **WordPress:** monthly archives at `/YYYY/MM/` are common when date permalinks enabled; also parse `/archives/` or calendar widgets. **Tumblr:** append `/archive` to blog URL, then step through month grid. |
| 2011–2015 | **Tumblr, WordPress, Medium (launched 2012)** | Social/discovery-centric blogging and publishing networks. | **Medium:** use publication/user pages + time tokens in URL (`/p/<id>` posts still expose publish dates in metadata); sort via feed/API mirrors where available. **Tumblr:** `/archive` + tag pages + month navigation. |
| 2016–2020 | **WordPress, Medium, Ghost, Dev.to** | Independent publishing + developer blogging growth. | **Ghost:** many sites expose `/archive/`, `/tag/<tag>/`, RSS dates; parse structured metadata (`article:published_time`). **Dev.to:** query by tag/date via platform search and API date fields. |
| 2021–2026 | **Substack, WordPress, Medium, LinkedIn newsletters/indie stacks** | Newsletter-blog convergence and creator-led publishing. | **Substack:** use `/archive` pages (newest→oldest) and post metadata dates; filter by date window in crawler. **WordPress/Medium:** continue monthly archives and metadata extraction. |

---

## Platform-specific “find by date” playbook

## 1) Blogger
- **Best signal:** permalink format usually includes year/month: `/YYYY/MM/post-slug.html`.
- **Discovery approach:**
  - Start at homepage and capture archive links.
  - Regex for `/(20\d\d|19\d\d)/(0[1-9]|1[0-2])/` in links.
  - Use Wayback CDX when blog is dormant.

## 2) LiveJournal
- **Best signal:** calendar/day-based journal navigation on user pages.
- **Discovery approach:**
  - Probe user root and calendar pages.
  - Enumerate target dates (`YYYY/MM/DD`) and verify entries.
  - For missing journals, use Wayback snapshots by user domain/path.

## 3) WordPress (hosted + self-hosted)
- **Best signal:** monthly archives and date permalinks on many sites.
- **Discovery approach:**
  - Try `/YYYY/MM/` and `/archives/`.
  - Parse `<time datetime>` and JSON-LD `datePublished`.
  - If no archive URL, collect posts then date-filter from metadata.

## 4) Tumblr
- **Best signal:** `/<blog>/archive` visual month/day grid.
- **Discovery approach:**
  - Always attempt `https://<blog>.tumblr.com/archive` (or custom-domain `/archive`).
  - Crawl month sections; preserve post IDs and timestamps.
  - Respect mature-content/archive visibility limitations.

## 5) Medium
- **Best signal:** publish date in page metadata; publication feeds.
- **Discovery approach:**
  - Crawl publication/user pages and extract `datePublished`.
  - Keep canonical URL + publish timestamp table for date querying.
  - Use tag/publication archive pages when present.

## 6) Substack
- **Best signal:** `/archive` listing with explicit publish dates.
- **Discovery approach:**
  - Pull archive index first, then post pages.
  - Store timezone-normalized publish datetime.
  - Backfill older years with Wayback if posts were deleted/paywalled.

## 7) Ghost / Dev.to / modern indie blogs
- **Best signal:** RSS/Atom dates + structured metadata.
- **Discovery approach:**
  - Prefer feeds for fast date indexing.
  - Enrich with on-page metadata for canonical post URLs.

---

## Source links used for this research

- WordPress usage statistics: https://w3techs.com/technologies/comparison/cm-wordpress
- Blogger (history + platform): https://en.wikipedia.org/wiki/Blogger_(service)
- LiveJournal (history): https://en.wikipedia.org/wiki/LiveJournal
- Open Diary (history): https://en.wikipedia.org/wiki/Open_Diary
- Tumblr (history + usage context): https://en.wikipedia.org/wiki/Tumblr
- Medium (platform history): https://en.wikipedia.org/wiki/Medium_(website)
- Substack milestone reporting (5M paid subs): https://www.axios.com/2025/07/17/substack-newsletter-funding-creator-economy
- Blogger developer URL format context: https://developers.google.com/blogger/docs/2.0/developers_guide_protocol

---

## Suggested integration into `Blog Time Traveler`

1. Add an `era` field to `BlogSource` (`early-web`, `blog-boom`, `social-blog`, `newsletter-era`).
2. Rotate discovery seeds by era per day to avoid source repetition.
3. Add per-platform date adapters:
   - `BloggerDateAdapter`, `WordPressDateAdapter`, `TumblrArchiveAdapter`, `SubstackArchiveAdapter`.
4. Fallback chain per source:
   - Native archive -> feed metadata -> site search -> Wayback CDX.
5. Track `date_discovery_confidence` in the source registry for quality control.
