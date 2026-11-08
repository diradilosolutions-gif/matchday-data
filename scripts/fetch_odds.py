"""Bookmaker odds from football-data.co.uk (display only - never used by the model).

What it does
  * fixtures.csv  -> odds for upcoming games (the site collects them on Friday
    afternoon for weekend games and Tuesday afternoon for midweek games).
  * mmz4281/<season>/<div>.csv -> the same pre-match odds plus CLOSING odds
    (the last price before kick-off) once a game has been played.
  * Each row is matched to our own match id (data/matches.json) by league,
    date (+/- 1 day) and team-name similarity.
  * Writes data/odds.json. Pre-match odds are only updated before kick-off, so
    what the page shows as "pre-match" is never changed after the game starts.

football-data.co.uk terms: for private individuals only, not for commercial
products. Switch to a licensed odds feed before the site is sold or made public.
"""
import csv, datetime as dt, difflib, io, json, os, re, sys, time, unicodedata, urllib.request

BASE = "https://www.football-data.co.uk/"
DIVS = {"E0": "epl", "E1": "champ", "SP1": "laliga", "I1": "seriea",
        "D1": "bundesliga", "F1": "ligue1", "N1": "nl", "P1": "ppl"}
OUT = "data/odds.json"
UA = {"User-Agent": "matchday-predictor (private, non-commercial; 4 requests every 6 hours)"}

# football-data.co.uk short names -> words that appear in the football-data.org name
ALIAS = {
    "man united": "manchester united", "man city": "manchester city", "nott'm forest": "nottingham forest",
    "wolves": "wolverhampton wanderers", "sheffield weds": "sheffield wednesday", "sheffield utd": "sheffield united",
    "qpr": "queens park rangers", "west brom": "west bromwich albion", "spurs": "tottenham",
    "ath madrid": "atletico madrid", "ath bilbao": "athletic club", "sociedad": "real sociedad", "betis": "real betis",
    "espanol": "espanyol", "vallecano": "rayo vallecano", "celta": "celta vigo", "alaves": "deportivo alaves",
    "la coruna": "deportivo la coruna", "sp gijon": "sporting gijon",
    "inter": "internazionale", "milan": "ac milan", "roma": "as roma", "verona": "hellas verona",
    "bayern munich": "bayern munchen", "dortmund": "borussia dortmund", "m'gladbach": "monchengladbach",
    "ein frankfurt": "eintracht frankfurt", "fc koln": "koln", "leverkusen": "bayer leverkusen",
    "hertha": "hertha berlin", "st pauli": "st. pauli", "hamburg": "hamburger",
    "paris sg": "paris saint germain", "st etienne": "saint etienne",
    "for sittard": "fortuna sittard", "nijmegen": "nec", "psv eindhoven": "psv", "go ahead eagles": "go ahead",
    "sp lisbon": "sporting", "sp braga": "braga", "guimaraes": "vitoria", "estrela": "estrela amadora",
    "famalicao": "famalicao", "porto": "fc porto", "benfica": "benfica",
}
NOISE = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "sv", "vfl", "vfb", "tsg", "fk", "ud", "cd", "rc",
         "rcd", "sd", "ca", "club", "de", "del", "la", "le", "the", "1", "04", "05", "1899", "1846", "1907",
         "1909", "1910", "1913", "1919", "and", "&", "calcio", "olympique", "stade", "hove"}


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("-", " ").replace(".", " ")
    return [t for t in re.split(r"[^a-z0-9']+", s) if t and t not in NOISE]


def sim(ours, theirs):
    """0..1: how well a football-data.co.uk team name fits one of our names."""
    t = ALIAS.get(theirs.lower().strip(), theirs)
    a, b = norm(ours), norm(t)
    if not a or not b:
        return 0.0
    def best(tok, pool):
        sc = 0.0
        for p in pool:
            if tok == p:
                return 1.0
            if len(tok) >= 3 and len(p) >= 3 and (p.startswith(tok) or tok.startswith(p)):
                sc = max(sc, 0.85)
            else:
                r = difflib.SequenceMatcher(None, tok, p).ratio()
                if r >= 0.8:
                    sc = max(sc, r * 0.9)
        return sc
    fwd = sum(best(x, a) for x in b) / len(b)          # their words found in our name
    back = sum(best(x, b) for x in a) / len(a)         # our words found in theirs
    return 0.7 * fwd + 0.3 * back


