"""Link previews for X and other apps: one small HTML page per matchup (site/g/<id>.html) with Open Graph
tags, which forwards to the app, plus a 1200x630 preview image (site/og/<id>.png) made with Pillow."""
import html
import logging
from pathlib import Path

from .assets import fetch
from .config import SITE_TITLE, SITE_URL

log = logging.getLogger(__name__)
FONT_DIR = Path("model/cache/fonts")
LOGO_DIR = Path("model/cache/logos")
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/BarlowCondensed-{}.ttf"
FALLBACK = ["/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
BG, FG, SUB, BRAND = (11, 11, 12), (244, 244, 242), (156, 156, 160), (251, 79, 20)
_fonts, _tried = {}, set()


def _font(weight, size):
    from PIL import ImageFont

    key = (weight, size)
    if key in _fonts:
        return _fonts[key]
    path = FONT_DIR / f"BarlowCondensed-{weight}.ttf"
    if weight not in _tried:
        _tried.add(weight)
        fetch(FONT_URL.format(weight), path)
    for p in [path] + [Path(x) for x in FALLBACK]:
        if p.exists():
            try:
                _fonts[key] = ImageFont.truetype(str(p), size)
                return _fonts[key]
            except OSError:
                continue
    _fonts[key] = ImageFont.load_default(size)
    return _fonts[key]


def _rgb(hexs, default=(80, 80, 80)):
    try:
        h = str(hexs).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return default


def _logo(m, size):
    from PIL import Image

    p = LOGO_DIR / f"{m['abbr']}.png"
    if not fetch(m.get("logo_url"), p):
        return None
    try:
        im = Image.open(p).convert("RGBA")
        im.thumbnail((size, size), Image.LANCZOS)
        return im
    except Exception as e:
        log.warning("og logo %s: %s", m["abbr"], e)
        return None


def _center(d, cx, y, s, font, fill):
    w = d.textlength(s, font=font)
    d.text((cx - w / 2, y), s, font=font, fill=fill)


def image(path, doc, M):
    from PIL import Image, ImageDraw

    a, h = M[doc["away"]], M[doc["home"]]
    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    from .context import pair
    d.rectangle([0, 0, 600, 14], fill=_rgb(pair(a.get("accent"), a.get("alts"), h.get("accent"))))
    d.rectangle([600, 0, 1200, 14], fill=_rgb(h.get("accent")))
    d.text((60, 46), "THE DRILL ", font=_font("Bold", 44), fill=FG)
    d.text((60 + d.textlength("THE DRILL ", font=_font("Bold", 44)), 46), "DOWN", font=_font("Bold", 44), fill=BRAND)
    wk = f"WEEK {doc['week']} · {doc['kickoff'].upper()}"
    d.text((1140 - d.textlength(wk, font=_font("SemiBold", 30)), 54), wk, font=_font("SemiBold", 30), fill=SUB)
    for m, cx in ((a, 300), (h, 900)):
        lg = _logo(m, 210)
        if lg:
            im.paste(lg, (cx - lg.width // 2, 140 + (210 - lg.height) // 2), lg)
        else:
            d.ellipse([cx - 95, 150, cx + 95, 340], fill=_rgb(m.get("color")))
            _center(d, cx, 205, m["abbr"], _font("Bold", 72), FG)
        _center(d, cx, 370, m["nick"].upper(), _font("ExtraBold", 64), FG)
    _center(d, 600, 215, "AT", _font("SemiBold", 40), SUB)
    ln = (doc.get("line") or {}).get("text") or "LINE PENDING"
    _center(d, 600, 470, ln, _font("Bold", 46), BRAND)
    _center(d, 600, 540, "MATCHUP CARDS · 3 KEYS TO SUCCESS · OUR NUMBER VS. THE MARKET", _font("SemiBold", 28), SUB)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def site_image(path):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1200, 14], fill=BRAND)
    _center(d, 600, 200, "THE DRILL DOWN", _font("ExtraBold", 140), FG)
    t = "THE DRILL "
    w = d.textlength("THE DRILL DOWN", font=_font("ExtraBold", 140))
    d.text((600 - w / 2 + d.textlength(t, font=_font("ExtraBold", 140)), 200), "DOWN", font=_font("ExtraBold", 140), fill=BRAND)
    _center(d, 600, 400, "WEEKLY NFL MATCHUP SCOUTING REPORTS", _font("SemiBold", 40), SUB)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def _first_sentence(s, n=200):
    s = (s or "").strip()
    cut = s.find(". ")
    s = s[:cut + 1] if 0 < cut < n else s
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def page(doc, M):
    a, h = M[doc["away"]], M[doc["home"]]
    route = f"#/{doc['season']}/{doc['week']}/{doc['id']}"
    title = f"{a['nick']} at {h['nick']}: who has the edge? · Week {doc['week']}"
    desc = _first_sentence(doc.get("summary")) or f"Matchup cards, keys to success and win probability for {a['name']} at {h['name']}."
    img = f"{SITE_URL}og/{doc['id']}.png"
    e = lambda s: html.escape(str(s), quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{e(title)} · {e(SITE_TITLE)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{e(SITE_TITLE)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{e(SITE_URL)}g/{e(doc['id'])}.html">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(img)}">
<link rel="canonical" href="{e(SITE_URL)}{e(route)}">
<meta http-equiv="refresh" content="1;url=../{e(route)}">
<script>location.replace("../{route}" + location.search);</script>
</head><body style="background:#0B0B0C;color:#F4F4F2;font-family:sans-serif"><p><a style="color:#FB4F14" href="../{e(route)}">Open the matchup</a></p></body></html>
"""


def write(site, docs, M):
    """docs: list of game docs for this week. Images are made once per game (they hold only stable facts)."""
    site = Path(site)
    n_img = 0
    if not (site / "og" / "site.png").exists():
        try:
            site_image(site / "og" / "site.png")
        except Exception as e:
            log.warning("og site image failed: %s", e)
    for doc in docs:
        (site / "g").mkdir(parents=True, exist_ok=True)
        (site / "g" / f"{doc['id']}.html").write_text(page(doc, M))
        p = site / "og" / f"{doc['id']}.png"
        if p.exists():
            continue
        try:
            image(p, doc, M)
            n_img += 1
        except Exception as e:
            log.warning("og image failed %s: %s", doc["id"], e)
    return n_img
