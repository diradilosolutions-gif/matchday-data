"""Upset Pick of the Day: one underdog pick per day, chosen ONLY from upset signals that have
proved themselves on past seasons (data/upset_rules.json, written by scripts/upset_backtest.py).

 - The bet type (underdog to win / win or draw / +1.5 handicap) is the one the back-test chose.
 - A game qualifies only if at least one PROVEN signal is present, there is a clear favourite,
   both teams have 8+ games, it is not a cup game, and the model's own chance for the bet is
   not hopeless (see FLOOR).
 - Strength = the model's chance + the model's general underdog bias for that bet + the extra
   each proven signal added in past seasons. The strongest game of the day is the pick.
 - If no signal has proved itself, the Upset Pick is PAUSED. No pick is ever made on a story.

Timing and locking: chosen from 18:00 SAST the evening before, at least 2 hours before
kick-off, then locked forever in data/potd.json. If nothing qualifies by 10:00 SAST on the day,
"no pick" is locked. Settled after the game.
Also writes data/potd_preview.json (what would be picked right now, not locked) and
data/potd_backtest.json (the same rules applied to this season's past matchdays).
"""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import finished, predict, load_choice  # noqa: E402
from upset import History, signals, dog_markets, dog_hits, MARKETS, NAMES, ts  # noqa: E402

D = Path(__file__).resolve().parent.parent / "data"
SAST = ZoneInfo("Africa/Johannesburg")
MIN_GAMES = 8
LEAD = timedelta(hours=2)
CUPS = {"ucl", "wc", "euro", "cli"}
FLOOR = {"dog_win": .15, "dog_dc": .35, "dog_h15": .55}


def load(name, default):
    p = D / name
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


def rules():
    r = load("upset_rules.json", None)
    if not r:
        return None, "not tested yet: run the 'Back-test models' workflow"
    if not r.get("market") or not r.get("proven"):
        return None, "paused: no upset signal has proved itself on past seasons"
    return r, None


def day_of(utc):
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(SAST).strftime("%Y-%m-%d")


def league_state(ms, choice):
    """History of finished games (with the model's pre-match chances), oldest first."""
    fin = sorted(finished(ms), key=lambda m: m["utc"])
    H, pre = History(), {}
    for m in fin:
        p = predict(fin, m["home"], m["away"], m["utc"], choice)
        pre[m["id"]] = p
        H.add(m["utc"], m["home"], m["away"], m["hg"], m["ag"], p["home"] if p else None, p["away"] if p else None)
    return fin, H, pre


def evaluate(R, H, fin, m, p):
    """Score one game for the Upset Pick. H must only contain games before kick-off."""
    t = ts(m["utc"])
    if not p or H.played(m["home"], t) < MIN_GAMES or H.played(m["away"], t) < MIN_GAMES:
        return None
    dog_home, sig = signals(H, m["utc"], m["home"], m["away"], p["home"], p["away"])
    if dog_home is None:
        return None
    mk = R["market"]
    present = [s for s in R["proven"] if sig.get(s)]
    if not present:
        return None
    model_p = dog_markets(p, dog_home)[mk]
    if model_p < FLOOR[mk]:
        return None
    bias = (R["base"].get(mk) or {}).get("lift", 0) or 0
    extra = sum(R["table"][s][mk]["extra"] for s in present)
    adj = min(.95, model_p + bias + extra)
    dog, fav = (m["home"], m["away"]) if dog_home else (m["away"], m["home"])
    return {"home": m["home"], "away": m["away"], "utc": m["utc"], "match_id": m["id"],
            "market": mk, "label": f"{dog} {MARKETS[mk]}", "dog": dog, "fav": fav,
            "side": "home" if dog_home else "away",
            "model_prob": round(model_p, 4), "bias": round(bias, 4), "adj_prob": round(adj, 4),
            "fair_odds": round(1 / adj, 2),
            "signals": [{"key": s, "text": NAMES[s], "extra": R["table"][s][mk]["extra"],
                         "n": R["table"][s][mk]["n"]} for s in present]}


def won(e, hg, ag):
    if e["market"] in MARKETS:
        return dog_hits(e["side"] == "home", hg, ag)[e["market"]]
    # picks locked by the earlier "Pick of the Day" version (favourite / goals markets)
    fav_home = e.get("side") == "home"
    fg, dg = (hg, ag) if fav_home else (ag, hg)
    return {"fav_win": fg > dg, "fav_dc": fg >= dg, "over15": hg + ag >= 2, "over25": hg + ag >= 3,
            "under35": hg + ag <= 3, "dog15": fg - dg < 2}[e["market"]]


