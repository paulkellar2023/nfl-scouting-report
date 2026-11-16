"""Second batch of field-style visuals: red zone, down-and-distance grid, explosive plays, win-probability
timeline, scoring by quarter, target tree, field-position tug-of-war, third downs, penalties, play-action
and motion splits. Each card compares the two teams in the game."""
import numpy as np
import pandas as pd

from .text import ordinal, possessive as poss
from .viz import _card, _jit

SRC = "NFLVERSE PLAY-BY-PLAY"
DIST = (("1-3", 1, 3), ("4-7", 4, 7), ("8+", 8, 99))
LANE_X = {"left": -1, "middle": 0, "right": 1}


def _rk(s, t, high=True):
    s = s.dropna()
    return int(((s > s[t]) if high else (s < s[t])).sum() + 1), len(s)


def _rank_txt(r, n, hi="most", lo="fewest"):
    if r == 1:
        return f"the NFL's {hi}"
    if r == n:
        return f"the NFL's {lo}"
    return f"{ordinal(r)}-{hi}" if r <= (n + 1) / 2 else f"{ordinal(n + 1 - r)}-{lo}"


def _z(s, t):
    s = s.dropna()
    return float((s[t] - s.mean()) / (s.std() or 1)) if t in s.index else np.nan


def _cur(pbp, season, week):
    d = pbp
    if "season" in d.columns:
        d = d[pd.to_numeric(d["season"], errors="coerce") == season]
    if "season_type" in d.columns:
        d = d[d["season_type"] == "REG"]
    return d[pd.to_numeric(d["week"], errors="coerce") < week]


