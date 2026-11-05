"""Download fixtures/results for every competition your football-data.org token can read
into data/matches.json. Needs the env var FOOTBALL_DATA_TOKEN.

The free plan has 12 competitions. Rather than hard-coding them, the script first asks
football-data.org which competitions the token covers, so nothing is missed if the list changes."""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.football-data.org/v4"
# football-data.org code -> our short league key (keys the site already uses are kept)
KEYS = {"PL": "epl", "PD": "laliga", "SA": "seriea", "BL1": "bundesliga", "FL1": "ligue1",
        "ELC": "champ", "DED": "nl", "PPL": "ppl", "BSA": "bsa", "CL": "ucl",
        "EC": "euro", "WC": "wc", "CLI": "cli"}
NAMES = {"epl": "Premier League", "laliga": "La Liga", "seriea": "Serie A", "bundesliga": "Bundesliga",
         "ligue1": "Ligue 1", "champ": "Championship", "nl": "Eredivisie", "ppl": "Primeira Liga",
         "bsa": "Brasileirão Série A", "ucl": "Champions League", "euro": "European Championship",
         "wc": "World Cup", "cli": "Copa Libertadores"}
FREE_FALLBACK = ["PL", "ELC", "PD", "SA", "BL1", "FL1", "DED", "PPL", "BSA", "CL", "EC", "WC"]
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
    if not (m.get("homeTeam") or {}).get("id") or not (m.get("awayTeam") or {}).get("id"):
        return None   # knockout tie where the teams are not known yet
    sc = m.get("score") or {}
    ft = sc.get("fullTime") or {}
    dur = sc.get("duration") or "REGULAR"
    # Cup games can go to extra time or penalties. Betting markets (and the model) are about
    # the 90 minutes, so use the regular-time score when the API gives it.
    reg = sc.get("regularTime") if dur != "REGULAR" else None
    hg, ag = (reg.get("home"), reg.get("away")) if reg and reg.get("home") is not None else (ft.get("home"), ft.get("away"))
    out = {"id": m["id"], "utc": m["utcDate"], "status": m["status"],
           "home": m["homeTeam"].get("shortName") or m["homeTeam"].get("name") or "TBC",
           "away": m["awayTeam"].get("shortName") or m["awayTeam"].get("name") or "TBC",
           "hg": hg, "ag": ag,
           # club crest image links (the page shows these instead of embedded logos)
           "hc": m["homeTeam"].get("crest"), "ac": m["awayTeam"].get("crest")}
    if dur != "REGULAR":
        out["dur"] = dur                         # EXTRA_TIME or PENALTY_SHOOTOUT
        out["winner"] = sc.get("winner")         # HOME_TEAM / AWAY_TEAM after extra time or pens
    if m.get("stage") and m["stage"] != "REGULAR_SEASON":
        out["stage"] = m["stage"]
    return out


def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit("Missing FOOTBALL_DATA_TOKEN")
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    leagues = dict(old.get("leagues", {}))   # keep old data for any league that fails today
    names = dict(old.get("names", {}))
    try:
        comps = get(f"{BASE}/competitions", token)["competitions"]
        codes = [(c["code"], c["name"]) for c in comps if c.get("code")]
        print("token covers:", ", ".join(c for c, _ in codes))
    except Exception as e:
        print(f"could not list competitions ({e}); using the known free list")
        codes = [(c, None) for c in FREE_FALLBACK]
    time.sleep(7)
    for code, api_name in codes:
        key = KEYS.get(code, code.lower())
        try:
            data = get(f"{BASE}/competitions/{code}/matches", token)
            ms = [x for x in (norm(m) for m in data["matches"]) if x]
            if not ms:
                print(f"{key}: no matches returned; keeping previous data")
            else:
                leagues[key] = ms
                names[key] = NAMES.get(key) or api_name or code
                print(f"{key}: {len(ms)} matches")
        except Exception as e:
            print(f"{key}: FAILED ({e}); keeping previous data")
        time.sleep(7)  # free plan allows 10 requests/minute
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(),
                               "names": names, "leagues": leagues}, separators=(",", ":")))


if __name__ == "__main__":
    main()
