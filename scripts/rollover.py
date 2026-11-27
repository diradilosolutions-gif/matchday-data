"""Daily rollover: 2 games a day, together worth about 2.00 at the model's fair odds.

Rules (fixed, so the record is honest):
 - Possible selections per game (each needs MIN_LEG to MAX_LEG model chance):
     * favourite to win        (clear favourite only: 45%+ and 10 points ahead)
     * favourite win or draw   (clear favourite only)
     * Over 1.5 goals
     * team +1.5 handicap      (the other side does not win by 2+; skipped if that team's win
                                chance is under 12%, i.e. hopeless mismatches)
 - The pair (two DIFFERENT games) whose combined fair odds are closest to TARGET is chosen;
   it must land between LOW and HIGH. Ties go to the more balanced pair (the weaker leg is stronger).
   If no pair lands in that range, there is no rollover that day.
 - Bookmaker prices are not used. Fair odds = 1 / model chance. Bookmakers usually pay a bit less.

Timing and locking (same as the Upset Pick): chosen from 18:00 SAST the evening before, only from
games at least 2 hours away, then locked forever in data/rollover.json. If nothing qualifies by
10:00 SAST on the day, "none" is locked. A postponed game is void and the ticket is settled on
the remaining selections.
Also: what would be picked right now (preview, not locked) and the same rules applied to this
season's past matchdays (each game judged only on earlier games).
"""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import finished, predict, load_choice  # noqa: E402

D = Path(__file__).resolve().parent.parent / "data"
OUT = D / "rollover.json"
SAST = ZoneInfo("Africa/Johannesburg")
MIN_LEG, MAX_LEG = 0.60, 0.88
TARGET, LOW, HIGH = 2.00, 1.85, 2.20
LEAD = timedelta(hours=2)
RULES = {"legs": 2, "target_odds": TARGET, "odds_range": [LOW, HIGH], "leg_chance": [MIN_LEG, MAX_LEG],
         "clear_favourite": "45%+ and 10 points ahead",
         "markets": ["favourite to win", "favourite win or draw", "Over 1.5 goals", "+1.5 handicap"]}


def load(name, default):
    p = D / name
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


def day_of(utc):
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(SAST).strftime("%Y-%m-%d")


def leg_options(m, h, d, a, o15, dog15, fav):
    """h/d/a/o15/dog15 as 0-1 chances, fav 'home'/'away'. All selections in the allowed chance range."""
    fp, dp = (h, a) if fav == "home" else (a, h)
    fav_t, dog_t = (m["home"], m["away"]) if fav == "home" else (m["away"], m["home"])
    fs, ds = ("home", "away") if fav == "home" else ("away", "home")
    opts = []
    if fp >= .45 and fp - dp >= .10:
        opts.append(("fav_win", f"{fav_t} to win", fp, fs))
        opts.append(("fav_dc", f"{fav_t} win or draw", 1 - dp, fs))
    opts.append(("over15", "Over 1.5 goals", o15, None))
    if dp >= .12:
        opts.append(("dog15", f"{dog_t} +1.5 handicap", dog15, ds))
    return [{"match_id": m["id"], "home": m["home"], "away": m["away"], "utc": m["utc"], "market": k,
             "label": label, "side": side, "model_prob": round(p, 4), "fair_odds": round(1 / p, 2)}
            for k, label, p, side in opts if MIN_LEG <= p <= MAX_LEG]


def leg_won(e, hg, ag):
    if e["market"] == "over15":
        return hg + ag >= 2
    mine, other = (hg, ag) if e["side"] == "home" else (ag, hg)
    if e["market"] == "fav_win":
        return mine > other
    return mine >= other if e["market"] == "fav_dc" else other - mine < 2


def pick_day(cands):
    """cands: every allowed selection of the day (several per game). Best 2-game pair near TARGET."""
    best = None
    for i, x in enumerate(cands):
        for y in cands[i + 1:]:
            if x["match_id"] == y["match_id"]:
                continue
            p = x["model_prob"] * y["model_prob"]
            odds = 1 / p
            if not LOW <= odds <= HIGH:
                continue
            key = (round(abs(odds - TARGET), 2), -min(x["model_prob"], y["model_prob"]))
            if best is None or key < best[0]:
                best = (key, x, y, p)
    if not best:
        return None
    _, x, y, p = best
    legs = sorted([x, y], key=lambda z: z["utc"])
    return {"legs": legs, "tickets": {"top2": {"legs": 2, "model_prob": round(p, 4), "fair_odds": round(1 / p, 2)}}}


def settle_ticket(t, legs):
    """won / lost / pending / void for the first t['legs'] selections (void legs are dropped)."""
    use = [x for x in legs[:t["legs"]] if x.get("status") != "void"]
    if not use:
        return "void"
    if any(x.get("status") == "lost" for x in use):
        return "lost"
    if all(x.get("status") == "won" for x in use):
        return "won"
    return "pending"


def runs(statuses):
    """Rollover runs from a list of won/lost day results (oldest first)."""
    ended, cur, best = [], 0, 0
    for s in statuses:
        if s == "won":
            cur += 1; best = max(best, cur)
        elif s == "lost":
            ended.append(cur); cur = 0
    return {"current": cur, "longest": best, "ended_after": ended}


