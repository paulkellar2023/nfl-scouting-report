# The Drill Down

Weekly NFL matchup previews on GitHub Pages: https://paulkellar2023.github.io/nfl-scouting-report/

A Python pipeline reads open nflverse data, finds the largest unit-vs-unit edges in each game, and writes JSON. A static site shows:

- **Week board:** games ordered by playoff leverage. Each tile shows the favorite and MODEL · MARKET · ELO.
- **Matchup page:** 3 keys to success per team, a 2-sentence LLM summary, and Team, Players, Fantasy and Model tabs. Each tab shows 6 ranked cards (fewer only when fewer qualify), including 1 or 2 field charts. A CARD TYPES filter shows more.
- **Projected weeks** through week 18, a **playoff bracket** seeded by projected final records, a **league table** with team pages, a **track record** page, and post-game **recaps**.
- **RSS feeds** (one per team plus all games) and a weekly **email digest** through Buttondown.

The full method for readers is in `site/methods.html`. This file covers setup and the code.

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
4. In the repo: **Settings > Secrets and variables > Actions > New repository secret**. Never put a key in a file: the repo is public.
   - `ANTHROPIC_API_KEY`: the LLM summary. Without it, the build uses a rule-based summary.
   - `BUTTONDOWN_API_KEY`: the weekly email. Without it, no email is created.
5. In `pipeline/config.py`: `HANDLE` (X handle on cards), `BUTTONDOWN_USERNAME` (signup form), `EMAIL_MODE` and `EMAIL_PER_TEAM` (see Email).
6. **Actions > weekly-build > Run workflow** for the first real build.

## Workflows

- **weekly-build** (`.github/workflows/weekly.yml`): Thursday 2 PM ET (report and newsletter), then data refreshes Sunday at 11 AM, 3 PM and 7 PM ET and Monday at 6 PM ET (cron is UTC, set for Eastern Standard Time; see the comment in the file for daylight time). Only the Thursday 2 PM run sends email (`SEND_EMAIL`), or a manual run with `send_email` checked. A manual run with both `send_email` and `force_send` checked sends to all subscribers again even if this week's newsletter already went out. A manual run with `email_test` checked makes the newsletter as a Buttondown draft and sends it only to the address in the `EMAIL_TEST_TO` secret; subscribers get nothing and the week's real send is not used up. Builds the next unplayed week, projected weeks, bracket, league table, track record, recaps, feeds and link previews, then commits `site/` and `model/` and deploys. Manual inputs:
  - `week`: build one week (blank = next unplayed week).
  - `backfill_weeks`: build past weeks first, for example `3-9`. Each uses only data from before that week. Weeks that already have a live report are skipped.
  - `refresh_started`: rebuild games that already kicked off (testing only).
  - `synthetic`: offline test data.
- **idea-scout** (`.github/workflows/ideas.yml`): Tuesdays. Collects new nflverse data releases, nflreadr/nflreadpy/nfl4th release notes, active NFL data repos on GitHub and posts from Open Source Football and r/NFLstatheads, asks the LLM for up to 10 ideas, checks each source's data coverage (this season's files, updated in the last 10 to 14 days), drops stale ones, ranks verified weekly data first, and opens one issue per idea (label `idea`, at most 5 per week, no repeats). Each issue has a mockup chart with made-up data (`pipeline/mockups.py`), in a chart type the site does not publish yet; the images are stored on the `idea-mockups` branch, so `main` and the site never change. Accept or decline by adding the label `accepted` or `declined`. Accepted issues are the queue for new cards; building one is still a code change. Sources are in `FEEDS` and `RELEASE_REPOS` in `pipeline/ideas.py`.
- **build-idea** (`.github/workflows/build-idea.yml`): when an `idea` issue gets the label `accepted`, Claude Code builds the card (rules in `CLAUDE.md`), tests it on synthetic data, and opens a draft PR. It comments the PR link (or why it built nothing) on the issue. Nothing reaches `main` until you merge. Run it by hand with an issue number to retry.
- **Deploy site** (`.github/workflows/pages.yml`): runs on any push to `main` that changes `site/`. Use it for front-end changes. No data build.

## Email

