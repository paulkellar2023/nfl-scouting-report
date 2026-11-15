"""NFL Next Gen Stats and Pro Football Reference charting (both via nflverse): season-to-date tables
and the stacked-box team card. Weekly rows are recency-weighted like the play-by-play stats."""
import logging

import numpy as np
import pandas as pd

from . import health
from . import stats as S
from .config import HALF_LIFE_WEEKS
from .text import ordinal, possessive as poss

log = logging.getLogger(__name__)
SRC_NGS = "NFL NEXT GEN STATS VIA NFLVERSE"
SRC_PFR = "PRO FOOTBALL REFERENCE VIA NFLVERSE"
PFR_ABBR = {"GNB": "GB", "KAN": "KC", "NWE": "NE", "NOR": "NO", "SFO": "SF", "TAM": "TB", "LVR": "LV", "OAK": "LV",
            "RAM": "LA", "LAR": "LA", "SDG": "LAC", "STL": "LA", "HTX": "HOU", "CLT": "IND", "CRD": "ARI",
            "RAV": "BAL", "OTI": "TEN", "JAC": "JAX"}
NEED = {
    "ngs_pass": ["player_gsis_id", "team_abbr", "week", "attempts", "avg_time_to_throw", "aggressiveness"],
    "ngs_rush": ["player_gsis_id", "team_abbr", "week", "rush_attempts", "rush_yards_over_expected_per_att",
                 "percent_attempts_gte_eight_defenders"],
    "ngs_rec": ["player_gsis_id", "team_abbr", "week", "targets", "avg_separation", "avg_cushion"],
    "pfr_pass": ["team", "week", "times_pressured"],
    "pfr_rush": ["team", "week", "rushing_broken_tackles"],
    "pfr_rec": ["team", "week", "receiving_broken_tackles"],
    "pfr_def": ["team", "week", "def_missed_tackles"],
}


def _clean(df, name, season, week):
    if df is None or not len(df):
        return None
    miss = [c for c in NEED[name] if c not in df.columns]
    if miss:
        health.warn(f"{name}: missing columns {miss}, cards that need it are skipped")
        return None
    d = df.copy()
    if "season" in d.columns:
        d = d[pd.to_numeric(d["season"], errors="coerce") == season]
    for c in ("season_type", "game_type"):
        if c in d.columns:
            d = d[d[c].astype(str).str.upper() == "REG"]
    d["week"] = pd.to_numeric(d["week"], errors="coerce")
    d = d[(d["week"] > 0) & (d["week"] < week)]
    tc = "team_abbr" if "team_abbr" in d.columns else "team"
    d[tc] = d[tc].astype(str).replace(PFR_ABBR)
    d["rw"] = 0.5 ** ((week - d["week"]) / HALF_LIFE_WEEKS)
    return d if len(d) else None


def _player(d, col, ncol, min_n, scale=1.0):
    d = d[d[col].notna() & (pd.to_numeric(d[ncol], errors="coerce") > 0)].copy()
    d["n_"] = pd.to_numeric(d[ncol], errors="coerce")
    d["wn"] = d["rw"] * d["n_"]
    d["wv"] = d["wn"] * pd.to_numeric(d[col], errors="coerce") * scale
    g = d.groupby("player_gsis_id").agg(wv=("wv", "sum"), wn=("wn", "sum"), n=("n_", "sum"))
    g = g[g["n"] >= min_n]
    g["value"] = g["wv"] / g["wn"]
    g["value_s"] = g["value"]
    return g[["value", "value_s", "n"]]


def _opp_map(sched, season):
    s = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    m = {}
    for _, g in s.iterrows():
        m[(g.home_team, g.week)] = g.away_team
        m[(g.away_team, g.week)] = g.home_team
    return m


def _team_rates(num, den, opp, min_games=4):
    """num, den: Series indexed by (team, week). Returns (offense table, defense table) via recency-weighted EB."""
    j = pd.DataFrame({"num": num, "den": den}).dropna()
    j = j[j["den"] > 0].reset_index()
    j.columns = ["team", "week", "num", "den"]
    j["opp"] = [opp.get((t, w)) for t, w in zip(j["team"], j["week"])]
    j = j[j["opp"].notna()]
    j["y"] = j["num"] / j["den"]
    j["w"] = 0.5 ** ((j["week"].max() + 1 - j["week"]) / HALF_LIFE_WEEKS) * j["den"]
    return S.eb(S.agg(j, "team", "y"), min_games), S.eb(S.agg(j, "opp", "y"), min_games)


