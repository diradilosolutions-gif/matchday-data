"""Pick of the Day: one pick per day, chosen by fixed rules, locked when it is chosen,
settled after the game, and kept forever in data/potd.json.

The same rules are copied in index.html (function potdPreview) so the site can show a
"preview, not locked yet" before this script has run. Keep the two in step.

Rules
 - only leagues that are not among the 3 least predictable in the back-test
   (and no cup competitions: too few games per team);
 - both teams have played at least MIN_GAMES league games;
 - markets considered: favourite to win, favourite win-or-draw, over 1.5, over 2.5,
   under 3.5, underdog +1.5;
 - the model's chance must be between P_MIN and P_MAX (fair odds about 1.22-1.39):
   high enough to be a strong pick, not so high that the price is pointless;
 - the strongest qualifying market of the day wins (ties: the favourite-to-win market first);
 - if nothing qualifies, the day is recorded as "no pick". We never force one.

Timing: a day's pick is chosen from 18:00 SAST the evening before. If nothing qualifies
it is re-checked until 10:00 SAST on the day, then "no pick" is locked.
A pick is only made at least 2 hours before its kick-off. Once written, never changed.
"""
import json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent))

D = Path(__file__).resolve().parent.parent / "data"
SAST = ZoneInfo("Africa/Johannesburg")
P_MIN, P_MAX = 72.0, 82.0
MIN_GAMES = 8
LEAD = timedelta(hours=2)
CUPS = {"ucl", "wc", "euro", "cli"}
DEFAULT_RANK = {"ppl": .9286, "nl": .9668, "seriea": .9859, "epl": .9909, "laliga": .9938,
                "ligue1": 1.0024, "bundesliga": 1.0088, "bsa": 1.0211, "champ": 1.0548}
ORDER = ["fav_win", "fav_dc", "over15", "over25", "under35", "dog15"]


def load(name, default):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else default


def excluded_leagues():
    rel = (load("model_choice.json", {}) or {}).get("league_reliability") or {}
    ll = {k: v["logloss"] for k, v in rel.items()} if rel else DEFAULT_RANK
    worst = sorted(ll, key=lambda k: ll[k])[-3:]
    return set(worst) | CUPS


def under35(lh, la):
    t = lh + la
    return 100 * sum(math.exp(-t) * t ** k / math.factorial(k) for k in range(4))


def markets(q, home, away):
    fav_home = q["fav"] == "home"
    fav, dog = (home, away) if fav_home else (away, home)
    pf = q["h"] if fav_home else q["a"]
    return [("fav_win", f"{fav} to win", pf),
            ("fav_dc", f"{fav} win or draw", pf + q["d"]),
            ("over15", "Over 1.5 goals", q["o15"]),
            ("over25", "Over 2.5 goals", q["o25"]),
            ("under35", "Under 3.5 goals", under35(q["lh"], q["la"])),
            ("dog15", f"{dog} +1.5 handicap", q["dog15"])]


def best_for_day(day, data, preds, now, skip):
    best = None
    for lg, ms in data["leagues"].items():
        if lg in skip:
            continue
        P = (preds.get(lg) or {}).get("matches") or {}
        played = {}
        for m in ms:
            if m["status"] == "FINISHED":
                played[m["home"]] = played.get(m["home"], 0) + 1
                played[m["away"]] = played.get(m["away"], 0) + 1
        for m in ms:
            if m["status"] not in ("SCHEDULED", "TIMED"):
                continue
            ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
            if ko.astimezone(SAST).strftime("%Y-%m-%d") != day or ko - now < LEAD:
                continue
            q = P.get(str(m["id"]))
            if not q or q.get("frozen"):
                continue
            if played.get(m["home"], 0) < MIN_GAMES or played.get(m["away"], 0) < MIN_GAMES:
                continue
            for key, label, p in markets(q, m["home"], m["away"]):
                if P_MIN <= p <= P_MAX:
                    cand = (p, -ORDER.index(key))
                    if best is None or cand > best["_rank"]:
                        best = {"_rank": cand, "league": lg, "match_id": m["id"], "utc": m["utc"],
                                "home": m["home"], "away": m["away"], "market": key, "label": label,
                                "side": q["fav"], "model_prob": round(p / 100, 4),
                                "fair_odds": round(100 / p, 2)}
    if best:
        best.pop("_rank")
    return best


def games_on(day, data):
    return any(datetime.fromisoformat(m["utc"].replace("Z", "+00:00")).astimezone(SAST).strftime("%Y-%m-%d") == day
               for ms in data["leagues"].values() for m in ms)


def won(e, hg, ag):
    k, fav_home = e["market"], e.get("side") == "home"
    fg, dg = (hg, ag) if fav_home else (ag, hg)
    return {"fav_win": fg > dg, "fav_dc": fg >= dg, "over15": hg + ag >= 2, "over25": hg + ag >= 3,
            "under35": hg + ag <= 3, "dog15": fg - dg < 2}[k]


