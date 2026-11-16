"""Field-style visuals: pass chart vs. defensive completion heat map, run chart vs. run defense by gap,
receiver target chart, drive chart, QB pressure map and fourth-down decision map."""
import numpy as np
import pandas as pd

from . import stats as S
from .clean import GAP_ORDER
from .text import ordinal, possessive as poss

SRC = "NFLVERSE PLAY-BY-PLAY"
LANES = ("left", "middle", "right")
BANDS = (("BEHIND", -99, 0), ("0-9", 0, 10), ("10-19", 10, 20), ("20+", 20, 99))
GAP_NAME = {"L END": "outside left", "L TACKLE": "off left tackle", "L GUARD": "behind the left guard", "MIDDLE": "up the middle",
            "R GUARD": "behind the right guard", "R TACKLE": "off right tackle", "R END": "outside right"}
BAND_NAME = {"BEHIND": "behind the line", "0-9": "short (0-9 yards)", "10-19": "intermediate (10-19)", "20+": "deep (20+)"}
LANE_NAME = {"left": "left", "middle": "middle", "right": "right"}
YL_BINS = [(80, 100, "OWN 1-20"), (60, 80, "OWN 21-40"), (40, 60, "OWN 41-OPP 40"), (20, 40, "OPP 39-21"), (0, 20, "OPP 20-1")]
TG_BINS = [(1, 1, "1"), (2, 2, "2"), (3, 3, "3"), (4, 5, "4-5"), (6, 99, "6+")]


def _jit(key, w):
    """Stable jitter from a play key (no RNG state)."""
    h = 0
    for ch in str(key):
        h = (h * 31 + ord(ch)) % 1000003
    return ((h * 2654435761) % 1000 / 1000 - 0.5) * w


def _card(cid, phase, kind, owner, score, t1, t2, sub, chart, note, src=SRC):
    return {"id": cid, "kind": kind, "phase": phase, "owner": owner, "score": round(float(score), 3), "edge": round(float(score), 3),
            "t1": t1, "t2": t2, "sub": sub, "chart": chart, "source": src, "note": note}


def _rkpct(s, t, high=True):
    s = s.dropna()
    return int(((s > s[t]) if high else (s < s[t])).sum() + 1), len(s)


