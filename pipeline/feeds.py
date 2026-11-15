"""RSS 2.0 feeds built from every week in site/data: feeds/all.xml and feeds/<TEAM>.xml."""
import datetime as dt
import json
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .config import SITE_TITLE, SITE_URL

MAX_ITEMS = 40


def _items(site):
    out = []
    for wdir in sorted((Path(site) / "data").glob("*/wk*")):
        try:
            games = json.loads((wdir / "games.json").read_text())
        except (OSError, ValueError):
            continue
        if games.get("synthetic") or games.get("projected") or games.get("backfill") or not wdir.name[2:].isdigit():
            continue
        for g in games["games"]:
            try:
                d = json.loads((wdir / f"{g['id']}.json").read_text())
            except (OSError, ValueError):
                continue
            out.append(d)
    return out


def _item(d, teams):
    a, h = d["away"], d["home"]
    title = f"Week {d['week']}: {teams[a]['nick']} at {teams[h]['nick']}"
    link = f"{SITE_URL}g/{d['id']}.html"
    parts = [d["kickoff"]]
    if d.get("line"):
        parts.append(f"Line: {d['line']['text']}")
    m = d.get("model")
    if m and m.get("market", {}).get("p_home") is not None:
        parts.append(f"Model {h} {round(100 * m['p_home'])}% vs. market {round(100 * m['market']['p_home'])}%")
    if d.get("summary"):
        parts.append(d["summary"])
    built = dt.datetime.strptime(d.get("line_asof") or d["built"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    return (built, f"<item><title>{escape(title)}</title><link>{escape(link)}</link>"
                   f"<guid isPermaLink=\"false\">{escape(d['id'])}</guid><pubDate>{format_datetime(built)}</pubDate>"
                   f"<description>{escape(' | '.join(parts))}</description></item>")


def _write(path, title, items, self_url):
    items = sorted(items, key=lambda x: x[0], reverse=True)[:MAX_ITEMS]
    now = format_datetime(dt.datetime.now(dt.timezone.utc))
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
           f"<title>{escape(title)}</title><link>{escape(SITE_URL)}</link>"
           f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>'
           f"<description>Weekly NFL matchup scouting reports and win probabilities.</description>"
           f"<lastBuildDate>{now}</lastBuildDate>" + "".join(x[1] for x in items) + "</channel></rss>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml)


def build(site, teams):
    docs = _items(site)
    per = {t: [] for t in teams}
    allx = []
    for d in docs:
        it = _item(d, teams)
        allx.append(it)
        for t in (d["away"], d["home"]):
            per.setdefault(t, []).append(it)
    fdir = Path(site) / "feeds"
    _write(fdir / "all.xml", f"{SITE_TITLE}: all games", allx, f"{SITE_URL}feeds/all.xml")
    for t, items in per.items():
        _write(fdir / f"{t}.xml", f"{SITE_TITLE}: {teams[t]['name']}", items, f"{SITE_URL}feeds/{t}.xml")
    return len(allx)
