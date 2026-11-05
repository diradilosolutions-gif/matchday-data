"""Goals models used by the site, the pick log and the back-test.

v1  Poisson from each team's last N games (the original model).
v2  Team ratings model (Dixon-Coles style):
      * every team gets an attack and a defence rating, adjusted for WHO they played
        (scoring 2 against the leaders counts for more than 2 against the bottom side);
      * separate league-wide home and away scoring rates, so home advantage is built in;
      * recent games count more (games lose half their weight every HALF_LIFE days);
      * ratings are pulled towards average when a team has few games;
      * a small correction for 0-0, 1-0, 0-1 and 1-1, which plain Poisson gets wrong
        (it under-predicts draws).

Which model the site uses is decided by data/model_choice.json, which the back-test
workflow writes after testing both on past seasons. With no file, v1 is used.
"""
import json, math
from datetime import datetime
from pathlib import Path

MODEL_VERSION = 1   # default when data/model_choice.json does not exist
N_FORM = 10         # v1: games of form used per team
MIN_GAMES = 5       # need at least this many finished games per team
SHRINK = 3          # v1: pseudo-games pulling a team towards league average

V2_DEFAULTS = {"half_life": 180, "rho": -0.08, "prior": 4.0, "window_days": 400}
CHOICE_FILE = Path(__file__).resolve().parent.parent / "data" / "model_choice.json"


def load_choice():
    """Return the model settings the back-test picked, or v1 if it has not run yet."""
    try:
        c = json.loads(CHOICE_FILE.read_text())
        if c.get("version") == 2:
            return {"version": 2, **{k: c.get(k, v) for k, v in V2_DEFAULTS.items()}}
    except (OSError, ValueError):
        pass
    return {"version": 1}


def describe(choice):
    if choice.get("version") == 2:
        return {"name": "Team ratings model (attack/defence adjusted for opponents, home and away, "
                        "recent games weighted, half-life %d days)" % choice["half_life"],
                "short": "team ratings v2", "version": 2,
                "half_life": choice["half_life"], "rho": choice["rho"]}
    return {"name": "Poisson goals model from each team's last %d games" % N_FORM,
            "short": "last %d games" % N_FORM, "version": 1, "form_games": N_FORM}


def pmf(lam, n):
    p = [math.exp(-lam)]
    for i in range(1, n + 1):
        p.append(p[-1] * lam / i)
    return p


def finished(ms):
    return [m for m in ms if m["status"] == "FINISHED" and m["hg"] is not None]


def _ts(utc):
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).timestamp()


def markets(lam_h, lam_a, rho=0.0):
    """Turn expected goals into home/draw/away and goal-market probabilities."""
    A, B = pmf(lam_h, 10), pmf(lam_a, 10)
    ph = pd = pa = o15 = o25 = btts = h_by2 = a_by2 = 0.0
    for i in range(11):
        for j in range(11):
            p = A[i] * B[j]
            if rho and i <= 1 and j <= 1:   # Dixon-Coles low-score correction
                p *= (1 - lam_h * lam_a * rho if i == 0 and j == 0 else
                      1 + lam_h * rho if i == 0 and j == 1 else
                      1 + lam_a * rho if i == 1 and j == 0 else 1 - rho)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
            if i + j >= 2: o15 += p
            if i + j >= 3: o25 += p
            if i > 0 and j > 0: btts += p
            if i - j >= 2: h_by2 += p      # home wins by 2+
            if j - i >= 2: a_by2 += p      # away wins by 2+
    tot = ph + pd + pa
    ph, pd, pa, o15, o25, btts, h_by2, a_by2 = [x / tot for x in (ph, pd, pa, o15, o25, btts, h_by2, a_by2)]
    home_fav = ph >= pa
    return {"lam_h": lam_h, "lam_a": lam_a, "home": ph, "draw": pd, "away": pa,
            "over15": o15, "over25": o25, "btts": btts,
            "fav": "home" if home_fav else "away",
            # underdog +1.5 covers unless the favourite wins by 2+ goals
            "dog15": 1 - (h_by2 if home_fav else a_by2)}


# ---------------------------------------------------------------- v1
def form(fin, team, before_utc=None):
    games = [m for m in fin if team in (m["home"], m["away"])
             and (before_utc is None or m["utc"] < before_utc)]
    games.sort(key=lambda m: m["utc"])
    games = games[-N_FORM:]
    gf = sum(m["hg"] if m["home"] == team else m["ag"] for m in games)
    ga = sum(m["ag"] if m["home"] == team else m["hg"] for m in games)
    return gf, ga, len(games)


