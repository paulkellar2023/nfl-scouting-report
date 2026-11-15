import logging

import numpy as np
import pandas as pd

from .config import HALF_LIFE_WEEKS, HALF_SECONDS_CUTOFF, NEUTRAL_MAX_SCORE_DIFF, WP_EFF, WP_NEUTRAL

log = logging.getLogger(__name__)

NUM_COLS = ["pass", "qb_dropback", "qb_scramble", "sack", "qb_hit", "complete_pass", "interception",
            "fumble_lost", "touchdown", "yards_gained", "air_yards", "yards_after_catch",
            "xyac_mean_yardage", "cpoe", "xpass", "wp", "score_differential", "half_seconds_remaining",
            "down", "ydstogo", "yardline_100", "epa", "success", "week", "play_id"]
GAP_ORDER = ["L END", "L TACKLE", "L GUARD", "MIDDLE", "R GUARD", "R TACKLE", "R END"]
FTN_COLS = ["is_play_action", "is_motion", "n_blitzers", "n_pass_rushers", "is_interception_worthy"]


def _share_present(d, mask, col):
    m = d.loc[mask, col]
    return float(m.notna().mean()) if len(m) else 0.0


def prepare(raw, target_week):
    pbp = raw["pbp"]
    if "season_type" in pbp.columns:
        pbp = pbp[pbp["season_type"] == "REG"]
    pbp = pbp[pbp["week"] < target_week]
    d = pbp[pbp["play_type"].isin(["pass", "run"]) & pbp["epa"].notna() & pbp["posteam"].notna()
            & pbp["down"].notna()].copy()
    for c in NUM_COLS:
        if c not in d.columns:
            d[c] = np.nan
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ["pass", "qb_dropback", "qb_scramble", "sack", "qb_hit", "complete_pass",
              "interception", "fumble_lost", "touchdown"]:
        d[c] = d[c].fillna(0)

    d["dropback"] = ((d["qb_dropback"] == 1) | (d["pass"] == 1)).astype(bool)
    d["scramble"] = d["qb_scramble"] == 1
    d["is_sack"] = d["sack"] == 1
    d["attempt"] = d["dropback"] & ~d["scramble"] & ~d["is_sack"] & d["air_yards"].notna()
    d["designed_run"] = (d["play_type"] == "run") & ~d["dropback"]
    d["qb_id"] = d["passer_player_id"].where(d["passer_player_id"].notna(), d["rusher_player_id"]).where(d["dropback"])
    d["w"] = 0.5 ** ((target_week - d["week"]) / HALF_LIFE_WEEKS)
    d["eff"] = d["wp"].between(*WP_EFF)
    d["neutral"] = (d["wp"].between(*WP_NEUTRAL) & (d["score_differential"].abs() <= NEUTRAL_MAX_SCORE_DIFF)
                    & (d["half_seconds_remaining"] > HALF_SECONDS_CUTOFF))
    d["is_pass"] = d["dropback"].astype(float)
    d["stuffed"] = np.where(d["designed_run"], (d["yards_gained"] <= 0).astype(float), np.nan)
    d["explosive"] = (((d["dropback"]) & (d["yards_gained"] >= 20)) | ((d["designed_run"]) & (d["yards_gained"] >= 10))).astype(float)
    d["short_yd"] = ((d["down"] == 2) & d["ydstogo"].between(1, 6)) | ((d["down"] == 3) & d["ydstogo"].between(1, 3))
    d["early"] = d["down"] <= 2
    d["yacoe"] = np.where(d["complete_pass"] == 1, d["yards_after_catch"] - d["xyac_mean_yardage"], np.nan)
    d["deep"] = np.where(d["attempt"], (d["air_yards"] >= 15).astype(float), np.nan)
    loc = d["run_location"].astype("object")
    gap = d["run_gap"].astype("object")
    lab = np.where(loc == "middle", "MIDDLE",
                   np.where(loc.isin(["left", "right"]),
                            loc.str[0].str.upper().fillna("") + " " + gap.fillna("").str.upper(), None))
    d["gap"] = pd.Series(lab, index=d.index).where(d["designed_run"])
    d.loc[~d["gap"].isin(GAP_ORDER), "gap"] = np.nan

    flags = {"ftn": False, "pressure": "proxy", "coverage": False, "int_worthy": False}
    ftn = raw.get("ftn")
    if ftn is not None and len(ftn):
        f = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
        keep = [c for c in FTN_COLS if c in f.columns]
        if {"game_id", "play_id"} <= set(f.columns) and keep:
            f = f[["game_id", "play_id"] + keep].copy()
            f["play_id"] = pd.to_numeric(f["play_id"], errors="coerce")
            for c in keep:
                f[c] = pd.to_numeric(f[c], errors="coerce").astype(float)
            f = f.dropna(subset=["play_id"]).drop_duplicates(["game_id", "play_id"])
            d = d.merge(f, on=["game_id", "play_id"], how="left")
            share = _share_present(d, d["dropback"], keep[0])
            flags["ftn"] = share >= 0.5 and {"is_play_action", "is_motion", "n_blitzers"} <= set(keep)
            flags["int_worthy"] = flags["ftn"] and "is_interception_worthy" in keep
            log.info("ftn coverage of dropbacks: %.0f%%", 100 * share)
    part = raw.get("part")
    if part is not None and len(part):
        p = part.rename(columns={"nflverse_game_id": "game_id", "old_game_id": "old_game_id"})
        cols = [c for c in ["was_pressure", "defense_man_zone_type", "defense_coverage_type",
                            "number_of_pass_rushers"] if c in p.columns]
        if {"game_id", "play_id"} <= set(p.columns) and cols:
            p = p[["game_id", "play_id"] + cols].copy()
            p["play_id"] = pd.to_numeric(p["play_id"], errors="coerce")
            p = p.dropna(subset=["play_id"]).drop_duplicates(["game_id", "play_id"])
            d = d.merge(p, on=["game_id", "play_id"], how="left")
            if "was_pressure" in cols:
                d["was_pressure"] = pd.to_numeric(d["was_pressure"].astype("object").replace({True: 1, False: 0}), errors="coerce")
                if _share_present(d, d["dropback"], "was_pressure") >= 0.5:
                    flags["pressure"] = "participation"
            if "defense_man_zone_type" in cols and _share_present(d, d["attempt"], "defense_man_zone_type") >= 0.5:
                flags["coverage"] = True
    if flags["pressure"] == "participation":
        d["pressure"] = np.where(d["dropback"], d["was_pressure"], np.nan)
    else:
        d["pressure"] = np.where(d["dropback"], ((d["qb_hit"] == 1) | d["is_sack"]).astype(float), np.nan)
    if flags["ftn"]:
        d["pa"] = np.where(d["dropback"], d["is_play_action"], np.nan)
        d["motion"] = np.where(d["dropback"], d["is_motion"], np.nan)
        d["blitz"] = np.where(d["dropback"], (d["n_blitzers"] > 0).astype(float), np.nan)
        src = "n_pass_rushers" if "n_pass_rushers" in d.columns else "number_of_pass_rushers"
        d["rushers"] = pd.to_numeric(d[src], errors="coerce") if src in d.columns else np.nan
    if flags["coverage"]:
        mz = d["defense_man_zone_type"].astype("object")
        d["man"] = np.where(d["attempt"] & mz.notna(), (mz == "MAN_COVERAGE").astype(float), np.nan)
        d["shell"] = d["defense_coverage_type"].astype("object").where(d["attempt"])
    log.info("flags: %s", flags)
    return d, flags
