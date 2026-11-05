"""Which upset signals actually work? Tested on past seasons (football-data.co.uk CSVs).

Usage:  python scripts/upset_backtest.py <folder with CSV files>   (same folder as compare_models.py)

For every past game with a clear favourite, it predicts the game with the site's model using only
earlier results, works out which upset signals were present, and records what happened.
Then, for each signal and each underdog bet (win / win-or-draw / +1.5 handicap) it compares
what really happened with what the model expected.

A signal is PROVEN for a bet only if, over past games where it was present:
  - there are at least MIN_GAMES games,
  - underdogs WITH the signal beat the model's expectation by at least MIN_LIFT more than
    underdogs WITHOUT it did (so a general bias of the model towards or against underdogs
    cannot make a signal look good), and
  - that difference is statistically clear (z-score of at least MIN_Z), not luck.
The general bias itself (all underdogs: model vs reality) is reported separately.
The bet type used for the Upset Pick is the one with the most proven signals.
Writes data/upset_rules.json, which scripts/pick_of_day.py and the site read.
"""
import json, math, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import predict, load_choice  # noqa: E402
from backtest import load  # noqa: E402
from upset import History, signals, dog_markets, dog_hits, zscore, NAMES, MARKETS  # noqa: E402

D = Path(__file__).resolve().parent.parent / "data"
MIN_GAMES, MIN_LIFT, MIN_Z = 150, 0.03, 3.0   # z 3: strict, because 24 signal-bet combinations are tested


def new_acc():
    return {m: {"n": 0, "p": [], "h": [], "ret": [], } for m in MARKETS}


def add(acc, probs, hits, rets):
    for m in MARKETS:
        a = acc[m]
        a["n"] += 1; a["p"].append(probs[m]); a["h"].append(hits[m])
        if rets.get(m) is not None:
            a["ret"].append(rets[m])


def summary(a):
    if not a["n"]:
        return None
    n = a["n"]; exp = sum(a["p"]) / n; act = sum(a["h"]) / n
    out = {"n": n, "model": round(exp, 4), "actual": round(act, 4), "lift": round(act - exp, 4),
           "z": round(zscore(a["h"], a["p"]), 2)}
    if a["ret"]:
        out["roi"] = round(sum(a["ret"]) / len(a["ret"]), 4); out["priced"] = len(a["ret"])
    return out


def main(folder):
    files = sorted(Path(folder).glob("*.csv"))
    groups = {}
    for f in files:
        groups.setdefault(f.stem.split("_")[0], []).append(str(f))
    choice = load_choice()
    base, per, off = new_acc(), {s: new_acc() for s in NAMES}, {s: new_acc() for s in NAMES}
    total = 0
    for lg, fl in sorted(groups.items()):
        rows = load(fl)
        if len(rows) < 200:
            continue
        H, n_lg = History(), 0
        for m in rows:
            p = predict(rows, m["home"], m["away"], m["utc"], choice)
            if p and H.played(m["home"], datetime.fromisoformat(m["utc"].replace("Z", "+00:00")).timestamp()) >= 8 \
                    and H.played(m["away"], datetime.fromisoformat(m["utc"].replace("Z", "+00:00")).timestamp()) >= 8:
                dog_home, sig = signals(H, m["utc"], m["home"], m["away"], p["home"], p["away"])
                if dog_home is not None:
                    probs, hits = dog_markets(p, dog_home), dog_hits(dog_home, m["hg"], m["ag"])
                    rets = {}
                    if m["odds"]:
                        o_dog = m["odds"][0] if dog_home else m["odds"][2]
                        o_dc = 1 / (1 / m["odds"][1] + 1 / o_dog)     # approximate double-chance price
                        rets = {"dog_win": (o_dog - 1) if hits["dog_win"] else -1,
                                "dog_dc": (o_dc - 1) if hits["dog_dc"] else -1}
                    add(base, probs, hits, rets)
                    for k, v in sig.items():
                        add(per[k] if v else off[k], probs, hits, rets)
                    n_lg += 1
            H.add(m["utc"], m["home"], m["away"], m["hg"], m["ag"],
                  p["home"] if p else None, p["away"] if p else None)
        total += n_lg
        print(f"{lg}: {len(rows)} games, {n_lg} with a clear favourite and enough history")

    def compare(a, b):
        """signal present (a) vs absent (b): extra = how much MORE underdogs beat the model with it."""
        r = summary(a)
        if not r or not b["n"]:
            return r
        res_a = (sum(a["h"]) - sum(a["p"])) / a["n"]; res_b = (sum(b["h"]) - sum(b["p"])) / b["n"]
        va = sum(p * (1 - p) for p in a["p"]) / a["n"] ** 2; vb = sum(p * (1 - p) for p in b["p"]) / b["n"] ** 2
        r["extra"] = round(res_a - res_b, 4)
        r["z"] = round((res_a - res_b) / math.sqrt(va + vb), 2) if va + vb > 0 else 0.0
        r["without"] = {"n": b["n"], "lift": round(res_b, 4)}
        return r
    table = {s: {m: compare(per[s][m], off[s][m]) for m in MARKETS} for s in NAMES}
    basesum = {m: summary(base[m]) for m in MARKETS}
    proven = {m: [s for s in NAMES if table[s][m] and table[s][m]["n"] >= MIN_GAMES
                  and table[s][m].get("extra", -1) >= MIN_LIFT and table[s][m]["z"] >= MIN_Z] for m in MARKETS}
    ranked = sorted(MARKETS, key=lambda m: (len(proven[m]), sum(table[s][m]["z"] for s in proven[m])), reverse=True)
    market = ranked[0] if proven[ranked[0]] else None
    out = {"tested": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "underdog_games": total,
           "model_version": choice.get("version", 1),
           "thresholds": {"min_games": MIN_GAMES, "min_lift": MIN_LIFT, "min_z": MIN_Z},
           "market": market, "proven": proven[market] if market else [],
           "proven_by_market": proven, "base": basesum, "table": table, "names": NAMES, "markets": MARKETS}
    D.mkdir(exist_ok=True)
    (D / "upset_rules.json").write_text(json.dumps(out, indent=1))
    print(f"\nTested on {total} underdog games.")
    for m in MARKETS:
        b = basesum[m]
        if b:
            print(f"  all underdogs, {MARKETS[m]}: model {b['model']:.1%}, actual {b['actual']:.1%}"
                  + (f", ROI {b['roi']:+.1%}" if 'roi' in b else ""))
    for s in NAMES:
        r = table[s].get(market or "dog_dc")
        if r:
            print(f"  {s:20s} n={r['n']:5d} vs model {r['lift']:+.3f}  extra vs no-signal {r.get('extra', 0):+.3f} z={r['z']:+.1f}"
                  + ("  PROVEN" if market and s in proven[market] else ""))
    print("Upset Pick bet type:", MARKETS.get(market, "none (no signal proved itself)"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
