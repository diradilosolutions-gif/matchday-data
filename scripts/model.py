"""Poisson goals model from each team's last N finished games."""
import math

N_FORM = 10      # games of form used per team
MIN_GAMES = 5    # need at least this many finished games per team
SHRINK = 3       # pseudo-games pulling a team towards league average


def pmf(lam, n):
    p = [math.exp(-lam)]
    for i in range(1, n + 1):
        p.append(p[-1] * lam / i)
    return p


def finished(ms):
    return [m for m in ms if m["status"] == "FINISHED" and m["hg"] is not None]


def form(fin, team, before_utc=None):
    games = [m for m in fin if team in (m["home"], m["away"])
             and (before_utc is None or m["utc"] < before_utc)]
    games.sort(key=lambda m: m["utc"])
    games = games[-N_FORM:]
    gf = sum(m["hg"] if m["home"] == team else m["ag"] for m in games)
    ga = sum(m["ag"] if m["home"] == team else m["hg"] for m in games)
    return gf, ga, len(games)


def predict(fin, home, away, before_utc=None):
    """Return dict of probabilities, or None if not enough data."""
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
    lam_h = lg_h * s[home][0] * s[away][1]
    lam_a = lg_a * s[away][0] * s[home][1]
    A, B = pmf(lam_h, 10), pmf(lam_a, 10)
    ph = pd = pa = o15 = o25 = btts = h_by2 = a_by2 = 0.0
    for i in range(11):
        for j in range(11):
            p = A[i] * B[j]
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
