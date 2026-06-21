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
WWW = os.path.join(ROOT, "docs")

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
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as exc:  # future regattas / lane sheets may 404
        print("  (fetch failed: %s -> %s)" % (url, exc))
        return ""


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
                marks[full] = [ps, secs]
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


def base_label(name):
    """Strip gender prefix so Men/Women/Mixed classifications share an X-axis label."""
    n = re.sub(r'\bGolden\s+', '', name)                      # "Golden Masters (55)" → "Masters (55)"
    n = re.sub(r'^Senior\s+(Men|Women)\s+', 'Senior ', n)     # "Senior Men Masters" → "Senior Masters"
    n = re.sub(r'^(Men|Women|Mixed|Girls|Boys)\s+', '', n)     # strip leading gender/section word
    n = re.sub(r'^Boys and Girls\s+', '', n)                   # "Boys and Girls 12" → "12"
    n = re.sub(r'\s*&\s*Under\b', '', n)                       # "18 & Under" → "18"
    n = re.sub(r'(?:Senior\s+)?Masters?\s*', '', n)            # "Masters (40)" → "(40)"
    n = re.sub(r'[()]', '', n)                                  # "(40)" → "40", "(65)" → "65"
    n = re.sub(r'\s*yrs\b', '', n, flags=re.I)                 # "60 yrs" → "60"
    n = re.sub(r'^Men and Women$', 'Open Mixed', n)
    return n.strip()


