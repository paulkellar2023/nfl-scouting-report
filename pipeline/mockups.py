"""Mockup charts for card ideas, drawn with made-up data. Only chart types the site does not publish yet, so every
idea also brings a new visual. Each image is stamped MOCKUP · MADE-UP DATA."""
import hashlib

import numpy as np

# Chart types the site already publishes (see site/app.js). A mockup never uses these.
SITE_TYPES = {"bars", "calib", "dist", "downs", "drives", "duel", "elotrend", "explmap", "fourthmap", "gaps", "injuries",
              "passchart", "pbars", "penalties", "probbars", "pscatter", "pstrip", "quarters", "rcvchart", "redzone",
              "runchart", "scatter", "splits", "strips", "thirds", "tree", "trend", "tug", "units", "waterfall", "wpline",
              "zones", "outcome_flow"}
NEW_TYPES = {
    "dumbbell": "two values per team joined by a line (for example offense vs. defense, or season vs. last 4 weeks)",
    "slope": "each team's change between two points in time, one line per team",
    "heatmap": "grid of the two teams (plus league average) by up to 8 sub-measures",
    "beeswarm": "every qualifying player as a dot on one axis, the two teams' players highlighted",
    "radar": "the two teams as polygons over 5 to 8 measures, league average as a ring",
    "bump": "weekly league rank of every team, the two teams highlighted",
    "ridgeline": "distribution of a per-play or per-game measure for each team vs. the league",
}
BG, FG, MUTE, GRID, A, B = "#0B0B0C", "#F4F4F2", "#8E8E93", "#2A2A2E", "#FB4F14", "#4FA3F7"


def _rng(key):
    return np.random.default_rng(int(hashlib.md5(key.encode()).hexdigest()[:8], 16))


def _vals(r, n, lo, hi):
    mid, sd = (lo + hi) / 2, (hi - lo) / 5
    return np.clip(r.normal(mid, sd, n), lo, hi)


