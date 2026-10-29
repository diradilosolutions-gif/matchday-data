"""Calculate EVERY prediction once and save it to data/predictions.json.
The website and the pick log both read this file, so they can never disagree.

Each prediction only uses games played BEFORE that match, so the recent results
shown on the site are honest back-tests, not hindsight."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import finished, predict, N_FORM, MODEL_VERSION

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


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = D / "matches.json"
    if not path.exists():
        sys.exit("data/matches.json not found; run fetch_data.py first")
    data = json.loads(path.read_text())
    out = {"updated": iso(now),
           "model": {"name": "Poisson goals model from each team's last %d games" % N_FORM,
                     "version": MODEL_VERSION, "form_games": N_FORM},
           "leagues": {}}
    for lg, ms in data["leagues"].items():
        fin = finished(ms)
        if len(fin) < 20:
            print(f"{lg}: not enough finished games yet ({len(fin)})")
            continue
        avg = {"home": round(sum(m["hg"] for m in fin) / len(fin), 2),
               "away": round(sum(m["ag"] for m in fin) / len(fin), 2)}
        matches = {}
        for m in sorted(fin, key=lambda m: m["utc"])[-BACK:]:
            p = predict(fin, m["home"], m["away"], m["utc"])
            if p:
                matches[str(m["id"])] = pack(p)
        for m in ms:
            if m["status"] not in ("SCHEDULED", "TIMED"):
                continue
            ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
            if not (now - timedelta(hours=2) <= ko <= now + WINDOW):
                continue
            p = predict(fin, m["home"], m["away"], m["utc"])
            if p:
                matches[str(m["id"])] = pack(p)
        out["leagues"][lg] = {"avg": avg, "matches": matches}
        print(f"{lg}: {len(matches)} predictions")
    (D / "predictions.json").write_text(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main()