def season_backtest(data, choice, now):
    days = {}
    for lg, ms in data["leagues"].items():
        fin = sorted(finished(ms), key=lambda m: m["utc"])
        for m in fin:
            p = predict(fin, m["home"], m["away"], m["utc"], choice)
            if not p:
                continue
            for leg in leg_options(m, p["home"], p["draw"], p["away"], p["over15"], p["dog15"], p["fav"]):
                leg = dict(leg, league=lg, score=f"{m['hg']}-{m['ag']}")
                leg["status"] = "won" if leg_won(leg, m["hg"], m["ag"]) else "lost"
                days.setdefault(day_of(m["utc"]), []).append(leg)
    rows = []
    for day in sorted(days):
        e = pick_day(days[day])
        if not e:
            continue
        for k, t in e["tickets"].items():
            t["status"] = settle_ticket(t, e["legs"])
        rows.append(dict(e, date=day))
    legs = [x for r in rows for x in r["legs"]]

    def tstats(k):
        ts = [r["tickets"][k] for r in rows if k in r["tickets"]]
        n, w = len(ts), sum(t["status"] == "won" for t in ts)
        return {"days": n, "won": w, "hit_rate": round(w / n, 3) if n else None,
                "avg_model_prob": round(sum(t["model_prob"] for t in ts) / n, 3) if n else None,
                "runs": runs([t["status"] for t in ts])}
    return {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "legs": {"n": len(legs), "won": sum(x["status"] == "won" for x in legs),
                     "avg_model_prob": round(sum(x["model_prob"] for x in legs) / len(legs), 3) if legs else None},
            "top2": tstats("top2"), "days_with_games": len(days), "days": rows}


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = load("matches.json", {"leagues": {}})
    preds = load("predictions.json", {"leagues": {}}).get("leagues", {})
    old = load("rollover.json", {})
    log = old.get("log", [])
    decided = {e["date"] for e in log}
    local = now.astimezone(SAST)
    preview = {}
    for offset in (0, 1):
        day_dt = (local + timedelta(days=offset)).date()
        day = day_dt.isoformat()
        cands, open_games = [], 0
        for lg, ms in data["leagues"].items():
            P = preds.get(lg, {}).get("matches", {})
            for m in ms:
                if m["status"] not in ("SCHEDULED", "TIMED") or day_of(m["utc"]) != day:
                    continue
                if datetime.fromisoformat(m["utc"].replace("Z", "+00:00")) - now < LEAD:
                    continue
                p = P.get(str(m["id"]))
                if not p:
                    continue
                open_games += 1
                for leg in leg_options(m, p["h"] / 100, p["d"] / 100, p["a"] / 100, p["o15"] / 100, p["dog15"] / 100, p["fav"]):
                    cands.append(dict(leg, league=lg))
        cand = pick_day(cands)
        preview[day] = cand
        if day in decided:
            continue
        opens = datetime.combine(day_dt - timedelta(days=1), datetime.min.time(), SAST) + timedelta(hours=18)
        closes = datetime.combine(day_dt, datetime.min.time(), SAST) + timedelta(hours=10)
        if local < opens:
            continue
        if cand:
            for x in cand["legs"]:
                x["status"] = "pending"; x["score"] = None
            for t in cand["tickets"].values():
                t["status"] = "pending"
            log.append(dict(cand, date=day, locked_at=iso))
            print(f"{day}: rollover locked: " + "; ".join(f"{x['home']} v {x['away']} {x['label']} {x['model_prob']:.0%}"
                                                      for x in cand["legs"]))
        elif open_games and local >= closes:   # games left to choose from, but none was strong enough
            log.append({"date": day, "locked_at": iso, "legs": [], "tickets": {}, "none": True})
            print(f"{day}: no 2-game pair landed between {LOW} and {HIGH}, 'none' locked")
    # settle
    results = {(lg, m["id"]): m for lg, ms in data["leagues"].items() for m in ms}
    for e in log:
        for x in e.get("legs", []):
            if x.get("status") == "pending":
                m = results.get((x["league"], x["match_id"]))
                if m and m["status"] == "FINISHED" and m["hg"] is not None:
                    x["status"] = "won" if leg_won(x, m["hg"], m["ag"]) else "lost"; x["score"] = f"{m['hg']}-{m['ag']}"
                elif m and m["status"] in ("POSTPONED", "CANCELLED"):
                    x["status"] = "void"
        for t in e.get("tickets", {}).values():
            if t.get("status") == "pending":
                t["status"] = settle_ticket(t, e["legs"])
    log.sort(key=lambda e: e["date"])
    live = {"top2": runs([e["tickets"]["top2"]["status"] for e in log if "top2" in e.get("tickets", {})])}
    bt = old.get("backtest") or {}
    last = bt.get("updated")
    if not last or bt.get("rules") != RULES or now - datetime.fromisoformat(last.replace("Z", "+00:00")) >= timedelta(hours=20):
        bt = dict(season_backtest(data, load_choice(), now), rules=RULES)
        print(f"this season under the same rules: Top 2 won {bt['top2']['won']} of {bt['top2']['days']} days")
    OUT.write_text(json.dumps({"updated": iso, "rules": RULES, "log": log, "live_runs": live,
                               "preview": preview, "backtest": bt}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
