# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a statistics site generator for the Kawaihae Canoe Club (KCC) MOKU (Moku O Hawaiʻi) outrigger canoe racing season. It scrapes race results from the HCRA website, aggregates race-time data by classification, and generates interactive charts and thumbnails.

**Output:** Interactive Chart.js HTML pages, PNG thumbnails, and a gallery index.

## Build & Development Commands

```sh
# Full build: fetch data, generate charts, and render thumbnails
python3 build.py

# Build without thumbnail rendering (faster for development)
python3 build.py --no-thumbs
```

**Requirements:**
- Python 3
- Node.js (for thumbnail rendering via chartjs-node-canvas)
- Dependencies: `npm install` (installs chart.js and chartjs-node-canvas)

## Architecture

The entire pipeline is in `build.py` with the following stages:

### 1. Data Scraping
- `fetch()` - Downloads with caching from `www.hcrapaddler.com`
- `moku_regattas()` - Extracts MOKU regatta IDs, dates, and names from the main results page
- `parse_results()` - Parses per-event results (club names, finishing times, disqualifications)
- `parse_lane_colors()` - Extracts club flag colors from lane sheets to style the charts

**Key parsing:**
- Time format: `MM:SS.SS` → stored as seconds (float)
- Results include numeric placements, DQ (disqualified), and SCR (scratched) entries
- Club names are normalized via `short_name()` to remove redundant suffixes

### 2. Chart Data Generation
For each unique event/classification (e.g., "Men Novice B"):
- Collect all finishing times across completed regattas
- Calculate fastest/slowest band (min/max per regatta)
- Assign line/point colors based on club flag colors
- Special handling: KCC (Kawaihae) is red, emphasized; white-flagged clubs use dashed lines
- Track DQ entries separately for visual marking (crosshair points)

**Sections (categories):** Keiki, Men, Women, Mixed — sorted by `section_sort_key()` using:
- Keiki: age (from name regex) then gender (girl < boy < other)
- Men/Women: novice B/A, freshman, sophomore, junior, senior, then Masters by age
- Mixed: novice divisions, then "Men and Women" / Open, then Masters

### 3. Chart Generation
Each classification gets:
- `charts/<slug>.html` - Full interactive page with legend, title, axes, tooltips
- Uses embedded JSON data (`__DATA__` placeholder in template)
- Supports `?thumb` query param to hide UI elements for thumbnail rendering
- Tooltips show regatta name, date, and finisher time

**Summary chart** (`charts/summary.html`):
- Scatter plot of median finish times by classification across all sections
- X-axis: unique base labels (stripped gender prefix via `base_label()`)
- Error bars show min/max range across regattas
- Grouped by section with color coding (Men: blue, Women: pink, Mixed: green)

### 4. Thumbnail Rendering
Node scripts render PNG thumbnails via `chartjs-node-canvas`:
- `render_thumb.js` - Full chart thumbnail (480x300)
- `render_summary_thumb.js` - Summary chart thumbnail (640x300)
- Reads JSON via stdin, writes PNG to file path in argv[2]
- Simplified styling (no legend/title/axes)

### 5. Index Gallery
`write_index()` generates `docs/index.html`:
- Flex-grid layout of classification thumbnails
- Grouped by section with pastel background colors
- Responsive (auto-fill columns, adjusts for mobile/tablet/desktop)
- Summary chart at the bottom
- KCC logo and section headings

## Key Data Structures

**Classification tuple:** `(event_no, name, section, slug, data)`
- `slug`: slugified classification name (for filenames)
- `data`: dict with `{"title", "regattas", "dates", "fastest", "slowest", "teams", "dqs"}`
  - `teams`: list of `{"name", "line", "point", "emphasize", "dash", "times"}`
  - `times`: list of seconds or None (one value per completed regatta)
  - `dqs`: list of `[secs, kind]` or None for each regatta (KCC DQ entries only)

**Club styling** (`club_style()`):
- Primary color from lane sheet; secondary for point markers
- KCC: red line (#D32F2F), white points, emphasized
- White-flagged: use secondary color, dashed line

## Important Implementation Details

**Normalization:**
- `normalize_name()` - Fixes "Mens" → "Men", "Woman" → "Women"
- `short_name()` - Strips club suffix ("Outrigger Canoe Club", etc.)
- `nice()` - Title-cases regatta names while respecting ʻokina and macrons
- `slugify()` - Creates URL-safe filenames

**Time formatting in UI:**
- `mmss(v)` JavaScript helper converts seconds to "M:SS.SS"

**Division order** (for sorting):
- `_DIVISION_ORDER = ["novice b", "novice a", "freshmen", "freshman", "sophomore", "junior", "senior"]`

**Color mapping** (`COLORMAP`):
- 15+ named colors from lane sheets mapped to hex codes

**Pastel backgrounds:**
- Keiki: #FFF4CC, Men: #D9E8FB, Women: #FBDCEC, Mixed: #DDF0DA

## Output Structure

```
docs/
  index.html                    # Gallery page
  CNAME                         # GitHub Pages custom domain
  charts/
    <slug>.html                 # One per classification
    summary.html                # Cross-classification median times
  thumbs/
    <slug>.png                  # PNG thumbnails for each classification
    summary.png                 # Summary chart thumbnail
```

## Configuration & Caching

- `.cache/` - On-disk HTML cache for fetched pages (never re-downloaded unless deleted)
- `.claude/settings.local.json` - Permissions for `WebFetch(domain:www.hcrapaddler.com)`

## Development Notes

- The scraper is resilient to missing data (future regattas may 404)
- Lane sheet colors may not exist for all clubs; falls back to gray (#888888)
- DQ entries only tracked for KCC crews; other clubs' DQs ignored
- Chart aspect ratio: 1.5 (width:height) for responsive sizing
- Thumbnail rendering can be slow; use `--no-thumbs` during development

## Git History Context

Recent changes include:
- DQ notation enhancements
- Summary chart addition with error bars
- Mobile appearance improvements
- Migration to Node-based rendering (away from Chrome headless)
- GitHub Pages setup with custom domain (CNAME)