# ---------------- tables ----------------
def tables(plays, pbp, season, week):
    T = {}
    att = plays[plays["attempt"] & plays["pass_location"].isin(LANES) & plays["air_yards"].notna()].copy() \
        if "pass_location" in plays.columns else plays.iloc[0:0]
    if len(att) > 2000:
        att["band"] = pd.cut(att["air_yards"], [-99, 0, 10, 20, 99], right=False, labels=[b[0] for b in BANDS]).astype(str)
        att["res"] = np.where(att["interception"] == 1, "int", np.where((att["complete_pass"] == 1) & (att["touchdown"] == 1), "td",
                              np.where(att["complete_pass"] == 1, "comp", "inc")))
        att["cell"] = att["band"] + "|" + att["pass_location"]
        T["att"] = att
        T["cell_lg"] = att.groupby("cell")["complete_pass"].mean()
        T["cell_def"] = att.groupby(["defteam", "cell"])["complete_pass"].agg(["mean", "size"])
        T["cell_off"] = att.groupby(["posteam", "cell"]).size().unstack(fill_value=0)
    ru = plays[plays["designed_run"] & plays["gap"].notna()].copy()
    if len(ru) > 1500:
        T["runs"] = ru
        T["gap_lg"] = ru.groupby("gap")["yards_gained"].mean()
        T["gap_def"] = ru.groupby(["defteam", "gap"])["yards_gained"].agg(["mean", "size"])
        T["gap_off"] = ru.groupby(["posteam", "gap"]).size().unstack(fill_value=0)
    if {"fixed_drive", "fixed_drive_result", "yardline_100", "game_id"} <= set(plays.columns):
        dp = plays.sort_values(["game_id", "fixed_drive", "play_id"] if "play_id" in plays.columns else ["game_id", "fixed_drive"])
        g = dp.groupby(["game_id", "posteam", "fixed_drive"]).agg(week=("week", "first"), start=("yardline_100", "first"),
                                                                  last=("yardline_100", "last"), gain=("yards_gained", "last"),
                                                                  res=("fixed_drive_result", "first")).reset_index()
        g["end"] = (g["last"] - g["gain"].fillna(0)).clip(0, 100)
        g["pts"] = g["res"].map({"Touchdown": 7, "Field goal": 3}).fillna(0)
        T["drives"] = g
    if pbp is not None and {"down", "ydstogo", "yardline_100", "play_type"} <= set(pbp.columns):
        d = pbp
        if "season" in d.columns:
            d = d[pd.to_numeric(d["season"], errors="coerce") == season]
        if "season_type" in d.columns:
            d = d[d["season_type"] == "REG"]
        f = d[(pd.to_numeric(d["week"], errors="coerce") < week) & (pd.to_numeric(d["down"], errors="coerce") == 4)
              & d["play_type"].isin(["pass", "run", "punt", "field_goal"]) & d["posteam"].notna()].copy()
        if "wp" in f.columns:
            f = f[f["wp"].between(0.05, 0.95)]
        if len(f) > 200:
            f["dec"] = np.where(f["play_type"].isin(["pass", "run"]), "go", np.where(f["play_type"] == "punt", "punt", "fg"))
            f["yb"] = pd.cut(f["yardline_100"], [0, 20, 40, 60, 80, 100], labels=[b[2] for b in YL_BINS[::-1]], include_lowest=True).astype(str)
            f["tb"] = pd.cut(f["ydstogo"].clip(upper=20), [0, 1, 2, 3, 5, 99], labels=[b[2] for b in TG_BINS]).astype(str)
            T["fourth"] = f
            T["fourth_lg"] = f.groupby(["yb", "tb"])["dec"].apply(lambda s: float((s == "go").mean())).to_dict()
    pr = plays[plays["dropback"] & plays["pressure"].notna() & plays["qb_id"].notna()] if "pressure" in plays.columns else plays.iloc[0:0]
    if len(pr) > 2000:
        g = pr.groupby("qb_id").agg(n=("epa", "size"), pr_rate=("pressure", "mean"))
        u = pr[pr["pressure"] == 1].groupby("qb_id")["epa"].agg(["mean", "size"])
        g = g.join(u.rename(columns={"mean": "epa_pr", "size": "n_pr"}))
        T["qbp"] = g[(g["n"] >= 100) & (g["n_pr"] >= 20)]
    return T


# ---------------- pass chart ----------------
def pass_card(T, a, b, M, game):
    if "att" not in T:
        return None
    att, lg, de_t, off_t = T["att"], T["cell_lg"], T["cell_def"], T["cell_off"]
    best = None
    for off, de in ((a, b), (b, a)):
        if off not in off_t.index:
            continue
        share = off_t.loc[off] / off_t.loc[off].sum()
        lg_share = off_t.sum() / off_t.values.sum()
        for cell, sh in share.items():
            if (de, cell) not in de_t.index or de_t.loc[(de, cell), "size"] < 8:
                continue
            use = sh / lg_share[cell] - 1
            allow = de_t.loc[(de, cell), "mean"] - lg[cell]
            if use < 0.15 or sh < 0.10:
                continue
            sc = use * 2 + abs(allow) * 6
            if best is None or sc > best[0]:
                best = (sc, off, de, cell, sh, allow)
    if best is None:
        return None
    sc, off, de, cell, sh, allow = best
    band, lane = cell.split("|")
    A, B = M[off]["label"], M[de]["label"]
    allowed = de_t.loc[(de, cell), "mean"]
    by_def = de_t.xs(cell, level=1)
    by_def = by_def[by_def["size"] >= 8]["mean"]
    r, n = _rkpct(by_def, de)
    where = f"{BAND_NAME[band]} to the {lane}" if lane != "middle" else f"{BAND_NAME[band]} over the middle"
    t1 = f"{A} throws {where} on {round(100 * sh)}% of passes."
    t2 = (f"{poss(B)} defense allows {round(100 * allowed)}% completions there, {ordinal(r)}-most." if allow > 0 else
          f"{poss(B)} defense holds it to {round(100 * allowed)}% completions there, {ordinal(n + 1 - r)}-fewest.")
    mine = att[att["posteam"] == off]
    dots = [{"x": round({"left": -1, "middle": 0, "right": 1}[p.pass_location] * 0.62 + _jit(f"{p.game_id}{p.play_id}", 0.48), 3),
             "y": round(float(p.air_yards), 1), "r": p.res} for p in mine.itertuples()]
    cells = [{"band": bb, "lane": ln, "comp": None if (de, f"{bb}|{ln}") not in de_t.index else round(float(de_t.loc[(de, f"{bb}|{ln}"), "mean"]), 3),
              "n": 0 if (de, f"{bb}|{ln}") not in de_t.index else int(de_t.loc[(de, f"{bb}|{ln}"), "size"]),
              "lg": round(float(lg.get(f"{bb}|{ln}", np.nan)), 3)} for bb, _, _ in BANDS for ln in LANES]
    return _card(f"passchart:{off}", "passchart", "team", off if allow > 0 else de, 0.9 + 0.25 * min(sc, 3), t1, t2,
                 f"Left: every {M[off]['nick']} pass, {game['span']}. Right: {M[de]['nick']} defense, completion % allowed vs. league by zone.",
                 {"type": "passchart", "off": off, "def": de, "dots": dots, "cells": cells, "hl": cell},
                 "Depth = air yards (exact) · side = left / middle / right (play-by-play has no exact sideline spot, so dots spread within each lane)")


