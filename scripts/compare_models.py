"""Test the old model (v1) against the new team-ratings model (v2) on past seasons and
pick the one that predicts best. Run by the "Back-test models" GitHub Action.

Usage:  python scripts/compare_models.py <folder with CSV files>
CSV files are football-data.co.uk files named <LEAGUE>_<anything>.csv, e.g. E0_2425.csv.
All files with the same <LEAGUE> prefix are treated as one league, in date order.

Every prediction uses ONLY games played before that match, exactly like the live site.
Writes data/model_choice.json (read by make_predictions.py) and data/backtest_report.md.
"""
import json, math, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import predict_v1, predict_v2, V2_DEFAULTS  # noqa: E402
from backtest import load, devig  # noqa: E402

D = Path(__file__).resolve().parent.parent / "data"
LEAGUE_NAMES = {"E0": "Premier League", "E1": "Championship", "SP1": "La Liga", "I1": "Serie A",
                "D1": "Bundesliga", "F1": "Ligue 1", "N1": "Eredivisie", "P1": "Primeira Liga",
                "BRA": "Brasileirão Série A"}
SWITCH_MARGIN = 0.002   # v2 must beat v1's average log loss by at least this much to be used


def candidates():
    base = dict(V2_DEFAULTS)
    c = [("v1: last 10 games", {"version": 1})]
    for hl in (90, 180, 365):
        c.append((f"v2: ratings, half-life {hl} days", dict(base, version=2, half_life=hl)))
    c.append(("v2: ratings, half-life 180 days, no low-score fix", dict(base, version=2, half_life=180, rho=0.0)))
    return c


def run(c, rows, m):
    if c["version"] == 1:
        return predict_v1(rows, m["home"], m["away"], m["utc"])
    return predict_v2(rows, m["home"], m["away"], m["utc"], c["half_life"], c["rho"], c["prior"], c["window_days"])


def ll(p):
    return -math.log(max(p, 1e-9))


def main(folder):
    files = sorted(Path(folder).glob("*.csv"))
    groups = {}
    for f in files:
        groups.setdefault(f.stem.split("_")[0], []).append(str(f))
    if not groups:
        sys.exit(f"no CSV files found in {folder}")
    cands = candidates()
    tot = {name: {"n": 0, "ll": 0.0, "brier": 0.0, "hit": 0, "o15ll": 0.0, "dogll": 0.0} for name, _ in cands}
    book = {"n": 0, "ll": 0.0, "brier": 0.0}
    per_league = {}
    for lg, fl in sorted(groups.items()):
        t0 = time.time()
        rows = load(fl)
        if len(rows) < 200:
            print(f"{lg}: only {len(rows)} matches, skipped")
            continue
        preds = {name: [run(c, rows, m) for m in rows] for name, c in cands}
        idx = [i for i in range(len(rows)) if all(preds[name][i] for name, _ in cands)]
        per_league[lg] = {"matches": len(idx)}
        for name, _ in cands:
            s = {"n": 0, "ll": 0.0}
            for i in idx:
                m, p = rows[i], preds[name][i]
                k = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
                pr = [p["home"], p["draw"], p["away"]]
                o15 = m["hg"] + m["ag"] >= 2
                d = (m["hg"] - m["ag"]) if p["fav"] == "home" else (m["ag"] - m["hg"])
                T = tot[name]
                T["n"] += 1; T["ll"] += ll(pr[k]); s["n"] += 1; s["ll"] += ll(pr[k])
                T["brier"] += sum((pr[j] - (j == k)) ** 2 for j in range(3))
                T["hit"] += max(range(3), key=lambda j: pr[j]) == k
                T["o15ll"] += ll(p["over15"] if o15 else 1 - p["over15"])
                T["dogll"] += ll(p["dog15"] if d < 2 else 1 - p["dog15"])
            per_league[lg][name] = round(s["ll"] / max(1, s["n"]), 4)
        for i in idx:
            m = rows[i]
            if m["odds"]:
                k = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
                q = devig(m["odds"])
                book["n"] += 1; book["ll"] += ll(q[k]); book["brier"] += sum((q[j] - (j == k)) ** 2 for j in range(3))
        print(f"{lg}: {len(rows)} games, {len(idx)} compared ({time.time() - t0:.0f}s)")

    res = []
    for name, c in cands:
        T = tot[name]
        if not T["n"]:
            continue
        res.append({"name": name, "settings": c, "matches": T["n"],
                    "logloss_1x2": round(T["ll"] / T["n"], 4), "brier_1x2": round(T["brier"] / T["n"], 4),
                    "lean_accuracy": round(T["hit"] / T["n"], 4),
                    "logloss_over15": round(T["o15ll"] / T["n"], 4), "logloss_dog15": round(T["dogll"] / T["n"], 4)})
    if not res:
        sys.exit("nothing could be compared")
    v1 = next(r for r in res if r["settings"]["version"] == 1)
    best = min(res, key=lambda r: r["logloss_1x2"])
    use = best if best["settings"]["version"] == 2 and v1["logloss_1x2"] - best["logloss_1x2"] >= SWITCH_MARGIN else v1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    choice = dict(use["settings"], chosen=use["name"], tested=now, matches=use["matches"],
                  reason=("beat v1 on past seasons" if use is not v1 else
                          "v2 was not clearly better than v1, so v1 stays"))
    D.mkdir(exist_ok=True)
    (D / "model_choice.json").write_text(json.dumps(choice, indent=1))
    bk = {"logloss_1x2": round(book["ll"] / book["n"], 4), "brier_1x2": round(book["brier"] / book["n"], 4),
          "matches": book["n"]} if book["n"] else None

    md = [f"# Model back-test ({now[:10]})", "",
          f"Tested on {use['matches']} past matches. Every prediction used only games played before that match.",
          "Lower log loss / Brier = better. Bookmaker closing prices are shown as the benchmark to beat.", "",
          "| Model | 1X2 log loss | 1X2 Brier | Lean right | Over 1.5 log loss | Underdog +1.5 log loss |",
          "|---|---|---|---|---|---|"]
    for r in sorted(res, key=lambda r: r["logloss_1x2"]):
        md.append(f"| {r['name']}{' **(now used)**' if r is use else ''} | {r['logloss_1x2']} | {r['brier_1x2']} | "
                  f"{r['lean_accuracy'] * 100:.1f}% | {r['logloss_over15']} | {r['logloss_dog15']} |")
    if bk:
        md.append(f"| Bookmakers (average odds, margin removed) | {bk['logloss_1x2']} | {bk['brier_1x2']} | | | |")
    md += ["", f"**Decision:** {use['name']} ({choice['reason']}).", "", "## By league (1X2 log loss)", "",
           "| League | Matches | " + " | ".join(r["name"] for r in res) + " |",
           "|---|---|" + "---|" * len(res)]
    for lg, x in per_league.items():
        md.append(f"| {LEAGUE_NAMES.get(lg, lg)} | {x['matches']} | " + " | ".join(str(x.get(r["name"], "")) for r in res) + " |")
    (D / "backtest_report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nSaved data/model_choice.json -> {use['name']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