def fnum(x):
    try:
        v = float(x)
        return round(v, 2) if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def get_csv(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.DictReader(io.StringIO(txt)))
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows if r]


def row_date(r):
    d = r.get("Date", "")
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(d, f).date()
        except ValueError:
            pass
    return None


def prices(r, closing=False):
    c = "C" if closing else ""
    o = {"h": fnum(r.get(f"Avg{c}H")), "d": fnum(r.get(f"Avg{c}D")), "a": fnum(r.get(f"Avg{c}A")),
         "mh": fnum(r.get(f"Max{c}H")), "md": fnum(r.get(f"Max{c}D")), "ma": fnum(r.get(f"Max{c}A")),
         "o25": fnum(r.get(f"Avg{c}>2.5")), "u25": fnum(r.get(f"Avg{c}<2.5")),
         "mo25": fnum(r.get(f"Max{c}>2.5")), "mu25": fnum(r.get(f"Max{c}<2.5"))}
    if not (o["h"] and o["d"] and o["a"]):
        return None
    return {k: v for k, v in o.items() if v}


def season_code(today):
    y = today.year if today.month >= 7 else today.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def match_rows(rows, fixtures_by_lg, closing_too):
    """Return {match_id: (row, league)} for rows we can place with confidence."""
    found, used = {}, set()
    for r in rows:
        lg = DIVS.get(r.get("Div", ""))
        d = row_date(r)
        if not lg or not d or lg not in fixtures_by_lg:
            continue
        best, bs = None, 0.0
        for m in fixtures_by_lg[lg]:
            md = m["_date"]
            if abs((md - d).days) > 1 or m["id"] in used:
                continue
            sh, sa = sim(m["home"], r.get("HomeTeam", "")), sim(m["away"], r.get("AwayTeam", ""))
            if min(sh, sa) < 0.65:
                continue
            s = sh + sa - 0.05 * abs((md - d).days)
            if s > bs:
                best, bs = m, s
        if best and bs >= 1.5:
            used.add(best["id"])
            found[best["id"]] = (r, lg)
    return found


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        ours = json.load(open("data/matches.json", encoding="utf-8"))
    except Exception as e:
        print("No data/matches.json yet:", e)
        return 0
    fixtures_by_lg = {}
    for lg, ms in (ours.get("leagues") or {}).items():
        if lg not in DIVS.values():
            continue
        L = []
        for m in ms:
            try:
                m = dict(m)
                m["_utc"] = dt.datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
                m["_date"] = m["_utc"].date()
                L.append(m)
            except Exception:
                continue
        fixtures_by_lg[lg] = L
    by_id = {m["id"]: m for L in fixtures_by_lg.values() for m in L}

    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {}
    store = old.get("matches", {}) if isinstance(old, dict) else {}
    problems, got_up, got_close = [], 0, 0

    # 1) upcoming games
    try:
        rows = get_csv(BASE + "fixtures.csv")
        for mid, (r, lg) in match_rows(rows, fixtures_by_lg, False).items():
            m = by_id[mid]
            p = prices(r)
            if not p or m["_utc"] <= now:            # never change pre-match odds after kick-off
                continue
            e = store.setdefault(str(mid), {"lg": lg})
            p["seen"] = now.strftime("%Y-%m-%dT%H:%MZ")
            e["pre"] = p
            got_up += 1
    except Exception as e:
        problems.append(f"fixtures.csv: {e}")

    # 2) played games: closing odds (and pre-match odds if we never saw the game in fixtures.csv)
    sc = season_code(now.date())
    divs_needed = [d for d, lg in DIVS.items() if lg in fixtures_by_lg]
    for div in divs_needed:
        try:
            time.sleep(1)
            rows = get_csv(f"{BASE}mmz4281/{sc}/{div}.csv")
            for mid, (r, lg) in match_rows(rows, fixtures_by_lg, True).items():
                e = store.setdefault(str(mid), {"lg": lg})
                c = prices(r, closing=True)
                if c:
                    e["close"] = c
                    got_close += 1
                if "pre" not in e:
                    p = prices(r)
                    if p:
                        p["seen"] = "season file (early-week price)"
                        e["pre"] = p
        except Exception as ex:
            problems.append(f"{div}.csv: {ex}")

    out = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "football-data.co.uk - average and best prices across bookmakers. Private, non-commercial use only.",
           "problems": problems, "matches": store}
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    print(f"odds: {got_up} upcoming games priced, {got_close} played games with closing odds, "
          f"{len(store)} games stored. Problems: {problems or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
