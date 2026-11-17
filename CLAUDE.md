# The Drill Down: rules for building cards

Weekly NFL matchup site. Python pipeline (`pipeline/`) writes JSON; the static site (`site/`) draws it. See README.md.

## A new card
- A card is a dict: `id` ("<type>:<team>"), `kind` ("team" or "player"), `phase`, `owner`, `score`, `edge`, `t1` (headline),
  `t2` (second line), `sub` (what the chart shows and the date span), `chart` ({"type": ..., data}), `source`, `note`.
  Copy the shape of `special._card` or `tendencies._card`.
- `t1` names one team and a rank; `t2` gives the other team. Use `M[team]["label"]` / `["nick"]` and `text.ordinal`, `text.possessive`.
- The chart shows the whole league (or all qualifying players) with the two teams highlighted.
- Score like the other cards in its module (about 0.3 to 1.0 times a z-score), so it competes fairly.
- Wire it into the card pool in `pipeline/build.py` next to the similar cards, and add its type to `CAT_TEAM` or `CAT_PLAYER`
  in `site/app.js`. Use an existing chart type when one fits; a new type needs a draw function in `site/app.js` in the
  same style (dark theme, `T(team).accent` for the two teams, `HALO` text, works at 390 px wide).

## A new data source is always optional
- Load it inside a try (see `load._try` and `special.load_bot`). Check the columns you need. If anything is missing:
  return None, call `health.warn(...)` once, and every card that needs it returns None. Never fail the build.
- No API keys in code (public repo). No scraping behind logins.
- Add a synthetic version to `pipeline/synth.py` so `python -m pipeline.build --synthetic --week 12 --no-llm --site /tmp/site` covers it.

## Writing
- No em dashes anywhere. Plain, short sentences.
- Add one entry for the card to `site/methods.html`; add new sources and files to README.md.
- Change only what the card needs. No refactors, no new comments or docstrings on code you did not write.