def render(spec, path, key):
    """spec: {"type", "title", "metric", "lo", "hi", "categories"}. Returns False when the type is not allowed."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = spec.get("type")
    if t not in NEW_TYPES:
        return False
    r = _rng(key)
    lo, hi = float(spec.get("lo", 0)), float(spec.get("hi", 1))
    if hi <= lo:
        lo, hi = 0.0, 1.0
    cats = [str(c) for c in (spec.get("categories") or [])][:8] or ["Measure 1", "Measure 2", "Measure 3", "Measure 4", "Measure 5"]
    metric = str(spec.get("metric") or "")
    plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID, "text.color": FG,
                         "axes.labelcolor": MUTE, "xtick.color": MUTE, "ytick.color": MUTE, "font.size": 12})
    polar = t == "radar"
    fig = plt.figure(figsize=(12, 6.75), dpi=100)
    ax = fig.add_subplot(111, polar=polar)
    if t == "dumbbell":
        v1, v2 = _vals(r, 32, lo, hi), _vals(r, 32, lo, hi)
        o = np.argsort(v1)
        for y, i in enumerate(o):
            hl = {3: A, 22: B}.get(i)
            ax.plot([v1[i], v2[i]], [y, y], color=hl or GRID, lw=2.5 if hl else 1.5)
            ax.scatter([v1[i]], [y], color=hl or MUTE, s=40, zorder=3)
            ax.scatter([v2[i]], [y], facecolor=BG, edgecolor=hl or MUTE, s=40, zorder=3)
        ax.set_yticks([])
        ax.set_xlabel(f"{metric}   (filled: {cats[0]} · open: {cats[1] if len(cats) > 1 else 'second value'})")
    elif t == "slope":
        v1, v2 = _vals(r, 32, lo, hi), _vals(r, 32, lo, hi)
        for i in range(32):
            hl = {3: A, 22: B}.get(i)
            ax.plot([0, 1], [v1[i], v2[i]], color=hl or GRID, lw=3 if hl else 1.2, zorder=3 if hl else 1)
        ax.set_xticks([0, 1], [cats[0], cats[1] if len(cats) > 1 else "Now"])
        ax.set_ylabel(metric)
    elif t == "heatmap":
        m = np.vstack([_vals(r, len(cats), lo, hi) for _ in range(3)])
        from matplotlib.colors import LinearSegmentedColormap
        z = (m - m[2]) / ((hi - lo) / 2)  # vs. league: blue below, orange above, dark at league average
        ax.imshow(z, cmap=LinearSegmentedColormap.from_list("d", [B, "#1A1A1E", A]), vmin=-1, vmax=1, aspect="auto")
        for (i, j), v in np.ndenumerate(m):
            ax.text(j, i, f"{v:.2f}" if hi - lo < 5 else f"{v:.0f}", ha="center", va="center", color=FG, fontsize=13, fontweight="bold")
        ax.set_yticks([0, 1, 2], ["TEAM A", "TEAM B", "LEAGUE"])
        ax.set_xticks(range(len(cats)), cats, rotation=20, ha="right")
    elif t == "beeswarm":
        v = _vals(r, 120, lo, hi)
        team = r.integers(0, 32, 120)
        y = np.zeros(120)  # swarm: stack dots that share a value bin, alternating up and down
        bins = np.floor((v - lo) / ((hi - lo) / 70)).astype(int)
        for b_ in np.unique(bins):
            idx = np.where(bins == b_)[0]
            y[idx] = [((k + 1) // 2) * (1 if k % 2 else -1) * 0.06 for k in range(len(idx))]
        cols = [A if k == 3 else B if k == 22 else MUTE for k in team]
        ax.scatter(v, y, c=cols, s=[90 if k in (3, 22) else 30 for k in team], alpha=0.9, edgecolors="none")
        ax.set_yticks([])
        ax.set_xlabel(metric + "   (every qualifying player)")
    elif t == "radar":
        n = len(cats)
        ang = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        for vals, col, lab in ((r.uniform(0.3, 1, n), A, "TEAM A"), (r.uniform(0.3, 1, n), B, "TEAM B"), (np.full(n, 0.6), MUTE, "LEAGUE")):
            vv = list(vals) + [vals[0]]
            ax.plot(ang + ang[:1], vv, color=col, lw=2.5 if lab != "LEAGUE" else 1, ls="-" if lab != "LEAGUE" else "--", label=lab)
            if lab != "LEAGUE":
                ax.fill(ang + ang[:1], vv, color=col, alpha=0.15)
        ax.set_xticks(ang, cats)
        ax.set_yticks([])
        ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), frameon=False)
    elif t == "bump":
        weeks = 11
        ranks = np.array([r.permutation(32) + 1 for _ in range(weeks)]).T
        for i in range(32):
            hl = {3: A, 22: B}.get(i)
            sm = np.convolve(ranks[i], np.ones(3) / 3, mode="same")
            ax.plot(range(1, weeks + 1), sm, color=hl or GRID, lw=3 if hl else 1, zorder=3 if hl else 1)
        ax.invert_yaxis()
        ax.set_xlabel("Week")
        ax.set_ylabel(f"League rank: {metric}")
    elif t == "ridgeline":
        xs = np.linspace(lo, hi, 200)
        for k, (lab, col) in enumerate((("LEAGUE", MUTE), ("TEAM B", B), ("TEAM A", A))):
            mu, sd = r.uniform(lo + (hi - lo) * 0.3, lo + (hi - lo) * 0.7), (hi - lo) / r.uniform(5, 8)
            d = np.exp(-0.5 * ((xs - mu) / sd) ** 2)
            ax.fill_between(xs, k, k + d * 0.9, color=col, alpha=0.35)
            ax.plot(xs, k + d * 0.9, color=col, lw=2)
            ax.text(lo, k + 0.15, lab, color=col, fontweight="bold")
        ax.set_yticks([])
        ax.set_xlabel(metric)
    if not polar:
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.suptitle(str(spec.get("title") or metric)[:110], x=0.04, ha="left", fontsize=17, fontweight="bold", color=FG)
    fig.text(0.04, 0.905, f"{t.upper()} · TEAM A and TEAM B are the two teams in the game", color=MUTE, fontsize=11)
    fig.text(0.98, 0.02, "MOCKUP · MADE-UP DATA", ha="right", color=A, fontsize=12, fontweight="bold")
    fig.subplots_adjust(left=0.08, right=0.9 if polar else 0.97, top=0.85, bottom=0.14)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return True
