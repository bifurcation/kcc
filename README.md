# HCRA MOKU Race-Time Charts

Generates an interactive statistics site for the [Kawaihae Canoe Club](https://www.kawaihaecanoeclub.com/)'s MOKU (Moku O Hawaiʻi) outrigger canoe racing season.

## What it produces

- `charts/<class>.html` — interactive Chart.js race-time line chart per classification
- `thumbs/<class>.png` — simplified thumbnail
- `index.html` — gallery of thumbnails

## Usage

```sh
python3 build.py              # full build (fetches data, generates charts + thumbnails)
python3 build.py --no-thumbs  # skip thumbnail rendering
```
