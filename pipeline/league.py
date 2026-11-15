"""League table and team pages: opponent-adjusted unit ranks, weekly trend, record, playoff odds, game log."""
import json
from pathlib import Path

import numpy as np

from . import stats as S

UNITS = ["pass_epa", "rush_epa", "explosive", "pressure", "stuff", "red_zone"]
TREND_WEEKS = 4


def _net(plays, upto):
    e = plays[plays["eff"] & (plays["week"] < upto)]
    if e["posteam"].nunique() < 30:
        return {}
    o, d = S.opp_adjust(e, "epa")
    return (o["value_s"] - d["value_s"].reindex(o.index)).dropna().to_dict()


def _ranks(v):
    order = sorted(v, key=lambda t: -v[t])
    return {t: i + 1 for i, t in enumerate(order)}


def build(site, season, week, plays, sched, tpls, lev_teams, M, qb, names, synthetic):
    teams = sorted(M)
    net_now, net_then = _net(plays, week), _net(plays, week - TREND_WEEKS)
    r_now, r_then = _ranks(net_now), (_ranks(net_then) if net_then else {})
    tp = {t.id: t for t in tpls}
    reg = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    done = reg[reg["result"].notna() & (reg["week"] < week)]
    e = plays[plays["eff"]]
    wk = e.groupby(["posteam", "week"])["epa"].mean()
    wd = e.groupby(["defteam", "week"])["epa"].mean()
    out = {}
    for t in teams:
        hg, ag = done[done["home_team"] == t], done[done["away_team"] == t]
        diff = np.concatenate([hg["result"].values, -ag["result"].values]).astype(float)
        units = {}
        for uid in UNITS:
            tpl = tp.get(uid)
            if tpl is None:
                continue
            ov = tpl.off["value_s"].get(t, np.nan)
            dv = tpl.deff["value_s"].get(t, np.nan)
            units[uid] = {"label": tpl.label, "fmt": tpl.fmt, "unit_off": tpl.unit_off, "unit_def": tpl.unit_def,
                          "off": {"v": None if np.isnan(ov) else round(float(ov), 4), "r": S.rank(tpl.off, t, tpl.sign)},
                          "def": {"v": None if np.isnan(dv) else round(float(dv), 4), "r": S.rank(tpl.deff, t, -tpl.sign)}}
        trend = [{"week": int(w), "off": round(float(wk.get((t, w), np.nan)), 3) if (t, w) in wk.index else None,
                  "def": round(float(wd.get((t, w), np.nan)), 3) if (t, w) in wd.index else None}
                 for w in sorted(e["week"].unique())]
        out[t] = {"w": int((diff > 0).sum()), "l": int((diff < 0).sum()), "t": int((diff == 0).sum()),
                  "pd": int(diff.sum()) if len(diff) else 0,
                  "net": {"v": round(float(net_now[t]), 4) if t in net_now else None, "r": r_now.get(t),
                          "chg": (r_then[t] - r_now[t]) if t in r_then and t in r_now else None},
                  "p_playoffs": lev_teams.get(t), "qb": names.get(qb.get(t), None),
                  "units": units, "trend": trend, "games": []}
    # game log from every built week (same data type as this build)
    for wdir in sorted((Path(site) / "data" / str(season)).glob("wk*")):
        gj = wdir / "games.json"
        if not gj.exists():
            continue
        board = json.loads(gj.read_text())
        if bool(board.get("synthetic")) != bool(synthetic):
            continue
        for tile in board["games"]:
            h, a = tile["home"], tile["away"]
            for t, opp, home in ((h, a, True), (a, h, False)):
                if t not in out:
                    continue
                pm = (tile.get("model") or {}).get("p_home")
                row = {"week": board["week"], "id": tile["id"], "opp": opp, "home": home, "kickoff": tile.get("kickoff"),
                       "p": None if pm is None else round(pm if home else 1 - pm, 3), "final": tile.get("final")}
                out[t]["games"].append(row)
    doc = {"season": season, "week": week, "trend_weeks": TREND_WEEKS, "teams": out}
    p = Path(site) / "data" / str(season) / "league.json"
    p.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False))
    return len(out)
