"""Play-type tendency matchups: where an offense throws (6 target zones) vs. how the defense holds up there,
and whether an offense leans pass or run vs. which one the defense is weaker against."""
import numpy as np
import pandas as pd

from . import stats as S
from .text import ordinal, possessive as poss

SRC = "NFLVERSE PLAY-BY-PLAY"
ZONES = [(d, s) for d in ("deep", "short") for s in ("left", "middle", "right")]
ZNAME = {("short", "middle"): "short over the middle", ("short", "left"): "short to the left", ("short", "right"): "short to the right",
         ("deep", "middle"): "deep over the middle", ("deep", "left"): "deep to the left", ("deep", "right"): "deep to the right"}


def _z(s, t):
    s = s.dropna()
    return float((s[t] - s.mean()) / (s.std() or 1)) if t in s.index else np.nan


def _rk(s, t, high=True):
    s = s.dropna()
    return int((s > s[t]).sum() + 1) if high else int((s < s[t]).sum() + 1), len(s)


def tables(plays, tpls):
    out = {}
    if "pass_location" in plays.columns and "air_yards" in plays.columns:
        a = plays[plays["eff"] & plays["attempt"] & plays["pass_location"].isin(["left", "middle", "right"]) & plays["air_yards"].notna()].copy()
        if len(a) > 2000:
            a["depth"] = np.where(a["air_yards"] >= 10, "deep", "short")
            a["zone"] = a["depth"] + "|" + a["pass_location"]
            cnt = a.groupby(["posteam", "zone"]).size().unstack(fill_value=0)
            out["z_share"] = cnt.div(cnt.sum(axis=1), axis=0)
            out["z_lg"] = a["zone"].value_counts(normalize=True)
            dz = {}
            for z, g in a.groupby("zone"):
                dz[z] = S.eb(S.agg(g, "defteam", "epa"), 15)["value_s"]
            out["z_def"] = pd.DataFrame(dz)
            out["z_def_lg"] = a.groupby("zone")["epa"].mean()
    if {"receiver_player_id", "receiver_player_name", "complete_pass"} <= set(plays.columns):
        r = plays[plays["eff"] & plays["attempt"] & plays["receiver_player_id"].notna()]
        if len(r) > 2000:
            cnt = r.groupby(["posteam", "receiver_player_id"]).size().rename("n").reset_index()
            top = cnt.sort_values("n", ascending=False).drop_duplicates("posteam").set_index("posteam")
            r = r.assign(top=r["receiver_player_id"].eq(r["posteam"].map(top["receiver_player_id"])).astype(float))
            nm = r.drop_duplicates("receiver_player_id").set_index("receiver_player_id")["receiver_player_name"]
            t1 = r[r["top"] == 1]
            out["wr1_def"] = S.eb(S.agg(t1, "defteam", "epa"), 30)["value_s"]
            out["wr1_catch"] = t1.groupby("defteam")["complete_pass"].mean()
            out["wr1_share"] = r.groupby("posteam")["top"].mean()
            out["wr1_name"] = top["receiver_player_id"].map(nm)
    tp = {t.id: t for t in tpls}
    nt = plays[plays["neutral"]]
    if "xpass" in nt.columns and nt["xpass"].notna().mean() > 0.5 and "pass_epa" in tp and "rush_epa" in tp:
        n2 = nt.assign(proe=nt["is_pass"] - nt["xpass"])
        out["proe"] = S.eb(S.agg(n2, "posteam", "proe"), 120)["value_s"]
        pa, ra = tp["pass_epa"].deff["value_s"], tp["rush_epa"].deff["value_s"]
        out["split"] = ((pa - pa.mean()) / pa.std() - (ra - ra.mean()) / ra.std()).dropna()
        out["pass_allowed"], out["rush_allowed"] = pa, ra
    return out


