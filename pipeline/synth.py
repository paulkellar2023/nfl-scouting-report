"""Synthetic nflverse-shaped data for offline testing. Column names follow nflverse pbp,
schedules, teams, rosters, participation and FTN charting."""
import datetime as dt

import numpy as np
import pandas as pd

from .teams_meta import TEAMS, espn_logo

FIRST = ["Jalen", "Marcus", "Tyler", "Devin", "Caleb", "Bryce", "Drew", "Malik", "Trey", "Jordan",
         "Cole", "Isaiah", "Brock", "Darius", "Kyle", "Andre", "Zach", "Jaylen", "Nico", "Owen",
         "Dante", "Elijah", "Grant", "Luke", "Quinn", "Rashad", "Shane", "Trent", "Wes", "Xavier"]
LAST = ["Hollins", "Mercer", "Dawkins", "Price", "Vance", "Okafor", "Lindqvist", "Barrett", "Calloway",
        "Pruitt", "Whitaker", "Nash", "Ellison", "Fontaine", "Graves", "Hutchins", "Iverson", "Jett",
        "Kimball", "Larkin", "Maddox", "Nolan", "Osei", "Pickett", "Ruiz", "Sutter", "Tolbert", "Upshaw",
        "Varner", "Wilder", "Yates", "Zeller", "Ashby", "Boone", "Crowe", "Dunbar"]
GAPS = [("left", "end"), ("left", "tackle"), ("left", "guard"), ("middle", None),
        ("right", "guard"), ("right", "tackle"), ("right", "end")]
ZONE = ["COVER_2", "COVER_3", "COVER_4", "COVER_6"]
MAN = ["COVER_1", "COVER_0", "2_MAN"]
TGT_W = {"WR1": 0.27, "WR2": 0.20, "WR3": 0.13, "TE1": 0.17, "RB1": 0.10, "RB2": 0.05}


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def _ep(yl, down, togo):
    return 5.6 - 0.065 * yl - 0.35 * (down - 1) - 0.04 * (min(togo, 20) - 10)


def _team_params(rng, teams):
    p = {}
    for t in teams:
        d = {k: rng.normal() for k in [
            "pass_tend", "pa", "motion", "blitz", "man", "adot", "rush_gen", "pblock", "pass_off",
            "pass_def", "rush_off", "rush_def", "pa_skill", "vs_man", "vs_zone", "motion_skill",
            "vs_blitz", "blitz_bite", "deep_allow", "yac", "tackle", "hawk", "run_stuff", "pace"]}
        d["gap_pref"] = rng.normal(0, 0.4, 7)
        d["gap_off"] = rng.normal(0, 0.8, 7)
        d["gap_def"] = rng.normal(0, 0.8, 7)
        d["zone_w"] = rng.dirichlet([3, 5, 3, 1.5])
        p[t] = d
    return p