# ---------------- run chart ----------------
def run_card(T, a, b, M, game):
    if "runs" not in T:
        return None
    ru, lg, de_t, off_t = T["runs"], T["gap_lg"], T["gap_def"], T["gap_off"]
    best = None
    for off, de in ((a, b), (b, a)):
        if off not in off_t.index:
            continue
        share = off_t.loc[off] / off_t.loc[off].sum()
        lg_share = off_t.sum() / off_t.values.sum()
        for gp, sh in share.items():
            if (de, gp) not in de_t.index or de_t.loc[(de, gp), "size"] < 8:
                continue
            use = sh / lg_share[gp] - 1
            allow = de_t.loc[(de, gp), "mean"] - lg[gp]
            if use < 0.15 or sh < 0.10:
                continue
            sc = use * 2 + abs(allow) * 0.6
            if best is None or sc > best[0]:
                best = (sc, off, de, gp, sh, allow)
    if best is None:
        return None
    sc, off, de, gp, sh, allow = best
    A, B = M[off]["label"], M[de]["label"]
    ypc = de_t.loc[(de, gp), "mean"]
    by_def = de_t.xs(gp, level=1)
    by_def = by_def[by_def["size"] >= 8]["mean"]
    r, n = _rkpct(by_def, de)
    t1 = f"{A} runs {GAP_NAME[gp]} on {round(100 * sh)}% of designed runs."
    t2 = (f"{poss(B)} defense gives up {ypc:.1f} yards per carry there, {ordinal(r)}-most." if allow > 0 else
          f"{poss(B)} defense allows just {ypc:.1f} yards per carry there, {ordinal(n + 1 - r)}-fewest.")
    mine = ru[ru["posteam"] == off]
    dots = [{"g": GAP_ORDER.index(p.gap), "x": round(_jit(f"{p.game_id}{p.play_id}", 0.7), 3), "y": float(np.clip(p.yards_gained, -5, 30))}
            for p in mine.itertuples()]
    cells = [{"gap": gg, "ypc": None if (de, gg) not in de_t.index else round(float(de_t.loc[(de, gg), "mean"]), 2),
              "n": 0 if (de, gg) not in de_t.index else int(de_t.loc[(de, gg), "size"]), "lg": round(float(lg.get(gg, np.nan)), 2)} for gg in GAP_ORDER]
    return _card(f"runchart:{off}", "runchart", "team", off if allow > 0 else de, 0.85 + 0.2 * min(sc, 3), t1, t2,
                 f"Left: every {M[off]['nick']} designed run by gap, {game['span']}. Right: {M[de]['nick']} defense, yards per carry allowed vs. league by gap.",
                 {"type": "runchart", "off": off, "def": de, "dots": dots, "cells": cells, "hl": gp, "gaps": GAP_ORDER},
                 "Gap from play-by-play run location and run gap · yards capped at -5 and +30 on the chart")