def _card(cid, phase, owner, score, t1, t2, sub, chart, note):
    return {"id": cid, "kind": "team", "phase": phase, "owner": owner, "score": round(float(score), 3), "edge": round(float(score), 3),
            "t1": t1, "t2": t2, "sub": sub, "chart": chart, "source": SRC, "note": note}


def zone_card(X, a, b, M, game):
    if "z_share" not in X:
        return None
    sh, df_ = X["z_share"], X["z_def"]
    best = None
    for off, de in ((a, b), (b, a)):
        if off not in sh.index or de not in df_.index:
            continue
        for d, s in ZONES:
            z = f"{d}|{s}"
            if z not in sh.columns or z not in df_.columns:
                continue
            zs, zd = _z(sh[z], off), _z(df_[z], de)
            if np.isnan(zs) or np.isnan(zd) or zs < 0.6:
                continue
            sc = 0.45 * (zs + abs(zd))
            if best is None or sc > best[0]:
                best = (sc, off, de, d, s, z, zd)
    if best is None:
        return None
    sc, off, de, d, s, z, zd = best
    A, B = M[off]["label"], M[de]["label"]
    r, n = _rk(sh[z], off)
    rd, nd = _rk(df_[z], de)
    share, allowed = float(sh.loc[off, z]), float(df_.loc[de, z])
    t1 = f"{A} throws {ZNAME[(d, s)]} on {round(100 * share)}% of passes, {ordinal(r)}-most."
    t2 = (f"{poss(B)} defense allows {allowed:+.2f} EPA per throw there, {ordinal(rd)}-worst." if zd > 0 else
          f"{poss(B)} defense is {ordinal(nd + 1 - rd)}-best there ({allowed:+.2f} EPA per throw).")
    cells = lambda tab, t, lg: [{"zone": f"{dd}|{ss}", "depth": dd, "side": ss, "v": round(float(tab.loc[t, f"{dd}|{ss}"]), 4) if f"{dd}|{ss}" in tab.columns else None,
                                 "lg": round(float(lg.get(f"{dd}|{ss}", np.nan)), 4)} for dd, ss in ZONES]
    return _card(f"zone:{off}", "zones", off if zd > 0 else de, sc, t1, t2,
                 f"Where {M[off]['nick']} passes go (share of throws) vs. {poss(M[de]['nick'])} EPA allowed by zone, {game['span']}. Deep = 10+ air yards.",
                 {"type": "zones", "hl": z,
                  "off": {"team": off, "label": f"{M[off]['nick']} targets".upper(), "fmt": "pct", "cells": cells(sh, off, X["z_lg"])},
                  "def": {"team": de, "label": f"{M[de]['nick']} defense: EPA allowed".upper(), "fmt": "epa", "cells": cells(df_, de, X["z_def_lg"])}},
                 "Left and right from the quarterback's view · garbage time removed · defense EPA shrunk to league mean")


