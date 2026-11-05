# Matchday Predictor: one model for the site and the pick log

## Update 5 Nov 2026: all free leagues, locked predictions, faster page, better model
**What's new**
- **All free football-data.org competitions.** The script now asks football-data.org which competitions your token covers and downloads all of them (12 on the free plan: Premier League, Championship, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Brasileirão Série A, Champions League, World Cup, European Championship). Cup and tournament games use the 90-minute score, which is what betting markets settle on.
- **Nothing disappears after kick-off.** The last prediction made before each kick-off is now saved in `data/predictions_archive.json` and locked. On the Results tab every game says either *"Saved before kick-off … locked"* or *"Rebuilt"* (for games played before this update). Games that have kicked off but have no result yet stay in Upcoming with a "Kicked off · result pending" tag instead of vanishing. The Results tab now keeps the whole season, not just the last 60 games.
- **Page is about 9 times smaller** (981 KB → about 115 KB). Club badges now come from football-data.org. The old embedded logos moved to `logos.js`, which only downloads if a badge is missing.
- **Open match cards stay open.** The 10-minute refresh used to redraw the page and close what you were reading; now it only redraws when there's new data.
- **New prediction model (v2)**, tested against the old one. It rates every team's attack and defence, adjusted for who they played, with home and away built in and recent games counting more. A new Action, **"Back-test models"**, tests both models on the last few seasons of real results and switches the site to v2 **only if it predicts better**. The result is written to `data/backtest_report.md`. It reruns on the 1st of every month.

**Upload these files** (Add file, Upload files, then Commit). Unzip first so the hidden `.github` folder is included:
1. `index.html` (replaces the old one)
2. `logos.js` (NEW, same folder as index.html)
3. `scripts/fetch_data.py`, `scripts/make_predictions.py`, `scripts/model.py`, `scripts/backtest.py` (replace)
4. `scripts/compare_models.py` (NEW)
5. `.github/workflows/update.yml` (replace) and `.github/workflows/backtest.yml` (NEW)

**Then:**
1. Actions tab, **"Update data and picks"**, Run workflow (about 3 minutes now, because there are 12 competitions).
2. Actions tab, **"Back-test models"**, Run workflow (about 5–15 minutes). Open `data/backtest_report.md` to see which model won.
3. Reload the site with Ctrl+F5. The grey bar shows the model in use (`last 10 games` or `team ratings v2`).

**Good to know**
- Champions League, World Cup and European Championship teams play few games in those competitions, so the model needs 5 games per team before it predicts. Until then those games show the basic table estimate.
- The tables for cup competitions lump all groups together, so read them as "form", not as the official standings.
- Locked predictions start from this update. Games already played show "Rebuilt" numbers, worked out using only results from before each game.

## What changed in this version
Before, the page worked out its own win chances from the table, while the pick log used a different goals model, so the two could disagree.
Now **one script calculates every prediction once** and saves it to `data/predictions.json`. The website and the pick log both read that file, so the numbers always match:
- win / draw / away chances, expected goals, Over 1.5, Over 2.5, Both teams to score and Underdog +1.5;
- also for the last 60 results in each league, using only games played *before* each match (so the Results tab shows honest back-tests);
- the page's "Verified pick record" now comes from the GitHub log instead of your browser.

## Update: risk engine, quick fixes and back-test
- **Risk is now the app's challenge function.** The favourite is always questioned, however strong it looks. Each match card shows a red 🚩 tag with the single biggest red flag, and the Risk section opens with it. New checks: bookmaker prices vs the model, no wins yet against top-half sides, the table disagreeing with the model, thin evidence. A "Reality check" line is added for favourites at 60%+. A High risk rating now stops confidence from showing as High.
- **Quick fixes:** one goals total everywhere; the model scoreline now matches the lean (the single most likely score overall is shown beside it when different); win-to-nil comes from the model's goal numbers; the filler line is gone; "Best market angle" is now "Most likely markets", and a hit is shown next to how often that market lands in a typical game.
- **Back-test:** `python scripts/backtest.py E0.csv` (add more seasons as extra files). It prints calibration tables, compares the model with bookmaker prices, tests the 78% pick threshold and flat-stake value bets, and saves `data/backtest_report.json`. Not run by the GitHub Action; run it on your own computer.
- Team news is still not part of the win chances; the page now says so.

## If you already set up the first version: upgrade in 5 minutes
In your GitHub repository, upload these 4 files over the old ones (Add file, Upload files, then Commit):
1. `scripts/make_predictions.py` (NEW)
2. `scripts/run_picks.py` (replaces the old one)
3. `.github/workflows/update.yml` (replaces the old one)
4. `index.html` (replaces the old one)

Then: Actions tab, "Update data and picks", Run workflow. After about 2 minutes check that `data/predictions.json` exists. Reload your site with Ctrl+F5. The grey bar should say **"model: last 10 games"**.

Your old picks stay as they are. Never edit `data/picks_log.json` by hand.

## First-time setup (new repository)
1. Free token at football-data.org (check your email for it).
2. Free GitHub account, new **Public** repository.
3. Upload everything in this zip (unzip first so the hidden `.github` folder is included).
4. Settings, Secrets and variables, Actions, New repository secret: `FOOTBALL_DATA_TOKEN` = your token.
5. Settings, Pages: publish from the `main` branch, root folder.
6. Actions tab, "Update data and picks", Run workflow. It then runs every 6 hours.

## How to read the grey status bar
- **Live data connected ... model: last 10 games**: everything is working.
- **predictions.json missing, using the basic table formula**: the page works, but the new step has not run yet. Run the workflow.
- **Data is X hours old**: the Action has stopped updating. Open the Actions tab and look for a red cross.
- **Live data problem ... (HTTP 404)**: the named file is not in your `data` folder yet.

## Good to know
- A pick is saved with the number it had when it was logged. The page can show a slightly different number later, as new results arrive.
- Leagues: every competition your football-data.org token covers (12 on the free plan). Not 2. Bundesliga or League One.
- Bookmaker odds are not recorded yet, so profit is not shown. Short-priced markets can have a high hit rate and still lose money.
- Team news and "Key out" notes on the page are still hand-written (researched 26 Oct) and do not update by themselves.

## Next steps
1. Add bookmaker odds so picks show real profit.
2. Improve the model (home/away strength) and test it on past seasons.
3. Add a premium login and payments.
