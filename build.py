#!/usr/bin/env python3
"""
Build a set of race-time charts for the MOKU (Moku O Hawaiʻi) 2026 regatta season.

Pipeline:
  1. Scrape the HCRA results page to discover the MOKU regattas that have results.
  2. Scrape each regatta's per-event results (club, finishing time).
  3. Scrape a MOKU lane sheet for each club's flag colors.
  4. For every race classification (e.g. "Men Novice B"), emit:
       - charts/<slug>.html : full interactive Chart.js page (band + per-team lines,
                              legend, title, axes, mouseover tooltips). Supports
                              ?thumb to render a simplified version (no legend/title/axes).
       - thumbs/<slug>.png  : simplified thumbnail, rendered via headless Chrome.
  5. Emit index.html : a flex-grid gallery of thumbnails linked to the chart pages,
       grouped into Keiki / Men / Women / Mixed sections with pastel cell backgrounds.

Usage:  python3 build.py            (full build)
        python3 build.py --no-thumbs  (skip the Chrome screenshot pass)
"""

import json
import os
import re
import subprocess
import sys
import urllib.request

BASE = "https://www.hcrapaddler.com/"
ROOT = os.path.dirname(os.path.abspath(__file__))
WWW = os.path.join(ROOT, "www")
CACHE = os.path.join(ROOT, ".cache")

# --- club flag color name -> hex -------------------------------------------------
COLORMAP = {
    "red": "#D32F2F", "white": "#FFFFFF", "blue": "#1565C0", "light blue": "#4FC3F7",
    "green": "#2E7D32", "light yellow": "#FFF176", "yellow": "#FBC02D", "gold": "#D4AF37",
    "orange": "#EF6C00", "purple": "#7B1FA2", "turquoise": "#1DE9B6", "beige": "#CBB994",
    "black": "#000000", "rust brown": "#8D5524", "rust": "#8D5524", "brown": "#795548",
}

# --- pastel section backgrounds --------------------------------------------------
SECTIONS = ["Keiki", "Men", "Women", "Mixed"]
PASTEL = {"Keiki": "#FFF4CC", "Men": "#D9E8FB", "Women": "#FBDCEC", "Mixed": "#DDF0DA"}


