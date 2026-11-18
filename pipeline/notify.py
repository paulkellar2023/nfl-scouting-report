"""Weekly Buttondown emails: one digest to every subscriber; with EMAIL_PER_TEAM also one per team
(subscribers tagged with the team abbreviation) and the digest goes to subscribers tagged ALL. Runs once per week: a marker file in the week folder blocks
repeats from the Saturday and Sunday refreshes. EMAIL_MODE = "draft" creates drafts only."""
import json
import logging
import os
from pathlib import Path

from . import health
from .config import EMAIL_MODE, EMAIL_PER_TEAM, SITE_TITLE, SITE_URL

log = logging.getLogger(__name__)
API = "https://api.buttondown.com/v1/emails"


def _tag_filter(tag):
    return {"predicate": "and", "groups": [],
            "filters": [{"field": "subscriber.tags", "operator": "contains", "value": tag}]}


FOOT = "A different lens on the data, not betting advice."


def _pct(x):
    return f"{round(100 * x)}%"


def _odds(d, teams):
    """'BAL -3.5 · Our model: BAL 61% (market 58%)'. Spread only, no total."""
    ln, m, h, a = d.get("line") or {}, d.get("model") or {}, d["home"], d["away"]
    parts = []
    if ln.get("spread") is not None:
        parts.append(ln["text"].split(" · O/U")[0])
    if m.get("p_home") is not None:
        fav = h if m["p_home"] >= 0.5 else a
        p = m["p_home"] if fav == h else 1 - m["p_home"]
        q = (m.get("market") or {}).get("p_home")
        mk = f" (market: {fav} {_pct(q if fav == h else 1 - q)})" if q is not None else ""
        parts.append(f"Our model: {fav} {_pct(p)}" + mk if abs(p - 0.5) > 0.005 else "Our model: even")
    return " · ".join(parts)