def best_upcoming(R, states, data, day, now, need_lead=True):
    best = None
    for lg, ms in data["leagues"].items():
        if lg in CUPS or lg not in states:
            continue
        fin, H, _, ch = states[lg]
        for m in ms:
            if m["status"] not in ("SCHEDULED", "TIMED") or day_of(m["utc"]) != day:
                continue
            if need_lead and datetime.fromisoformat(m["utc"].replace("Z", "+00:00")) - now < LEAD:
                continue
            e = evaluate(R, H, fin, m, predict(fin, m["home"], m["away"], m["utc"], ch))
            if e and (best is None or (e["adj_prob"], len(e["signals"])) > (best["adj_prob"], len(best["signals"]))):
                best = dict(e, league=lg)
    return best


def season_backtest(R, data, choice, now):
    """The same rules on this season's past matchdays (each game judged only on earlier games)."""
    days = {}
    for lg, ms in data["leagues"].items():
        if lg in CUPS:
            continue
        fin = sorted(finished(ms), key=lambda m: m["utc"])
        H = History()
        for m in fin:
            p = predict(fin, m["home"], m["away"], m["utc"], choice)
            e = evaluate(R, H, fin, m, p)
            if e:
                e = dict(e, league=lg, date=day_of(m["utc"]), score=f"{m['hg']}-{m['ag']}",
                         won=won(e, m["hg"], m["ag"]))
                d = days.get(e["date"])
                if d is None or (e["adj_prob"], len(e["signals"])) > (d["adj_prob"], len(d["signals"])):
                    days[e["date"]] = e
            H.add(m["utc"], m["home"], m["away"], m["hg"], m["ag"], p["home"] if p else None, p["away"] if p else None)
    picks = [days[d] for d in sorted(days)]
    n, w = len(picks), sum(1 for x in picks if x["won"])
    return {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "market": R["market"],
            "summary": {"picks": n, "won": w, "hit_rate": round(w / n, 3) if n else None,
                        "avg_model_prob": round(sum(x["model_prob"] for x in picks) / n, 3) if n else None,
                        "avg_adj_prob": round(sum(x["adj_prob"] for x in picks) / n, 3) if n else None},
            "picks": picks[-30:]}


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = load("matches.json", {"leagues": {}})
    log = load("potd.json", [])
    R, why = rules()
    choice = load_choice()
    preview = {"updated": iso, "state": "ok" if R else ("not_tested" if "not tested" in why else "paused"),
               "reason": why, "market": R["market"] if R else None, "days": {}}
    if R:
        states = {}
        for lg, ms in data["leagues"].items():
            if lg not in CUPS:
                fin, H, pre = league_state(ms, choice)
                states[lg] = (fin, H, pre, choice)
        decided = {e["date"] for e in log}
        local = now.astimezone(SAST)
        for offset in (0, 1):
            day_dt = (local + timedelta(days=offset)).date()
            day = day_dt.isoformat()
            cand = best_upcoming(R, states, data, day, now)
            preview["days"][day] = cand
            if day in decided:
                continue
            opens = datetime.combine(day_dt - timedelta(days=1), datetime.min.time(), SAST) + timedelta(hours=18)
            closes = datetime.combine(day_dt, datetime.min.time(), SAST) + timedelta(hours=10)
            if local < opens:
                continue
            if cand:
                log.append(dict(cand, date=day, locked_at=iso, status="pending", score=None))
                print(f"{day}: Upset Pick locked: {cand['home']} v {cand['away']}, {cand['label']} "
                      f"(model {cand['model_prob']:.0%}, with proven signals {cand['adj_prob']:.0%})")
            elif any(day_of(m["utc"]) == day for ms in data["leagues"].values() for m in ms) and local >= closes:
                log.append({"date": day, "locked_at": iso, "status": "none"})
                print(f"{day}: no game had a proven upset signal, 'no pick' locked")
        bt_old = load("potd_backtest.json", {})
        last = bt_old.get("updated")
        if not last or bt_old.get("market") != R["market"] or \
                now - datetime.fromisoformat(last.replace("Z", "+00:00")) >= timedelta(hours=20):
            bt = season_backtest(R, data, choice, now)
            (D / "potd_backtest.json").write_text(json.dumps(bt, indent=1, ensure_ascii=False))
            print(f"this season under the same rules: {bt['summary']['won']} won of {bt['summary']['picks']}")
    else:
        print("Upset Pick:", why)
    results = {(lg, m["id"]): m for lg, ms in data["leagues"].items() for m in ms}
    for e in log:
        if e.get("status") == "pending":
            m = results.get((e["league"], e["match_id"]))
            if m and m["status"] == "FINISHED" and m["hg"] is not None:
                e["status"] = "won" if won(e, m["hg"], m["ag"]) else "lost"
                e["score"] = f"{m['hg']}-{m['ag']}"; e["settled_at"] = iso
            elif m and m["status"] in ("POSTPONED", "CANCELLED"):
                e["status"] = "void"
    log.sort(key=lambda e: e["date"])
    (D / "potd.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    (D / "potd_preview.json").write_text(json.dumps(preview, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