def fetch(url):
    """Fetch a URL (with a small on-disk cache) and return text."""
    os.makedirs(CACHE, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", url)[:150] + ".html"
    path = os.path.join(CACHE, key)
    if os.path.exists(path):
        return open(path, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (hcra-stats build)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except Exception as exc:  # future regattas / lane sheets may 404
        print("  (fetch failed: %s -> %s)" % (url, exc))
        txt = ""
    open(path, "w", encoding="utf-8").write(txt)
    return txt


# --- scraping --------------------------------------------------------------------
def moku_regattas(main_html):
    """Return [(rid, date, name)] for MOKU regattas, in listed order."""
    s = main_html.find("MOKU (Moku")
    e = main_html.find("OHCRA (")
    seg = main_html[s:e]
    out = []
    for date, rid, name in re.findall(
        r'(\d{4}-\d{2}-\d{2}).*?<A href="\?view=byevent&rid=(\d+)"[^>]*>(.*?)</A>', seg, re.S
    ):
        out.append((rid, date, re.sub(r"\s+", " ", name).strip()))
    return out


def parse_time(s):
    m = re.match(r"\s*(\d+):(\d+(?:\.\d+)?)\s*$", s)
    return round(int(m.group(1)) * 60 + float(m.group(2)), 2) if m else None


ROW_RE = re.compile(
    r'WIDTH=5%[^>]*ALIGN="LEFT"[^>]*>([^<]*)</TD>'      # place cell (may carry STYLE/TITLE)
    r'<TD[^>]*colspan=3[^>]*TITLE="\d+">([^<]+)</TD>'   # club full name
    r"<TD class='time-column'[^>]*>([^<]*)</TD>"         # time (may be empty)
)


def parse_results(html):
    """Return {event_no: {"name", "clubs": {full: secs}, "marks": {full: [kind, secs]}}}.

    Finishers (numeric place) go in "clubs"; DQ / SCR go in "marks" as
    ["dq", secs|None] / ["scr", None] (secs present when a DQ'd crew has a time)."""
    events = re.findall(r"Event (\d+):\s*([^<]+?)\s*</A>", html)
    blocks = re.split(r"Event \d+:\s*[^<]+?\s*</A>", html)
    out = {}
    for i, (no, name) in enumerate(events):
        clubs, marks = {}, {}
        for place, club, time in (m.groups() for m in ROW_RE.finditer(blocks[i + 1])):
            full = re.sub(r"\s+", " ", club).strip()
            ps = place.strip().upper()
            secs = parse_time(time)
            if ps.isdigit():
                if secs is not None:
                    clubs[full] = secs
            elif ps.startswith("DQ"):
                marks[full] = ["dq", secs]
            elif ps.startswith("SCR"):
                marks[full] = ["scr", None]
        out[int(no)] = {"name": re.sub(r"\s+", " ", name).strip(),
                        "clubs": clubs, "marks": marks}
    return out


def parse_lane_colors(html):
    """Return {club_fullname: [hex, ...]} from the lane sheet color legend."""
    m = re.search(r"COLOR.{0,8}NUMBERS", html, re.I)
    seg = html[m.start():m.start() + 6000] if m else html
    out = {}
    for club, colors in re.findall(r"<B>([^<]+)</B>\s*-\s*([^,;]+)", seg):
        hexes = []
        for part in colors.split("/"):
            hexes.append(COLORMAP.get(part.strip().lower(), "#888888"))
        out[re.sub(r"\s+", " ", club).strip()] = hexes
    return out


# --- derived helpers -------------------------------------------------------------
def short_name(full):
    return re.sub(r"\s+(Outrigger Canoe Club|Canoe Club|Outrigger Team)\b", "", full).strip()


def nice(name):
    """Title-case an ALL-CAPS regatta name, respecting the ʻokina and macrons."""
    def word(w):
        if not w:
            return w
        if w[0] in "ʻ'`":
            return w[0] + w[1:2].upper() + w[2:].lower()
        return w[0].upper() + w[1:].lower()
    return " ".join(word(w) for w in name.split("/")[0].split())


def club_style(full, lane):
    cols = lane.get(full) or ["#888888"]
    primary = cols[0]
    secondary = cols[1] if len(cols) > 1 else cols[0]
    if full.startswith("Kawaihae"):
        return {"line": "#D32F2F", "point": "#FFFFFF", "emphasize": True}
    if primary.upper() == "#FFFFFF":  # white line is invisible -> use secondary, dashed
        return {"line": secondary, "point": "#FFFFFF", "dash": True}
    return {"line": primary, "point": secondary}


def normalize_name(name):
    """Fix HCRA source inconsistencies: 'Mens' -> 'Men', 'Woman' -> 'Women'."""
    name = re.sub(r'\bMens\b', 'Men', name)
    name = re.sub(r'\bWoman\b', 'Women', name)
    return name


_DIVISION_ORDER = ["novice b", "novice a", "freshmen", "freshman", "sophomore", "junior", "senior"]


def section_sort_key(name, sec):
    """Return a sort key that orders items within a section as requested."""
    n = name.lower()
    if sec == "Keiki":
        age_m = re.search(r'(\d+)', n)
        age = int(age_m.group(1)) if age_m else 999
        gender = 0 if 'girl' in n else (1 if 'boy' in n else 2)
        return (age, gender)
    if sec in ("Men", "Women"):
        if "master" not in n:
            for i, div in enumerate(_DIVISION_ORDER):
                if div in n:
                    return (0, i, 0)
        age_m = re.search(r'\((\d+)', n)
        return (1, int(age_m.group(1)) if age_m else 999, 0)
    if sec == "Mixed":
        for i, div in enumerate(["novice b", "novice a"]):
            if div in n:
                return (0, i)
        if "men and women" in n or "open" in n:
            return (1, 0)
        age_m = re.search(r'\((\d+)', n)
        return (2, int(age_m.group(1)) if age_m else 999)
    return (999,)


def section_of(name):
    n = name.lower().strip()
    if "girl" in n or "boy" in n:
        return "Keiki"
    if "mixed" in n:
        if re.search(r"mixed\s*1[0-8]\b", n):  # "Mixed 18" youth crew
            return "Keiki"
        return "Mixed"
    if "wom" in n:
        return "Women"
    if "men" in n or "man" in n:
        return "Men"
    return "Men"


def slugify(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


# --- chart page template ---------------------------------------------------------
PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>__TITLE__ — 2026 MOKU</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js"></script>
<style>html,body{margin:0;height:100%;font-family:Arial,Helvetica,sans-serif;background:#fff}
#wrap{height:100vh;padding:8px;box-sizing:border-box}</style>
</head>
<body>
<div id="wrap"><canvas id="c"></canvas></div>
<script>
const CHART = __DATA__;
const THUMB = new URLSearchParams(location.search).has("thumb");
function mmss(v){let m=Math.floor(v/60);let s=(v-m*60).toFixed(2).padStart(5,"0");return m+":"+s;}
window.onload = function () {
  const band = [
    {label:"Fastest",data:CHART.fastest,borderColor:"rgba(150,150,150,0.5)",borderWidth:1,
     pointStyle:false,fill:false,order:100,spanGaps:true},
    {label:"Slowest",data:CHART.slowest,borderColor:"rgba(150,150,150,0.5)",borderWidth:1,
     pointStyle:false,fill:"-1",backgroundColor:"rgba(170,170,170,0.45)",order:100,spanGaps:true},
  ];
  const GREY = "#b3b3b3";
  const teams = CHART.teams.map(t => {
    // In thumbnails: only Kawaihae (bold red); every other club is a thin grey line.
    const lc = THUMB ? (t.emphasize ? "#D32F2F" : GREY) : t.line;
    return {
      label:t.name, data:t.times,
      borderColor:lc, backgroundColor:lc,
      pointBackgroundColor:THUMB?lc:t.line, pointBorderColor:THUMB?lc:(t.point||"#555"),
      pointBorderWidth:THUMB?0:2,
      borderDash:(!THUMB && t.dash)?[6,4]:[],
      borderWidth:t.emphasize?4:(THUMB?1:2),
      pointRadius:THUMB?(t.emphasize?2:0):(t.emphasize?5:3),
      pointHoverRadius:t.emphasize?7:5,
      pointStyle:"circle", fill:false, spanGaps:false, order:t.emphasize?0:1,
    };
  });

  const labels = CHART.regattas.map((r,i) => [r, CHART.dates[i]]);
  new Chart(document.getElementById("c"), {
    type:"line",
    data:{labels, datasets:[...band, ...teams]},
    options:{
      maintainAspectRatio:false,
      animation:false,
      interaction:{mode:"nearest", intersect:true},
      plugins:{
        title:{display:!THUMB, text:CHART.title+" — 2026 MOKU regattas", font:{size:18}},
        legend:{display:!THUMB, labels:{filter:i=>i.text!=="Fastest"&&i.text!=="Slowest"}},
        tooltip:{enabled:!THUMB, callbacks:{
          title:items=>CHART.regattas[items[0].dataIndex]+" ("+CHART.dates[items[0].dataIndex]+")",
          label:c=>c.dataset.label+": "+mmss(c.parsed.y),
        }},
      },
      scales:{
        x:{display:!THUMB, title:{display:!THUMB, text:"Regatta"}},
        y:{display:!THUMB, title:{display:!THUMB, text:"Race time (min:sec)"},
           ticks:{callback:v=>mmss(v)}},
      },
    },
  });
};
</script>
</body>
</html>
"""


def main():
    no_thumbs = "--no-thumbs" in sys.argv

    print("Scraping main results page ...")
    main_html = fetch(BASE + "hcra_results.php?year=2026")
    regs = moku_regattas(main_html)

    # scrape each regatta; keep only those that actually have finisher times
    completed = []   # (rid, date, name, results-dict)
    lane = {}
    for rid, date, name in regs:
        html = fetch(BASE + "hcra_results.php?view=byevent&rid=%s" % rid)
        results = parse_results(html)
        if not any(ev["clubs"] for ev in results.values()):
            print("  skip (no results yet): %s %s" % (date, name))
            continue
        completed.append((rid, date, name, results))
        if not lane:
            lane = parse_lane_colors(fetch(BASE + "members/hcra_laneform.php?reg_id=%s" % rid))
        print("  %s  %s  (%d events with results)" %
              (date, name, sum(1 for ev in results.values() if ev["clubs"])))

    if not completed:
        print("No completed MOKU regattas found.")
        return
    print("Lane-sheet colors for %d clubs." % len(lane))

    reg_short = [short_name(nice(n)) for (_, _, n, _) in completed]
    reg_dates = [d[5:] for (_, d, _, _) in completed]  # MM-DD

    # union of event numbers that have any results
    event_nos = sorted({no for (_, _, _, res) in completed
                        for no, ev in res.items() if ev["clubs"]})

    os.makedirs(os.path.join(WWW, "charts"), exist_ok=True)
    os.makedirs(os.path.join(WWW, "thumbs"), exist_ok=True)

    classifications = []  # (event_no, name, section, slug)
    for no in event_nos:
        # canonical classification name = first regatta that ran this event
        name = normalize_name(next(res[no]["name"] for (_, _, _, res) in completed
                                   if no in res and res[no]["clubs"]))
        clubs = []
        for (_, _, _, res) in completed:
            clubs += list(res.get(no, {}).get("clubs", {}).keys())
        clubs = sorted(set(clubs), key=lambda c: (not c.startswith("Kawaihae"), short_name(c)))

        teams = []
        for full in clubs:
            times = [res.get(no, {}).get("clubs", {}).get(full) for (_, _, _, res) in completed]
            st = club_style(full, lane)
            teams.append({"name": short_name(full), **st, "times": times})

        fastest, slowest = [], []
        for ci in range(len(completed)):
            vals = [t["times"][ci] for t in teams if t["times"][ci] is not None]
            fastest.append(min(vals) if vals else None)
            slowest.append(max(vals) if vals else None)

        data = {"title": name, "regattas": reg_short, "dates": reg_dates,
                "fastest": fastest, "slowest": slowest, "teams": teams}
        slug = slugify(name)
        html = PAGE.replace("__TITLE__", name).replace(
            "__DATA__", json.dumps(data, ensure_ascii=False))
        open(os.path.join(WWW, "charts", slug + ".html"), "w", encoding="utf-8").write(html)
        classifications.append((no, name, section_of(name), slug))

    print("Wrote %d chart pages." % len(classifications))

    # thumbnails via headless Chrome
    if not no_thumbs:
        print("Rendering thumbnails ...")
        for no, name, sec, slug in classifications:
            src = "file://" + os.path.join(WWW, "charts", slug + ".html") + "?thumb=1"
            out = os.path.join(WWW, "thumbs", slug + ".png")
            subprocess.run(
                [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                 "--screenshot=" + out, "--window-size=480,300",
                 "--virtual-time-budget=2500", src],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  %d thumbnails." % len(classifications))

    # index gallery
    write_index(classifications)
    print("Wrote index.html")


def write_index(classifications):
    by_sec = {s: [] for s in SECTIONS}
    for no, name, sec, slug in classifications:
        by_sec[sec].append((no, name, slug))

    parts = ["""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>MOKU 2026 — Race-Time Charts</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;margin:24px;color:#222;background:#fafafa}
  .logo{text-align:center;margin:8px 0 28px}
  .logo img{max-width:241px;height:auto}
  h2{margin:28px 0 12px;border-bottom:2px solid #ddd;padding-bottom:4px}
  .grid{display:flex;flex-wrap:wrap;gap:14px}
  .cell{width:240px;border-radius:10px;padding:10px;box-sizing:border-box;
        text-decoration:none;color:#222;box-shadow:0 1px 3px rgba(0,0,0,.18);
        transition:transform .08s ease, box-shadow .08s ease}
  .cell:hover{transform:translateY(-2px);box-shadow:0 4px 10px rgba(0,0,0,.25)}
  .cell .name{font-weight:bold;font-size:14px;margin-bottom:8px;text-align:center}
  .cell img{width:100%;height:auto;display:block;border-radius:6px;background:#fff;
            border:1px solid rgba(0,0,0,.08)}
</style>
</head>
<body>
<div class="logo"><img src="https://d36m266ykvepgv.cloudfront.net/uploads/media/2IyyAC2srE/c-241-200/logo.png" alt="Kawaihae Canoe Club"></div>
"""]
    for sec in SECTIONS:
        items = sorted(by_sec[sec], key=lambda x: section_sort_key(x[1], sec))
        if not items:
            continue
        parts.append('<h2>%s</h2>\n<div class="grid">\n' % sec)
        for no, name, slug in items:
            parts.append(
                '  <a class="cell" style="background:%s" href="charts/%s.html">'
                '<div class="name">%s</div>'
                '<img src="thumbs/%s.png" alt="%s" loading="lazy"></a>\n'
                % (PASTEL[sec], slug, name, slug, name))
        parts.append("</div>\n")
    parts.append("</body>\n</html>\n")
    os.makedirs(WWW, exist_ok=True)
    open(os.path.join(WWW, "index.html"), "w", encoding="utf-8").write("".join(parts))


if __name__ == "__main__":
    main()
