"""Special teams (all kicking plays, EPA per game), field goals over expected, and fourth-down aggressiveness
from the raw play-by-play. Team cards that compete with the other Team-tab cards."""
import numpy as np
import pandas as pd

from . import stats as S
from .config import HALF_LIFE_WEEKS
from .text import ordinal, possessive as poss

SRC = "NFLVERSE PLAY-BY-PLAY"
ST_TYPES = {"punt", "kickoff", "field_goal", "extra_point"}


def _cur(pbp, season, week):
    d = pbp
    if "season" in d.columns:
        d = d[pd.to_numeric(d["season"], errors="coerce") == season]
    if "season_type" in d.columns:
        d = d[d["season_type"] == "REG"]
    d = d[pd.to_numeric(d["week"], errors="coerce") < week].copy()
    d["w"] = 0.5 ** ((week - d["week"]) / HALF_LIFE_WEEKS)
    return d


def _fg_x(fg):
    """Expected make probability: nflverse fg_prob when present, else a logistic fit on kick distance."""
    if "fg_prob" in fg.columns and fg["fg_prob"].notna().mean() > 0.8:
        return pd.to_numeric(fg["fg_prob"], errors="coerce").fillna(fg["fg_prob"].mean())
    x = pd.to_numeric(fg["kick_distance"], errors="coerce").fillna(40).values
    y = fg["made"].values.astype(float)
    b = np.array([4.0, -0.08])
    X = np.column_stack([np.ones_like(x), x])
    for _ in range(25):
        p = 1 / (1 + np.exp(-X @ b))
        Wd = p * (1 - p) + 1e-6
        b = b + np.linalg.solve(X.T @ (X * Wd[:, None]) + 1e-6 * np.eye(2), X.T @ (y - p))
    return pd.Series(1 / (1 + np.exp(-X @ b)), index=fg.index)


def tables(pbp, season, week):
    out = {}
    if pbp is None or "play_type" not in pbp.columns:
        return out
    d = _cur(pbp, season, week)
    st = d[d["play_type"].isin(ST_TYPES) & d["epa"].notna() & d["posteam"].notna()]
    if len(st) > 200:
        rows = pd.concat([st.assign(team=st["posteam"], v=st["epa"]), st.assign(team=st["defteam"], v=-st["epa"])])
        g = rows.groupby(["team", "game_id"]).agg(y=("v", "sum"), w=("w", "first")).reset_index()
        out["st"] = S.eb(S.agg(g, "team", "y"), 4)
    if "field_goal_result" in d.columns:
        fg = d[d["play_type"] == "field_goal"].copy()
        if len(fg) > 60:
            fg["made"] = fg["field_goal_result"] == "made"
            fg["x"] = _fg_x(fg)
            fg["oe"] = 3 * (fg["made"].astype(float) - fg["x"])
            g = fg.groupby("posteam").agg(value=("oe", "sum"), n=("oe", "size"))
            g = g[g["n"] >= 5]
            g["value_s"] = g["value"]
            out["fg"] = g
    need = {"down", "ydstogo", "yardline_100", "wp", "half_seconds_remaining"}
    if need <= set(d.columns):
        f = d[(pd.to_numeric(d["down"], errors="coerce") == 4) & (pd.to_numeric(d["ydstogo"], errors="coerce") <= 2)
              & (pd.to_numeric(d["yardline_100"], errors="coerce") <= 60) & d["wp"].between(0.10, 0.90)
              & (pd.to_numeric(d["half_seconds_remaining"], errors="coerce") > 120)
              & d["play_type"].isin(["pass", "run", "punt", "field_goal"])].copy()
        if len(f) > 60:
            f["go"] = f["play_type"].isin(["pass", "run"]).astype(float)
            out["go"] = S.eb(S.agg(f, "posteam", "go"), 6)
    return out


def _bars(tab, hl, fmt, label, col="value_s"):
    s = tab[col].dropna().sort_values(ascending=False)
    return {"type": "bars", "fmt": fmt, "pts": [{"team": t, "v": round(float(v), 4)} for t, v in s.items()],
            "hl": list(hl), "med": round(float(s.median()), 4), "y_label": label}


def _rk(tab, t):
    s = tab["value_s"].dropna()
    return int((s > s[t]).sum()) + 1, len(s)


