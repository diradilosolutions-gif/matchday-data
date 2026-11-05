"""Calculate EVERY prediction once and save it to data/predictions.json.
The website and the pick log both read this file, so they can never disagree.

Each prediction only uses games played BEFORE that match, so the recent results
shown on the site are honest back-tests, not hindsight."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import finished, predict, load_choice, describe

D = Path(__file__).resolve().parent.parent / "data"
WINDOW = timedelta(days=10)   # upcoming fixtures shown on the site
BACK = 60                     # recent results re-predicted for the site's Results tab


def pct(x):
    return round(x * 100, 1)


def pack(p):
    return {"h": pct(p["home"]), "d": pct(p["draw"]), "a": pct(p["away"]),
            "lh": round(p["lam_h"], 2), "la": round(p["lam_a"], 2),
            "o15": pct(p["over15"]), "o25": pct(p["over25"]), "btts": pct(p["btts"]),
            "dog15": pct(p["dog15"]), "fav": p["fav"]}


def news_for(news, cover, lg, m, now):
    """Injury/suspension news for one match, from data/team_news.json (or None)."""
    T = (news.get("teams") or {}).get(lg, {})
    ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))

    def ok(i):
        if i.get("fx"):   # API-Football news belongs to one fixture date
            return abs((datetime.fromisoformat(i["fx"]).date() - ko.date()).days) <= 1
        return ko - now <= timedelta(days=8)   # FPL / manual notes describe the current situation

    def side(team):
        x = T.get(team) or {}
        o, d = [i for i in x.get("out", []) if ok(i)], [i for i in x.get("doubt", []) if ok(i)]
        return {"out": o, "doubt": d} if o or d else None
    h, a = side(m["home"]), side(m["away"])
    if not h and not a and not cover.get(lg):
        return None
    return {"h": h, "a": a, "cover": cover.get(lg, []), "upd": news.get("updated")}


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = D / "matches.json"
    if not path.exists():
        sys.exit("data/matches.json not found; run fetch_data.py first")
    data = json.loads(path.read_text())
    choice = load_choice()   # written by the back-test workflow; v1 until it has run
    desc = describe(choice)
    print("model:", desc["name"])
    # The archive keeps the last prediction published BEFORE each kick-off. Once a game has
    # started its entry is never touched again, so the site can show exactly what was predicted.
    arch_path = D / "predictions_archive.json"
    arch = json.loads(arch_path.read_text()) if arch_path.exists() else {}
    out = {"updated": iso(now), "model": desc, "leagues": {}}
    try:   # per-league reliability from the back-test, shown on the site
        out["model"]["league_reliability"] = json.loads((D / "model_choice.json").read_text()).get("league_reliability", {})
    except (OSError, ValueError):
        pass
    # team news: shown on the site, saved and locked at kick-off like the predictions
    news = json.loads((D / "team_news.json").read_text()) if (D / "team_news.json").exists() else {}
    src = news.get("sources") or {}
    cover = {}
    for lg in data["leagues"]:
        c = []
        if lg == "epl" and (src.get("fpl") or {}).get("ok"):
            c.append("Fantasy Premier League")
        elif lg != "epl" and (src.get("api_football") or {}).get("ok"):
            c.append("API-Football")
        cover[lg] = c
    out["news_sources"] = {k: {kk: vv for kk, vv in v.items() if kk != "entries"} for k, v in src.items()}
    news_path = D / "news_archive.json"
    narch = json.loads(news_path.read_text()) if news_path.exists() else {}
    locked = rebuilt = 0
    for lg, ms in data["leagues"].items():
        A = arch.setdefault(lg, {})
        fin = finished(ms)
        enough = len(fin) >= 20
        matches = {}
        if enough:
            for m in ms:
                if m["status"] not in ("SCHEDULED", "TIMED"):
                    continue
                ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
                if not (now - timedelta(hours=2) <= ko <= now + WINDOW):
                    continue
                p = predict(fin, m["home"], m["away"], m["utc"], choice)
                if not p:
                    continue
                pk = pack(p)
                matches[str(m["id"])] = pk
                if now < ko:   # still before kick-off: this becomes the saved pre-match prediction
                    prev = A.get(str(m["id"]), {})
                    A[str(m["id"])] = dict(pk, ko=m["utc"], saved=iso(now), model=desc["short"],
                                           first_saved=prev.get("first_saved", iso(now)),
                                           home=m["home"], away=m["away"])
        # Started or finished games: show the locked pre-match prediction if one was saved,
        # otherwise (games from before this feature) a back-test rebuilt from earlier results only.
        recent = {str(m["id"]) for m in sorted(fin, key=lambda m: m["utc"])[-BACK:]}
        for m in ms:
            mid = str(m["id"])
            if mid in matches or m["status"] in ("SCHEDULED", "TIMED"):
                continue
            if mid in A:
                matches[mid] = dict(A[mid], frozen=True); locked += 1
            elif enough and mid in recent and m["status"] == "FINISHED":
                p = predict(fin, m["home"], m["away"], m["utc"], choice)
                if p:
                    matches[mid] = dict(pack(p), frozen=False); rebuilt += 1
        avg = ({"home": round(sum(m["hg"] for m in fin) / len(fin), 2),
                "away": round(sum(m["ag"] for m in fin) / len(fin), 2)} if fin else None)
        NA, NM = narch.setdefault(lg, {}), {}
        for m in ms:
            mid = str(m["id"])
            ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
            if m["status"] in ("SCHEDULED", "TIMED") and now < ko <= now + WINDOW:
                nw = news_for(news, cover, lg, m, now)
                if nw:
                    NA[mid] = dict(nw, saved=iso(now))   # overwritten until kick-off, then locked
                    NM[mid] = NA[mid]
            elif mid in NA and ko >= now - timedelta(days=14):
                NM[mid] = dict(NA[mid], frozen=True)     # team news as it stood before kick-off
        out["leagues"][lg] = {"avg": avg, "matches": matches, "news": NM}
        print(f"{lg}: {len(matches)} predictions" + ("" if enough else f" (only {len(fin)} finished games, too few to predict)"))
    print(f"finished/started games: {locked} locked pre-match predictions, {rebuilt} rebuilt back-tests")
    (D / "predictions.json").write_text(json.dumps(out, separators=(",", ":")))
    arch_path.write_text(json.dumps(arch, separators=(",", ":")))
    news_path.write_text(json.dumps(narch, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
