"""Walk-forward back-test of scripts/model.py on football-data.co.uk CSV files.

Usage:   python scripts/backtest.py E0.csv [E0_2425.csv ...]
Needs only the standard library. Every prediction uses ONLY games played before
that match (same rule as the live site), so nothing here is hindsight.

It answers four questions:
 1. Calibration: when the model says 60%, does it land about 60% of the time?
 2. Is it better or worse than the bookmakers' own prices (Brier score, log loss)?
 3. Which pick threshold (the 78% in run_picks.py) is honest for Over 1.5 / Underdog +1.5?
 4. Would betting where the model disagrees with the bookmakers have made money?

Output: a printed report plus data/backtest_report.json and data/backtest_report.md.
"""
import csv, json, math, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import predict, load_choice  # noqa: E402
MODEL_VERSION = load_choice()["version"]

D = Path(__file__).resolve().parent.parent / "data"
ODDS_SETS = [("AvgH", "AvgD", "AvgA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365H", "B365D", "B365A"), ("PSH", "PSD", "PSA"),
             ("MaxH", "MaxD", "MaxA"), ("BbAvH", "BbAvD", "BbAvA")]
BINS = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]


def num(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def parse_date(d, t):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(d.strip(), f)
            break
        except ValueError:
            dt = None
    if dt is None:
        return None
    hh, mm = "12", "00"
    if t and ":" in t:
        hh, mm = t.strip().split(":")[:2]
    return f"{dt:%Y-%m-%d}T{int(hh):02d}:{int(mm):02d}:00Z"


def load(files):
    rows = []
    for fn in files:
        with open(fn, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                utc = parse_date(r.get("Date", ""), r.get("Time", ""))
                try:   # main-league files use FTHG/FTAG, the "extra leagues" files (e.g. Brazil) use HG/AG
                    hg, ag = int(r.get("FTHG") or r["HG"]), int(r.get("FTAG") or r["AG"])
                except (KeyError, ValueError, TypeError):
                    continue
                r["HomeTeam"] = r.get("HomeTeam") or r.get("Home")
                r["AwayTeam"] = r.get("AwayTeam") or r.get("Away")
                if not utc or not r.get("HomeTeam") or not r.get("AwayTeam"):
                    continue
                odds = None
                for cols in ODDS_SETS:
                    v = [num(r.get(c)) for c in cols]
                    if all(v):
                        odds = v
                        break
                o25 = None
                for cols in (("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5"), ("BbAv>2.5", "BbAv<2.5")):
                    v = [num(r.get(c)) for c in cols]
                    if all(v):
                        o25 = v
                        break
                rows.append({"id": len(rows), "utc": utc, "status": "FINISHED", "home": r["HomeTeam"].strip(),
                             "away": r["AwayTeam"].strip(), "hg": hg, "ag": ag, "odds": odds, "o25": o25})
    rows.sort(key=lambda m: m["utc"])
    return rows


def devig(odds):
    q = [1 / o for o in odds]
    t = sum(q)
    return [x / t for x in q]


def brier(p, k):
    return sum((p[i] - (1 if i == k else 0)) ** 2 for i in range(3))


def logloss(p, k):
    return -math.log(max(p[k], 1e-9))


def calib(events):
    """events = [(prob 0-1, hit bool)] -> table rows."""
    out = []
    for lo, hi in BINS:
        e = [(p, h) for p, h in events if lo <= p * 100 < hi]
        if not e:
            continue
        out.append({"band": f"{lo}-{min(hi, 100)}%", "n": len(e),
                    "model_avg": round(100 * sum(p for p, _ in e) / len(e), 1),
                    "actual": round(100 * sum(h for _, h in e) / len(e), 1)})
    return out


def main(files):
    rows = load(files)
    if len(rows) < 100:
        sys.exit(f"Only {len(rows)} usable matches found. Check the CSV has Date, HomeTeam, AwayTeam, FTHG, FTAG.")
    print(f"{len(rows)} finished matches loaded, model v{MODEL_VERSION}; predicting each from earlier games only...")
    recs = []
    for m in rows:
        p = predict(rows, m["home"], m["away"], m["utc"])
        if not p:
            continue
        k = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
        recs.append({"m": m, "p": p, "k": k, "pr": [p["home"], p["draw"], p["away"]]})
    n = len(recs)
    print(f"{n} matches had enough history to be predicted (the first few weeks of the data are skipped).")
    rep = {"model_version": MODEL_VERSION, "matches_predicted": n}

    # 1X2 accuracy and the model's own skill vs bookmakers
    lean_hits = sum(1 for r in recs if max(range(3), key=lambda i: r["pr"][i]) == r["k"])
    rep["lean_accuracy"] = round(lean_hits / n, 3)
    both = [r for r in recs if r["m"]["odds"]]
    if both:
        mb = sum(brier(r["pr"], r["k"]) for r in both) / len(both)
        bb = sum(brier(devig(r["m"]["odds"]), r["k"]) for r in both) / len(both)
        ml = sum(logloss(r["pr"], r["k"]) for r in both) / len(both)
        bl = sum(logloss(devig(r["m"]["odds"]), r["k"]) for r in both) / len(both)
        rep["vs_bookmaker"] = {"matches": len(both), "model_brier": round(mb, 4), "book_brier": round(bb, 4),
                               "model_logloss": round(ml, 4), "book_logloss": round(bl, 4),
                               "verdict": "model is better than the bookmakers' prices" if mb < bb else
                                          "bookmakers' prices are better than the model (lower score = better)"}

    # calibration of every stated outcome probability, and of the favourite specifically
    ev = [(r["pr"][i], r["k"] == i) for r in recs for i in range(3)]
    rep["calibration_all_outcomes"] = calib(ev)
    fav = [(max(r["pr"]), max(range(3), key=lambda i: r["pr"][i]) == r["k"]) for r in recs]
    rep["calibration_favourite"] = calib(fav)

    # goal markets
    def market(name, pf, hit):
        e = [(pf(r["p"]), hit(r)) for r in recs]
        rep.setdefault("markets", {})[name] = {"calibration": calib(e)}
        return e

    def dog_cover(r):
        m, p = r["m"], r["p"]
        d = (m["hg"] - m["ag"]) if p["fav"] == "home" else (m["ag"] - m["hg"])
        return d < 2

    e15 = market("over15", lambda p: p["over15"], lambda r: r["m"]["hg"] + r["m"]["ag"] >= 2)
    market("over25", lambda p: p["over25"], lambda r: r["m"]["hg"] + r["m"]["ag"] >= 3)
    market("btts", lambda p: p["btts"], lambda r: r["m"]["hg"] > 0 and r["m"]["ag"] > 0)
    edog = market("dog15", lambda p: p["dog15"], dog_cover)

    # pick-threshold table (what run_picks.py logs). Underdog picks also need the dog to have a 12%+ win chance.
    def thr_rows(events, extra=lambda r: True):
        rows_ = []
        for t in (0.70, 0.74, 0.78, 0.82, 0.86, 0.90):
            sel = [(p, h) for (p, h), r in zip(events, recs) if p >= t and extra(r)]
            if sel:
                rows_.append({"threshold": t, "picks": len(sel), "model_avg": round(100 * sum(p for p, _ in sel) / len(sel), 1),
                              "hit_rate": round(100 * sum(h for _, h in sel) / len(sel), 1),
                              "break_even_odds": round(len(sel) / max(1, sum(h for _, h in sel)), 2)})
        return rows_
    rep["pick_thresholds"] = {"over15": thr_rows(e15),
                              "dog15": thr_rows(edog, lambda r: 100 * (r["p"]["away"] if r["p"]["fav"] == "home" else r["p"]["home"]) >= 12)}

    # does betting the model's disagreements with the bookmakers pay? (flat 1 unit, average odds)
    val = {}
    for edge in (0.00, 0.05, 0.10, 0.15):
        bets = prof = 0
        for r in both:
            for i in range(3):
                if r["pr"][i] * r["m"]["odds"][i] - 1 >= edge:
                    bets += 1
                    prof += (r["m"]["odds"][i] - 1) if r["k"] == i else -1
        val[f"edge>={int(edge * 100)}%"] = {"bets": bets, "profit_units": round(prof, 1),
                                           "roi_pct": round(100 * prof / bets, 1) if bets else None}
    rep["value_bets_1x2"] = val

    # ---- print + save
    def show(title, rows_, cols):
        print(f"\n{title}")
        print("  " + "  ".join(f"{c:>12}" for c in cols))
        for x in rows_:
            print("  " + "  ".join(f"{str(x.get(c, '')):>12}" for c in cols))
    print(f"\nLean (most likely outcome) was right {rep['lean_accuracy']*100:.1f}% of the time.")
    if "vs_bookmaker" in rep:
        v = rep["vs_bookmaker"]
        print(f"\nModel vs bookmakers on {v['matches']} matches (lower is better):")
        print(f"  Brier   model {v['model_brier']}  book {v['book_brier']}\n  LogLoss model {v['model_logloss']}  book {v['book_logloss']}\n  => {v['verdict']}")
    show("Calibration of the FAVOURITE (does a stated 60% land ~60%?)", rep["calibration_favourite"], ["band", "n", "model_avg", "actual"])
    show("Calibration of ALL home/draw/away probabilities", rep["calibration_all_outcomes"], ["band", "n", "model_avg", "actual"])
    for k, t in rep["markets"].items():
        show(f"Calibration: {k}", t["calibration"], ["band", "n", "model_avg", "actual"])
    for k, t in rep["pick_thresholds"].items():
        show(f"Pick threshold table: {k}", t, ["threshold", "picks", "model_avg", "hit_rate", "break_even_odds"])
    print("\nFlat-stake value bets (model prob x bookmaker odds - 1 >= edge):")
    for k, x in val.items():
        print(f"  {k:>10}: {x['bets']} bets, profit {x['profit_units']} units, ROI {x['roi_pct']}%")
    print("\nHow to read it: if 'actual' sits below 'model_avg' in a band, the model is overconfident there.\n"
          "A pick threshold is only honest where hit_rate >= model_avg, and it only makes money if the odds you\n"
          "can really get are above break_even_odds. Over 1.5 odds are not in these files, so check them yourself.")
    D.mkdir(exist_ok=True)
    (D / "backtest_report.json").write_text(json.dumps(rep, indent=1))
    print(f"\nSaved {D / 'backtest_report.json'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