def _rank_txt(r, n, good="best", bad="worst"):
    if r == 1:
        return f"the NFL's {good}"
    if r == n:
        return f"the NFL's {bad}"
    return f"{ordinal(r)}-{good}" if r <= (n + 1) / 2 else f"{ordinal(n + 1 - r)}-{bad}"


def _card(cid, phase, owner, score, t1, t2, sub, chart, note):
    return {"id": cid, "kind": "team", "phase": phase, "owner": owner, "score": round(float(score), 3), "edge": round(float(score), 3),
            "t1": t1, "t2": t2, "sub": sub, "chart": chart, "source": SRC, "note": note}


def st_card(T, a, b, M, game):
    tab = T.get("st")
    if tab is None or a not in tab.index or b not in tab.index:
        return None
    za, zb = S.zscore(tab, a), S.zscore(tab, b)
    if np.isnan(za) or np.isnan(zb):
        return None
    hi, lo = (a, b) if za >= zb else (b, a)
    rh, n = _rk(tab, hi)
    rl, _ = _rk(tab, lo)
    vh, vl = float(tab.loc[hi, "value_s"]), float(tab.loc[lo, "value_s"])
    t1 = f"{poss(M[hi]['label'])} special teams are worth {vh:+.1f} points per game, {_rank_txt(rh, n)}."
    t2 = f"{poss(M[lo]['label'])} are {_rank_txt(rl, n)} ({vl:+.1f})."
    return _card(f"st:{a}{b}", "special", hi, 0.6 * abs(za - zb), t1, t2,
                 f"Expected points added per game on punts, kickoffs, field goals and extra points, {game['span']}.",
                 _bars(tab, (a, b), "yds", "SPECIAL TEAMS EPA PER GAME"),
                 "Kicking and return units together · recency-weighted · shrunk to league mean")


def fg_card(T, a, b, M, game):
    tab = T.get("fg")
    if tab is None:
        return None
    have = [t for t in (a, b) if t in tab.index]
    if not have:
        return None
    sd = float(tab["value"].std()) or 1.0
    own = max(have, key=lambda t: abs(tab.loc[t, "value"]))
    v = float(tab.loc[own, "value"])
    r, n = _rk(tab, own)
    t1 = (f"{poss(M[own]['label'])} kicker is {v:+.1f} points over expected on field goals, {_rank_txt(r, n)}." if v >= 0 else
          f"{poss(M[own]['label'])} kicker is {abs(v):.1f} points below expected on field goals, {_rank_txt(r, n)}.")
    oth = next((t for t in have if t != own), None)
    t2 = (f"{poss(M[oth]['label'])} is at {float(tab.loc[oth, 'value']):+.1f}." if oth else "Close games can swing on one kick.")
    return _card(f"fg:{own}", "special", own, 0.6 * abs(v) / sd, t1, t2,
                 f"Field goal points over expected (made minus expected makes, x3), {game['span']}.",
                 _bars(tab, (a, b), "yds", "FG POINTS OVER EXPECTED"),
                 f"Expected make rate by kick distance · {own}: {int(tab.loc[own, 'n'])} attempts · not shrunk")


def fourth_card(T, a, b, M, game):
    tab = T.get("go")
    if tab is None or a not in tab.index or b not in tab.index:
        return None
    za, zb = S.zscore(tab, a), S.zscore(tab, b)
    if np.isnan(za) or np.isnan(zb):
        return None
    own = a if abs(za) >= abs(zb) else b
    oth = b if own == a else a
    r, n = _rk(tab, own)
    v, vo = float(tab.loc[own, "value_s"]), float(tab.loc[oth, "value_s"])
    coach = (game.get("coach") or {}).get(own)
    who = f"{coach}'s {M[own]['nick']}" if isinstance(coach, str) and coach else M[own]["label"]
    t1 = f"{who} go for it on {round(100 * v)}% of 4th-and-short from their own 40 on, {_rank_txt(r, n, 'highest', 'lowest')} rate."
    t2 = f"{M[oth]['label']}: {round(100 * vo)}%, {_rank_txt(*_rk(tab, oth), 'highest', 'lowest')}."
    return _card(f"fourth:{own}", "fourth", own, 0.7 * max(abs(za), abs(zb)), t1, t2,
                 f"Go rate on 4th and 1-2 at or past their own 40, win probability 10-90%, {game['span']}.",
                 _bars(tab, (a, b), "pct", "4TH-AND-SHORT GO RATE"),
                 "Outside the last 2 minutes of each half · recency-weighted · shrunk to league mean")
