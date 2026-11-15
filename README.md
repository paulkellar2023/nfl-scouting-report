# Scouting Report

Weekly NFL matchup previews on GitHub Pages. A Python pipeline reads open nflverse data, finds the largest unit-vs-unit edges in each game, and writes JSON. A static site shows a Week Board (games ordered by playoff leverage) and a dashboard for each matchup: 3 keys to success per team, 4 to 6 team cards, 4 to 6 player cards, and a 2-sentence LLM summary.

## Setup

1. Create an empty public repo on GitHub (for example `paulkellar2023/nfl-scouting-report`). Do not add a README.
2. Push this folder to it:
   ```bash
   cd nfl-scouting-report
   git init -b main
   git add .
   git commit -m "Initial scouting report"
   git remote add origin https://github.com/paulkellar2023/nfl-scouting-report.git
   git push -u origin main
   ```
3. In the repo: **Settings > Pages > Build and deployment > Source = GitHub Actions**.
4. In the repo: **Settings > Secrets and variables > Actions > New repository secret**. Name `ANTHROPIC_API_KEY`, value = your key. Do not put the key in any file: the repo is public. The pipeline reads it in `pipeline/summary.py` (`os.environ.get("ANTHROPIC_API_KEY")`). Without the secret, the build still runs and the summary box is hidden.
5. Set your X handle in `pipeline/config.py` (`HANDLE`). It shows in the footer of each card.
6. **Actions > weekly-build > Run workflow** for the first real build. After that it runs every Thursday at 13:37 UTC.

## Run locally

```bash
pip install -r requirements.txt
python -m pipeline.build                      # real data, next unplayed week
python -m pipeline.build --week 11            # backfill a week (uses only data before week 11)
python -m pipeline.build --synthetic --week 12  # offline test data
cd site && python -m http.server 8000         # open http://localhost:8000
```

## Method

- **Cleanup:** regular season only. Pass and run plays only (no kneels, spikes, penalty-only plays or special teams). Scrambles and sacks count as dropbacks.
- **Filters:** efficiency stats use 10 to 90% win probability. Tendency stats (pass rate over expected) use a neutral script: 20 to 80% win probability, one-score game, not the last 2 minutes of a half.
- **Recency:** exponential weights by week, half-life 6 weeks.
- **Opponent adjustment:** pass and rush EPA use a play-level ridge regression (offense + defense + home). The ridge penalty for each block is sigma2 / tau2, from a method-of-moments estimate, so the ridge is the shrinkage.
- **Starting QB:** pass EPA uses only the projected starter's dropbacks. The starter is the schedule's QB for the game if nflverse lists one, else the QB with most dropbacks in the team's last game.
- **Shrinkage:** all other rates use empirical Bayes (method of moments) toward the league mean.
- **Edge score:** z(offense) + z(opposing defense), oriented so positive = offense edge. A z-score is the shrunk deviation over the raw spread, so noisy stats score lower. Tendency cards scale the edge by how often the choosing side does the thing. Gap cards take the best of 7 gaps, so they pay a penalty (`GAP_MAX_PENALTY`).
- **Leverage:** 10,000-run Monte Carlo of the rest of the season. Market spread for this week, regressed EPA ratings after. Tiebreakers are approximate (wins, division wins, coin flip).

## Data sources

All through `nflreadpy`: play-by-play, schedules (lines), teams, rosters, participation (pressure, man/zone, coverage shell) and FTN charting (play action, motion, blitzers, rushers, interception-worthy throws). The pipeline checks each optional source and turns off any card whose fields are missing. The `flags` object in each `games.json` shows what was available.

## Layout

```
pipeline/            Python build
  build.py           entry point
  clean.py           filters, weights, joins
  stats.py           weighted rates, EB shrinkage, ridge adjustment
  templates_team.py  team stat templates
  templates_player.py player cards
  story.py           edge scoring, headlines, keys, card selection
  leverage.py        playoff Monte Carlo
  summary.py         LLM summary (ANTHROPIC_API_KEY)
  synth.py           synthetic nflverse-shaped data for tests
site/                static site (GitHub Pages root)
  data/              generated JSON, committed by the workflow
  assets/            logos and headshots, downloaded by the workflow
```

Credit for the visual style: @benwolby. Matchup page idea: Ray Carpenter (raycarp.com).