def _llm(facts, ask):
    """One short line in the house voice, or None. Every number must appear in the facts (same check as summaries)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        from .config import LLM_MODEL
        from .summary import _nums
        msg = anthropic.Anthropic().messages.create(
            model=LLM_MODEL, max_tokens=4000,
            system=("You write for a punchy NFL analytics newsletter: confident, concrete, a little playful, no hype words, "
                    "no em dashes, no betting advice. Use only facts and numbers from the JSON. " + ask),
            messages=[{"role": "user", "content": json.dumps(facts)}])
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text if text and not (_nums(text) - _nums(json.dumps(facts))) else None
    except Exception as e:
        log.warning("email: LLM line failed: %s", e)
        return None


TABS = (("team", "TEAM"), ("players", "PLAYERS"), ("fantasy", "FANTASY"), ("model", "MODEL"))


def _route(d, tab=None):
    return f"#/{d['season']}/{d['week']}/{d['id']}"


def game_specs(d, prefix):
    """One screenshot per matchup tab: the first card each tab shows."""
    have = {"team": d.get("team_n"), "players": d.get("player_n"), "fantasy": d.get("fantasy_n"), "model": len(d.get("model_cards") or [])}
    return [{"name": f"{prefix}_{t}", "route": _route(d), "tab": t, "sel": "article.card"} for t, _ in TABS if have.get(t)]


def _deep(docs):
    """(game, team, swing): the team with the biggest playoff-odds swing this week, and its game."""
    sw = [(v, t, d) for d in docs for t, v in ((d.get("leverage") or {}).get("by_team") or {}).items()]
    if not sw:
        return (docs[0], None, 0.0) if docs else (None, None, 0.0)
    v, t, d = max(sw, key=lambda x: x[0])
    return d, t, v


def _bubble(league, week, skip):
    """A random bubble team (25-75% playoff odds), the same pick for every run of the week."""
    import random

    pool = sorted(t for t, x in ((league or {}).get("teams") or {}).items()
                  if x.get("outcomes") and 0.25 <= (x.get("p_playoffs") or 0) <= 0.75 and t != skip)
    return random.Random(f"{(league or {}).get('season')}-{week}").choice(pool) if pool else None


# Email HTML in the site's style: dark page, Nunito Sans text, Barlow Condensed numbers and headers, orange accent.
# Inline styles only (email clients drop <style>); the web fonts load where the client allows, else system fonts.
BG, PANEL, LINE, INK, MUTE, BRAND = "#0B0B0C", "#121215", "#24242A", "#F3F3F1", "#9B9BA1", "#FB4F14"
SANS = "'Nunito Sans','Avenir Next','Segoe UI',Helvetica,Arial,sans-serif"
NUM = "'Barlow Condensed','DIN Condensed','Arial Narrow',Helvetica,Arial,sans-serif"
FONTS = "https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;700;800;900&family=Barlow+Condensed:wght@600&display=swap"


def _md(t):
    """Escape, then **bold** and [text](url)."""
    import html
    import re

    t = html.escape(str(t), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: f'<b style="color:{INK}">{m.group(1)}</b>', t)
    return re.sub(r"\[(.+?)\]\((\S+?)\)",
                  lambda m: f'<a href="{m.group(2)}" style="color:{BRAND};text-decoration:none;font-weight:700"><span style="color:{BRAND}">{m.group(1)}</span></a>', t)


def _h2(t, href=None):
    more = (f'<a href="{href}" style="float:right;font-size:11px;letter-spacing:.12em;color:{MUTE};text-decoration:none"><span style="color:{MUTE}">ON THE SITE &#8594;</span></a>'
            if href else "")
    return (f'<h2 style="margin:34px 0 10px;padding-top:14px;border-top:3px solid {BRAND};font-family:{SANS};font-size:15px;'
            f'font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:{BRAND}">{more}{_md(t)}</h2>')


def _game(d, tab=None):
    return f"{SITE_URL}g/{d['id']}.html" + (f"?tab={tab}" if tab and tab != "team" else "")


def _team(t):
    return f"{SITE_URL}#/team/{t}"


def _p(t, size=16, color=INK):
    return f'<p style="margin:0 0 12px;font-family:{SANS};font-size:{size}px;line-height:1.5;color:{color}">{_md(t)}</p>'


def _logo(teams, t, px=26):
    """Logos from the site itself (site/assets/logos, committed), so they load wherever the site does."""
    u = SITE_URL + teams[t]["logo"] if teams[t].get("logo") else teams[t].get("logo_url")
    return f'<img src="{u}" width="{px}" height="{px}" alt="" style="vertical-align:middle;border:0">' if u else ""


def _matchup(teams, d, big=False):
    a, h = d["away"], d["home"]
    px, fs = (34, 28) if big else (22, 19)
    return (f'<div style="font-family:{NUM};font-size:{fs}px;font-weight:600;letter-spacing:.02em;color:{INK};margin:0 0 4px">'
            f'{_tl(teams, a, px, True)} <a href="{_game(d)}" style="color:{MUTE};text-decoration:none"><span style="color:{MUTE}">AT</span></a> {_tl(teams, h, px)}</div>')


def _tl(teams, t, px, logo_first=False):
    """Logo + name, linked to the team page."""
    name, lg = teams[t]["nick"].upper(), _logo(teams, t, px)
    return f'<a href="{_team(t)}" style="color:{INK};text-decoration:none"><span style="color:{INK}">{lg + " " + name if logo_first else name + " " + lg}</span></a>' 


def _img(url, alt, href=None):
    im = (f'<img src="{url}" alt="{alt}" width="600" style="display:block;width:100%;max-width:600px;height:auto;'
          f'margin:0 0 14px;border-radius:12px;border:1px solid {LINE}">')
    return f'<a href="{href}">{im}</a>' if href else im


def _tag(t):
    return f'<div style="font-family:{SANS};font-size:11px;font-weight:900;letter-spacing:.16em;color:{MUTE};margin:4px 0 6px">{t}</div>'


def _wrap(parts):
    """Full HTML page: sent with Buttondown's "naked" template it fills the reader's window in the site's dark style
    (no Buttondown card around it). Naked emails must carry their own unsubscribe link."""
    body = "".join(parts)
    unsub = (f'<p style="margin:10px 0 0;font-family:{SANS};font-size:12px;color:{MUTE}">'
             f'<a href="{{{{ unsubscribe_url }}}}" style="color:{MUTE}"><span style="color:{MUTE}">Unsubscribe</span></a>'
             f' · <a href="{SITE_URL}" style="color:{MUTE}"><span style="color:{MUTE}">The Drill Down</span></a></p>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="dark"><link href="{FONTS}" rel="stylesheet"></head>'
            f'<body style="margin:0;padding:0;background:{BG}"><div style="background:{BG};padding:24px 0;width:100%">'
            f'<div style="max-width:720px;margin:0 auto;padding:0 16px;background:{BG};color:{INK}">'
            f'<div style="font-family:{SANS};font-size:13px;font-weight:900;letter-spacing:.2em;color:{INK}">THE DRILL <span style="color:{BRAND}">DOWN</span></div>'
            f'{body}<p style="margin:30px 0 0;font-family:{SANS};font-size:12px;color:{MUTE}">{FOOT}</p>{unsub}</div></div></body></html>')


def _team_body(d, team, teams, imgs=None):
    imgs, nick = imgs or {}, lambda t: teams[t]["nick"]
    P = [_h2(f"{nick(d['away'])} at {nick(d['home'])}"), _matchup(teams, d, True), _p(f"{d['kickoff']} · {_odds(d, teams)}", 14, MUTE)]
    if d.get("summary"):
        P.append(_p(d["summary"].split(". ")[0].rstrip(".") + "."))
    for tk, tl in TABS:
        if f"g{d['id']}_{tk}" in imgs:
            P += [_tag(tl), _img(imgs[f"g{d['id']}_{tk}"], tl)]
    keys = d.get("keys", {}).get(team, [])
    if keys:
        P.append(_h2(f"{nick(team)}: 3 keys"))
        P += [_p(f"**{i + 1}. {k['phrase']}.** {k['detail']}", 15) for i, k in enumerate(keys)]
    P.append(_p(f"[Open the full matchup]({SITE_URL}g/{d['id']}.html)"))
    return _wrap(P)


def _picks(docs, g):
    """Games and cards for the extra sections: upsets, chart of the week, fantasy card of the week."""
    ups = []
    for d in docs:
        m = d.get("model") or {}
        q = (m.get("market") or {}).get("p_home")
        if m.get("p_home") is not None and q is not None and (m["p_home"] >= 0.5) != (q >= 0.5):
            side = d["home"] if m["p_home"] >= 0.5 else d["away"]
            ups.append((max(m["p_home"], 1 - m["p_home"]), 1 - max(q, 1 - q), side, d))
    # Skip the games already in the "disagrees most" cards (same rule as the week board: top 3 gaps of 8+ points).
    has = [d for d in docs if (d.get("model") or {}).get("p_home") is not None and (d["model"].get("market") or {}).get("p_home") is not None]
    gap = lambda d: abs(d["model"]["p_home"] - d["model"]["market"]["p_home"])
    shown = {d["id"] for d in sorted([d for d in has if gap(d) >= 0.08], key=gap, reverse=True)[:3]}
    ups = sorted([u for u in ups if u[3]["id"] not in shown], key=lambda x: -x[0])
    tc = [(c["score"], c, d) for d in docs if d is not g for c in d.get("team_cards", [])[:d.get("team_n", 0)] if c.get("score") is not None]
    fc = [(c["score"], c, d) for d in docs for c in d.get("fantasy_cards", [])[:d.get("fantasy_n", 0)] if c.get("score") is not None]
    return ups[:3], (max(tc, key=lambda x: x[0]) if tc else None), (max(fc, key=lambda x: x[0]) if fc else None)


def _report(record, week):
    """Last graded week: picks right for model and market, plus the best and worst call."""
    gs = [x for x in ((record or {}).get("published") or {}).get("games", []) if x.get("y") is not None and x.get("week", 0) < week]
    if not gs:
        return None
    wk = max(x["week"] for x in gs)
    gs = [x for x in gs if x["week"] == wk]
    right = lambda p, y: (p >= 0.5) == (y == 1)
    m = sum(right(x["p"], x["y"]) for x in gs)
    k = sum(right(x["pm"], x["y"]) for x in gs if x.get("pm") is not None)
    conf = lambda x: abs(x["p"] - 0.5)
    good = [x for x in gs if right(x["p"], x["y"]) and x.get("pm") is not None and not right(x["pm"], x["y"])]
    bad = [x for x in gs if not right(x["p"], x["y"])]
    return {"week": wk, "n": len(gs), "model": m, "market": k,
            "best": max(good, key=conf) if good else None, "worst": max(bad, key=conf) if bad else None}


def _section(sid, title, parts, href=None):
    top = f'<p style="margin:6px 0 0;text-align:right"><a href="#top" style="font-family:{SANS};font-size:12px;font-weight:800;color:{MUTE};text-decoration:none"><span style="color:{MUTE}">&#8593; TOP</span></a></p>'
    return [f'<a id="{sid}" name="{sid}"></a>', _h2(title, href)] + parts + [top]


def _digest_body(docs, week, teams, bracket=None, league=None, imgs=None, record=None):
    imgs = imgs or {}
    season = docs[0]["season"] if docs else ""
    g, st, sv = _deep(docs)
    nick = lambda t: teams[t]["nick"]
    ups, cotw, fotw = _picks(docs, g)
    S = []  # (id, title, parts)
    # At a glance: the model-vs-market cards from the week board, then what is at stake, the surest pick and the coin flip.
    probs = [(max(d["model"]["p_home"], 1 - d["model"]["p_home"]), d) for d in docs if (d.get("model") or {}).get("p_home") is not None]
    sure = max(probs, key=lambda x: x[0]) if probs else None
    flip = min(probs, key=lambda x: x[0]) if probs else None
    fav = lambda d: d["home"] if d["model"]["p_home"] >= 0.5 else d["away"]
    box = lambda k, v, pre="": (f'<div style="background:{PANEL};border:1px solid {LINE};border-radius:12px;padding:12px 16px;margin:0 0 8px">'
                                f'{_tag(k)}{pre}{_p(v, 15).replace("margin:0 0 12px", "margin:0")}</div>')
    board = f"{SITE_URL}#/{season}/{week}"
    P = [_img(imgs["disagree"], "Where the model disagrees most", board)] if "disagree" in imgs else []
    if st:
        P.append(box("MOST AT STAKE", f"The [{teams[st]['name']}]({_team(st)}): [this game]({_game(g)}) swings their playoff odds by **{round(100 * sv)} points**."))
    if sure:
        o = sure[1]["away"] if fav(sure[1]) == sure[1]["home"] else sure[1]["home"]
        P.append(box("SUREST PICK", f"[{nick(fav(sure[1]))} over the {nick(o)}]({_game(sure[1], 'model')}), **{_pct(sure[0])}**."))
    if flip and flip[1] is not (sure or (0, None))[1]:
        P.append(box("COIN FLIP", f"[{nick(flip[1]['away'])} at {nick(flip[1]['home'])}]({_game(flip[1], 'model')}): **{_pct(flip[0])}** for the {nick(fav(flip[1]))}."))
    if P:
        S.append(("glance", "At a glance", P, board))
    rc = _report(record, week)
    if rc:
        P = [box(f"WEEK {rc['week']} PICKS", f"Our model **{rc['model']}-{rc['n'] - rc['model']}** · the market {rc['market']}-{rc['n'] - rc['market']}.")]
        for lab, x in (("BEST CALL", rc["best"]), ("WORST CALL", rc["worst"])):
            if x:
                side = x["home"] if x["p"] >= 0.5 else x["away"]
                P.append(box(lab, f"[{nick(side)}]({SITE_URL}g/{x['id']}.html) at **{_pct(max(x['p'], 1 - x['p']))}**"
                         + (f" when the market had them at {_pct(x['pm'] if side == x['home'] else 1 - x['pm'])}" if x.get("pm") is not None else "")
                         + f". Final: {nick(x['away'])} {x['final'][x['away']]}, {nick(x['home'])} {x['final'][x['home']]}."))
        P.append(_p(f"[Full track record]({SITE_URL}#/record)", 14))
        S.append(("report", "Last week's report card", P, f"{SITE_URL}#/record"))
    if g:
        P = [_matchup(teams, g, True), _p(f"{g['kickoff']} · {_odds(g, teams)}", 14, MUTE)]
        if g.get("summary"):
            P.append(_p(g["summary"].split(". ")[0].rstrip(".") + "."))
        for tk, tl in TABS:
            if f"top_{tk}" in imgs:
                P += [_tag(f'<a href="{_game(g, tk)}" style="color:{MUTE};text-decoration:none"><span style="color:{MUTE}">{tl} TAB &#8594;</span></a>'), _img(imgs[f"top_{tk}"], tl, _game(g, tk))]
        P.append(_p(f"[All the cards, keys and the model]({SITE_URL}g/{g['id']}.html)"))
        S.append(("gotw", "Game of the week", P, _game(g)))
    if ups:
        P = [_p("Our model favors the team the market makes the underdog.", 14, MUTE)]
        for pm, pk, side, d in ups:
            P.append(box(f"{nick(d['away']).upper()} AT {nick(d['home']).upper()}",
                         f"**{nick(side)} {_pct(pm)}** by our model, {_pct(pk)} by the market. [Why]({SITE_URL}g/{d['id']}.html?tab=model)",
                         f'<div style="float:right">{_logo(teams, side, 30)}</div>'))
        S.append(("upsets", "Upset alert", P, board))
    if cotw and "cotw" in imgs:
        d = cotw[2]
        S.append(("cotw", "Chart of the week", [_p(f"The biggest edge on the board, from {nick(d['away'])} at {nick(d['home'])}.", 14, MUTE),
                                                _img(imgs["cotw"], cotw[1]["t1"], _game(d)), _p(f"[Open the matchup]({_game(d)})", 14)], _game(d)))
    if fotw and "fotw" in imgs:
        d = fotw[2]
        S.append(("fantasy", "Fantasy: start or sit", [_p(f"The strongest fantasy signal this week, from {nick(d['away'])} at {nick(d['home'])}.", 14, MUTE),
                                                       _img(imgs["fotw"], fotw[1]["t1"], _game(d, "fantasy")), _p(f"[Fantasy tab]({_game(d, 'fantasy')})", 14)], _game(d, "fantasy")))
    if "seeds" in imgs or (bracket and bracket.get("seeds")):
        P = [_img(imgs["seeds"], "Projected playoff seeds", f"{SITE_URL}#/bracket")] if "seeds" in imgs else \
            [_p(f"**{c}:** " + " · ".join(f"{x['seed']}. {nick(x['team'])}" for x in (bracket["seeds"].get(c) or [])[:7]), 15) for c in ("AFC", "NFC")]
        if bracket and bracket.get("champion"):
            P.append(_p(f"Model's Super Bowl pick: **{teams[bracket['champion']]['name']}**. [Full bracket]({SITE_URL}#/bracket)"))
        S.append(("playoffs", "Playoff picture", P, f"{SITE_URL}#/bracket"))
    bt = _bubble(league, week, st)
    if bt and "bubble" in imgs:
        S.append(("bubble", f"On the bubble: {teams[bt]['name']}",
                  [_p(f"**{_pct(league['teams'][bt]['p_playoffs'])}** to make the playoffs. How their season ends across 10,000 simulations:"),
                   _img(imgs["bubble"], f"{teams[bt]['name']} season outcomes", _team(bt)), _p(f"[Team page]({_team(bt)})", 14)], _team(bt)))
    rest = [d for d in docs if d is not g]
    if rest:
        P = []
        for d in rest:
            # The LLM summary when there is one; the rule-based summary is too long here, so its one-line teaser instead.
            hook = d["summary"] if d.get("summary_src") == "llm" and d.get("summary") else (d.get("tease") or [None])[0] or ""
            links = f"[Preview]({_game(d)}) · [Model]({_game(d, 'model')}) · [Fantasy]({_game(d, 'fantasy')})"
            P.append(f'<div style="border-bottom:1px solid {LINE};padding:10px 0">'
                     f'{_matchup(teams, d)}'
                     f'{_p(_odds(d, teams), 13, MUTE).replace("margin:0 0 12px", "margin:0 0 2px")}'
                     f'{_p(hook, 14).replace("margin:0 0 12px", "margin:0 0 4px") if hook else ""}'
                     f'{_p(links, 13).replace("margin:0 0 12px", "margin:0")}</div>')
        P.append(_p(f"[Open the week board]({SITE_URL}#/{season}/{week})"))
        S.append(("slate", "The rest of the slate", P, board))
    facts = {"week": week, "most_at_stake": st and {"team": teams[st]["name"], "playoff_odds_swing_percentage_points": round(100 * sv)},
             "upsets": [{"team": nick(u[2]), "model_pct": round(100 * u[0]), "market_pct": round(100 * u[1])} for u in ups] or None,
             "game_of_the_week": g and f"{nick(g['away'])} at {nick(g['home'])}"}
    facts = {k: v for k, v in facts.items() if v}
    intro = _llm(facts, "Write a 2-sentence opening for this week's issue that teases the most interesting thing in it. "
                        "Only mention what the JSON has; never mention something that is missing.")
    toc = " &nbsp;·&nbsp; ".join(f'<a href="#{sid}" style="color:{INK};text-decoration:none;font-weight:800"><span style="color:{INK}">{t.split(":")[0].upper()}</span></a>' for sid, t, *_ in S)
    P = ['<a id="top" name="top"></a>',
         f'<h1 style="margin:14px 0 8px;font-family:{SANS};font-size:30px;font-weight:900;line-height:1.1;color:{INK}">Week {week} <span style="color:{BRAND}">preview</span></h1>',
         _p(intro or "Where our model splits from the market, who has the most riding on this week, and how the playoff race looks.", 17),
         f'<p style="margin:0 0 6px;font-family:{SANS};font-size:11px;line-height:2;letter-spacing:.08em;color:{MUTE}">IN THIS ISSUE: {toc}</p>']
    for sid, t, parts, href in S:
        P += _section(sid, t, parts, href)
    P.append(_p("**Your call:** reply with the team you want in next week's bubble chart.", 14, MUTE))
    return _wrap(P)


def send_week(wdir, teams, ordered_ids, week, test_to=None):
    """test_to: an address. Then only the digest is made, as a Buttondown draft sent to that address alone;
    no subscriber gets it and the week's send marker is not written (or checked)."""
    key = os.environ.get("BUTTONDOWN_API_KEY")  # GitHub Actions repository secret
    if not key:
        log.info("email: BUTTONDOWN_API_KEY not set, skipping")
        return
    marker = Path(wdir) / "email_sent.json"
    if marker.exists() and not test_to:
        log.info("email: week %s already sent (%s), skipping", week, marker)
        return
    import requests

    docs = []
    for gid in ordered_ids:
        try:
            docs.append(json.loads((Path(wdir) / f"{gid}.json").read_text()))
        except (OSError, ValueError):
            pass
    gj = Path(wdir) / "games.json"
    tease = {t["id"]: t.get("tease") for t in json.loads(gj.read_text()).get("games", [])} if gj.exists() else {}
    for d in docs:
        d.setdefault("tease", tease.get(d["id"]))
    status = "about_to_send" if EMAIL_MODE == "send" and not test_to else "draft"
    hdr = {"Authorization": f"Token {key}"}
    if status == "about_to_send":
        hdr["X-Buttondown-Live-Dangerously"] = "true"  # newer API versions refuse a direct send without it
    import tempfile

    from . import snaps

    site = Path(wdir).parents[2]
    read = lambda p: json.loads(p.read_text()) if p.exists() else None
    bracket, league = read(Path(wdir).parent / "bracket.json"), read(Path(wdir).parent / "league.json")
    record = read(Path(wdir).parent / "record.json")
    g, st, _ = _deep(docs)
    specs = [dict(x, name="top_" + x["name"].split("_")[-1]) for x in game_specs(g, "top")] if g else []
    ups, cotw, fotw = _picks(docs, g)
    if docs:
        specs.append({"name": "disagree", "route": f"#/{docs[0]['season']}/{week}", "sel": "section.disagree", "width": 620})
    for name, pick, tab in (("cotw", cotw, "team"), ("fotw", fotw, "fantasy")):
        if pick:
            specs.append({"name": name, "route": _route(pick[2]), "tab": tab, "sel": "article.card", "text": pick[1]["t1"][:40]})
    if bracket and bracket.get("seeds"):
        specs.append({"name": "seeds", "route": "#/bracket", "sel": ".seed-grid", "width": 700})
    bt = _bubble(league, week, st)
    if bt:
        specs.append({"name": "bubble", "route": f"#/team/{bt}", "sel": "article.card", "text": "End-of-season outcomes"})
    for d in (docs if EMAIL_PER_TEAM else []):
        specs += [dict(x, name=f"g{d['id']}_" + x["name"].split("_")[-1]) for x in game_specs(d, "g")]
    imgs = snaps.shots(site, specs, key, tempfile.mkdtemp())
    subject = f"{SITE_TITLE}: Week {week} preview"
    if g:
        subject += f" · {teams[g['away']]['nick']} at {teams[g['home']]['nick']} leads the way"
    jobs = [(subject, _digest_body(docs, week, teams, bracket, league, imgs, record), "ALL" if EMAIL_PER_TEAM else None)]
    if test_to:
        jobs = [("[TEST] " + jobs[0][0], jobs[0][1], None)]
    for d in (docs if EMAIL_PER_TEAM and not test_to else []):
        for t in (d["away"], d["home"]):
            opp = d["home"] if t == d["away"] else d["away"]
            jobs.append((f"{SITE_TITLE}: {teams[t]['nick']} vs. {teams[opp]['nick']}, Week {week}",
                         _team_body(d, t, teams, imgs), t))
    health.info("email_images", len(imgs))
    ok = 0
    for subject, body, tag in jobs:
        try:
            payload = {"subject": subject, "body": body, "status": status, "template": "naked"}
            if tag:
                payload["filters"] = _tag_filter(tag)
            r = requests.post(API, headers=hdr, timeout=20, json=payload)
            if r.status_code in (400, 403, 422):  # plan or API refuses "naked": use the newsletter's default template
                log.warning("email: naked template refused (%s %s), using the default template", r.status_code, r.text[:200])
                payload.pop("template")
                payload["body"] = "<!-- buttondown-editor-mode: fancy -->" + body
                r = requests.post(API, headers=hdr, timeout=20, json=payload)
            r.raise_for_status()
            if test_to:  # send the draft to the test address only
                requests.post(f"{API}/{r.json()['id']}/send-draft", headers=hdr, timeout=20,
                              json={"recipients": [test_to]}).raise_for_status()
                log.info("email: test draft sent to the EMAIL_TEST_TO address")
            ok += 1
        except Exception as e:  # one failed email must not stop the others or the build
            log.warning("email: %s failed: %s %s", tag, e, getattr(getattr(e, "response", None), "text", "")[:300])
    log.info("email: %d/%d %s created for week %s", ok, len(jobs), status, week)
    health.info("email", {"created": ok, "total": len(jobs), "status": status})
    if ok < len(jobs):
        health.warn(f"email: only {ok}/{len(jobs)} {status}s created (search the log for 'email:')")
    if ok and not test_to:
        marker.write_text(json.dumps({"week": week, "status": status, "created": ok}))