The Thursday 2 PM ET build sends one digest to all subscribers, in sections with a jump list at the top: at a glance (the week board's model-vs-market cards, most at stake, surest pick, coin flip), last week's report card, the game of the week with one chart per tab, upset alert, chart of the week, fantasy start or sit, the playoff seeds table, one bubble team's season-outcome chart, and one line per other game. Chart images are screenshots of the built site (Playwright), uploaded to Buttondown; if that fails the email goes out without them. The email is HTML in the site's colors and fonts. It (the Saturday and Sunday runs skip it: a marker file `email_sent.json` in the week folder blocks repeats).

- `EMAIL_MODE = "send"` sends right away. `"draft"` only creates drafts in Buttondown for you to review and send.
- `EMAIL_PER_TEAM = True` also sends one email per team to subscribers tagged with that team. This needs Buttondown's paid tagging add-on. With `False`, readers who want one team use its RSS feed.
- The run log shows `email: N/N about_to_send created`. Problems are listed in the build health warnings.

## Run locally

```bash
pip install -r requirements.txt
python -m pipeline.build                         # real data, next unplayed week
python -m pipeline.build --week 11 --backfill    # backfill a past week (uses only data before week 11)
python -m pipeline.build --synthetic --week 12   # offline test data
python -m pipeline.build --no-llm                # rule-based summaries
cd site && python -m http.server 8000            # open http://localhost:8000
```

## Method (short)

- **Cleanup:** regular season, pass and run plays only. Scrambles and sacks count as dropbacks. Efficiency stats use 10 to 90% win probability. Tendency stats use a neutral script (20 to 80%, one-score game, not the last 2 minutes of a half).
- **Recency:** exponential weights by week, half-life 6 weeks.
- **Opponent adjustment:** pass and rush EPA use a play-level ridge regression (offense + defense + home). The ridge penalty is sigma2 / tau2 (method of moments), so the ridge is the shrinkage. Pass EPA uses only the projected starting QB's dropbacks.
- **Shrinkage:** other rates use empirical Bayes toward the league mean.
- **Edge score:** z(offense) + z(opposing defense). Cards are ranked by score, at most 2 per phase. `with_field()` in `build.py` makes sure each view has 1 or 2 field charts. `fill()` brings each view to 6 cards, preferring card types the week's other games don't show (`FILL_VARIETY`), and `vary()` cuts a type's score by up to `VARIETY` (15%) when earlier games this week showed it.
- **Leverage and projections:** 10,000-run Monte Carlo of the rest of the season, with real results for games already played.
- **Matchup colors:** the home team keeps its accent. The away team takes its first alternate color that does not clash (`context.pair` and `pairColors` in `app.js`: close in RGB, or the same hue family with both saturated).

## Win-probability model

Not betting advice. A ridge regression on home margin, then P(home win) = Phi(margin / sigma).

- **Features (home minus away), all walk-forward:** passing and rushing matchups, starting QB value, offensive and defensive injury load, rest, and "injuries behind ratings" (`inj_hist`). Home field is the only unpenalized term.
- **Luck:** each build fits raw EPA and a fumble-luck version (fumble plays get the season's average fumble result) and keeps the one with the lower leave-one-season-out log loss. Projected weeks and playoff games are at full health.
- **Fit:** alpha by leave-one-season-out, sigma by log loss. Seasons from `MODEL_FIRST_SEASON`. Completed seasons are cached in `model/cache/` (`features_v2_{raw|lk}_<season>.csv`; bump `FEAT_VER` in `model.py` when features change).
- **Factor chart:** the model is linear, so each contribution is its exact SHAP value. They sum to the projected margin.
- **Elo** (`elo.py`): 538-style from final scores since 2015 (K = 20, home field 48, margin multiplier, 1/3 regression to 1505). Shown and graded next to the model and market.
- **Track record** (`record.py`): published picks, backfilled picks, season walk-forward and past-season backtests, by Brier score and log loss.

## Data sources

All through `nflreadpy`: play-by-play, schedules and lines, teams, rosters, participation, FTN charting, injuries, snap counts, Next Gen Stats (passing, rushing, receiving), PFR advanced stats, expected fantasy points, weekly player stats and ESPN QBR. Outside nflverse: Ben Baldwin's nfl4th pre-computed 4th-down values (`special.load_bot`, read with `pyreadr`) and Open-Meteo kickoff forecasts (`weather.py`, no key). Each optional source is checked: if a source or column is missing, its cards are skipped and a health warning is logged. The `flags` object in each `games.json` shows what was available.

## Layout

```
pipeline/              Python build
  build.py             entry point, card assembly, field-chart rules
  load.py              nflreadpy loads, model history cache
  clean.py             filters, weights, joins
  stats.py             weighted rates, EB shrinkage, ridge adjustment
  templates_team.py    team stat templates
  templates_player.py  player cards
  story.py             edge scoring, headlines, keys, card selection
  tendencies.py        target zones, pass/run lean
  viz.py, viz2.py      field charts (16 types)
  special.py           special teams, field goals, 4th downs
  extras.py            Next Gen Stats and PFR tables and cards
  fantasy.py           Fantasy tab cards
  model.py             win-probability model, luck variants, walk-forward
  model_cards.py       Model tab cards and rule-based summary
  elo.py               Elo ratings
  leverage.py          playoff Monte Carlo and projected records
  bracket.py           standings, seeds, projected bracket
  league.py            league table and team pages
  record.py            track record and post-game recaps
  context.py           team metadata, colors, matchup color pairs
  share.py             link-preview pages (site/g) and images (site/og)
  feeds.py             RSS feeds
  weather.py           kickoff forecasts (Open-Meteo)
  notify.py            Buttondown email
  summary.py           LLM summary (ANTHROPIC_API_KEY)
  health.py            build warnings
  synth.py             synthetic nflverse-shaped data for tests
site/                  static site (GitHub Pages root)
  app.js, style.css    front end
  methods.html         method page for readers
  data/                generated JSON, committed by the workflow
  g/, og/              link-preview pages and images
  feeds/               RSS
  assets/              logos and headshots, downloaded by the workflow
```

The win-probability model started from Luke McHugh's NFL prediction model (https://lmchugh17.github.io/nfl-betting-model). Credit for the visual style: @benwolby. Matchup page idea: Ray Carpenter (raycarp.com).