# ---------------- drive chart ----------------
def drive_card(T, a, b, M, game):
    if "drives" not in T:
        return None
    dr = T["drives"]
    rows, ppd = {}, {}
    for t in (a, b):
        g = dr[dr["posteam"] == t]
        last = g.drop_duplicates("game_id")[["game_id", "week"]].sort_values("week").tail(2)["game_id"].tolist()
        g = g[g["game_id"].isin(last)].sort_values(["week", "fixed_drive"])
        if len(g) < 6:
            return None
        rows[t] = [{"wk": int(x.week), "s": round(100 - float(x.start), 1), "e": round(100 - float(x.end), 1), "res": str(x.res)} for x in g.itertuples()]
        ppd[t] = float(g["pts"].mean())
    lg = float(dr["pts"].mean())
    hi, lo = (a, b) if ppd[a] >= ppd[b] else (b, a)
    t1 = f"{M[hi]['label']} scored {ppd[hi]:.1f} points per drive over its last 2 games."
    t2 = f"{M[lo]['label']}: {ppd[lo]:.1f} (league average {lg:.1f})."
    sc = 0.5 * abs(ppd[a] - ppd[b]) / 0.6
    return _card(f"drives:{a}{b}", "drives", "team", hi, sc, t1, t2,
                 "Every drive from the last 2 games, from where it started to where it ended, colored by result.",
                 {"type": "drives", "teams": [{"team": t, "rows": rows[t], "ppd": round(ppd[t], 2)} for t in (a, b)]},
                 "Points per drive counts touchdowns as 7 · field goals 3 · garbage time removed")


# ---------------- fourth-down map ----------------
def fourth_map_card(T, a, b, M, game):
    if "fourth" not in T:
        return None
    f, lg = T["fourth"], T["fourth_lg"]
    best = None
    for t in (a, b):
        g = f[f["posteam"] == t]
        if len(g) < 12:
            continue
        # go decisions vs. league go rate in the same cells
        exp = g.apply(lambda r: lg.get((r["yb"], r["tb"]), 0.0), axis=1)
        over = float((g["dec"] == "go").mean() - exp.mean())
        if best is None or abs(over) > abs(best[1]):
            best = (t, over, g, float((g["dec"] == "go").sum()), float(exp.sum()))
    if best is None:
        return None
    t, over, g, go, xgo = best
    if abs(go - xgo) < 1.5:
        return None
    coach = (game.get("coach") or {}).get(t)
    who = f"{coach}'s {M[t]['nick']}" if isinstance(coach, str) and coach else M[t]["label"]
    times = f"{int(go)} time{'s' if int(go) != 1 else ''}"
    t1 = (f"{who} went for it {times} on 4th down, about {go - xgo:.0f} more than a typical team would." if over > 0 else
          f"{who} went for it {times} on 4th down, about {xgo - go:.0f} fewer than a typical team would.")
    t2 = "Aggressive calls add expected points over a season." if over > 0 else "Punting in go spots costs expected points."
    pts = [{"x": [b_[2] for b_ in YL_BINS].index(r.yb) if r.yb in [b_[2] for b_ in YL_BINS] else 0,
            "y": [b_[2] for b_ in TG_BINS].index(r.tb) if r.tb in [b_[2] for b_ in TG_BINS] else 0,
            "d": r.dec, "j": round(_jit(f"{r.game_id}{getattr(r, 'play_id', 0)}", 0.7), 3), "k": round(_jit(f"k{r.game_id}{getattr(r, 'play_id', 0)}", 0.6), 3)}
           for r in g.itertuples()]
    bg = [{"x": i, "y": j, "go": round(float(lg.get((yb[2], tb[2]), 0.0)), 3)} for i, yb in enumerate(YL_BINS) for j, tb in enumerate(TG_BINS)]
    return _card(f"fourthmap:{t}", "fourth", "team", t, 0.6 + 2.0 * abs(over), t1, t2,
                 f"Every {M[t]['nick']} 4th down by field position and distance, {game['span']}. Shading = how often the league goes for it there.",
                 {"type": "fourthmap", "team": t, "pts": pts, "bg": bg, "xl": [b_[2] for b_ in YL_BINS], "yl": [b_[2] for b_ in TG_BINS]},
                 "Win probability 5-95% · go = run or pass play · kneels and penalties left out")