# --- chart page template ---------------------------------------------------------
PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>__TITLE__ — KCC 2026</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js"></script>
<style>html,body{margin:0;height:100%;font-family:Arial,Helvetica,sans-serif;background:#fff}
#wrap{height:100%;padding:8px;box-sizing:border-box}</style>
</head>
<body>
<div id="wrap"><canvas id="c" style="width:100%"></canvas></div>
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
  const dqs = CHART.dqs || [];
  const teams = CHART.teams.map(t => {
    const lc = THUMB ? (t.emphasize ? "#D32F2F" : GREY) : t.line;
    if (!t.emphasize) {
      return {
        label:t.name, data:t.times,
        borderColor:lc, backgroundColor:lc,
        pointBackgroundColor:THUMB?lc:t.line, pointBorderColor:THUMB?lc:(t.point||"#555"),
        pointBorderWidth:THUMB?0:2,
        borderDash:(!THUMB && t.dash)?[6,4]:[],
        borderWidth:THUMB?1:2,
        pointRadius:THUMB?0:3, pointHoverRadius:5,
        pointStyle:"circle", fill:false, spanGaps:false, order:1,
      };
    }
    const dqIdx = new Set(dqs.map((d,i) => d!=null?i:-1).filter(i=>i>=0));
    const data = t.times.map((v,i) => v!==null ? v : (dqs[i]!=null ? dqs[i][0] : null));
    return {
      label:t.name, data,
      borderColor:lc, backgroundColor:lc,
      pointBackgroundColor:data.map((v,i) => dqIdx.has(i) ? "transparent" : (THUMB?lc:t.line)),
      pointBorderColor:data.map((v,i) => dqIdx.has(i) ? lc : (THUMB?lc:(t.point||"#555"))),
      pointBorderWidth:data.map((v,i) => dqIdx.has(i) ? 2 : (THUMB?0:2)),
      borderDash:[],
      borderWidth:4,
      pointRadius:data.map((v,i) => v===null?0 : dqIdx.has(i)?(THUMB?4:7):(THUMB?2:5)),
      pointHoverRadius:data.map((v,i) => dqIdx.has(i)?9:7),
      pointStyle:data.map((v,i) => dqIdx.has(i)?"crossRot":"circle"),
      fill:false, spanGaps:false, order:0,
    };
  });

  const labels = CHART.regattas.map((r,i) => [r, CHART.dates[i]]);
  new Chart(document.getElementById("c"), {
    type:"line",
    data:{labels, datasets:[...band, ...teams]},
    options:{
      responsive:true, maintainAspectRatio:true, aspectRatio:1.5,
      animation:false,
      interaction:{mode:"nearest", intersect:true},
      plugins:{
        title:{display:!THUMB, text:"KCC — "+CHART.title+" — 2026 regattas", font:{size:18}},
        legend:{display:!THUMB, labels:{filter:i=>i.text!=="Fastest"&&i.text!=="Slowest"}},
        tooltip:{enabled:!THUMB, callbacks:{
          title:items=>CHART.regattas[items[0].dataIndex]+" ("+CHART.dates[items[0].dataIndex]+")",
          label:c=>{const d=(CHART.dqs||[])[c.dataIndex];const dq=c.dataset.order===0&&d!=null;return c.dataset.label+": "+mmss(c.parsed.y)+(dq?" ("+d[1]+")":"");},
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

# --- summary chart template -------------------------------------------------------
SUMMARY_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KCC 2026 — Season Overview</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js"></script>
<style>html,body{margin:0;height:100%;font-family:Arial,Helvetica,sans-serif;background:#fff}
#wrap{height:100%;padding:8px;box-sizing:border-box}</style>
</head>
<body>
<div id="wrap"><canvas id="c" style="width:100%"></canvas></div>
<script>
const SUMMARY = __SUMMARY_DATA__;
const THUMB = new URLSearchParams(location.search).has("thumb");
function mmss(v){let m=Math.floor(v/60);let s=(v-m*60).toFixed(2).padStart(5,"0");return m+":"+s;}

const errorBarPlugin = {
  id:"errorBars",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    chart.data.datasets.forEach((ds, di) => {
      if (!ds.errorBars) return;
      const meta = chart.getDatasetMeta(di);
      if (meta.hidden) return;
      meta.data.forEach(pt => {
        if (!pt || isNaN(pt.x) || isNaN(pt.y)) return;
        const eb = ds.errorBars[Math.round(chart.scales.x.getValueForPixel(pt.x))];
        if (!eb) return;
        const x = pt.x;
        const yLo = chart.scales.y.getPixelForValue(eb.lo);
        const yHi = chart.scales.y.getPixelForValue(eb.hi);
        const cap = THUMB ? 3 : 5;
        ctx.save();
        ctx.strokeStyle = ds.borderColor;
        ctx.lineWidth = THUMB ? 1 : 1.5;
        ctx.beginPath();
        ctx.moveTo(x, yLo); ctx.lineTo(x, yHi);
        ctx.moveTo(x-cap, yLo); ctx.lineTo(x+cap, yLo);
        ctx.moveTo(x-cap, yHi); ctx.lineTo(x+cap, yHi);
        ctx.stroke();
        ctx.restore();
      });
    });
  }
};

window.onload = function() {
  const datasets = SUMMARY.datasets.map(ds => ({
    label: ds.label, data: ds.data.filter(p => p !== null), errorBars: ds.errorBars,
    borderColor: ds.borderColor, backgroundColor: ds.borderColor,
    pointRadius: THUMB ? 3 : 5, pointHoverRadius: 7, pointStyle: "circle",
  }));
  new Chart(document.getElementById("c"), {
    type: "scatter",
    data: {datasets},
    options: {
      responsive: true, maintainAspectRatio: true, aspectRatio: 1.5, animation: false,
      interaction: {mode:"nearest", intersect:true},
      plugins: {
        title: {display:!THUMB, text:"KCC 2026 — Median Finish Times by Classification", font:{size:18}},
        legend: {display:!THUMB},
        tooltip: {enabled:!THUMB, callbacks:{
          title: items => SUMMARY.labels[Math.round(items[0].parsed.x)],
          label: c => {
            const eb = c.dataset.errorBars[Math.round(c.parsed.x)];
            const med = c.dataset.label + ": " + mmss(c.parsed.y);
            return eb ? med + "  (" + mmss(eb.lo) + " – " + mmss(eb.hi) + ")" : med;
          },
        }},
      },
      scales: {
        x: {
          display:!THUMB, type:"linear",
          min:-0.5, max:SUMMARY.labels.length-0.5,
          afterBuildTicks(axis) {
            axis.ticks = Array.from({length:SUMMARY.labels.length}, (_,i) => ({value:i}));
          },
          ticks:{
            callback: v => SUMMARY.labels[v] || "",
            maxRotation:45, minRotation:45, font:{size:11},
          },
        },
        y: {display:!THUMB, title:{display:!THUMB, text:"Finish time (min:sec)"},
            min:0, max:SUMMARY.yMax,
            ticks:{stepSize:15, callback:v=>mmss(v)}},
      },
    },
    plugins: [errorBarPlugin],
  });
};
</script>
</body>
</html>
"""


def build_summary(classifications):
    """Build data for the cross-classification summary scatter chart (all sections)."""
    SERIES_DEF = [
        ("Men",   lambda name, sec: sec == "Men"   or (sec == "Keiki" and "boy"  in name.lower() and "mixed" not in name.lower())),
        ("Women", lambda name, sec: sec == "Women" or (sec == "Keiki" and "girl" in name.lower() and "mixed" not in name.lower())),
        ("Mixed", lambda name, sec: "mixed" in name.lower()),
    ]
    COLORS   = {"Men": "#1565C0", "Women": "#AD1457", "Mixed": "#2E7D32"}
    OFFSETS  = {"Men": 0.0,       "Women": 0.15,      "Mixed": 0.30}

    # Ordered unique X labels: only include positions covered by an active series
    all_items = []
    for sec in SECTIONS:
        sec_items = sorted([(no, name, s, slug, data)
                            for no, name, s, slug, data in classifications if s == sec],
                           key=lambda x: section_sort_key(x[1], sec))
        all_items.extend(sec_items)

    active = [pred for _, pred in SERIES_DEF]
    seen, labels = {}, []
    for no, name, sec, slug, data in all_items:
        if not any(p(name, sec) for p in active):
            continue
        bl = base_label(name)
        if bl not in seen:
            seen[bl] = len(labels)
            labels.append(bl)

    datasets = []
    for ser_name, predicate in SERIES_DEF:
        data_pts   = [None] * len(labels)
        error_bars = [None] * len(labels)
        offset = OFFSETS[ser_name]
        for no, name, sec, slug, data in all_items:
            if not predicate(name, sec):
                continue
            nm = name.lower()
            if "novice b" in nm:
                mult = 2.10
            elif sec == "Keiki":
                age = int(m2.group(1)) if (m2 := re.search(r'(\d+)', name)) else 999
                mult = 2.10 if age <= 14 else 1.0
            elif "junior" in nm:
                mult = 0.5
            else:
                mult = 1.0
            bl = base_label(name)
            idx = seen[bl]
            x_off = 0.0 if bl == "Open Mixed" else offset
            times = sorted(t * mult for team in data["teams"] if team.get("emphasize")
                           for t in team["times"] if t is not None)
            if times:
                nt = len(times)
                med = times[nt // 2] if nt % 2 else (times[nt // 2 - 1] + times[nt // 2]) / 2
                data_pts[idx]   = {"x": round(idx + x_off, 3), "y": round(med, 2)}
                error_bars[idx] = {"lo": round(times[0], 2), "hi": round(times[-1], 2)}
        datasets.append({
            "label": ser_name, "data": data_pts, "errorBars": error_bars,
            "borderColor": COLORS[ser_name], "backgroundColor": COLORS[ser_name],
        })

    all_lo = [eb["lo"] for ds in datasets for eb in ds["errorBars"] if eb]
    all_hi = [eb["hi"] for ds in datasets for eb in ds["errorBars"] if eb]
    pad = (max(all_hi) - min(all_lo)) * 0.05
    y_min = round(min(all_lo) - pad, 1)
    y_max = round(max(all_hi) + pad, 1)

    return {"labels": labels, "datasets": datasets, "yMin": y_min, "yMax": y_max}


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

    classifications = []  # (event_no, name, section, slug, data)
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

        kcc_dqs = []
        for (_, _, _, res) in completed:
            marks = res.get(no, {}).get("marks", {})
            entry = next(((secs, kind) for club, (kind, secs) in marks.items()
                          if club.startswith("Kawaihae") and kind.startswith("DQ") and secs is not None),
                         None)
            kcc_dqs.append(list(entry) if entry else None)
        data = {"title": name, "regattas": reg_short, "dates": reg_dates,
                "fastest": fastest, "slowest": slowest, "teams": teams, "dqs": kcc_dqs}
        slug = slugify(name)
        html = PAGE.replace("__TITLE__", name).replace(
            "__DATA__", json.dumps(data, ensure_ascii=False))
        open(os.path.join(WWW, "charts", slug + ".html"), "w", encoding="utf-8").write(html)
        classifications.append((no, name, section_of(name), slug, data))

    print("Wrote %d chart pages." % len(classifications))

    # thumbnails via Node + chartjs-node-canvas
    if not no_thumbs:
        print("Rendering thumbnails ...")
        script = os.path.join(ROOT, "render_thumb.js")
        for no, name, sec, slug, data in classifications:
            out = os.path.join(WWW, "thumbs", slug + ".png")
            subprocess.run(
                ["node", script, out],
                input=json.dumps(data, ensure_ascii=False).encode(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  %d thumbnails." % len(classifications))

    # summary chart
    summary = build_summary(classifications)
    open(os.path.join(WWW, "charts", "summary.html"), "w", encoding="utf-8").write(
        SUMMARY_PAGE.replace("__SUMMARY_DATA__", json.dumps(summary, ensure_ascii=False)))
    if not no_thumbs:
        subprocess.run(
            ["node", os.path.join(ROOT, "render_summary_thumb.js"),
             os.path.join(WWW, "thumbs", "summary.png")],
            input=json.dumps(summary, ensure_ascii=False).encode(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Wrote summary chart.")

    # index gallery
    write_index(classifications)
    print("Wrote index.html")


def write_index(classifications):
    by_sec = {s: [] for s in SECTIONS}
    for no, name, sec, slug, *_ in classifications:
        by_sec[sec].append((no, name, slug))

    parts = ["""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kawaihae Canoe Club — 2026 Results</title>
<style>
  body{font-family:Arial,Helvetica,sans-serif;margin:16px;color:#222;background:#fafafa}
  .logo{text-align:center;margin:8px 0 28px}
  .logo img{max-width:min(241px,25vw);height:auto}
  h2{margin:28px 0 12px;border-bottom:2px solid #ddd;padding-bottom:4px}
  .grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
  @media(min-width:600px){.grid{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}}
  @media(min-width:900px){.grid{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}}
  .cell{border-radius:10px;padding:10px;box-sizing:border-box;
        text-decoration:none;color:#222;box-shadow:0 1px 3px rgba(0,0,0,.18);
        transition:transform .08s ease, box-shadow .08s ease}
  .cell:hover{transform:translateY(-2px);box-shadow:0 4px 10px rgba(0,0,0,.25)}
  .cell .name{font-weight:bold;font-size:13px;margin-bottom:8px;text-align:center;
              line-height:1.3}
  .cell img{width:100%;aspect-ratio:3/2;object-fit:contain;display:block;border-radius:6px;
            background:#fff;border:1px solid rgba(0,0,0,.08)}
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
    parts.append(
        '<h2>Season Overview</h2>\n'
        '<a class="cell" style="background:#EEE8F8;display:block;max-width:640px" '
        'href="charts/summary.html">'
        '<div class="name">Median Finish Times by Classification</div>'
        '<img src="thumbs/summary.png" alt="Season Overview" loading="lazy"></a>\n'
    )
    parts.append("</body>\n</html>\n")
    os.makedirs(WWW, exist_ok=True)
    open(os.path.join(WWW, "index.html"), "w", encoding="utf-8").write("".join(parts))


if __name__ == "__main__":
    main()
