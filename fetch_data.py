"""Download fixtures/results for each league from football-data.org into data/matches.json.
Needs the env var FOOTBALL_DATA_TOKEN (free token from football-data.org)."""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.football-data.org/v4"
# our league key -> football-data.org code (only leagues on the free plan)
COMPS = {"epl": "PL", "laliga": "PD", "seriea": "SA", "bundesliga": "BL1",
         "ligue1": "FL1", "champ": "ELC", "nl": "DED"}
OUT = Path(__file__).resolve().parent.parent / "data" / "matches.json"


def get(url, token):
    req = urllib.request.Request(url, headers={"X-Auth-Token": token})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                print("  rate limited, waiting 65s"); time.sleep(65); continue
            raise


def norm(m):
    ft = (m.get("score") or {}).get("fullTime") or {}
    return {"id": m["id"], "utc": m["utcDate"], "status": m["status"],
            "home": m["homeTeam"].get("shortName") or m["homeTeam"]["name"],
            "away": m["awayTeam"].get("shortName") or m["awayTeam"]["name"],
            "hg": ft.get("home"), "ag": ft.get("away")}


def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit("Missing FOOTBALL_DATA_TOKEN")
    old = json.loads(OUT.read_text())["leagues"] if OUT.exists() else {}
    leagues = dict(old)  # keep old data for any league that fails today
    for key, code in COMPS.items():
        try:
            data = get(f"{BASE}/competitions/{code}/matches", token)
            leagues[key] = [norm(m) for m in data["matches"]]
            print(f"{key}: {len(leagues[key])} matches")
        except Exception as e:
            print(f"{key}: FAILED ({e}); keeping previous data")
        time.sleep(7)  # free plan allows 10 requests/minute
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(),
                               "leagues": leagues}, separators=(",", ":")))


if __name__ == "__main__":
    main()