# ---------------- player visuals ----------------
def receiver_card(T, a, b, M, game, ctx, name, img):
    if "att" not in T:
        return None
    att = T["att"]
    best = None
    for t in (a, b):
        for pid in ctx["tgt"].get(t, [])[:2]:
            g = att[att["receiver_player_id"] == pid]
            if len(g) >= 25 and (best is None or len(g) > len(best[2])):
                best = (pid, t, g)
    if best is None:
        return None
    pid, t, g = best
    opp = b if t == a else a
    nm = name(pid)
    cr, adot = float(g["complete_pass"].mean()), float(g["air_yards"].mean())
    fav = g["cell"].value_counts()
    cell = fav.index[0]
    band, lane = cell.split("|")
    where = f"{BAND_NAME[band]} to the {lane}" if lane != "middle" else f"{BAND_NAME[band]} over the middle"
    t1 = f"{nm} catches {round(100 * cr)}% of his targets, {adot:.1f} yards downfield on average."
    t2 = f"His spot: {where} ({round(100 * fav.iloc[0] / len(g))}% of targets)."
    de_t = T["cell_def"]
    if (opp, cell) in de_t.index:
        t2 += f" {poss(M[opp]['label'])} defense allows {round(100 * de_t.loc[(opp, cell), 'mean'])}% completions there."
    dots = [{"x": round({"left": -1, "middle": 0, "right": 1}[p.pass_location] * 0.62 + _jit(f"{p.game_id}{p.play_id}", 0.48), 3),
             "y": round(float(p.air_yards), 1), "r": p.res} for p in g.itertuples()]
    return _card(f"rcvchart:{pid}", "rcvchart", "player", t, 0.95, t1, t2,
                 f"Every target to {nm}, {game['span']}.",
                 {"type": "rcvchart", "team": t, "dots": dots, "name": nm, "img": img(pid)},
                 f"{len(g)} targets · depth = air yards · side = left / middle / right")


def pressure_card(T, a, b, M, game, ctx, name, img, ttt=None, rush=None):
    q = T.get("qbp")
    if q is None or len(q) < 12:
        return None
    qs = [(ctx["qb"].get(t), t) for t in (a, b) if ctx["qb"].get(t) in q.index]
    if not qs:
        return None
    xcol, xlab, xfmt = "pr_rate", "PRESSURE RATE FACED", "pct"
    if ttt is not None and len(set(q.index) & set(ttt.index)) >= 12:
        q = q.join(ttt["value"].rename("ttt"), how="inner")
        xcol, xlab, xfmt = "ttt", "AVERAGE TIME TO THROW (SECONDS)", "sec"
        qs = [x for x in qs if x[0] in q.index]
        if not qs:
            return None
    z = (q["epa_pr"] - q["epa_pr"].mean()) / (q["epa_pr"].std() or 1)
    pid, t = max(qs, key=lambda x: abs(z[x[0]]))
    opp = b if t == a else a
    nm, v = name(pid), float(q.loc[pid, "epa_pr"])
    r = int((q["epa_pr"] > v).sum() + 1)
    t1 = f"Under pressure, {nm} averages {v:+.2f} EPA per dropback, {ordinal(r)} of {len(q)}."
    t2 = ""
    if rush is not None and opp in rush.index:
        rr = int((rush["value_s"] > rush.loc[opp, "value_s"]).sum() + 1)
        t2 = f"{poss(M[opp]['label'])} pass rush ranks {ordinal(rr)} ({round(100 * float(rush.loc[opp, 'value_s']))}% of dropbacks)."
    hl = {x[0] for x in qs}
    pts = [{"id": p, "name": name(p), "short": str(name(p)).split()[-1], "team": ctx["team"].get(p), "hl": p in hl,
            "img": img(p) if p in hl else None, "x": round(float(row[xcol]), 3), "y": round(float(row["epa_pr"]), 3)} for p, row in q.iterrows()]
    return _card(f"pressmap:{pid}", "pressmap", "player", t, 0.7 * abs(float(z[pid])) + 0.3, t1, t2,
                 f"Every QB with 100+ dropbacks, {game['span']}. Up = better when pressured.",
                 {"type": "pscatter", "pts": pts, "fmt_x": xfmt, "fmt_y": "epa", "x_label": xlab, "x_sub": "",
                  "y_label": "EPA PER DROPBACK UNDER PRESSURE", "y_sub": "", "med": [round(float(q[xcol].median()), 3), round(float(q["epa_pr"].median()), 3)]},
                 "Pressure = charted pressure when available, else QB hit or sack")
