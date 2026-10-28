# Matchday Predictor: data + verified pick log

**What this does (free, automatic):**
1. Every 6 hours it downloads fixtures/results for 7 leagues (EPL, La Liga, Serie A, Bundesliga, Ligue 1, Championship, Eredivisie).
2. It predicts each upcoming game from every team's last 10 matches.
3. When a game qualifies, it saves the pick **before kick-off** to `data/picks_log.json`.
4. After the game it records win/loss. Picks are never edited, and every save is timestamped by GitHub, so anyone can verify your record.
5. It writes `data/summary.json` (hit rate, last 30 days) and `data/picks_upcoming.json` (picks for your app to show).

**Picks it logs:** Over 1.5 goals, and Underdog +1.5 handicap, only when the model says 78%+ (change `MIN_PROB` in `scripts/run_picks.py`).

**Not included yet:** 2. Bundesliga and League One (not on the free data plan), and bookmaker odds (so profit tracking is blank until you add an odds source; `odds` stays empty).

## Setup (about 20 minutes, no coding)
1. **Free data token:** register at football-data.org, check your email, copy the API token.
2. **GitHub:** create a free account at github.com, then New repository, name it `matchday-data`, make it **Public** (public = anyone can check your record).
3. **Upload files:** on the repo page choose Add file, Upload files, and drag in everything from this zip (keep the `scripts`, `data` and `.github` folders; the `.github` folder is hidden on some computers, so unzip first and enable "show hidden files"). Click Commit.
4. **Add the token:** Settings, Secrets and variables, Actions, New repository secret. Name: `FOOTBALL_DATA_TOKEN`. Value: your token.
5. **Run it:** Actions tab, "Update data and picks", Run workflow. After about 2 minutes, open the `data` folder; you should see the json files.
6. It then runs by itself every 6 hours.

## Check it is working
- `data/matches.json` has leagues with matches.
- `data/picks_log.json` fills with picks once games are within 4 days.
- Give it 2 to 4 weeks before reading anything into `summary.json`.

## Important
- Do not edit `picks_log.json` by hand. Its value is that it is untouched.
- Never promise winnings. Show the record honestly.
- Free-plan scores are slightly delayed, so results can settle a little late.

## Next steps
1. Show `picks_upcoming.json` and `summary.json` inside the Matchday Predictor app.
2. Add bookmaker odds so picks show real profit.
3. Test the model on past seasons and tune `MIN_PROB`.
4. Add the premium login and payments.