def tables(plays, pbp, season, week):
    T = {"plays": plays}
    pl = plays[plays["dropback"] | plays["designed_run"]].copy()
    pl["games"] = 1
    T["n_games"] = pl.groupby("posteam")["game_id"].nunique()
    T["n_games_d"] = pl.groupby("defteam")["game_id"].nunique()
    # red zone: plays snapped inside the 20; drives that reach it
    rz = pl[pl["yardline_100"] <= 20].copy()
    if len(rz) > 800:
        rz["td"] = (rz["touchdown"] == 1).astype(float)
        T["rz"] = rz
        dr = rz.groupby(["game_id", "posteam", "defteam", "fixed_drive"]).agg(res=("fixed_drive_result", "first")).reset_index()
        dr["td"] = (dr["res"] == "Touchdown").astype(float)
        T["rz_off"], T["rz_def"] = dr.groupby("posteam")["td"].mean(), dr.groupby("defteam")["td"].mean()
        T["rz_lg"] = float(dr["td"].mean())
        rz["band"] = pd.cut(rz["yardline_100"], [0, 5, 10, 20], labels=["1-5", "6-10", "11-20"], include_lowest=True).astype(str)
        T["rz_band_def"] = rz.groupby(["defteam", "band"])["td"].agg(["mean", "size"])
        T["rz_band_lg"] = rz.groupby("band")["td"].mean()
    # down and distance
    e = pl[pl["eff"] & pl["down"].isin([1, 2, 3])].copy()
    e["dist"] = pd.cut(e["ydstogo"], [0, 3, 7, 99], labels=[x[0] for x in DIST]).astype(str)
    e["cell"] = e["down"].astype(int).astype(str) + "|" + e["dist"]
    T["dd_off"] = e.groupby(["posteam", "cell"]).agg(sr=("success", "mean"), pr=("dropback", "mean"), n=("epa", "size"))
    T["dd_def"] = e.groupby(["defteam", "cell"]).agg(sr=("success", "mean"), n=("epa", "size"))
    T["dd_lg"] = e.groupby("cell").agg(sr=("success", "mean"), pr=("dropback", "mean"))
    # explosive plays: 20+ yards
    ex = pl[(pl["yards_gained"] >= 20)].copy()
    lane = ex["pass_location"].where(ex["dropback"], ex.get("run_location")) if "pass_location" in ex.columns else None
    ex["lane"] = lane if lane is not None else "middle"
    T["exp"] = ex
    T["exp_off"] = ex.groupby("posteam").size() / T["n_games"]
    T["exp_def"] = ex.groupby("defteam").size() / T["n_games_d"]
    # third downs
    td3 = pl[(pl["down"] == 3)].copy()
    td3["conv"] = ((td3["yards_gained"] >= td3["ydstogo"]) | (td3["touchdown"] == 1)).astype(float)
    T["third"] = td3
    T["third_off"], T["third_def"] = td3.groupby("posteam")["conv"].mean(), td3.groupby("defteam")["conv"].mean()
    # play action and motion splits (needs FTN charting)
    db = pl[pl["dropback"] & pl["eff"]]
    for k in ("pa", "motion"):
        if k in db.columns and db[k].notna().mean() > 0.5:
            T[f"{k}_off"] = db.groupby(["posteam", k])["epa"].mean().unstack()
            T[f"{k}_def"] = db.groupby(["defteam", k])["epa"].mean().unstack()
            T[f"{k}_rate"] = db.groupby("posteam")[k].mean()
    # target tree
    if "receiver_player_id" in plays.columns:
        tg = plays[plays["attempt"] & plays["receiver_player_id"].notna()]
        g = tg.groupby(["posteam", "receiver_player_id"]).agg(n=("epa", "size"), adot=("air_yards", "mean"), epa=("epa", "mean"))
        g["share"] = g["n"] / g.groupby(level=0)["n"].transform("sum")
        T["tree"] = g
    # drive starts and scoring by quarter
    if {"fixed_drive", "fixed_drive_result", "qtr"} <= set(plays.columns):
        dv = plays.sort_values(["game_id", "fixed_drive"] + (["play_id"] if "play_id" in plays.columns else []))
        g = dv.groupby(["game_id", "posteam", "defteam", "fixed_drive"]).agg(start=("yardline_100", "first"), q=("qtr", "last"),
                                                                             res=("fixed_drive_result", "first")).reset_index()
        g["pts"] = g["res"].map({"Touchdown": 7, "Field goal": 3}).fillna(0)
        T["start_off"] = (100 - g.groupby("posteam")["start"].mean())
        T["start_def"] = (100 - g.groupby("defteam")["start"].mean())
        T["start_lg"] = float((100 - g["start"]).mean())
        g["q"] = g["q"].clip(upper=4).astype(int)
        T["q_for"] = g.groupby(["posteam", "q"])["pts"].sum().unstack(fill_value=0).div(T["n_games"], axis=0)
        T["q_against"] = g.groupby(["defteam", "q"])["pts"].sum().unstack(fill_value=0).div(T["n_games_d"], axis=0)
    # raw play-by-play: win probability and penalties
    if pbp is not None:
        d = _cur(pbp, season, week)
        if {"wp", "game_seconds_remaining", "posteam", "game_id"} <= set(d.columns):
            w = d[d["wp"].notna() & d["posteam"].notna() & d["game_seconds_remaining"].notna()][
                ["game_id", "week", "posteam", "defteam", "wp", "game_seconds_remaining"]].copy()
            T["wp"] = w
        if {"penalty", "penalty_team", "penalty_type"} <= set(d.columns):
            pn = d[pd.to_numeric(d["penalty"], errors="coerce") == 1]
            if len(pn) > 200:
                T["pen"] = pn
                T["pen_g"] = pn.groupby("penalty_team").size() / T["n_games"]
    return T


# ---------------------------------------------------------------- cards
def redzone_card(T, a, b, M, game):
    if "rz" not in T:
        return None
    best = None
    for off, de in ((a, b), (b, a)):
        zo, zd = _z(T["rz_off"], off), _z(T["rz_def"], de)
        if np.isnan(zo) or np.isnan(zd):
            continue
        sc = abs(zo + zd)
        if best is None or sc > best[0]:
            best = (sc, off, de, zo, zd)
    if best is None:
        return None
    sc, off, de, zo, zd = best
    vo, vd = float(T["rz_off"][off]), float(T["rz_def"][de])
    ro, n = _rk(T["rz_off"], off)
    rd, _ = _rk(T["rz_def"], de)
    t1 = f"{M[off]['label']} scores touchdowns on {round(100 * vo)}% of red-zone trips, {_rank_txt(ro, n, 'highest', 'lowest')}."
    t2 = f"{poss(M[de]['label'])} defense allows {round(100 * vd)}%, {_rank_txt(rd, n, 'highest', 'lowest')}."
    rz = T["rz"]
    mine = rz[rz["posteam"] == off]
    def lanex(p):
        loc = getattr(p, "pass_location", None) if p.dropback else getattr(p, "run_location", None)
        return LANE_X.get(loc, 0) * 0.62 + _jit(f"{p.game_id}{p.play_id}", 0.45)
    dots = [{"x": round(lanex(p), 3), "y": float(p.yardline_100), "p": bool(p.dropback), "td": bool(p.touchdown == 1)} for p in mine.itertuples()]
    bd = T["rz_band_def"]
    cells = [{"band": bb, "v": None if (de, bb) not in bd.index else round(float(bd.loc[(de, bb), "mean"]), 3),
              "n": 0 if (de, bb) not in bd.index else int(bd.loc[(de, bb), "size"]), "lg": round(float(T["rz_band_lg"].get(bb, np.nan)), 3)}
             for bb in ("1-5", "6-10", "11-20")]
    return _card(f"redzone:{off}", "redzone", "team", off if zo + zd > 0 else de, 0.6 + 0.3 * min(sc, 3), t1, t2,
                 f"Left: every {M[off]['nick']} play snapped inside the 20, {game['span']}. Right: {M[de]['nick']} defense, touchdown rate per play allowed by distance.",
                 {"type": "redzone", "off": off, "def": de, "dots": dots, "cells": cells},
                 "Trip = a drive with at least one play inside the opponent's 20 · lane spread within left / middle / right")