def backtest(data, now, skip):
    """Apply the same rules to every past matchday this season, predicting each game only
    from results before its kick-off. Clearly a back-test: these picks were never published."""
    from model import finished, predict, load_choice
    from make_predictions import pack
    choice = load_choice()
    days = {}
    for lg, ms in data["leagues"].items():
        if lg in skip:
            continue
        fin = finished(ms)
        for m in fin:
            day = datetime.fromisoformat(m["utc"].replace("Z", "+00:00")).astimezone(SAST).strftime("%Y-%m-%d")
            days.setdefault(day, []).append((lg, m, fin))
    picks, none_days = [], 0
    for day in sorted(days):
        best = None
        for lg, m, fin in days[day]:
            before = [x for x in fin if x["utc"] < m["utc"]]
            n_h = sum(1 for x in before if m["home"] in (x["home"], x["away"]))
            n_a = sum(1 for x in before if m["away"] in (x["home"], x["away"]))
            if n_h < MIN_GAMES or n_a < MIN_GAMES:
                continue
            p = predict(fin, m["home"], m["away"], m["utc"], choice)
            if not p:
                continue
            q = pack(p)
            for key, label, pr in markets(q, m["home"], m["away"]):
                if P_MIN <= pr <= P_MAX:
                    cand = (pr, -ORDER.index(key))
                    if best is None or cand > best["_rank"]:
                        best = {"_rank": cand, "date": day, "league": lg, "home": m["home"], "away": m["away"],
                                "market": key, "label": label, "side": q["fav"], "model_prob": round(pr / 100, 4),
                                "score": f"{m['hg']}-{m['ag']}", "_hg": m["hg"], "_ag": m["ag"]}
        if best:
            best["won"] = won(best, best.pop("_hg"), best.pop("_ag"))
            best.pop("_rank")
            picks.append(best)
        else:
            none_days += 1
    n = len(picks)
    w = sum(1 for x in picks if x["won"])
    by = {}
    for x in picks:
        b = by.setdefault(x["market"], {"picks": 0, "won": 0})
        b["picks"] += 1; b["won"] += x["won"]
    return {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "model": choice.get("version", 1),
            "rules": {"p_min": P_MIN, "p_max": P_MAX, "min_games": MIN_GAMES, "excluded": sorted(skip)},
            "summary": {"picks": n, "won": w, "hit_rate": round(w / n, 3) if n else None,
                        "avg_model_prob": round(sum(x["model_prob"] for x in picks) / n, 3) if n else None,
                        "no_pick_days": none_days},
            "by_market": by, "picks": picks}


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = load("matches.json", {"leagues": {}})
    preds = load("predictions.json", {"leagues": {}}).get("leagues", {})
    log = load("potd.json", [])
    decided = {e["date"] for e in log}
    skip = excluded_leagues()
    local = now.astimezone(SAST)
    for offset in (0, 1):
        day_dt = (local + timedelta(days=offset)).date()
        day = day_dt.isoformat()
        if day in decided:
            continue
        opens = datetime.combine(day_dt - timedelta(days=1), datetime.min.time(), SAST) + timedelta(hours=18)
        closes = datetime.combine(day_dt, datetime.min.time(), SAST) + timedelta(hours=10)
        if local < opens:
            continue
        pick = best_for_day(day, data, preds, now, skip)
        if pick:
            log.append(dict(pick, date=day, locked_at=iso, status="pending", score=None))
            decided.add(day)
            print(f"{day}: Pick of the Day locked: {pick['home']} v {pick['away']}, {pick['label']} ({pick['model_prob']:.0%})")
        elif not games_on(day, data):
            continue                  # no matches that day: nothing to record
        elif local >= closes:
            log.append({"date": day, "locked_at": iso, "status": "none"})
            decided.add(day)
            print(f"{day}: no game met the rules, 'no pick' locked")
        else:
            print(f"{day}: nothing qualifies yet, will check again")
    results = {(lg, m["id"]): m for lg, ms in data["leagues"].items() for m in ms}
    for e in log:
        if e.get("status") == "pending":
            m = results.get((e["league"], e["match_id"]))
            if m and m["status"] == "FINISHED" and m["hg"] is not None:
                e["status"] = "won" if won(e, m["hg"], m["ag"]) else "lost"
                e["score"] = f"{m['hg']}-{m['ag']}"
                e["settled_at"] = iso
            elif m and m["status"] in ("POSTPONED", "CANCELLED"):
                e["status"] = "void"
    log.sort(key=lambda e: e["date"])
    (D / "potd.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    # back-test of the rules: refreshed about once a day (it re-predicts the whole season)
    bt_path = D / "potd_backtest.json"
    old = load("potd_backtest.json", {})
    last = old.get("updated")
    if not last or now - datetime.fromisoformat(last.replace("Z", "+00:00")) >= timedelta(hours=20):
        bt = backtest(data, now, skip)
        bt_path.write_text(json.dumps(bt, indent=1, ensure_ascii=False))
        s = bt["summary"]
        print(f"back-test of the rules: {s['won']} won of {s['picks']} picks; {s['no_pick_days']} matchdays without a pick")


if __name__ == "__main__":
    main()
