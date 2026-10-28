"""Log new picks BEFORE kick-off, settle finished ones, write summary files.
Existing log entries are never edited except to add the result."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import finished, predict

D = Path(__file__).resolve().parent.parent / "data"
MIN_PROB = 0.78                # tune later using backtests
LEAD = timedelta(minutes=45)   # only log picks at least this long before kick-off
HORIZON = timedelta(days=4)    # only look this far ahead
LABEL = {"over15": "Over 1.5 goals", "dog15": "Underdog +1.5 handicap"}


def load(name, default):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else default


def candidates(p):
    out = []
    if p["over15"] >= MIN_PROB:
        out.append(("over15", p["over15"], None))
    dog_side = "away" if p["fav"] == "home" else "home"
    if p["dog15"] >= MIN_PROB and p[dog_side] >= 0.12:   # skip hopeless mismatches
        out.append(("dog15", p["dog15"], dog_side))
    return out


def won(entry, hg, ag):
    if entry["market"] == "over15":
        return hg + ag >= 2
    dg, fg = (hg, ag) if entry["side"] == "home" else (ag, hg)
    return dg + 1.5 > fg


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = load("matches.json", {"leagues": {}})
    log = load("picks_log.json", [])
    seen = {e["id"] for e in log}
    new = 0
    for lg, ms in data["leagues"].items():
        fin = finished(ms)
        for m in ms:
            ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
            if m["status"] not in ("SCHEDULED", "TIMED") or not (now + LEAD < ko < now + HORIZON):
                continue
            p = predict(fin, m["home"], m["away"], m["utc"])
            if not p:
                continue
            for market, prob, side in candidates(p):
                eid = f"{lg}:{m['id']}:{market}"
                if eid in seen:
                    continue
                log.append({"id": eid, "league": lg, "match_id": m["id"], "utc": m["utc"],
                            "home": m["home"], "away": m["away"], "market": market,
                            "label": LABEL[market], "side": side,
                            "model_prob": round(prob, 4), "fair_odds": round(1 / prob, 2),
                            "odds": None,  # fill from an odds feed later
                            "created_at": iso(now), "won": None, "score": None})
                seen.add(eid); new += 1
    results = {(lg, m["id"]): m for lg, ms in data["leagues"].items() for m in ms}
    settled = 0
    for e in log:
        if e["won"] is None:
            m = results.get((e["league"], e["match_id"]))
            if m and m["status"] == "FINISHED" and m["hg"] is not None:
                e["won"] = won(e, m["hg"], m["ag"]); e["score"] = f"{m['hg']}-{m['ag']}"; settled += 1
    (D / "picks_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))

    done = [e for e in log if e["won"] is not None]

    def stats(rows):
        n = len(rows)
        if not n:
            return {"picks": 0}
        w = sum(e["won"] for e in rows)
        r = {"picks": n, "wins": w, "hit_rate": round(w / n, 3),
             "avg_model_prob": round(sum(e["model_prob"] for e in rows) / n, 3)}
        priced = [e for e in rows if e["odds"]]
        if priced:
            r["priced_picks"] = len(priced)
            r["profit_units"] = round(sum((e["odds"] - 1) if e["won"] else -1 for e in priced), 2)
        return r

    cut = iso(now - timedelta(days=30))
    summary = {"updated": iso(now), "since": min((e["created_at"] for e in log), default=None),
               "pending": len(log) - len(done), "all": stats(done),
               "last_30_days": stats([e for e in done if e["utc"] >= cut]),
               "by_market": {k: stats([e for e in done if e["market"] == k]) for k in LABEL}}
    (D / "summary.json").write_text(json.dumps(summary, indent=1))
    up = sorted([e for e in log if e["won"] is None and e["utc"] > iso(now)], key=lambda e: e["utc"])
    (D / "picks_upcoming.json").write_text(json.dumps(up, indent=1, ensure_ascii=False))
    print(f"new picks: {new}, settled: {settled}, upcoming: {len(up)}")


if __name__ == "__main__":
    main()