def downs_card(T, a, b, M, game):
    off_t, def_t, lg = T["dd_off"], T["dd_def"], T["dd_lg"]
    best = None
    for off, de in ((a, b), (b, a)):
        for cell in lg.index:
            if (off, cell) not in off_t.index or (de, cell) not in def_t.index:
                continue
            o, d_ = off_t.loc[(off, cell)], def_t.loc[(de, cell)]
            if o["n"] < 15 or d_["n"] < 15:
                continue
            gap = (o["sr"] - lg.loc[cell, "sr"]) + (d_["sr"] - lg.loc[cell, "sr"])
            if best is None or abs(gap) > abs(best[0]):
                best = (gap, off, de, cell)
    if best is None:
        return None
    gap, off, de, cell = best
    dn, ds = cell.split("|")
    o, d_ = off_t.loc[(off, cell)], def_t.loc[(de, cell)]
    nm = {"1": "1st", "2": "2nd", "3": "3rd"}[dn]
    dist = {"1-3": "short", "4-7": "medium", "8+": "long"}[ds]
    t1 = f"On {nm} and {dist}, {M[off]['label']} succeeds on {round(100 * o['sr'])}% of plays (league {round(100 * lg.loc[cell, 'sr'])}%)."
    t2 = f"{poss(M[de]['label'])} defense allows {round(100 * d_['sr'])}% there."
    ok = lambda tab, t, c: (t, c) in tab.index and tab.loc[(t, c), "n"] >= 8
    grid = lambda tab, t: [{"cell": c, "sr": round(float(tab.loc[(t, c), "sr"]), 3) if ok(tab, t, c) else None,
                           "pr": round(float(tab.loc[(t, c), "pr"]), 3) if "pr" in tab.columns and (t, c) in tab.index else None,
                           "n": int(tab.loc[(t, c), "n"]) if (t, c) in tab.index else 0, "lg": round(float(lg.loc[c, "sr"]), 3)} for c in lg.index]
    return _card(f"downs:{off}", "downs", "team", off if gap > 0 else de, 0.45 + 2.2 * abs(gap), t1, t2,
                 f"Success rate by down and distance: {M[off]['nick']} offense vs. {M[de]['nick']} defense, {game['span']}.",
                 {"type": "downs", "off": off, "def": de, "hl": cell, "o": grid(off_t, off), "d": grid(def_t, de)},
                 "Success = positive EPA · garbage time removed · offense cells also show pass rate")


