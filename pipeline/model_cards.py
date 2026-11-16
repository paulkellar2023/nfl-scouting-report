"""Cards for the Model tab: our number vs. the market, factor contributions (exact linear SHAP),
margin distribution, injuries, unit ratings, and the model's backtest record."""
import numpy as np

from .text import fmt, possessive as poss

SRC = "NFLVERSE PLAY-BY-PLAY · INJURIES · SNAP COUNTS · SCHEDULES (LINES)"


def _fav(p_home, h, a):
    return (h, p_home) if p_home >= 0.5 else (a, 1 - p_home)


def _line(m, h, a):
    t = h if m >= 0 else a
    return f"{t} -{abs(round(m * 2) / 2):g}"


def _card(cid, owner, t1, t2, sub, chart, note, score=1.0):
    return {"id": f"model_{cid}", "kind": "model", "phase": "model", "owner": owner, "score": score,
            "t1": t1, "t2": t2, "sub": sub, "chart": chart, "source": SRC, "note": note}


def build(mp, meta, M, names, elo=None):
    h, a = mp["home"], mp["away"]
    H, A = M[h]["label"], M[a]["label"]
    lab = {h: H, a: A}
    ph, m = mp["p_home"], mp["margin"]
    pm = mp["market"]["p_home"]
    fav, pf = _fav(ph, h, a)
    cards = []

    if pm is not None:
        gap = ph - pm
        side = h if gap > 0 else a
        if abs(gap) < 0.03:
            t1, t2 = "The model agrees with the market.", f"{lab[fav]} {fmt(pf, 'pct')} to win."
        else:
            t1 = f"The model likes {lab[side]} more than the market."
            t2 = f"{fmt(ph if side == h else 1 - ph, 'pct')} model vs. {fmt(pm if side == h else 1 - pm, 'pct')} market."
        cards.append(_card("market", side if abs(gap) >= 0.03 else fav, t1, t2,
                           f"Win probability. Market = {'vig-free moneyline' if mp['market']['source'] == 'moneyline' else 'spread converted to probability'} at build time.",
                           {"type": "probbars", "home": h, "away": a,
                            "rows": [{"label": "MODEL", "p": ph}, {"label": "MARKET", "p": pm}] + ([{"label": "ELO", "p": elo["p_home"]}] if elo else [])},
                           "Not betting advice · market line at build time"))

    items = sorted([c for c in mp["contribs"] if abs(c["pts"]) >= 0.05], key=lambda c: -abs(c["pts"]))
    if items:
        top = items[0]
        tt = h if top["pts"] > 0 else a
        cards.append(_card("shap", tt, f"{top['label']} drives the number.",
                           f"{abs(top['pts']):.1f} points toward {lab[tt]}.",
                           f"Each factor's push on the projected margin, in points. Positive = toward {H}. Sum = {_line(m, h, a)}.",
                           {"type": "waterfall", "home": h, "away": a, "items": items, "total": m},
                           "Linear model, so contributions are exact SHAP values · vs. an average matchup"))

    elo_card = None
    if elo and (elo["hist"].get(h) or elo["hist"].get(a)):
        ef, epf = _fav(elo["p_home"], h, a)
        hi = max((h, a), key=lambda t: elo["now"][t])
        elo_card = _card("elo", ef, f"Elo makes {lab[ef]} a {fmt(epf, 'pct')} favorite.",
                         f"{lab[hi]} {elo['now'][hi]:.0f} vs. {lab[a if hi == h else h]} {elo['now'][a if hi == h else h]:.0f} (average 1505).",
                         "Elo rating after each game this season. Elo uses only scores, so it is a check on the model.",
                         {"type": "elotrend", "series": [{"team": t, "pts": elo["hist"].get(t, [])} for t in (a, h)]},
                         "538-style Elo: K=20, home field 48 points, margin-of-victory multiplier, one third back to the mean each season")

    spread = mp["market"]["spread"]
    t2 = f"Market: {_line(spread, h, a)}." if spread is not None else "No market spread yet."
    if spread is not None and abs(spread - m) >= 1.5:
        t2 = f"Market: {_line(spread, h, a)}, a {abs(spread - m):.1f}-point gap."
    cards.append(_card("dist", fav, f"Model fair line: {_line(m, h, a)}.", t2,
                       f"Distribution of {H}'s margin. Shaded area = {H} win ({fmt(ph, 'pct')}).",
                       {"type": "dist", "home": h, "away": a, "mu": m, "sigma": mp["sigma"], "market": spread},
                       f"Normal margin, sigma = {mp['sigma']:.1f} points (fit by log loss)"))
    if elo_card:
        cards.append(elo_card)

    if meta.get("injuries_available") and not mp.get("projected"):
        inj = mp["injuries"]
        load = {t: sum(r["weight"] for r in inj.get(t, [])) for t in (h, a)}
        worse = max((h, a), key=lambda t: load[t])
        pts = mp["inj_pts"]["off"] + mp["inj_pts"]["def"]
        if load[worse] < 0.5:
            t1, t2 = "Both teams are close to full strength.", "Injuries barely move the number."
        else:
            t1 = f"{lab[worse]} is missing {load[worse]:.1f} starters' worth of snaps."
            t2 = f"Injuries move the line {abs(pts):.1f} points toward {lab[h if pts > 0 else a]}."
        cards.append(_card("injuries", h if worse == a else a, t1, t2,
                           "Players listed Out, Doubtful or Questionable, weighted by recent snap share. QBs are in the QB factor.",
                           {"type": "injuries", "home": h, "away": a,
                            "teams": [{"team": t, "rows": inj.get(t, [])[:8]} for t in (a, h)]},
                           "Weight = snap share (last 4 games) x status (Out 1.0, Doubtful 0.85, Questionable 0.25)"))

    r = mp["ratings"]
    mu = r.get("mu", {"pass": 0, "rush": 0})
    rows = []
    for key, unit, sign in (("off_pass", "pass", 1), ("off_rush", "rush", 1), ("def_pass", "pass", -1), ("def_rush", "rush", -1)):
        rows.append({"label": {"off_pass": "PASS OFFENSE", "off_rush": "RUSH OFFENSE", "def_pass": "PASS DEFENSE",
                               "def_rush": "RUSH DEFENSE"}[key],
                     h: round(sign * (r[h][key] - mu[unit]), 4), a: round(sign * (r[a][key] - mu[unit]), 4)})
    best = max(rows, key=lambda x: abs(x[h] - x[a]))
    bt = h if best[h] > best[a] else a
    qh, qa = mp["qb"][h], mp["qb"][a]
    cards.append(_card("units", bt, f"The biggest unit gap: {poss(lab[bt])} {best['label'].lower()}.",
                       f"{abs(best[h] - best[a]):.2f} EPA per play better than {poss(lab[a if bt == h else h])}.",
                       "Opponent-adjusted EPA per play vs. league average, the inputs to the model. Right = better.",
                       {"type": "units", "home": h, "away": a, "rows": rows,
                        "qb": [{"team": t, "name": names.get(q["id"], q["id"] or "Unknown"), "v": q["value"]} for t, q in ((a, qa), (h, qh))]},
                       "Recency-weighted, last season's plays at 35% weight"))

    bt_rows = meta.get("backtest") or []
    if bt_rows:
        n = sum(x["n"] for x in bt_rows)
        mb = sum(x["model_brier"] * x["n"] for x in bt_rows) / n
        kb = sum(x["mkt_brier"] * x["n"] for x in bt_rows) / n
        better = "beats" if mb < kb else "trails"
        cards.append(_card("record", fav, "How good is this model?",
                           f"It {better} the market: Brier {mb:.3f} vs. {kb:.3f}.",
                           f"Walk-forward backtest, {bt_rows[0]['season']}" + (f"-{bt_rows[-1]['season']}" if len(bt_rows) > 1 else "")
                           + f" ({n} games). Each season uses only earlier data.",
                           {"type": "calib", "pts": meta.get("calib", []), "seasons": bt_rows},
                           "Brier score: lower is better · market = closing line"))
    return cards


def summary(mp, M, elo_p=None):
    h, a = mp["home"], mp["away"]
    lab = {h: M[h]["label"], a: M[a]["label"]}
    fav, pf = _fav(mp["p_home"], h, a)
    s = f"Model: {lab[fav]} {fmt(pf, 'pct')} to win, fair line {_line(mp['margin'], h, a)}."
    pm = mp["market"]["p_home"]
    if pm is not None:
        mf, mpf = _fav(pm, h, a)
        s += f" Market: {lab[mf]} {fmt(mpf, 'pct')}."
    if elo_p is not None:
        ef, epf = _fav(elo_p, h, a)
        s += f" Elo: {lab[ef]} {fmt(epf, 'pct')}."
    items = sorted(mp["contribs"], key=lambda c: -abs(c["pts"]))
    if items and abs(items[0]["pts"]) >= 0.3:
        t = h if items[0]["pts"] > 0 else a
        s += f" The largest factor is {items[0]['label'].lower()}, worth {abs(items[0]['pts']):.1f} points toward {lab[t]}."
    return s