def _players(rng, teams, P):
    rows, pl = [], {}
    for t in teams:
        for pos in ["QB1", "QB2", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1"]:
            pid = f"00-SYN{t:>3}{pos}".replace(" ", "X")
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            q = rng.normal(0.6 * P[t]["pass_off"], 0.6) if pos == "QB1" else rng.normal(-0.6, 0.5)
            pl[pid] = {"name": name, "team": t, "pos": pos, "q": q, "yac": rng.normal(), "stuff": rng.normal()}
            rows.append({"gsis_id": pid, "full_name": name, "position": pos[:2], "team": t, "headshot_url": None})
    return pl, pd.DataFrame(rows)


def _schedule(rng, season, teams):
    start = dt.date(season, 9, 10)
    rows = []
    for wk in range(1, 19):
        perm = rng.permutation(teams).reshape(16, 2)
        thu = start + dt.timedelta(days=7 * (wk - 1))
        for i, (a, h) in enumerate(perm):
            if i == 0:
                day, wd, gt = thu, "Thursday", "20:15"
            elif i == 1:
                day, wd, gt = thu + dt.timedelta(days=3), "Sunday", "20:20"
            elif i == 2:
                day, wd, gt = thu + dt.timedelta(days=4), "Monday", "20:15"
            else:
                day, wd, gt = thu + dt.timedelta(days=3), "Sunday", "13:00" if i < 11 else "16:25"
            rows.append({"game_id": f"{season}_{wk:02d}_{a}_{h}", "season": season, "game_type": "REG",
                         "week": wk, "gameday": day.isoformat(), "weekday": wd, "gametime": gt,
                         "away_team": a, "home_team": h, "div_game": int(TEAMS[a][3] == TEAMS[h][3])})
    return pd.DataFrame(rows)


def _qb_for(t, wk, inj):
    if t in inj and inj[t][0] <= wk <= inj[t][1]:
        return f"00-SYN{t:>3}QB2".replace(" ", "X")
    return f"00-SYN{t:>3}QB1".replace(" ", "X")


def _sim_game(rng, g, P, PL, inj, out):
    gid, wk, home, away = g.game_id, g.week, g.home_team, g.away_team
    score = {home: 0, away: 0}
    clock, drive_no, play_id = 3600.0, 0, 0
    pos = home if rng.random() < 0.5 else away
    while clock > 0:
        drive_no += 1
        off = pos
        de = away if pos == home else home
        qb = _qb_for(off, wk, inj)
        yl = int(np.clip(rng.normal(72, 8), 40, 92))
        down, togo, result = 1, 10, None
        drive_plays = []
        while result is None:
            if clock <= 0:
                result = "End of half"
                break
            if down == 4:
                if yl <= 35:
                    if rng.random() < 0.85:
                        score[off] += 3
                        result = "Field goal"
                    else:
                        result = "Missed field goal"
                    break
                if not (togo <= 2 and yl <= 55 and rng.random() < 0.55):
                    result = "Punt"
                    break
            play_id += 1
            t_left = clock / 3600.0
            diff = score[off] - score[de]
            wp = float(_sig(1.2 * diff / (7 * np.sqrt(max(t_left, 0.02)))))
            base = {1: -0.4, 2: 0.0, 3: 0.9 if togo >= 4 else -0.2, 4: 0.8}[down]
            lg = base + 0.10 * np.clip(togo - 8, -6, 10) - 0.04 * diff * (1 - t_left)
            xpass = float(_sig(lg))
            is_pass = rng.random() < _sig(lg + 0.45 * P[off]["pass_tend"])
            ep0 = _ep(yl, down, togo)
            r = {"game_id": gid, "season": g.season, "season_type": "REG", "week": wk,
                 "home_team": home, "away_team": away, "posteam": off, "defteam": de,
                 "play_id": play_id, "down": down, "ydstogo": togo, "yardline_100": yl,
                 "qtr": min(4, 1 + int((3600 - clock) // 900)), "game_seconds_remaining": clock,
                 "half_seconds_remaining": clock - 1800 if clock > 1800 else clock,
                 "score_differential": diff, "wp": wp, "xpass": xpass, "fixed_drive": drive_no,
                 "pass": 0, "qb_dropback": 0, "qb_scramble": 0, "sack": 0, "qb_hit": 0,
                 "pass_attempt": 0, "complete_pass": 0, "interception": 0, "fumble_lost": 0,
                 "touchdown": 0, "air_yards": np.nan, "yards_after_catch": np.nan,
                 "xyac_mean_yardage": np.nan, "cpoe": np.nan, "run_gap": None, "run_location": None,
                 "pass_location": None, "passer_player_id": None, "passer_player_name": None,
                 "rusher_player_id": None, "rusher_player_name": None, "receiver_player_id": None,
                 "receiver_player_name": None, "rushing_yards": np.nan}
            f = {"nflverse_game_id": gid, "nflverse_play_id": play_id, "is_play_action": 0, "is_motion": 0,
                 "n_blitzers": 0, "n_pass_rushers": 0, "is_interception_worthy": 0, "is_screen_pass": 0}
            pt = {"nflverse_game_id": gid, "play_id": play_id, "possession_team": off, "was_pressure": None,
                  "defense_man_zone_type": None, "defense_coverage_type": None,
                  "number_of_pass_rushers": None, "time_to_throw": None}
            turnover = False
            if is_pass:
                blitz = rng.random() < _sig(-1.3 + 0.7 * P[de]["blitz"])
                nb = int(rng.integers(1, 3)) if blitz else 0
                nr = 4 + nb if blitz else (3 if rng.random() < 0.08 else 4)
                man = rng.random() < _sig(-0.5 + 0.8 * P[de]["man"])
                shell = rng.choice(MAN, p=[0.7, 0.1, 0.2]) if man else rng.choice(ZONE, p=P[de]["zone_w"])
                pa = down <= 2 and rng.random() < _sig(-1.4 + 0.7 * P[off]["pa"])
                motion = rng.random() < _sig(0.1 + 0.8 * P[off]["motion"])
                pres = rng.random() < _sig(-1.05 + 0.45 * P[de]["rush_gen"] - 0.45 * P[off]["pblock"]
                                           + 0.35 * blitz - 0.25 * pa - 0.3 * (nr == 3))
                q = (0.45 * PL[qb]["q"] + 0.30 * P[off]["pass_off"] - 0.40 * P[de]["pass_def"]
                     + 0.35 * pa * P[off]["pa_skill"] + 0.3 * (P[off]["vs_man"] if man else P[off]["vs_zone"])
                     + 0.25 * motion * P[off]["motion_skill"]
                     + (0.25 * P[off]["vs_blitz"] - 0.35 * P[de]["blitz_bite"] if blitz else 0.0))
                if pres:
                    q -= 0.9
                sack = pres and rng.random() < 0.24 - 0.04 * PL[qb]["q"]
                scr = pres and not sack and rng.random() < 0.12
                r.update({"pass": 1, "qb_dropback": 1, "passer_player_id": qb, "passer_player_name": PL[qb]["name"]})
                f.update({"is_play_action": int(pa), "is_motion": int(motion), "n_blitzers": nb, "n_pass_rushers": nr})
                pt.update({"was_pressure": int(pres), "number_of_pass_rushers": nr,
                           "defense_man_zone_type": "MAN_COVERAGE" if man else "ZONE_COVERAGE",
                           "defense_coverage_type": shell, "time_to_throw": round(float(rng.normal(2.8, 0.5)), 2)})
                r["qb_hit"] = int(sack or (pres and rng.random() < 0.45))
                if sack:
                    yards = -int(rng.integers(3, 11))
                    r.update({"play_type": "pass", "sack": 1})
                elif scr:
                    yards = int(np.clip(rng.normal(6, 5), -2, 30))
                    r.update({"play_type": "run", "qb_scramble": 1, "passer_player_id": None,
                              "passer_player_name": None, "rusher_player_id": qb, "rusher_player_name": PL[qb]["name"]})
                else:
                    air = int(np.clip(round(rng.normal(7.4 + 1.6 * P[off]["adot"] + 0.8 * P[de]["deep_allow"], 9.0)), -5, 55))
                    air = min(air, yl)
                    cp_exp = float(_sig(1.15 - 0.075 * air))
                    pc = float(_sig(1.15 - 0.075 * air + 0.45 * q - (0.3 if pres else 0.0)))
                    worthy = rng.random() < 0.035 * np.exp(-0.5 * q) * (1.5 if pres else 1.0)
                    intc = (worthy and rng.random() < 0.55 + 0.12 * P[de]["hawk"]) or rng.random() < 0.002
                    comp = (not intc) and rng.random() < pc
                    recs = list(TGT_W)
                    w = np.array([TGT_W[k] * (1.6 if air >= 15 and k in ("WR1", "WR2") else 1.0) for k in recs])
                    rk = rng.choice(recs, p=w / w.sum())
                    rid = f"00-SYN{off:>3}{rk}".replace(" ", "X")
                    xyac = float(np.clip(5.2 - 0.12 * air, 0.8, 8.0))
                    yac = max(0, int(round(rng.normal(xyac + 0.8 * PL[rid]["yac"] + 0.6 * P[off]["yac"] - 0.8 * P[de]["tackle"], 3.5)))) if comp else 0
                    yards = air + yac if comp else 0
                    r.update({"play_type": "pass", "pass_attempt": 1, "complete_pass": int(comp),
                              "interception": int(intc), "air_yards": air, "xyac_mean_yardage": xyac,
                              "yards_after_catch": yac if comp else np.nan, "cpoe": 100 * (int(comp) - cp_exp),
                              "receiver_player_id": rid, "receiver_player_name": PL[rid]["name"],
                              "pass_location": rng.choice(["left", "middle", "right"])})
                    f["is_interception_worthy"] = int(worthy or intc)
                    turnover = intc
            else:
                gi = rng.choice(7, p=np.exp(P[off]["gap_pref"]) / np.exp(P[off]["gap_pref"]).sum())
                loc, gap = GAPS[gi]
                rb = f"00-SYN{off:>3}{'RB1' if rng.random() < 0.7 else 'RB2'}".replace(" ", "X")
                mu = (4.1 + 0.9 * P[off]["rush_off"] - 0.9 * P[de]["rush_def"] + 0.6 * P[off]["gap_off"][gi]
                      - 0.6 * P[de]["gap_def"][gi] + (0.6 if togo <= 2 else 0.0))
                stuff_p = _sig(-1.4 - 0.4 * P[off]["rush_off"] + 0.4 * P[de]["rush_def"] + 0.3 * P[de]["run_stuff"] + 0.2 * PL[rb]["stuff"])
                if rng.random() < stuff_p:
                    yards = int(rng.integers(-3, 1))
                else:
                    yards = int(round(max(1.0, rng.gamma(2.0, max(mu, 1.5) / 2.0))))
                r.update({"play_type": "run", "run_location": loc, "run_gap": gap, "rusher_player_id": rb,
                          "rusher_player_name": PL[rb]["name"], "rushing_yards": yards})
                if rng.random() < 0.008:
                    r["fumble_lost"] = 1
                    turnover = True
            yards = min(yards, yl)
            r["yards_gained"] = yards
            new_yl = yl - yards
            if not turnover and new_yl <= 0:
                score[off] += 7
                r["touchdown"] = 1
                epa = 6.95 - ep0
                result = "Touchdown"
            elif turnover:
                epa = -_ep(100 - new_yl, 1, 10) - ep0
                result = "Turnover"
            elif yards >= togo:
                down, togo = 1, min(10, new_yl)
                epa = _ep(new_yl, down, togo) - ep0
            elif down == 4:
                epa = -_ep(100 - new_yl, 1, 10) - ep0
                result = "Turnover on downs"
            else:
                down, togo = down + 1, togo - yards
                epa = _ep(new_yl, down, togo) - ep0
            yl = new_yl
            r["epa"] = float(epa)
            r["success"] = float(epa > 0)
            clock -= rng.uniform(22, 38) - 3 * P[off]["pace"]
            drive_plays.append(r)
            out["ftn"].append(f)
            out["part"].append(pt)
        for r in drive_plays:
            r["fixed_drive_result"] = result
        out["pbp"].extend(drive_plays)
        pos = de
    return score


def load(season=2026, target_week=12, seed=11):
    rng = np.random.default_rng(seed)
    teams = list(TEAMS)
    P = _team_params(rng, teams)
    PL, rosters = _players(rng, teams, P)
    sched = _schedule(rng, season, teams)
    inj = {}
    for t in rng.choice(teams, 4, replace=False):
        s = int(rng.integers(3, 9))
        inj[t] = (s, s + 2)
    benched = teams[int(rng.integers(0, 32))]
    inj[benched] = (8, 99)
    out = {"pbp": [], "ftn": [], "part": []}
    rating = {t: 2.5 * (P[t]["pass_off"] + 0.5 * P[t]["rush_off"] + P[t]["pass_def"] + 0.5 * P[t]["rush_def"]) for t in teams}
    for c in ["away_score", "home_score", "result", "total", "spread_line", "total_line",
              "away_moneyline", "home_moneyline"]:
        sched[c] = np.nan
    sched["away_qb_id"] = None
    sched["home_qb_id"] = None
    for i, g in sched.iterrows():
        mu = rating[g.home_team] - rating[g.away_team] + 1.5 + rng.normal(0, 1.5)
        if g.week <= target_week:
            sched.loc[i, "spread_line"] = round(mu * 2) / 2
            sched.loc[i, "total_line"] = round((44 + 1.2 * (P[g.home_team]["pass_off"] + P[g.away_team]["pass_off"]) + rng.normal(0, 1.5)) * 2) / 2
            p = float(_sig(mu / 7.5))
            fav = -round(100 * p / (1 - p) / 5) * 5 if p >= 0.5 else round(100 * (1 - p) / p / 5) * 5
            dog = round(100 * p / (1 - p) / 5) * 5 if p >= 0.5 else -round(100 * (1 - p) / p / 5) * 5
            sched.loc[i, "home_moneyline"] = fav
            sched.loc[i, "away_moneyline"] = dog
        if g.week < target_week:
            sc = _sim_game(rng, g, P, PL, inj, out)
            sched.loc[i, "home_score"] = sc[g.home_team]
            sched.loc[i, "away_score"] = sc[g.away_team]
            sched.loc[i, "result"] = sc[g.home_team] - sc[g.away_team]
            sched.loc[i, "total"] = sc[g.home_team] + sc[g.away_team]
            sched.loc[i, "home_qb_id"] = _qb_for(g.home_team, g.week, inj)
            sched.loc[i, "away_qb_id"] = _qb_for(g.away_team, g.week, inj)
    teams_df = pd.DataFrame([{"team_abbr": t, "team_name": v[0], "team_nick": v[1], "team_conf": v[2],
                              "team_division": v[3], "team_color": v[4], "team_color2": v[5],
                              "team_logo_espn": espn_logo(t)} for t, v in TEAMS.items()])
    return {"pbp": pd.DataFrame(out["pbp"]), "sched": sched, "teams": teams_df, "rosters": rosters,
            "part": pd.DataFrame(out["part"]), "ftn": pd.DataFrame(out["ftn"]), "synthetic": True}


ROLE_SNAP = {"QB1": ("off", 1.0), "RB1": ("off", 0.62), "RB2": ("off", 0.38), "WR1": ("off", 0.92), "WR2": ("off", 0.85),
             "WR3": ("off", 0.6), "TE1": ("off", 0.78), "DL1": ("def", 0.8), "LB1": ("def", 0.95), "CB1": ("def", 0.97),
             "S1": ("def", 0.99)}


def load_history(seasons, target_season, target_week, seed=11):
    """Several synthetic seasons plus synthetic injuries, snap counts and player id map."""
    parts = [load(s, target_week if s == target_season else 19, seed + (s - target_season)) for s in seasons]
    rng = np.random.default_rng(seed)
    pbp = pd.concat([p["pbp"] for p in parts], ignore_index=True)
    sched = pd.concat([p["sched"] for p in parts], ignore_index=True)
    sched["home_rest"] = rng.choice([6, 7, 7, 7, 10, 13], len(sched))
    sched["away_rest"] = rng.choice([6, 7, 7, 7, 10, 13], len(sched))
    sched["location"] = "Home"
    inj, snaps, players = [], [], []
    for t in TEAMS:
        for role, (side, pct) in ROLE_SNAP.items():
            pid = f"00-SYN{t:>3}{role}".replace(" ", "X")
            players.append({"gsis_id": pid, "pfr_id": "pfr" + pid, "display_name": f"{t} {role}", "position": role[:2]})
    pl = {p["gsis_id"]: p for p in players}
    for _, g in sched[sched["result"].notna() | (sched["week"] == target_week)].iterrows():
        for t, opp in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
            for role, (side, pct) in ROLE_SNAP.items():
                pid = f"00-SYN{t:>3}{role}".replace(" ", "X")
                if g.week < target_week or g.season < target_season:
                    v = float(np.clip(rng.normal(pct, 0.05), 0, 1))
                    snaps.append({"season": g.season, "game_type": "REG", "week": g.week, "pfr_player_id": "pfr" + pid,
                                  "player": f"{t} {role}", "team": t, "offense_pct": v if side == "off" else 0.0,
                                  "defense_pct": v if side == "def" else 0.0})
                if role != "QB1" and rng.random() < 0.08:
                    inj.append({"season": g.season, "game_type": "REG", "week": g.week, "team": t, "gsis_id": pid,
                                "full_name": f"{t} {role}", "position": pl[pid]["position"],
                                "report_status": rng.choice(["Out", "Doubtful", "Questionable"], p=[0.5, 0.15, 0.35])})
    return {"pbp": pbp, "sched": sched, "teams": parts[-1]["teams"], "rosters": parts[-1]["rosters"],
            "part": parts[-1]["part"], "ftn": parts[-1]["ftn"], "injuries": pd.DataFrame(inj),
            "snaps": pd.DataFrame(snaps), "players": pd.DataFrame(players), "synthetic": True,
            "cur_pbp": parts[-1]["pbp"], "cur_sched": parts[-1]["sched"]}