def explosive_card(T, a, b, M, game):
    eo, ed = T["exp_off"], T["exp_def"]
    best = None
    for off, de in ((a, b), (b, a)):
        zo, zd = _z(eo, off), _z(ed, de)
        if np.isnan(zo) or np.isnan(zd):
            continue
        if best is None or abs(zo + zd) > best[0]:
            best = (abs(zo + zd), off, de, zo + zd)
    if best is None:
        return None
    sc, off, de, tot = best
    ro, n = _rk(eo, off)
    rd, _ = _rk(ed, de)
    t1 = f"{M[off]['label']} averages {eo[off]:.1f} plays of 20+ yards per game, {_rank_txt(ro, n)}."
    t2 = f"{poss(M[de]['label'])} defense allows {ed[de]:.1f}, {_rank_txt(rd, n)}."
    ex = T["exp"]
    arrows = lambda df: [{"s": round(100 - float(p.yardline_100), 1), "e": round(min(100.0, 100 - float(p.yardline_100) + float(p.yards_gained)), 1),
                          "l": LANE_X.get(p.lane, 0), "p": bool(p.dropback), "td": bool(p.touchdown == 1),
                          "j": round(_jit(f"{p.game_id}{p.play_id}", 0.5), 3)} for p in df.itertuples()]
    return _card(f"explosive_map:{off}", "explosive_map", "team", off if tot > 0 else de, 0.55 + 0.3 * min(sc, 3), t1, t2,
                 f"Every 20+ yard play: {M[off]['nick']} offense (top) and allowed by the {M[de]['nick']} defense (bottom), {game['span']}.",
                 {"type": "explmap", "off": off, "def": de, "a": arrows(ex[ex["posteam"] == off]), "b": arrows(ex[ex["defteam"] == de])},
                 "Arrow = where the play started to where it ended · driving left to right · lane from play-by-play")


