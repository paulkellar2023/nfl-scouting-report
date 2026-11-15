SEASON = 2026

# Recency: exponential decay by weeks before the target week.
HALF_LIFE_WEEKS = 6.0

# Efficiency filter (garbage time removed) and stricter neutral-script filter for tendencies.
WP_EFF = (0.10, 0.90)
WP_NEUTRAL = (0.20, 0.80)
NEUTRAL_MAX_SCORE_DIFF = 8
HALF_SECONDS_CUTOFF = 120

# Monte Carlo leverage.
N_SIMS = 10000
MARGIN_SD = 13.5
HFA_PTS = 1.5
PLAYS_PER_GAME = 62
FUTURE_RATING_REGRESS = 0.6
PRIMETIME_BONUS = 0.02

# Card selection.
MIN_TEAM_CARDS = 4
MAX_TEAM_CARDS = 6
MIN_PLAYER_CARDS = 4
MAX_PLAYER_CARDS = 6
MAX_CARDS_PER_PHASE = 2
SOFT_SCORE_FLOOR = 1.0
# Gap cards take the max over 7 gaps; subtract this so they compete fairly with single-stat cards.
GAP_MAX_PENALTY = 1.0

SITE_TITLE = "The Drill Down"
HANDLE = ""
LLM_MODEL = "claude-haiku-5-5"
BG_HEX = "#0B0B0C"

# Win-probability model: first season with features (needs the prior season's plays for week 1 priors).
MODEL_FIRST_SEASON = 2016
