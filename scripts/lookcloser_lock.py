"""Save the Look closer assessment of every upcoming clear-favourite game BEFORE kick-off.

Why a browser: the assessment (risk check, match-up, verdict, underdog facts) lives in index.html. Running the
page's own code headless guarantees the saved list is exactly what the site shows, with no second copy of the
logic to drift apart.

Each run (every 6 hours, from update.yml):
 - opens the site from this repo in headless Chromium and reads mdpLookCloserList(day, true) for today,
   tomorrow and the day after (SAST), upcoming games only;
 - saves or refreshes each game's assessment while kick-off is more than LOCK_BEFORE away;
 - after that the entry is final and never changed (the last assessment before kick-off is kept);
 - settles finished games from data/matches.json (did the favourite win?).
Output: data/lookcloser.json. Every clear-favourite game is saved, not only the listed ones (score >= 4),
so listed and unlisted favourites can be compared later.
"""
import json, os, sys, threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "lookcloser.json"
SAST = ZoneInfo("Africa/Johannesburg")
LOCK_BEFORE = timedelta(minutes=30)
MIN_SCORE = 4


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def read_page(port, days):
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("CHROME_PATH") or None
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        pg = b.new_page()
        # only the local site: no crests, fonts or other outside requests
        pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith(f"http://127.0.0.1:{port}") else r.abort())
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/index.html")
        pg.wait_for_function("() => window.MDP_LIVE && MDP_LIVE.loaded && typeof mdpLookCloserList === 'function'", timeout=90000)
        rows = pg.evaluate("""(days) => {var out=[];days.forEach(function(d){mdpLookCloserList(d,true).forEach(function(x){
            if(x.t!=='u')return;
            out.push({lg:x.k,id:x.id,utc:x.utc,home_name:x.hn,away_name:x.an,fav_name:x.fn,dog_name:x.dn,
                      fav_side:(x.fn===x.hn?'home':'away'),fp:x.fp,dp:x.dp,d:x.d,s:x.s,why:x.why})})});return out}""", days)
        b.close()
    if errors:
        print("page errors:", errors[:3])
    return rows


def main(now=None):
    now = now or datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    log = {f"{e['lg']}:{e['id']}": e for e in old.get("log", [])}
    local = now.astimezone(SAST).date()
    days = [(local + timedelta(days=i)).isoformat() for i in range(3)]
    srv = serve()
    try:
        rows = read_page(srv.server_address[1], days)
    finally:
        srv.shutdown()
    saved = 0
    for x in rows:
        key = f"{x['lg']}:{x['id']}"
        ko = datetime.fromisoformat(x["utc"].replace("Z", "+00:00"))
        e = log.get(key)
        if e and e.get("final"):
            continue
        if ko - now <= LOCK_BEFORE:          # too close to kick-off: keep the last saved assessment
            if e:
                e["final"] = True
            continue
        log[key] = dict(x, assessed_at=iso, final=False)
        saved += 1
    # finalise anything whose kick-off is near or past, then settle from results
    res = {}
    for lg, ms in json.loads((D / "matches.json").read_text()).get("leagues", {}).items():
        for m in ms:
            res[f"{lg}:{m['id']}"] = m
    for key, e in log.items():
        ko = datetime.fromisoformat(e["utc"].replace("Z", "+00:00"))
        if not e.get("final") and ko - now <= LOCK_BEFORE:
            e["final"] = True
        m = res.get(key)
        if m and m.get("status") == "FINISHED" and m.get("hg") is not None and "res" not in e:
            hg, ag = m["hg"], m["ag"]
            e["res"] = "home" if hg > ag else "away" if ag > hg else "draw"
            e["fav_won"] = e["res"] == e["fav_side"]
            e["score"] = f"{hg}–{ag}"
        elif m and m.get("status") in ("POSTPONED", "CANCELLED"):
            e["void"] = True
    entries = sorted(log.values(), key=lambda e: e["utc"])
    OUT.write_text(json.dumps({"updated": iso, "rules": {"min_score": MIN_SCORE, "lock_before_minutes": 30},
                               "log": entries}, indent=1, ensure_ascii=False))
    listed = [e for e in entries if e["s"] >= MIN_SCORE and "fav_won" in e]
    print(f"Look closer: {saved} assessments saved or refreshed; {len(entries)} games on file; "
          f"listed favourites settled: {sum(e['fav_won'] for e in listed)} won of {len(listed)}")


if __name__ == "__main__":
    main()
