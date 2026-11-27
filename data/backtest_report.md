# Model back-test (2026-11-27)

Tested on 16702 past matches. Every prediction used only games played before that match.
Models are picked on matches before 2025-11-26 (13664 matches). Matches from 2025-11-26 on (3038) were kept aside and only used to confirm the winner (last column).

Lower log loss / Brier = better. Bookmaker closing prices are shown as the benchmark to beat.

Models are ranked on results AND goals (1X2 log loss + Over 2.5 log loss).

| Model | Combined score | 1X2 log loss | Over 2.5 log loss | Lean right | Over 1.5 log loss | Underdog +1.5 log loss | Kept-aside combined score |
|---|---|---|---|---|---|---|---|
| v2: ratings, half-life 365 days, steadier (prior 12) **(now used)** | 1.6881 | 1.0051 | 0.683 | 51.1% | 0.568 | 0.5456 | 1.6871 |
| v2: ratings, half-life 180 days, steadier (prior 12) | 1.6887 | 1.006 | 0.6826 | 51.1% | 0.5676 | 0.5459 | 1.688 |
| v2: ratings, half-life 180 days, steadier (prior 8) | 1.6899 | 1.0048 | 0.6851 | 51.1% | 0.5695 | 0.5484 | 1.6874 |
| v2: ratings, half-life 365 days, steadier (prior 8) | 1.69 | 1.0046 | 0.6855 | 51.0% | 0.5699 | 0.5461 | 1.6872 |
| v2: ratings, half-life 180 days | 1.696 | 1.0057 | 0.6902 | 51.0% | 0.5734 | 0.5513 | 1.6895 |
| v2: ratings, half-life 365 days | 1.6963 | 1.006 | 0.6904 | 50.6% | 0.5736 | 0.5493 | 1.6896 |
| v2: ratings, half-life 180 days, no low-score fix | 1.6965 | 1.0063 | 0.6902 | 51.0% | 0.5726 | 0.5513 | 1.6907 |
| v2: ratings, half-life 90 days | 1.6996 | 1.0079 | 0.6918 | 50.8% | 0.5745 | 0.553 | 1.6937 |
| v1: last 10 games | 1.7383 | 1.0301 | 0.7082 | 48.7% | 0.5865 | 0.5494 | 1.7274 |
| Bookmakers (average odds, margin removed, all matches) | | 0.9803 | | | | | |

**Decision:** v2: ratings, half-life 365 days, steadier (prior 12) (the model in use was still the best on past seasons).

## By league (1X2 log loss)

| League | Matches | v1: last 10 games | v2: ratings, half-life 90 days | v2: ratings, half-life 180 days | v2: ratings, half-life 365 days | v2: ratings, half-life 180 days, no low-score fix | v2: ratings, half-life 180 days, steadier (prior 8) | v2: ratings, half-life 365 days, steadier (prior 8) | v2: ratings, half-life 180 days, steadier (prior 12) | v2: ratings, half-life 365 days, steadier (prior 12) |
|---|---|---|---|---|---|---|---|---|---|---|
| Brasileirão Série A | 5371 | 1.0422 | 1.0223 | 1.0209 | 1.0213 | 1.0209 | 1.0195 | 1.02 | 1.0197 | 1.0199 |
| Bundesliga | 1225 | 1.0279 | 1.0077 | 1.0055 | 1.0064 | 1.008 | 1.0021 | 1.0027 | 1.002 | 1.0017 |
| Premier League | 1523 | 1.0225 | 0.9943 | 0.9909 | 0.9906 | 0.9919 | 0.9913 | 0.9904 | 0.9935 | 0.9918 |
| Championship | 2243 | 1.0827 | 1.0552 | 1.0542 | 1.0546 | 1.0534 | 1.0519 | 1.0525 | 1.0513 | 1.0519 |
| Ligue 1 | 1297 | 1.026 | 1.0052 | 1.0032 | 1.0035 | 1.0032 | 1.0026 | 1.0022 | 1.0044 | 1.0031 |
| Serie A | 1131 | 1.0086 | 0.9913 | 0.9885 | 0.9882 | 0.9895 | 0.9913 | 0.9899 | 0.9959 | 0.9934 |
| Eredivisie | 1137 | 0.978 | 0.9632 | 0.9608 | 0.9612 | 0.9642 | 0.959 | 0.9583 | 0.961 | 0.9587 |
| Primeira Liga | 1231 | 0.9528 | 0.933 | 0.9279 | 0.9271 | 0.9291 | 0.9338 | 0.931 | 0.9411 | 0.9363 |
| La Liga | 1544 | 1.0169 | 0.998 | 0.9936 | 0.9925 | 0.9945 | 0.9925 | 0.9907 | 0.9943 | 0.9915 |
