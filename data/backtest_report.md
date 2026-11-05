# Model back-test (2026-11-05)

Tested on 17015 past matches. Every prediction used only games played before that match.
Lower log loss / Brier = better. Bookmaker closing prices are shown as the benchmark to beat.

| Model | 1X2 log loss | 1X2 Brier | Lean right | Over 1.5 log loss | Underdog +1.5 log loss |
|---|---|---|---|---|---|
| v2: ratings, half-life 180 days **(now used)** | 1.0044 | 0.6004 | 51.0% | 0.5651 | 0.5528 |
| v2: ratings, half-life 365 days | 1.0044 | 0.6004 | 50.8% | 0.5652 | 0.5508 |
| v2: ratings, half-life 180 days, no low-score fix | 1.0051 | 0.6008 | 51.1% | 0.5645 | 0.5528 |
| v2: ratings, half-life 90 days | 1.0069 | 0.6022 | 50.8% | 0.5664 | 0.5536 |
| v1: last 10 games | 1.0282 | 0.6164 | 48.8% | 0.579 | 0.5509 |
| Bookmakers (average odds, margin removed) | 0.9803 | 0.5842 | | | |

**Decision:** v2: ratings, half-life 180 days (beat v1 on past seasons).

## By league (1X2 log loss)

| League | Matches | v1: last 10 games | v2: ratings, half-life 90 days | v2: ratings, half-life 180 days | v2: ratings, half-life 365 days | v2: ratings, half-life 180 days, no low-score fix |
|---|---|---|---|---|---|---|
| Brasileirão Série A | 5339 | 1.0425 | 1.0225 | 1.0211 | 1.0215 | 1.0211 |
| Bundesliga | 1207 | 1.0318 | 1.0113 | 1.0088 | 1.0094 | 1.0113 |
| Premier League | 1503 | 1.0223 | 0.9945 | 0.9909 | 0.9904 | 0.9918 |
| Championship | 2207 | 1.084 | 1.056 | 1.0546 | 1.0549 | 1.0538 |
| Ligue 1 | 1279 | 1.0263 | 1.0048 | 1.0024 | 1.0024 | 1.0025 |
| Serie A | 1512 | 1.0092 | 0.9894 | 0.9859 | 0.9855 | 0.9877 |
| Eredivisie | 1221 | 0.9848 | 0.9691 | 0.9668 | 0.9672 | 0.9702 |
| Primeira Liga | 1223 | 0.9528 | 0.9333 | 0.9286 | 0.928 | 0.9299 |
| La Liga | 1524 | 1.0166 | 0.9981 | 0.9938 | 0.9927 | 0.9946 |