def tables(x, plays, sched, season, week):
    """x: dict of raw frames (may be empty). Returns dict of tables plus names/teams for player ids."""
    out, names, teams = {}, {}, {}
    d = {k: _clean((x or {}).get(k), k, season, week) for k in NEED}
    for k in ("ngs_pass", "ngs_rush", "ngs_rec"):
        if d[k] is not None and "player_display_name" in d[k].columns:
            last = d[k].sort_values("week").drop_duplicates("player_gsis_id", keep="last")
            names.update(dict(zip(last["player_gsis_id"], last["player_display_name"])))
            teams.update(dict(zip(last["player_gsis_id"], last["team_abbr"])))
    if d["ngs_pass"] is not None:
        out["qb_ttt"] = _player(d["ngs_pass"], "avg_time_to_throw", "attempts", 100)
        out["qb_aggr"] = _player(d["ngs_pass"], "aggressiveness", "attempts", 100, 0.01)
    if d["ngs_rush"] is not None:
        r = d["ngs_rush"]
        out["rb_ryoe"] = _player(r, "rush_yards_over_expected_per_att", "rush_attempts", 50)
        r = r.assign(box=pd.to_numeric(r["percent_attempts_gte_eight_defenders"], errors="coerce") / 100 * r["rush_attempts"])
        g = r.groupby(["team_abbr", "week"])[["box", "rush_attempts"]].sum()
        out["box_off"], out["box_def"] = _team_rates(g["box"], g["rush_attempts"], _opp_map(sched, season))
    if d["ngs_rec"] is not None:
        out["wr_sep"] = _player(d["ngs_rec"], "avg_separation", "targets", 25)
        out["wr_cush"] = _player(d["ngs_rec"], "avg_cushion", "targets", 25)
    opp = _opp_map(sched, season)
    p = plays
    if d["pfr_pass"] is not None:
        num = d["pfr_pass"].groupby(["team", "week"])["times_pressured"].sum()
        den = p[p["dropback"]].groupby(["posteam", "week"]).size()
        den.index.names = ["team", "week"]
        out["press_off"], out["press_def"] = _team_rates(num, den, opp)
    if d["pfr_rush"] is not None and d["pfr_rec"] is not None and d["pfr_def"] is not None:
        bt = (d["pfr_rush"].groupby(["team", "week"])["rushing_broken_tackles"].sum()
              .add(d["pfr_rec"].groupby(["team", "week"])["receiving_broken_tackles"].sum(), fill_value=0))
        tch = p[(p["play_type"] == "run") | (p["complete_pass"] == 1)].groupby(["posteam", "week"]).size()
        tch.index.names = ["team", "week"]
        off, _ = _team_rates(bt, tch, opp)
        mt = d["pfr_def"].groupby(["team", "week"])["def_missed_tackles"].sum()
        # missed tackles by a defense per opponent touch: key the defense's rows by the defense itself
        opp_tch = pd.Series({(opp[k], k[1]): v for k, v in tch.items() if k in opp})
        dfn, _ = _team_rates(mt, opp_tch, opp)
        out["tackle_off"], out["tackle_def"] = off, dfn
    got = sorted(k for k in out)
    log.info("extras: %s", got)
    health.info("extras", got)
    out["names"], out["teams"] = names, teams
    return out


def box_card(X, a, b, M, game):
    """a = offense, b = defense. Stacked boxes (8+ defenders) faced by a's runs vs. stacked by b's defense."""
    o, d = X.get("box_off"), X.get("box_def")
    if o is None or d is None:
        return None
    za, zb = S.zscore(o, a), S.zscore(d, b)
    if np.isnan(za) or np.isnan(zb):
        return None
    e = za + zb
    A, B = M[a]["label"], M[b]["label"]
    va, vb = float(o.loc[a, "value_s"]), float(d.loc[b, "value_s"])
    na, nb = int(o["value_s"].notna().sum()), int(d["value_s"].notna().sum())
    ra, rb = S.rank(o, a, 1), S.rank(d, b, 1)
    pc = lambda v: f"{round(v * 100)}%"
    def rk(r, n):
        if r == 1:
            return "the most in the NFL"
        if r == n:
            return "the fewest in the NFL"
        return f"{ordinal(r)}-most" if r <= (n + 1) / 2 else f"{ordinal(n + 1 - r)}-fewest"
    off_txt = f"{poss(A)} runs face 8+ defenders {pc(va)} of the time, {rk(ra, na)}."
    def_txt = f"{poss(B)} defense puts 8+ in the box on {pc(vb)} of runs, {rk(rb, nb)}."
    owner, l1, l2 = (b, def_txt, off_txt) if e >= 0 else (a, off_txt, def_txt)
    pts = lambda tab: [{"team": t, "v": round(float(v), 4)} for t, v in tab["value_s"].dropna().items()]
    allv = [p["v"] for p in pts(o) + pts(d)]
    return {"id": f"box:{a}", "kind": "team", "phase": "box", "owner": owner, "score": round(abs(e) * 0.75, 3),
            "edge": round(e, 3), "t1": l1, "t2": l2, "sub": f"Share of designed runs with 8+ defenders in the box, {game['span']}.",
            "chart": {"type": "duel", "fmt": "pct", "axis": "RUNS VS. 8+ DEFENDERS IN THE BOX", "better_off": "left",
                      "avg": round(float(np.mean(allv)), 4),
                      "rows": [{"label": f"{A} run game faces".upper(), "side": "off", "hl": a, "pts": pts(o)},
                               {"label": f"{B} defense stacks".upper(), "side": "def", "hl": b, "pts": pts(d)}]},
            "source": SRC_NGS, "note": f"Recency-weighted, shrunk to league mean · {a}: n={int(o.loc[a, 'n'])} games"}