def wp_card(T, a, b, M, game):
    if "wp" not in T:
        return None
    w = T["wp"]
    stats, series = {}, {}
    for t in (a, b):
        g = w[(w["posteam"] == t) | (w["defteam"] == t)].copy()
        if not len(g):
            return None
        g["twp"] = np.where(g["posteam"] == t, g["wp"], 1 - g["wp"])
        g["sec"] = 3600 - g["game_seconds_remaining"].clip(lower=0)
        blown = come = 0
        for gid, gg in g.groupby("game_id"):
            fin = gg.sort_values("sec")["twp"].iloc[-1]
            if gg["twp"].max() >= 0.8 and fin < 0.5:
                blown += 1
            if gg["twp"].min() <= 0.2 and fin > 0.5:
                come += 1
        stats[t] = (blown, come)
        last = g.drop_duplicates("game_id").sort_values("week").tail(2)
        series[t] = []
        for gid, wk in zip(last["game_id"], last["week"]):
            gg = g[g["game_id"] == gid].sort_values("sec")
            step = max(1, len(gg) // 60)
            pts = [[round(float(s), 0), round(float(v), 3)] for s, v in zip(gg["sec"].values[::step], gg["twp"].values[::step])]
            opp = gg["defteam"].where(gg["posteam"] == t, gg["posteam"]).iloc[0]
            series[t].append({"wk": int(wk), "opp": opp, "pts": pts, "won": bool(gg["twp"].iloc[-1] > 0.5)})
    sc = 0.5 + 0.25 * sum(sum(v) for v in stats.values())
    big = max((a, b), key=lambda t: max(stats[t]))
    bl, cm = stats[big]
    t1 = (f"{M[big]['label']} has blown {bl} game{'s' if bl != 1 else ''} it led with 80%+ win odds this season." if bl >= cm else
          f"{M[big]['label']} has come back to win {cm} game{'s' if cm != 1 else ''} after falling to 20% or worse.")
    o = b if big == a else a
    t2 = f"{M[o]['label']}: {stats[o][0]} blown, {stats[o][1]} comebacks."
    return _card(f"wpline:{a}{b}", "wpline", "team", big, min(sc, 1.4), t1, t2,
                 "Win probability through each team's last 2 games.",
                 {"type": "wpline", "teams": [{"team": t, "games": series[t]} for t in (a, b)]},
                 "nflverse win probability model · 50% line dashed")


def quarters_card(T, a, b, M, game):
    if "q_for" not in T:
        return None
    qf, qa = T["q_for"], T["q_against"]
    if a not in qf.index or b not in qf.index:
        return None
    net = {t: [float(qf.loc[t].get(q, 0) - qa.loc[t].get(q, 0)) if t in qa.index else 0.0 for q in (1, 2, 3, 4)] for t in (a, b)}
    gaps = [(abs(net[a][i] - net[b][i]), i) for i in range(4)]
    g, i = max(gaps)
    hi, lo = (a, b) if net[a][i] >= net[b][i] else (b, a)
    qn = ["1st", "2nd", "3rd", "4th"][i]
    t1 = f"{M[hi]['label']} outscores opponents by {net[hi][i]:+.1f} points per game in the {qn} quarter."
    t2 = f"{M[lo]['label']}: {net[lo][i]:+.1f}."
    rows = [{"team": t, "for": [round(float(qf.loc[t].get(q, 0)), 2) for q in (1, 2, 3, 4)],
             "against": [round(float(qa.loc[t].get(q, 0)), 2) if t in qa.index else 0 for q in (1, 2, 3, 4)]} for t in (a, b)]
    return _card(f"quarters:{a}{b}", "quarters", "team", hi, 0.45 + 0.15 * g, t1, t2,
                 f"Points per game scored (up) and allowed (down) by quarter, {game['span']}.",
                 {"type": "quarters", "rows": rows, "hl": i},
                 "Offensive touchdowns and field goals by the quarter the drive ended · overtime counted as 4th")


def tree_card(T, a, b, M, game, name, img):
    if "tree" not in T:
        return None
    tr = T["tree"]
    teams, conc = [], {}
    for t in (a, b):
        if t not in tr.index.get_level_values(0):
            return None
        g = tr.loc[t].sort_values("n", ascending=False).head(5)
        g = g[g["n"] >= 10]
        if len(g) < 3:
            return None
        conc[t] = float(g["share"].iloc[0])
        teams.append({"team": t, "players": [{"id": pid, "name": name(pid), "short": str(name(pid)).split()[-1], "img": img(pid),
                                              "share": round(float(r["share"]), 3), "adot": round(float(r["adot"]), 1), "epa": round(float(r["epa"]), 3)}
                                             for pid, r in g.iterrows()]})
    top = max((a, b), key=lambda t: conc[t])
    p0 = next(x for x in teams if x["team"] == top)["players"][0]
    o = b if top == a else a
    t1 = f"{p0['name']} gets {round(100 * p0['share'])}% of {poss(M[top]['label'])} targets, {p0['adot']:.1f} yards downfield on average."
    t2 = f"{poss(M[o]['label'])} top target gets {round(100 * conc[o])}%."
    return _card(f"tree:{top}", "tree", "player", top, 0.6 + 2 * abs(conc[a] - conc[b]), t1, t2,
                 f"Top 5 targets on each team: height = average depth of target, size = share of targets, color = EPA per target, {game['span']}.",
                 {"type": "tree", "teams": teams},
                 "Depth only: free play-by-play has no route data")


def tug_card(T, a, b, M, game):
    if "start_off" not in T:
        return None
    so, sd = T["start_off"], T["start_def"]
    if a not in so.index or b not in so.index:
        return None
    net = {t: float(so[t] - sd.get(t, np.nan)) for t in (a, b)}
    hi, lo = (a, b) if net[a] >= net[b] else (b, a)
    t1 = f"{M[hi]['label']} starts drives at its own {so[hi]:.0f} on average; its opponents start at their {sd[hi]:.0f}."
    t2 = f"{M[lo]['label']}: own {so[lo]:.0f} vs. opponents' {sd[lo]:.0f}."
    return _card(f"tug:{a}{b}", "tug", "team", hi, 0.55 + 0.1 * abs(net[a] - net[b]), t1, t2,
                 f"Average drive start for each offense and for its opponents (yard line from its own goal line), {game['span']}.",
                 {"type": "tug", "rows": [{"team": t, "own": round(float(so[t]), 1), "opp": round(float(sd[t]), 1)} for t in (a, b)],
                  "lg": round(T["start_lg"], 1)},
                 "Combines special teams, turnovers and defense · garbage time included")


def third_card(T, a, b, M, game):
    to, tdf, th = T["third_off"], T["third_def"], T["third"]
    best = None
    for off, de in ((a, b), (b, a)):
        zo, zd = _z(to, off), _z(tdf, de)
        if np.isnan(zo) or np.isnan(zd):
            continue
        if best is None or abs(zo + zd) > best[0]:
            best = (abs(zo + zd), off, de, zo + zd)
    if best is None:
        return None
    sc, off, de, tot = best
    ro, n = _rk(to, off)
    rd, _ = _rk(tdf, de)
    t1 = f"{M[off]['label']} converts {round(100 * to[off])}% of 3rd downs, {_rank_txt(ro, n, 'highest', 'lowest')}."
    t2 = f"{poss(M[de]['label'])} defense allows {round(100 * tdf[de])}%, {_rank_txt(rd, n, 'highest', 'lowest')}."
    dots = lambda df: [{"x": int(min(p.ydstogo, 15)), "c": bool(p.conv), "j": round(_jit(f"{p.game_id}{p.play_id}", 0.8), 3)} for p in df.itertuples()]
    return _card(f"thirds:{off}", "thirds", "team", off if tot > 0 else de, 0.5 + 0.25 * min(sc, 3), t1, t2,
                 f"Every 3rd down by yards to go: {M[off]['nick']} offense (top) and {M[de]['nick']} defense (bottom), {game['span']}.",
                 {"type": "thirds", "off": off, "def": de, "a": dots(th[th["posteam"] == off]), "b": dots(th[th["defteam"] == de])},
                 "Converted = gained the yards to go or scored · 15+ grouped at the right")


def penalty_card(T, a, b, M, game):
    if "pen" not in T:
        return None
    pg, pn = T["pen_g"], T["pen"]
    if a not in pg.index or b not in pg.index:
        return None
    hi = a if pg[a] >= pg[b] else b
    lo = b if hi == a else a
    r, n = _rk(pg, hi)
    rows = []
    for t in (a, b):
        g = pn[pn["penalty_team"] == t].groupby("penalty_type").size().sort_values(ascending=False).head(5) / T["n_games"].get(t, 1)
        rows.append({"team": t, "per_game": round(float(pg[t]), 2), "types": [{"k": k, "v": round(float(v), 2)} for k, v in g.items()]})
    t1 = f"{M[hi]['label']} is flagged {pg[hi]:.1f} times per game, {_rank_txt(r, n)}."
    t2 = f"{M[lo]['label']}: {pg[lo]:.1f} per game."
    return _card(f"penalties:{a}{b}", "penalties", "team", hi, 0.35 + 0.35 * abs(_z(pg, a) - _z(pg, b)), t1, t2,
                 f"Accepted and declined penalties per game, top 5 types for each team, {game['span']}.",
                 {"type": "penalties", "rows": rows},
                 "Officiating crew data is not included yet")


def splits_card(T, a, b, M, game):
    have = [k for k in ("pa", "motion") if f"{k}_off" in T]
    if not have:
        return None
    best = None
    for k in have:
        oo, dd = T[f"{k}_off"], T[f"{k}_def"]
        for off, de in ((a, b), (b, a)):
            if off not in oo.index or de not in dd.index or 1 not in oo.columns:
                continue
            lift = float(oo.loc[off, 1] - oo.loc[off, 0])
            dl = float(dd.loc[de, 1] - dd.loc[de, 0])
            sc = abs(lift + dl)
            if not np.isnan(sc) and (best is None or sc > best[0]):
                best = (sc, k, off, de, lift, dl)
    if best is None:
        return None
    sc, k, off, de, lift, dl = best
    word = "play action" if k == "pa" else "pre-snap motion"
    rate = float(T[f"{k}_rate"].get(off, np.nan))
    t1 = (f"{M[off]['label']} gains {lift:.2f} more EPA per dropback with {word} than without (uses it {round(100 * rate)}% of the time)." if lift >= 0 else
          f"{M[off]['label']} is {abs(lift):.2f} EPA per dropback worse with {word} than without (uses it {round(100 * rate)}% of the time).")
    t2 = (f"{poss(M[de]['label'])} defense gives up {dl:.2f} more EPA per dropback against it." if dl >= 0 else
          f"{poss(M[de]['label'])} defense is {abs(dl):.2f} EPA per dropback better against it.")
    oo, dd = T[f"{k}_off"], T[f"{k}_def"]
    return _card(f"splits:{k}{off}", "splits", "team", off if lift + dl > 0 else de, 0.45 + 1.5 * min(sc, 0.6), t1, t2,
                 f"EPA per dropback with and without {word}: {M[off]['nick']} offense vs. {M[de]['nick']} defense, {game['span']}.",
                 {"type": "splits", "word": word.upper(), "rows": [
                     {"team": off, "label": f"{M[off]['nick']} offense".upper(), "with": round(float(oo.loc[off, 1]), 3), "without": round(float(oo.loc[off, 0]), 3)},
                     {"team": de, "label": f"{M[de]['nick']} defense allows".upper(), "with": round(float(dd.loc[de, 1]), 3), "without": round(float(dd.loc[de, 0]), 3)}]},
                 "FTN charting · garbage time removed · not shrunk", "FTN CHARTING VIA NFLVERSE")
