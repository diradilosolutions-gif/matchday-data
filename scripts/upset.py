"""Upset signals: things that might make an underdog more dangerous than the model thinks.

Used by BOTH the back-test (scripts/upset_backtest.py, past seasons) and the live
Upset Pick of the Day (scripts/pick_of_day.py), so a signal means exactly the same thing in both.
Every signal only looks at games played BEFORE the kick-off being judged.

A signal is only trusted when the back-test shows that, in past games where it was present,
underdogs did clearly better than the model expected. Signals that do not prove themselves
are ignored, however convincing they sound.
"""
import math
from datetime import datetime

SEASON_DAYS = 300        # "this season" = the last 300 days (works for Aug-May and Jan-Dec leagues)
MIN_VENUE = 5
FAV_GAP = 6.0            # a clear favourite: at least 6 points more likely to win than the underdog

NAMES = {
    "dog_unbeaten_venue": "Underdog unbeaten at this venue (5+ games)",
    "dog_strong_venue": "Underdog strong at this venue (well above the league norm)",
    "dog_giant_killer": "Underdog has won more games as an underdog than the model expected",
    "dog_h2h": "Underdog already beat or drew with this favourite this season",
    "dog_in_form": "Underdog unbeaten in their last 6 (1.8+ points a game)",
    "fav_form_dip": "Favourite's form has dipped well below their season average",
    "fav_poor_venue": "Favourite's record at this venue is well below the league norm",
    "fav_leaky": "Favourite conceding well above the league average lately",
    "fav_short_rest": "Favourite had at least 2 days' less rest",
}
MARKETS = {"dog_win": "to win", "dog_dc": "win or draw", "dog_h15": "+1.5 handicap"}


def ts(utc):
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).timestamp()


class History:
    """Walk through games in kick-off order; ask for signals before adding each result."""

    def __init__(self):
        self.team = {}      # team -> list of dicts (oldest first)
        self.games = []     # (t, home_win, away_win, goals) for league norms
        self.und = []       # (t, model chance, won) for every underdog so far: the model's general bias

    def norms(self, t):
        g = [x for x in self.games if t - x[0] <= 365 * 86400]
        if len(g) < 30:
            return {"home": .45, "away": .29, "gpt": 1.35}
        n = len(g)
        return {"home": sum(x[1] for x in g) / n, "away": sum(x[2] for x in g) / n,
                "gpt": sum(x[3] for x in g) / n / 2}

    def recent(self, team, t):
        return [x for x in self.team.get(team, []) if 0 < t - x["t"] <= SEASON_DAYS * 86400]

    def add(self, utc, home, away, hg, ag, p_home=None, p_away=None):
        t = ts(utc)
        for me, opp, gf, ga, hm, pw in ((home, away, hg, ag, True, p_home), (away, home, ag, hg, False, p_away)):
            self.team.setdefault(me, []).append({"t": t, "opp": opp, "gf": gf, "ga": ga, "home": hm, "pw": pw})
        self.games.append((t, hg > ag, ag > hg, hg + ag))
        if p_home is not None and p_away is not None and abs(p_home - p_away) >= FAV_GAP / 100:
            dh = p_home < p_away
            self.und.append((t, p_home if dh else p_away, (hg > ag) if dh else (ag > hg)))

    def bias(self, t):
        """How much more often underdogs have won than the model said (recent 2 years)."""
        u = [x for x in self.und if t - x[0] <= 730 * 86400]
        return (sum(x[2] for x in u) - sum(x[1] for x in u)) / len(u) if len(u) >= 50 else 0.0

    def played(self, team, t):
        return len(self.recent(team, t))


def _pts(g):
    return 3 if g["gf"] > g["ga"] else 1 if g["gf"] == g["ga"] else 0


def signals(H, utc, home, away, p_home, p_away):
    """Return (dog_is_home, {signal: True/False}) or (None, None) if there is no clear favourite."""
    if abs(p_home - p_away) < FAV_GAP / 100:
        return None, None
    t = ts(utc)
    dog_home = p_home < p_away
    dog, fav = (home, away) if dog_home else (away, home)
    N = H.norms(t)
    hd, hf = H.recent(dog, t), H.recent(fav, t)
    s = {}
    # underdog at this venue
    dv = [g for g in hd if g["home"] == dog_home]
    dbase = N["home"] if dog_home else N["away"]
    if len(dv) >= MIN_VENUE:
        w = sum(g["gf"] > g["ga"] for g in dv); l = sum(g["gf"] < g["ga"] for g in dv)
        s["dog_unbeaten_venue"] = l == 0
        s["dog_strong_venue"] = l > 0 and (w / len(dv) >= dbase + .2 or l / len(dv) <= .15)
    else:
        s["dog_unbeaten_venue"] = s["dog_strong_venue"] = False
    # underdog's record as an underdog (needs the model's chance for their earlier games)
    # (compared with the model's general bias, so a model that underrates ALL underdogs
    #  does not make every team look like a giant-killer)
    #  Uses the last two seasons: one season has too few underdog games to separate skill from luck.
    und = [g for g in H.team.get(dog, []) if 0 < t - g["t"] <= 730 * 86400 and g["pw"] is not None and g["pw"] <= .4]
    wins = sum(g["gf"] > g["ga"] for g in und); exp = sum(g["pw"] for g in und) + H.bias(t) * len(und)
    s["dog_giant_killer"] = len(und) >= 10 and (wins - exp) / len(und) >= .10
    # head to head this season
    s["dog_h2h"] = any(g["opp"] == fav and g["gf"] >= g["ga"] for g in hd)
    # underdog form
    d6 = hd[-6:]
    s["dog_in_form"] = len(d6) >= 5 and all(g["gf"] >= g["ga"] for g in d6) and sum(map(_pts, d6)) / len(d6) >= 1.8
    # favourite weaknesses
    f6 = hf[-6:]
    sp = sum(map(_pts, hf)) / len(hf) if hf else 0
    rp = sum(map(_pts, f6)) / len(f6) if f6 else 0
    s["fav_form_dip"] = len(f6) >= 5 and len(hf) >= 10 and rp <= sp - .7 and rp < 1.2
    fv = [g for g in hf if g["home"] == (not dog_home)]
    fbase = N["away"] if dog_home else N["home"]
    s["fav_poor_venue"] = len(fv) >= MIN_VENUE and sum(g["gf"] > g["ga"] for g in fv) / len(fv) <= fbase - .2
    gc = sum(g["ga"] for g in f6) / len(f6) if f6 else 0
    s["fav_leaky"] = len(f6) >= 5 and gc >= 1.5 and gc >= N["gpt"] * 1.35
    rf = (t - hf[-1]["t"]) / 86400 if hf else None
    rd = (t - hd[-1]["t"]) / 86400 if hd else None
    s["fav_short_rest"] = rf is not None and rd is not None and rf <= 3.5 and rd - rf >= 2
    return dog_home, s


def dog_markets(p, dog_home):
    """Model chances for the underdog markets, from a model.predict() result."""
    pw = p["home"] if dog_home else p["away"]
    return {"dog_win": pw, "dog_dc": pw + p["draw"], "dog_h15": p["dog15"]}


def dog_hits(dog_home, hg, ag):
    dg, fg = (hg, ag) if dog_home else (ag, hg)
    return {"dog_win": dg > fg, "dog_dc": dg >= fg, "dog_h15": fg - dg < 2}


def zscore(hits, probs):
    var = sum(p * (1 - p) for p in probs)
    return (sum(hits) - sum(probs)) / math.sqrt(var) if var > 0 else 0.0