def lean_card(X, a, b, M, game):
    if "proe" not in X:
        return None
    pr, sp = X["proe"], X["split"]
    best = None
    for off, de in ((a, b), (b, a)):
        zl, zsp = _z(pr, off), (float(sp[de]) if de in sp.index else np.nan)
        if np.isnan(zl) or np.isnan(zsp) or abs(zl) < 0.7 or abs(zsp) < 0.5:
            continue
        aligned = np.sign(zl) == np.sign(zsp)
        sc = (0.45 if aligned else 0.3) * (abs(zl) + abs(zsp))
        if best is None or sc > best[0]:
            best = (sc, off, de, zl, zsp, aligned)
    if best is None:
        return None
    sc, off, de, zl, zsp, aligned = best
    A, B = M[off]["label"], M[de]["label"]
    v = float(pr[off])
    r, n = _rk(pr, off, high=zl > 0)
    pa, ra = X["pass_allowed"].dropna(), X["rush_allowed"].dropna()
    pass_rank = int((pa < pa[de]).sum() + 1)  # 1 = fewest EPA allowed = best
    run_rank = int((ra < ra[de]).sum() + 1)
    pct = f"{'+' if v >= 0 else '−'}{abs(round(100 * v))}%"
    if zl > 0:
        t1 = f"{A} throws more than expected in neutral situations ({pct} pass rate over expected), {ordinal(r)}-most."
    else:
        t1 = f"{A} leans on the run ({pct} pass rate over expected), {ordinal(r)}-most run-heavy."
    if aligned:
        weak, strong, wr, sr = (("the pass", "the run", pass_rank, run_rank) if zsp > 0 else ("the run", "the pass", run_rank, pass_rank))
        t2 = f"{poss(B)} defense is weaker against {weak} ({ordinal(wr)}) than {strong} ({ordinal(sr)})."
    else:
        lean, lr = ("the pass", pass_rank) if zl > 0 else ("the run", run_rank)
        t2 = f"That plays into {poss(B)} strength: its defense ranks {ordinal(lr)} against {lean}."
    pts = lambda s: [{"team": t, "v": round(float(x), 4)} for t, x in s.dropna().items()]
    return _card(f"lean:{off}", "lean", off if aligned else de, sc, t1, t2,
                 f"Pass rate over expected (neutral situations) vs. how much worse each defense is against the pass than the run, {game['span']}.",
                 {"type": "strips", "rows": [
                     {"label": f"{M[off]['nick']} offense: pass rate over expected".upper(), "fmt": "pct_pm", "hl": off, "pts": pts(pr),
                      "left": "RUN-HEAVY", "right": "PASS-HEAVY"},
                     {"label": f"{M[de]['nick']} defense: weaker vs. pass or run".upper(), "fmt": "num1", "hl": de, "pts": pts(sp),
                      "left": "WEAKER VS. RUN", "right": "WEAKER VS. PASS"}]},
                 "Defense lean = pass-defense z-score minus run-defense z-score (opponent-adjusted EPA allowed)")


def wr1_card(X, a, b, M, game):
    if "wr1_def" not in X:
        return None
    d, sh, nm = X["wr1_def"].dropna(), X["wr1_share"], X["wr1_name"]
    best = None
    for off, de in ((a, b), (b, a)):
        zd = _z(d, de)
        if np.isnan(zd) or abs(zd) < 0.7 or off not in nm.index or pd.isna(nm[off]):
            continue
        sc = 0.5 * abs(zd)
        if best is None or sc > best[0]:
            best = (sc, off, de, zd)
    if best is None:
        return None
    sc, off, de, zd = best
    A, B = M[off]["label"], M[de]["label"]
    r, _ = _rk(d, de, high=zd > 0)
    catch = float(X["wr1_catch"][de])
    t1 = (f"{poss(B)} defense allows {d[de]:+.2f} EPA per target to top receivers, {ordinal(r)}-worst."
          if zd > 0 else f"{poss(B)} defense holds top receivers to {d[de]:+.2f} EPA per target, {ordinal(r)}-best.")
    t2 = f"{A} feed {nm[off]}, {round(100 * float(sh[off]))}% of their targets."
    pts = lambda s: [{"team": t, "v": round(float(x), 4)} for t, x in s.dropna().items()]
    return _card(f"wr1:{off}", "wr1", off if zd > 0 else de, sc, t1, t2,
                 f"EPA per target each defense allows to the opposing top receiver vs. how much each offense leans on its top receiver, {game['span']}.",
                 {"type": "strips", "rows": [
                     {"label": f"{M[de]['nick']} defense: EPA allowed per target to top receivers".upper(), "fmt": "epa", "hl": de, "pts": pts(d),
                      "left": "STINGY", "right": "GENEROUS"},
                     {"label": f"{M[off]['nick']} offense: share of targets to top receiver".upper(), "fmt": "pct_pm", "hl": off, "pts": pts(sh),
                      "left": "SPREAD OUT", "right": "TOP-HEAVY"}]},
                 f"Top receiver = most targets on the team · catch rate allowed to top receivers {round(100 * catch)}% · garbage time removed · defense EPA shrunk to league mean")