def predict_v1(fin, home, away, before_utc=None):
    pool = [m for m in fin if before_utc is None or m["utc"] < before_utc]
    if len(pool) < 20:
        return None
    lg_h = sum(m["hg"] for m in pool) / len(pool)
    lg_a = sum(m["ag"] for m in pool) / len(pool)
    g = (lg_h + lg_a) / 2
    s = {}
    for t in (home, away):
        gf, ga, n = form(pool, t, before_utc)
        if n < MIN_GAMES:
            return None
        s[t] = ((gf + SHRINK * g) / (n + SHRINK) / g, (ga + SHRINK * g) / (n + SHRINK) / g)
    return markets(lg_h * s[home][0] * s[away][1], lg_a * s[away][0] * s[home][1])


# ---------------------------------------------------------------- v2
_FIT_CACHE = {}


def fit_v2(fin, before_utc=None, half_life=180, prior=4.0, window_days=400):
    """Fit attack/defence ratings from games before `before_utc`. Cached per kick-off time."""
    key = (id(fin), len(fin), before_utc, half_life, prior, window_days)
    if key in _FIT_CACHE:
        return _FIT_CACHE[key]
    now = _ts(before_utc) if before_utc else max(_ts(m["utc"]) for m in fin) + 1
    games, counts = [], {}
    for m in fin:
        if before_utc is not None and m["utc"] >= before_utc:
            continue
        age = (now - _ts(m["utc"])) / 86400
        if age > window_days:
            continue
        games.append((m["home"], m["away"], m["hg"], m["ag"], 0.5 ** (age / half_life)))
        counts[m["home"]] = counts.get(m["home"], 0) + 1
        counts[m["away"]] = counts.get(m["away"], 0) + 1
    if len(games) < 20:
        _FIT_CACHE[key] = None
        return None
    W = sum(g[4] for g in games)
    mu_h = sum(g[2] * g[4] for g in games) / W   # league home scoring rate
    mu_a = sum(g[3] * g[4] for g in games) / W   # league away scoring rate
    teams = list(counts)
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    for _ in range(25):
        gs = {t: prior for t in teams}; es = {t: prior for t in teams}
        for h, a, hg, ag, w in games:
            gs[h] += w * hg; es[h] += w * mu_h * dfn[a]
            gs[a] += w * ag; es[a] += w * mu_a * dfn[h]
        att = {t: gs[t] / es[t] for t in teams}
        gc = {t: prior for t in teams}; ec = {t: prior for t in teams}
        for h, a, hg, ag, w in games:
            gc[h] += w * ag; ec[h] += w * mu_a * att[a]
            gc[a] += w * hg; ec[a] += w * mu_h * att[h]
        dfn = {t: gc[t] / ec[t] for t in teams}
        # keep the average team at exactly 1.0 so mu_h / mu_a stay the league rates
        la = math.exp(sum(math.log(att[t]) for t in teams) / len(teams))
        ld = math.exp(sum(math.log(dfn[t]) for t in teams) / len(teams))
        att = {t: v / la for t, v in att.items()}
        dfn = {t: v / ld for t, v in dfn.items()}
    fit = {"mu_h": mu_h, "mu_a": mu_a, "att": att, "def": dfn, "n": counts}
    _FIT_CACHE[key] = fit
    if len(_FIT_CACHE) > 5000:
        _FIT_CACHE.clear()
    return fit


def predict_v2(fin, home, away, before_utc=None, half_life=180, rho=-0.08, prior=4.0, window_days=400):
    f = fit_v2(fin, before_utc, half_life, prior, window_days)
    if not f or f["n"].get(home, 0) < MIN_GAMES or f["n"].get(away, 0) < MIN_GAMES:
        return None
    lam_h = f["mu_h"] * f["att"][home] * f["def"][away]
    lam_a = f["mu_a"] * f["att"][away] * f["def"][home]
    return markets(lam_h, lam_a, rho)


# ---------------------------------------------------------------- the one everyone calls
def predict(fin, home, away, before_utc=None, choice=None):
    """Return dict of probabilities, or None if not enough data."""
    c = choice or load_choice()
    if c.get("version") == 2:
        return predict_v2(fin, home, away, before_utc, c["half_life"], c["rho"], c["prior"], c["window_days"])
    return predict_v1(fin, home, away, before_utc)
