# Model back-test (2026-11-05)

Tested on 17015 past matches. Every prediction used only games played before that match.
Lower log loss / Brier = better. Bookmaker closing prices are shown as the benchmark to beat.

Models are ranked on results AND goals (1X2 log loss + Over 2.5 log loss).

| Model | Combined score | 1X2 log loss | Over 2.5 log loss | Lean right | Over 1.5 log loss | Underdog +1.5 log loss |
|---|---|---|---|---|---|---|
| v2: ratings, half-life 365 days, steadier (prior 12) **(now used)** | 1.6878 | 1.0042 | 0.6836 | 51.3% | 0.5601 | 0.5479 |
| v2: ratings, half-life 180 days, steadier (prior 12) | 1.6885 | 1.0053 | 0.6832 | 51.2% | 0.5598 | 0.5478 |
| v2: ratings, half-life 180 days, steadier (prior 8) | 1.6893 | 1.0038 | 0.6854 | 51.2% | 0.5616 | 0.5502 |
| v2: ratings, half-life 365 days, steadier (prior 8) | 1.6894 | 1.0034 | 0.686 | 51.1% | 0.5619 | 0.5479 |
| v2: ratings, half-life 180 days | 1.6945 | 1.0044 | 0.6902 | 51.0% | 0.5651 | 0.5528 |
| v2: ratings, half-life 365 days | 1.6948 | 1.0044 | 0.6904 | 50.8% | 0.5652 | 0.5508 |
| v2: ratings, half-life 180 days, no low-score fix | 1.6953 | 1.0051 | 0.6902 | 51.1% | 0.5645 | 0.5528 |
| v2: ratings, half-life 90 days | 1.6985 | 1.0069 | 0.6916 | 50.8% | 0.5664 | 0.5536 |
| v1: last 10 games | 1.7361 | 1.0282 | 0.7079 | 48.8% | 0.579 | 0.5509 |
| Bookmakers (average odds, margin removed) | | 0.9803 | | | | |

**Decision:** v2: ratings, half-life 365 days, steadier (prior 12) (beat v1 on past seasons).

## By league (1X2 log loss)

| League | Matches | v1: last 10 games | v2: ratings, half-life 90 days | v2: ratings, half-life 180 days | v2: ratings, half-life 365 days | v2: ratings, half-life 180 days, no low-score fix | v2: ratings, half-life 180 days, steadier (prior 8) | v2: ratings, half-life 365 days, steadier (prior 8) | v2: ratings, half-life 180 days, steadier (prior 12) | v2: ratings, half-life 365 days, steadier (prior 12) |
|---|---|---|---|---|---|---|---|---|---|---|
| Brasileirão Série A | 5339 | 1.0425 | 1.0225 | 1.0211 | 1.0215 | 1.0211 | 1.0197 | 1.0202 | 1.0198 | 1.0201 |
| Bundesliga | 1207 | 1.0318 | 1.0113 | 1.0088 | 1.0094 | 1.0113 | 1.0051 | 1.0055 | 1.0047 | 1.0044 |
| Premier League | 1503 | 1.0223 | 0.9945 | 0.9909 | 0.9904 | 0.9918 | 0.9912 | 0.9902 | 0.9934 | 0.9916 |
| Championship | 2207 | 1.084 | 1.056 | 1.0546 | 1.0549 | 1.0538 | 1.0523 | 1.0528 | 1.0518 | 1.0522 |
| Ligue 1 | 1279 | 1.0263 | 1.0048 | 1.0024 | 1.0024 | 1.0025 | 1.0019 | 1.0013 | 1.0037 | 1.0022 |
| Serie A | 1512 | 1.0092 | 0.9894 | 0.9859 | 0.9855 | 0.9877 | 0.989 | 0.9876 | 0.9934 | 0.9908 |
| Eredivisie | 1221 | 0.9848 | 0.9691 | 0.9668 | 0.9672 | 0.9702 | 0.9649 | 0.9643 | 0.9667 | 0.9646 |
| Primeira Liga | 1223 | 0.9528 | 0.9333 | 0.9286 | 0.928 | 0.9299 | 0.9345 | 0.9319 | 0.9417 | 0.9372 |
| La Liga | 1524 | 1.0166 | 0.9981 | 0.9938 | 0.9927 | 0.9946 | 0.9925 | 0.9907 | 0.9942 | 0.9914 |
