#!/usr/bin/env python3
"""
Live Ticker - a tiny always-on-top sports score crawl, in the spirit of the
ESPN BottomLine and the mid-2000s Yahoo! Sports ticker.

* Shows ONLY games in progress (no finals, no upcoming games, no news).
* Grouped by sport, then ordered by time remaining, least time left first.
* Every Division I college football (FBS + FCS) and college basketball game,
  plus pro and other college sports.
* Polls fast (every few seconds) while games are live.

Pure Python standard library (tkinter + urllib). Run:  python live_ticker.py
Right-click the bar (or click the ⋮ button) for settings.
"""

import gzip
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

APP_NAME = "Live Ticker"
VERSION = "1.0.0"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".live_ticker.json")
API = "https://site.api.espn.com/apis/site/v2/sports"

# --------------------------------------------------------------------------
# Leagues
# --------------------------------------------------------------------------
# Time-remaining models. Every estimate is in *real-world minutes* so games
# from different sports can be sorted against each other.
#   clock:    periods x period length (min), countdown clock. `factor` is real
#             minutes per game-clock minute; `breaks` = {after period: minutes}
#             (halftime / intermissions); `ot` = OT period length (0 = untimed).
#   soccer:   clock counts up; 2 x 45 (+ extra time).
#   baseball: innings, real minutes per half-inning.
#   sets:     best-of-N sets (volleyball), minutes per set.


def clock(periods, plen, ot, factor, breaks):
    return {"kind": "clock", "periods": periods, "plen": plen, "ot": ot,
            "factor": factor, "breaks": breaks}


SOCCER = {"kind": "soccer"}

LEAGUES = [
    # key       label       sport       path                                    groups    model                                            priority college color
    ("ncaaf",  "NCAAF",     "cfb",      "football/college-football",            [80, 81], clock(4, 15, 0, 3.1, {2: 20}),                   True,  True,  "#c8541b"),
    ("ncaam",  "NCAAM",     "cbbm",      "basketball/mens-college-basketball",   [50],     clock(2, 20, 5, 2.6, {1: 15}),                   True,  True,  "#1d5fbf"),
    ("ncaaw",  "NCAAW",     "cbbw",      "basketball/womens-college-basketball", [50],     clock(4, 10, 5, 2.6, {2: 15}),                   True,  True,  "#7b3fb5"),
    ("cbase",  "NCAA BSB",  "cbase",    "baseball/college-baseball",            None,     {"kind": "baseball", "innings": 9, "half": 10},  False, True,  "#1e5a32"),
    ("csoft",  "NCAA SB",   "csoft",    "baseball/college-softball",            None,     {"kind": "baseball", "innings": 7, "half": 7},   False, True,  "#2a7a46"),
    ("mlax",   "NCAAM LAX", "claxm",     "lacrosse/mens-college-lacrosse",       None,     clock(4, 15, 4, 2.0, {2: 10}),                   False, True,  "#5c4a9e"),
    ("wlax",   "NCAAW LAX", "claxw",     "lacrosse/womens-college-lacrosse",     None,     clock(4, 15, 3, 2.0, {2: 10}),                   False, True,  "#7a4a9e"),
    ("mhky",   "NCAAM HKY", "chkym",    "hockey/mens-college-hockey",           None,     clock(3, 20, 5, 2.0, {1: 15, 2: 15}),            False, True,  "#2f6b74"),
    ("nfl",    "NFL",       "pfb",      "football/nfl",                         None,     clock(4, 15, 10, 2.9, {2: 13}),                  False, False, "#0a3a7a"),
    ("cfl",    "CFL",       "pfb",      "football/cfl",                         None,     clock(4, 15, 0, 2.7, {2: 15}),                   False, False, "#b5121b"),
    ("ufl",    "UFL",       "pfb",      "football/ufl",                         None,     clock(4, 15, 0, 2.9, {2: 13}),                   False, False, "#1b3f8f"),
    ("nba",    "NBA",       "pbb",      "basketball/nba",                       None,     clock(4, 12, 5, 2.5, {2: 15}),                   False, False, "#b3122e"),
    ("wnba",   "WNBA",      "pbb",      "basketball/wnba",                      None,     clock(4, 10, 5, 2.6, {2: 15}),                   False, False, "#e06a1b"),
    ("mlb",    "MLB",       "mlb",      "baseball/mlb",                         None,     {"kind": "baseball", "innings": 9, "half": 8.7}, False, False, "#16467f"),
    ("nhl",    "NHL",       "nhl",      "hockey/nhl",                           None,     clock(3, 20, 5, 1.9, {1: 18, 2: 18}),            False, False, "#3a3a3a"),
    ("mls",    "MLS",       "soc",      "soccer/usa.1",                         None,     SOCCER,                                          False, False, "#21613f"),
    ("nwsl",   "NWSL",      "soc",      "soccer/usa.nwsl",                      None,     SOCCER,                                          False, False, "#21613f"),
    ("epl",    "EPL",       "soc",      "soccer/eng.1",                         None,     SOCCER,                                          False, False, "#3d195b"),
    ("laliga", "LALIGA",    "soc",      "soccer/esp.1",                         None,     SOCCER,                                          False, False, "#21613f"),
    ("seriea", "SERIE A",   "soc",      "soccer/ita.1",                         None,     SOCCER,                                          False, False, "#21613f"),
    ("bund",   "BUNDES",    "soc",      "soccer/ger.1",                         None,     SOCCER,                                          False, False, "#21613f"),
    ("ligue1", "LIGUE 1",   "soc",      "soccer/fra.1",                         None,     SOCCER,                                          False, False, "#21613f"),
    ("ucl",    "UCL",       "soc",      "soccer/uefa.champions",                None,     SOCCER,                                          False, False, "#0b2a6b"),
    ("uel",    "UEL",       "soc",      "soccer/uefa.europa",                   None,     SOCCER,                                          False, False, "#0b2a6b"),
    ("ligamx", "LIGA MX",   "soc",      "soccer/mex.1",                         None,     SOCCER,                                          False, False, "#21613f"),
    ("pll",    "PLL",       "plax",     "lacrosse/pll",                         None,     clock(4, 12, 5, 2.2, {2: 10}),                   False, False, "#5c4a9e"),
]

# Sports, in the order they appear in the crawl. College and pro are separate
# sports, and men's and women's college games are separate groups (the group
# name is only shown once, at the start of each group).
SPORTS = [
    ("cfb",   "COLLEGE FOOTBALL"),
    ("cbbm",  "MEN'S COLLEGE BASKETBALL"),
    ("cbbw",  "WOMEN'S COLLEGE BASKETBALL"),
    ("cbase", "COLLEGE BASEBALL"),
    ("csoft", "COLLEGE SOFTBALL"),
    ("claxm", "MEN'S COLLEGE LACROSSE"),
    ("claxw", "WOMEN'S COLLEGE LACROSSE"),
    ("chkym", "MEN'S COLLEGE HOCKEY"),
    ("pfb",   "PRO FOOTBALL"),
    ("pbb",   "PRO BASKETBALL"),
    ("mlb",   "MLB"),
    ("nhl",   "NHL"),
    ("soc",   "SOCCER"),
    ("plax",  "PRO LACROSSE"),
]
SPORT_ORDER = {k: i for i, (k, _) in enumerate(SPORTS)}
SPORT_LABEL = dict(SPORTS)

LEAGUE = {}
for _i, _row in enumerate(LEAGUES):
    _k, _label, _sport, _path, _groups, _model, _prio, _college, _color = _row
    LEAGUE[_k] = {"key": _k, "label": _label, "sport": _sport, "path": _path, "groups": _groups,
                  "model": _model, "priority": _prio, "college": _college,
                  "color": _color, "order": _i}

DEFAULTS = {
    "layout": 2,                 # bump to reset saved window position/size
    "corner": "top-right",       # default dock corner
    "x": None, "y": None, "width": 420,
    "font_size": 11,
    "speed": 70,                 # pixels per second
    "pause_on_hover": True,
    "topmost": True,
    "opacity": 1.0,
    "name_style": "short",       # "short" (Ohio State) or "abbr" (OSU)
    "show_situation": True,      # baseball/softball outs and runners
    "fast_poll": 3,              # seconds, college football/basketball while live
    "live_poll": 6,              # seconds, everything else while live
    "bypass_cache": True,        # ask ESPN's CDN for a fresh copy every poll
    "show_tv": True,             # TV / streaming channel after each score
    "enabled": {k: True for k in LEAGUE},
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("layout") != DEFAULTS["layout"]:   # old full-width layout
            for k in ("x", "y", "width", "layout", "corner"):
                saved.pop(k, None)
        for k, v in saved.items():
            if k == "enabled" and isinstance(v, dict):
                cfg["enabled"].update({kk: bool(vv) for kk, vv in v.items() if kk in LEAGUE})
            elif k in cfg:
                cfg[k] = v
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------

def _ssl_context():
    # Frozen apps and python.org macOS builds often lack system CA certs;
    # prefer certifi's bundle when it's available.
    if not os.environ.get("SSL_CERT_FILE"):
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


SSL_CTX = _ssl_context()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (LiveTicker/%s)" % VERSION,
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def fetch_json(url, timeout=8):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


# --------------------------------------------------------------------------
# Parsing + time-remaining estimates
# --------------------------------------------------------------------------

# US pro leagues show the city ("Boston"), except where a city has more than
# one team in that league; those teams show the team name ("Giants", "Jets").
CITY_LEAGUES = {"nfl", "ufl", "nba", "wnba", "mlb", "nhl", "pll"}
# Cities shared by 2+ teams in a league. Refreshed from ESPN's team lists at
# startup; these defaults cover the current leagues if that lookup fails.
SHARED_CITIES = {
    "nfl": {"los angeles", "new york"},
    "mlb": {"chicago", "los angeles", "new york"},
    "nhl": {"new york"},
    "nba": {"los angeles"},          # Clippers ("LA") and Lakers
}
_CITY_ALIASES = {"la": "los angeles", "ny": "new york"}


def _city_key(loc):
    k = (loc or "").strip().lower()
    return _CITY_ALIASES.get(k, k)


def display_name(league, t):
    """Name shown for a team (in 'team names' mode)."""
    if league in CITY_LEAGUES and t.get("city") and t.get("team"):
        if _city_key(t["city"]) in SHARED_CITIES.get(league, set()):
            return t["team"]
        return "Los Angeles" if _city_key(t["city"]) == "los angeles" else t["city"]
    return t["short"]


def refresh_shared_cities():
    """Rebuild SHARED_CITIES from ESPN's current team lists (runs in background)."""
    for key in CITY_LEAGUES:
        try:
            data = fetch_json("%s/%s/teams?limit=200" % (API, LEAGUE[key]["path"]))
            teams = data["sports"][0]["leagues"][0]["teams"]
            counts = {}
            for item in teams:
                tm = item.get("team") or {}
                if tm.get("location") and tm.get("name"):     # skip all-star / placeholder teams
                    c = _city_key(tm["location"])
                    counts[c] = counts.get(c, 0) + 1
            if counts:
                SHARED_CITIES[key] = {c for c, n in counts.items() if n > 1}
        except Exception:
            pass


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clock_secs(status):
    if status.get("clock") is not None:
        return _num(status.get("clock"))
    m = re.match(r"(\d+):(\d+)", str(status.get("displayClock", "")))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0.0


def remaining_minutes(model, status, home, away, situation, short_detail):
    """Estimated real-world minutes until the game ends."""
    kind = model["kind"]
    period = int(_num(status.get("period"), 1)) or 1
    name = (status.get("type") or {}).get("name", "")

    if kind == "clock":
        P, plen = model["periods"], model["plen"] * 60
        c = _clock_secs(status)
        if "HALFTIME" in name:                         # ESPN sometimes reports period+1 here
            period, c = max(P // 2, 1), 0.0
        game_secs = c + (P - period) * plen if period <= P else (c if model["ot"] else 0)
        real = game_secs / 60.0 * model["factor"]
        for after, mins in model["breaks"].items():
            if period < after or (period == after and c > 0):
                real += mins
            elif period == after and c == 0:          # halftime / intermission now
                real += mins / 2.0
        if period > P and not model["ot"]:            # untimed OT (college football)
            real += 4
        return max(real, 0.1)

    if kind == "soccer":
        elapsed = _clock_secs(status) / 60.0
        if "HALFTIME" in name:
            return 7 + 45 + 4
        if "SHOOTOUT" in name or period >= 5:
            return 4
        if period <= 1:
            return max(45 - elapsed, 0) + 2 + 15 + 45 + 4
        if period == 2:
            return max(90 - elapsed, 0) + 3
        return max(120 - elapsed, 0) + 2

    if kind == "baseball":
        inn = period
        word = short_detail.strip().lower()
        done = (inn - 1) * 2
        if word.startswith(("mid", "middle")):
            done += 1
        elif word.startswith("end"):
            done += 2
        elif word.startswith(("bot", "bottom")):
            done += 1 + min(_num(situation.get("outs")), 2.9) / 3.0
        else:  # top
            done += min(_num(situation.get("outs")), 2.9) / 3.0
        halves_left = model["innings"] * 2 - done
        if halves_left <= 0:                           # extra innings
            halves_left = 1.0 - (done % 1)
        return max(halves_left, 0.2) * model["half"]

    if kind == "sets":
        a, b = int(_num(away["score"])), int(_num(home["score"]))
        to_win = model["best_of"] // 2 + 1
        min_more = max(to_win - max(a, b), 1)
        max_more = max(model["best_of"] - a - b, min_more)
        pts = max(away.get("set_pts") or 0, home.get("set_pts") or 0)
        frac = min(pts / 25.0, 0.95)
        return max((min_more + max_more) / 2.0 - frac, 0.2) * model["per_set"]

    return 60.0


_ORD = re.compile(r"^\s*(\d+:\d+)\s*-\s*(.+)$")


def _status_text(short_detail):
    s = short_detail or ""
    m = _ORD.match(s)                                  # "10:13 - 2nd" -> "10:13 2nd"
    if m:
        s = "%s %s" % (m.group(1), m.group(2))
    return s.replace("Halftime", "HALF").replace("End of ", "End ")


def parse_scoreboard(data, lg):
    """Return (live_games, seconds_until_next_scheduled_start or None)."""
    games, soonest = [], None
    now = datetime.now(timezone.utc)
    for ev in data.get("events", []) or []:
        st = ev.get("status") or {}
        stype = st.get("type") or {}
        state = stype.get("state")
        if state == "pre":
            try:
                d = datetime.strptime(ev.get("date", "").replace("Z", "+0000"),
                                      "%Y-%m-%dT%H:%M%z" if len(ev.get("date", "")) <= 17 else "%Y-%m-%dT%H:%M:%S%z")
                secs = (d - now).total_seconds()
                soonest = secs if soonest is None else min(soonest, secs)
            except ValueError:
                pass
            continue
        if state != "in":
            continue
        g = parse_live_event(ev, lg)
        if g:
            games.append(g)
    return games, soonest


def parse_live_event(ev, lg):
    st = ev.get("status") or {}
    stype = st.get("type") or {}
    comps = ev.get("competitions") or [{}]
    comp = comps[0]
    sides = {}
    for i, c in enumerate(comp.get("competitors") or []):
        tm = c.get("team") or {}
        rank = (c.get("curatedRank") or {}).get("current")
        lines = [ls.get("value") for ls in (c.get("linescores") or [])]
        side = c.get("homeAway") or ("home" if i == 0 else "away")
        sides[side] = {
            "id": str(tm.get("id", "")),
            "abbr": tm.get("abbreviation") or tm.get("shortDisplayName") or "?",
            "short": tm.get("shortDisplayName") or tm.get("name") or tm.get("abbreviation") or "?",
            "city": tm.get("location") or "",
            "team": tm.get("name") or "",
            "score": str(c.get("score", "0") if c.get("score") not in (None, "") else "0"),
            "rank": rank if isinstance(rank, int) and 1 <= rank <= 25 else None,
            "set_pts": int(_num(lines[-1])) if lines and lg["model"]["kind"] == "sets" else None,
            "aliases": team_aliases(tm) if lg["key"] in TV_GUIDE_SPORTS else None,
        }
    if "home" not in sides or "away" not in sides:
        return None
    home, away = sides["home"], sides["away"]
    sit = comp.get("situation") or {}
    short_detail = stype.get("shortDetail") or stype.get("detail") or st.get("displayClock", "")
    model = lg["model"]

    extra, poss, redzone = "", None, False
    if model["kind"] == "baseball":
        bits = []
        if sit.get("outs") is not None:
            o = int(_num(sit.get("outs")))
            bits.append("%d out" % o)
        bases = [n for n, k in (("1st", "onFirst"), ("2nd", "onSecond"), ("3rd", "onThird")) if sit.get(k)]
        if len(bases) == 3:
            bits.append("bases loaded")
        elif bases:
            bits.append("on " + ", ".join(bases))
        extra = " · ".join(bits)

    try:
        start = datetime.strptime(ev.get("date", "")[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        start = None

    link = ""
    for ln in ev.get("links") or []:
        if ln.get("href", "").startswith("http"):
            link = ln["href"]
            break

    return {
        "id": "%s:%s" % (lg["key"], ev.get("id")),
        "league": lg["key"],
        "away": away,
        "home": home,
        "status": _status_text(short_detail),
        "extra": extra,
        "poss": poss,
        "redzone": redzone,
        "link": link,
        "remaining": remaining_minutes(model, st, home, away, sit, short_detail),
        "start": start,
        "espn_tv": espn_channels(comp),
    }


# --------------------------------------------------------------------------
# Data hub: schedules polls per feed, merges results
# --------------------------------------------------------------------------

def fmt_time(ts):
    if not ts:
        return "--:--"
    return datetime.fromtimestamp(ts).strftime("%I:%M:%S %p").lstrip("0")


def sort_key(g):
    """Sport first (crawl order above), then least time remaining first."""
    lg = LEAGUE[g["league"]]
    return (SPORT_ORDER[lg["sport"]], round(g["remaining"], 1), lg["order"], g["id"])


def us_eastern_now():
    """Current US Eastern time (ESPN's scoreboard day), without needing tz data."""
    from datetime import timedelta
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    y = utc.year

    def nth_sunday(month, n):
        d = datetime(y, month, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)      # first Sunday
        return d + timedelta(weeks=n - 1)
    dst_start = nth_sunday(3, 2) + timedelta(hours=7)     # 2 AM EST  = 07:00 UTC
    dst_end = nth_sunday(11, 1) + timedelta(hours=6)      # 2 AM EDT  = 06:00 UTC
    return utc - timedelta(hours=4 if dst_start <= utc < dst_end else 5)


def scoreboard_dates():
    """Dates to request. ESPN's undated scoreboard doesn't roll over to the new
    day until late morning, so morning games would be missed; always ask for
    today explicitly. Until 6 AM, also ask for yesterday so games that run past
    midnight stay on the ticker."""
    from datetime import timedelta
    now = us_eastern_now()
    days = [now]
    if now.hour < 6:
        days.insert(0, now - timedelta(days=1))
    return [d.strftime("%Y%m%d") for d in days]


# --------------------------------------------------------------------------
# TV / streaming channels
# --------------------------------------------------------------------------
# College football and men's basketball channels come from Matt Sarzyniak's
# "College Sports on TV" (mattsarzsports.com), which is more complete for
# small-conference streams. Everything else uses ESPN's own broadcast list.
TV_GUIDE_SPORTS = {"ncaaf": "football", "ncaam": "basketball"}
TV_GUIDE_API = "https://api.mattsarzsports.com/graphql"
TV_GUIDE_QUERY = ("query dailyTvGames($input: DailyTvGamesInput) { dailyTvGames(input: $input) "
                  "{ tvGames { visitingTeam homeTeam network timeWithOffset } } }")
TV_GUIDE_REFRESH = 15 * 60       # seconds; the schedule rarely changes during the day


def espn_channels(comp):
    """Channel text from ESPN: national outlets if any, else the teams' regional ones."""
    geo = comp.get("geoBroadcasts") or []
    pick = lambda market: [g["media"]["shortName"] for g in geo
                           if (g.get("market") or {}).get("type") == market and (g.get("media") or {}).get("shortName")]
    names = pick("National") or (pick("Home") + pick("Away"))
    if not names:
        names = [n for b in comp.get("broadcasts") or [] for n in b.get("names") or []]
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return " / ".join(out[:2])


def _tnorm(s):
    s = (s or "").lower().replace("&", " and ")
    for a, b in (("\u00e9", "e"), ("\u00f1", "n"), ("'", ""), ("\u2019", "")):
        s = s.replace(a, b)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def _exact_keys(name):
    n = _tnorm(name)
    out, w = {n}, n.split()
    for i, x in enumerate(w):
        if x == "st":                                   # St. = State or Saint
            for r in ("state", "saint"):
                out.add(" ".join(w[:i] + [r] + w[i + 1:]))
    return {v.replace(" ", "") for v in out if v}


_LOOSE_DROP = {"state", "st", "university", "univ", "u", "the", "of", "college", "west", "point"}


def _loose_keys(name):
    words = _tnorm(re.sub(r"\([^)]*\)", " ", name or "")).split()
    k = "".join(x for x in words if x not in _LOOSE_DROP)
    out = {k} if len(k) >= 3 else set()
    if len(words) >= 2:                                  # initials: "UT Rio Grande Valley" -> utrgv
        out.add("".join(x if len(x) <= 2 else x[0] for x in words))
    return out


def team_aliases(tm):
    names = {tm.get(k) for k in ("location", "shortDisplayName", "displayName", "abbreviation", "nickname")}
    if tm.get("displayName") and tm.get("name") and tm["displayName"].endswith(tm["name"]):
        names.add(tm["displayName"][: -len(tm["name"])].strip())
    exact, loose = set(), set()
    for n in names:
        if n:
            exact |= _exact_keys(n)
            loose |= _loose_keys(n)
    return (exact, loose)


def _team_score(name, sides):
    """2 = exact name match with a team in the game, 1 = loose match, 0 = none."""
    ex, lo = _exact_keys(name), _loose_keys(name)
    if any(ex & s[0] for s in sides):
        return 2
    for s in sides:
        if lo & s[1]:
            return 1
        if any(len(a) >= 10 and len(b) >= 10 and (a.endswith(b) or b.endswith(a))
               for a in lo for b in s[1]):               # "A&M-Kingsville" vs "Texas A&M-Kingsville"
            return 1
    return 0


class TvGuide:
    """Fetches and matches the mattsarzsports.com daily schedules."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.entries = {}          # sport -> [(visiting, home, start ts, network)]
        self.fetched = {}          # sport -> (dates tuple, wall time)
        self.cache = {}            # ESPN game id -> channel text ("" = none found)

    def refresh(self, force=False):
        for key, sport in TV_GUIDE_SPORTS.items():
            if not self.cfg["enabled"].get(key, True) or not self.cfg.get("show_tv", True):
                continue
            dates = tuple(scoreboard_dates())
            prev = self.fetched.get(sport)
            if not force and prev and prev[0] == dates and time.time() - prev[1] < TV_GUIDE_REFRESH:
                continue
            rows = []
            try:
                for d in dates:
                    rows += self._fetch(sport, "%s-%s-%s" % (d[:4], d[4:6], d[6:]))
            except Exception as e:
                if os.environ.get("LIVE_TICKER_DEBUG"):
                    print("tv guide error", sport, repr(e), file=sys.stderr)
                self.fetched[sport] = (dates, time.time() - TV_GUIDE_REFRESH + 120)   # retry in 2 min
                continue
            with self.lock:
                self.entries[sport] = rows
                self.cache = {k: v for k, v in self.cache.items() if not k.startswith(key + ":")}
            self.fetched[sport] = (dates, time.time())

    def _fetch(self, sport, day):
        body = json.dumps({"query": TV_GUIDE_QUERY,
                           "variables": {"input": {"sport": sport, "startDate": day}}}).encode()
        req = urllib.request.Request(TV_GUIDE_API, data=body, headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": HEADERS["User-Agent"], "Origin": "https://www.mattsarzsports.com"})
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for g in ((data.get("data") or {}).get("dailyTvGames") or {}).get("tvGames") or []:
            try:
                ts = datetime.strptime(g["timeWithOffset"][:16], "%Y-%m-%dT%H:%M").replace(
                    tzinfo=timezone.utc).timestamp()
            except (KeyError, ValueError, TypeError):
                ts = None
            v = (g.get("visitingTeam") or [""])[0]
            h = (g.get("homeTeam") or [""])[0]
            net = re.sub(r"<[^>]+>", " ", g.get("network") or "").strip()
            if net:
                out.append((v, h, ts, " ".join(net.split())))
        return out

    def channel(self, g):
        """Channel text for an ESPN game (matched schedule first, else ESPN's)."""
        sport = TV_GUIDE_SPORTS.get(g["league"])
        if not sport:
            return g.get("espn_tv", "")
        hit = self.cache.get(g["id"])
        if hit is None:
            hit = self._match(sport, g)
            if hit or sport in self.entries:            # don't cache misses before data arrives
                self.cache[g["id"]] = hit
        return hit or g.get("espn_tv", "")

    def _match(self, sport, g):
        sides = [g["away"]["aliases"], g["home"]["aliases"]]
        if not all(sides):
            return ""
        with self.lock:
            rows = list(self.entries.get(sport, []))
        scored = {}
        for v, h, ts, net in rows:
            if ts and g.get("start") and abs(ts - g["start"]) > 4 * 3600:
                continue
            # A Division I team plays once a day, so one exact name (2) or two
            # loose ones (1 + 1) is enough to identify the game.
            score = _team_score(v, sides) + _team_score(h, sides)
            if score >= 2:
                k = (v, h)
                sc, nets = scored.get(k, (score, []))
                if net not in nets:
                    nets.append(net)
                scored[k] = (sc, nets)
        if not scored:
            return ""
        ranked = sorted(scored.values(), key=lambda x: -x[0])
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return ""                                    # ambiguous: fall back to ESPN
        return " / ".join(ranked[0][1][:3])


class Feed:
    def __init__(self, lg, group):
        self.lg, self.group = lg, group
        self.key = "%s/%s" % (lg["key"], group)
        self.next_due = 0.0
        self.busy = False
        self.errors = 0
        self.last_ok = 0.0          # wall time of last successful fetch
        self.live_count = 0

    def urls(self, bypass):
        # NB: limit=1000 makes ESPN fall back to 25 games, and date ranges
        # ("20261101-20261102") are rejected, so request one day at a time.
        out = []
        for day in scoreboard_dates():
            q = ["limit=300", "dates=%s" % day]
            if self.group is not None:
                q.append("groups=%s" % self.group)
            if bypass:
                q.append("_=%d" % int(time.time() * 1000))
            out.append("%s/%s/scoreboard?%s" % (API, self.lg["path"], "&".join(q)))
        return out


class DataHub:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.results = {}          # feed key -> (fetched wall time, [games])
        self.version = 0
        self.running = True
        self.feeds = []
        for lg in LEAGUE.values():
            for grp in (lg["groups"] or [None]):
                self.feeds.append(Feed(lg, grp))
        self.pool = ThreadPoolExecutor(max_workers=8)
        self.tv = TvGuide(cfg)

    def start(self):
        threading.Thread(target=refresh_shared_cities, daemon=True).start()
        threading.Thread(target=self._tv_loop, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()

    def _tv_loop(self):
        while self.running:
            self.tv.refresh()
            with self.lock:
                self.version += 1          # redraw cards with any newly matched channels
            time.sleep(30)

    def stop(self):
        self.running = False
        self.pool.shutdown(wait=False)

    def poll_now(self):
        for f in self.feeds:
            f.next_due = 0.0

    def _loop(self):
        # Priority (college football/basketball) feeds get scheduled first.
        order = sorted(self.feeds, key=lambda f: (not f.lg["priority"], f.lg["order"]))
        while self.running:
            now = time.monotonic()
            for f in order:
                if not self.cfg["enabled"].get(f.lg["key"], True):
                    if f.key in self.results:
                        with self.lock:
                            self.results.pop(f.key, None)
                            self.version += 1
                    f.next_due = 0.0
                    continue
                if not f.busy and now >= f.next_due:
                    f.busy = True
                    try:
                        self.pool.submit(self._run, f)
                    except RuntimeError:
                        return
            time.sleep(0.1)

    def _interval(self, f, live, soonest):
        prio = f.lg["priority"]
        if live:
            return max(1.0, float(self.cfg["fast_poll"] if prio else self.cfg["live_poll"]))
        if soonest is not None and soonest < 15 * 60:   # a game is about to start
            return 8.0 if prio else 15.0
        if soonest is not None and soonest < 3 * 3600:
            return 30.0 if prio else 60.0
        return 120.0 if prio else 300.0

    def _run(self, f):
        interval = 30.0
        try:
            games, soonest = [], None
            for url in f.urls(self.cfg.get("bypass_cache", True)):
                g, so = parse_scoreboard(fetch_json(url), f.lg)
                games += g
                if so is not None:
                    soonest = so if soonest is None else min(soonest, so)
            f.errors = 0
            f.last_ok = time.time()
            f.live_count = len(games)
            interval = self._interval(f, bool(games), soonest)
            with self.lock:
                self.results[f.key] = (f.last_ok, games)
                self.version += 1
        except Exception as e:  # network hiccup, bad JSON, etc.
            f.errors += 1
            interval = min(3 * (2 ** min(f.errors, 5)), 60)
            if os.environ.get("LIVE_TICKER_DEBUG"):
                print("fetch error", f.key, repr(e), file=sys.stderr)
            with self.lock:   # drop data that's gone stale (> 3 min old)
                r = self.results.get(f.key)
                if r and time.time() - r[0] > 180:
                    self.results.pop(f.key, None)
                    self.version += 1
        finally:
            f.next_due = time.monotonic() + interval
            f.busy = False

    def snapshot(self):
        with self.lock:
            merged = {}
            for _, games in self.results.values():
                for g in games:
                    merged[g["id"]] = g          # dedupes FBS/FCS crossover games
            version = self.version
        games = sorted(merged.values(), key=sort_key)
        return version, games

    def last_refresh(self):
        """Wall time of the most recent successful fetch (None if none yet)."""
        oks = [f.last_ok for f in self.feeds if f.last_ok]
        return max(oks) if oks else None

    def freshness(self):
        """Age (s) of the stalest feed that currently has live games, else of newest fetch."""
        now = time.time()
        live = [now - f.last_ok for f in self.feeds
                if self.cfg["enabled"].get(f.lg["key"], True) and f.live_count and f.last_ok]
        if live:
            return max(live)
        oks = [now - f.last_ok for f in self.feeds if f.last_ok]
        return min(oks) if oks else None


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

# Plain white text on black.
BG = "#000000"
BG_PANEL = "#000000"
FG = "#ffffff"
NAME_FG = SCORE_FG = RANK_FG = STATUS_FG = DIM_FG = POSS_FG = REDZONE_FG = FG
SEP_FG = "#444444"


# --------------------------------------------------------------------------
# Start automatically at login
# --------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_NAME = "LiveTicker"


def _launch_command():
    """Command line that starts the ticker with no console window."""
    if getattr(sys, "frozen", False):                     # packaged .exe / .app
        return [sys.executable]
    exe = sys.executable
    if sys.platform == "win32":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            exe = w
    return [exe, os.path.abspath(__file__)]


def _mac_plist():
    return os.path.expanduser("~/Library/LaunchAgents/com.liveticker.plist")


def _linux_desktop():
    return os.path.expanduser("~/.config/autostart/live-ticker.desktop")


def startup_enabled():
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, STARTUP_NAME)
            return True
        if sys.platform == "darwin":
            return os.path.exists(_mac_plist())
        return os.path.exists(_linux_desktop())
    except OSError:
        return False


def set_startup(enable):
    """Turn start-at-login on or off. Returns True on success."""
    cmd = _launch_command()
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if enable:
                    winreg.SetValueEx(k, STARTUP_NAME, 0, winreg.REG_SZ,
                                      " ".join('"%s"' % c for c in cmd))
                else:
                    try:
                        winreg.DeleteValue(k, STARTUP_NAME)
                    except FileNotFoundError:
                        pass
        elif sys.platform == "darwin":
            path = _mac_plist()
            if enable:
                if getattr(sys, "frozen", False) and ".app/" in sys.executable:
                    app = sys.executable.split(".app/")[0] + ".app"
                    cmd = ["/usr/bin/open", "-a", app]
                args = "".join("<string>%s</string>" % c for c in cmd)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                            '<plist version="1.0"><dict><key>Label</key><string>com.liveticker</string>'
                            '<key>ProgramArguments</key><array>%s</array>'
                            '<key>RunAtLoad</key><true/></dict></plist>\n' % args)
            elif os.path.exists(path):
                os.remove(path)
        else:
            path = _linux_desktop()
            if enable:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=Live Ticker\nExec=%s\n"
                            "X-GNOME-Autostart-enabled=true\n" % " ".join('"%s"' % c for c in cmd))
            elif os.path.exists(path):
                os.remove(path)
        return True
    except OSError:
        return False


def work_area(root):
    """Usable screen rectangle (x0, y0, x1, y1), excluding the taskbar / menu bar."""
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):  # SPI_GETWORKAREA
                return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
    if sys.platform == "darwin":
        return 0, 25, sw, sh
    return 0, 0, sw, sh


class Card:
    __slots__ = ("tag", "gid", "x", "w", "bg", "sig")

    def __init__(self, tag, gid, x):
        self.tag, self.gid, self.x = tag, gid, x
        self.w, self.bg, self.sig = 0, None, None


class TickerApp:
    MARKER = "__marker__"
    HEADER = "__hdr__:"

    def __init__(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        import tkinter as tk
        import tkinter.font as tkfont
        self.tk, self.tkfont = tk, tkfont
        self.cfg = load_config()
        self.hub = DataHub(self.cfg)

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.overrideredirect(True)
        self.aqua = self.root.tk.call("tk", "windowingsystem") == "aqua"

        self._make_fonts()
        self.h = self.f_name.metrics("linespace") + 14

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = int(self.cfg["width"] or 420)
        if self.cfg["x"] is None or self.cfg["y"] is None:
            x, y = self._corner_xy(self.cfg.get("corner", "top-right"), w)
        else:
            x = max(-w + 100, min(int(self.cfg["x"]), sw - 100))
            y = max(0, min(int(self.cfg["y"]), sh - self.h))
        self.root.geometry("%dx%d+%d+%d" % (w, self.h, x, y))
        self._apply_window_attrs()

        # Layout: [LIVE n ●] [ scrolling canvas ............ ] [⋮ ✕]
        self.left = tk.Canvas(self.root, width=10, height=self.h, bg=BG_PANEL, highlightthickness=0, bd=0)
        self.right = tk.Canvas(self.root, width=10, height=self.h, bg=BG_PANEL, highlightthickness=0, bd=0)
        self.canvas = tk.Canvas(self.root, height=self.h, bg=BG, highlightthickness=0, bd=0)
        self.left.pack(side="left", fill="y")
        self.right.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._build_panels()

        self.cards = []
        self.seq = 0
        self.games = []
        self.by_id = {}
        self.cursor = None          # (game id, remaining) of last card appended
        self.data_version = -1
        self.hover = False
        self.paused = False
        self.acc = 0.0
        self.last_frame = time.perf_counter()
        self.drag = None
        self._save_job = None
        self.started = False
        self.tail_sport = None
        self.need_marker = True
        self.t_start = time.monotonic()

        self._bind()
        self._build_menu()
        self.hub.start()
        self.root.after(15, self._frame)
        self.root.after(250, self._pull_data)
        self.root.after(1000, self._each_second)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    # ---- setup -----------------------------------------------------------
    def _make_fonts(self):
        fams = set(self.tkfont.families(self.root))
        family = next((f for f in ("Segoe UI Semibold", "Segoe UI", "Helvetica Neue",
                                   "SF Pro Text", "Arial", "DejaVu Sans") if f in fams), "TkDefaultFont")
        fs = int(self.cfg["font_size"])
        self.f_name = self.tkfont.Font(root=self.root, family=family, size=fs, weight="bold")
        self.f_score = self.tkfont.Font(root=self.root, family=family, size=fs + 1, weight="bold")
        self.f_status = self.tkfont.Font(root=self.root, family=family, size=fs, weight="bold")
        self.f_small = self.tkfont.Font(root=self.root, family=family, size=max(fs - 2, 7), weight="bold")
        self.f_pill = self.tkfont.Font(root=self.root, family=family, size=max(fs - 2, 7), weight="bold")
        self.fonts = {"name": self.f_name, "score": self.f_score, "status": self.f_status,
                      "small": self.f_small, "pill": self.f_pill}

    def _apply_window_attrs(self):
        try:
            self.root.attributes("-topmost", bool(self.cfg["topmost"]))
        except Exception:
            pass
        try:
            self.root.attributes("-alpha", float(self.cfg["opacity"]))
        except Exception:
            pass

    def _build_panels(self):
        L, R, h = self.left, self.right, self.h
        L.delete("all")
        R.delete("all")
        ymid = h // 2
        t = L.create_text(10, ymid, anchor="w", text="LIVE", font=self.f_pill, fill=FG)
        x2 = L.bbox(t)[2]
        self.count_item = L.create_text(x2 + 12, ymid, anchor="w", text="0", font=self.f_name, fill=NAME_FG)
        self.dot_item = L.create_oval(0, 0, 0, 0, fill="#666", outline="")
        self._layout_left()

        # Two click zones: [ ≡ | × ]. Clicks are handled in _release, by position.
        # Drawn with lines rather than font glyphs so they look the same everywhere.
        for dy in (-5, 0, 5):                                   # menu: three bars
            R.create_line(8, ymid + dy, 22, ymid + dy, fill=FG, width=2)
        R.create_line(36, ymid - 5, 46, ymid + 5, fill=FG, width=2)   # close: an X
        R.create_line(36, ymid + 5, 46, ymid - 5, fill=FG, width=2)
        R.config(width=56)

    def _layout_left(self):
        L, ymid = self.left, self.h // 2
        x2 = L.bbox(self.count_item)[2]
        L.coords(self.dot_item, x2 + 8, ymid - 3, x2 + 14, ymid + 3)
        L.config(width=x2 + 22)

    def _bind(self):
        for w in (self.canvas, self.left, self.right):
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<B1-Motion>", self._motion)
            w.bind("<ButtonRelease-1>", self._release)
            w.bind("<Button-3>", self._popup)
            if self.aqua:
                w.bind("<Button-2>", self._popup)
                w.bind("<Control-Button-1>", self._popup)
        self.canvas.bind("<Double-Button-1>", self._open_game)
        self.canvas.bind("<Enter>", lambda e: setattr(self, "hover", True))
        self.canvas.bind("<Leave>", lambda e: setattr(self, "hover", False))
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda e: self._set_speed(self.cfg["speed"] + 10))
        self.canvas.bind("<Button-5>", lambda e: self._set_speed(self.cfg["speed"] - 10))
        self.right.bind("<Motion>", self._edge_cursor)

    def _build_menu(self):
        tk = self.tk
        m = tk.Menu(self.root, tearoff=0)
        self.v_pause = tk.BooleanVar(value=False)
        m.add_checkbutton(label="Pause scrolling", variable=self.v_pause,
                          command=lambda: setattr(self, "paused", self.v_pause.get()))
        m.add_command(label="Refresh now", command=self.hub.poll_now)
        m.add_separator()

        sp = tk.Menu(m, tearoff=0)
        self.v_speed = tk.IntVar(value=int(self.cfg["speed"]))
        for name, v in (("Slow", 40), ("Medium", 70), ("Fast", 110), ("Very fast", 160)):
            sp.add_radiobutton(label=name, variable=self.v_speed, value=v, command=lambda v=v: self._set_speed(v))
        m.add_cascade(label="Scroll speed", menu=sp)

        sz = tk.Menu(m, tearoff=0)
        self.v_size = tk.IntVar(value=int(self.cfg["font_size"]))
        for name, v in (("Small", 9), ("Medium", 11), ("Large", 13), ("Extra large", 16)):
            sz.add_radiobutton(label=name, variable=self.v_size, value=v, command=lambda v=v: self._set_size(v))
        m.add_cascade(label="Text size", menu=sz)

        wd = tk.Menu(m, tearoff=0)
        for label, corner in (("Upper right corner", "top-right"), ("Upper left corner", "top-left"),
                              ("Lower right corner", "bottom-right"), ("Lower left corner", "bottom-left")):
            wd.add_command(label=label, command=lambda c=corner: self._dock(c))
        wd.add_separator()
        for px in (300, 420, 600, 800):
            wd.add_command(label="%d px wide" % px, command=lambda px=px: self._set_width(px))
        m.add_cascade(label="Position / width", menu=wd)

        lg = tk.Menu(m, tearoff=0)
        self.v_leagues = {}
        lg.add_command(label="All on", command=lambda: self._all_leagues(True))
        lg.add_command(label="College football + basketball only", command=self._college_only)
        lg.add_separator()
        for k, info in LEAGUE.items():
            v = tk.BooleanVar(value=self.cfg["enabled"].get(k, True))
            self.v_leagues[k] = v
            lg.add_checkbutton(label=info["label"], variable=v, command=lambda k=k: self._toggle_league(k))
        m.add_cascade(label="Leagues", menu=lg)

        dp = tk.Menu(m, tearoff=0)
        self.v_names = tk.StringVar(value=self.cfg["name_style"])
        dp.add_radiobutton(label="Names (Ohio State, Boston)", variable=self.v_names, value="short", command=self._names)
        dp.add_radiobutton(label="Abbreviations (OSU)", variable=self.v_names, value="abbr", command=self._names)
        dp.add_separator()
        self.v_tv = tk.BooleanVar(value=self.cfg.get("show_tv", True))
        dp.add_checkbutton(label="Show TV / streaming channel", variable=self.v_tv, command=self._show_tv)
        self.v_sit = tk.BooleanVar(value=self.cfg["show_situation"])
        dp.add_checkbutton(label="Show outs & runners (baseball/softball)", variable=self.v_sit, command=self._situation)
        self.v_hover = tk.BooleanVar(value=self.cfg["pause_on_hover"])
        dp.add_checkbutton(label="Pause while mouse is over ticker", variable=self.v_hover,
                           command=lambda: self._set("pause_on_hover", self.v_hover.get()))
        self.v_top = tk.BooleanVar(value=self.cfg["topmost"])
        dp.add_checkbutton(label="Always on top", variable=self.v_top, command=self._topmost)
        op = tk.Menu(dp, tearoff=0)
        self.v_alpha = tk.DoubleVar(value=float(self.cfg["opacity"]))
        for pct in (100, 90, 80, 70, 60):
            op.add_radiobutton(label="%d%%" % pct, variable=self.v_alpha, value=pct / 100.0,
                               command=lambda p=pct: self._opacity(p / 100.0))
        dp.add_cascade(label="Opacity", menu=op)
        m.add_cascade(label="Display", menu=dp)

        m.add_separator()
        self.v_startup = tk.BooleanVar(value=startup_enabled())
        m.add_checkbutton(label="Start automatically when I log in", variable=self.v_startup,
                          command=self._toggle_startup)
        m.add_separator()
        m.add_command(label="%s %s" % (APP_NAME, VERSION), state="disabled")
        m.add_command(label="Quit", command=self.quit)
        self.menu = m

    # ---- settings actions --------------------------------------------------
    def _set(self, key, value):
        self.cfg[key] = value
        self._save_soon()

    def _save_soon(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(800, lambda: save_config(self.cfg))

    def _set_speed(self, v):
        v = max(10, min(400, int(v)))
        self.v_speed.set(v)
        self._set("speed", v)

    def _set_size(self, v):
        self._set("font_size", v)
        for key, f in self.fonts.items():
            base = v + (1 if key == "score" else 0) - (2 if key in ("small", "pill") else 0)
            f.configure(size=max(base, 7))
        self.h = self.f_name.metrics("linespace") + 14
        self.root.geometry("%dx%d" % (self.root.winfo_width(), self.h))
        for c in (self.canvas, self.left, self.right):
            c.config(height=self.h)
        self._build_panels()
        self._reset_crawl()

    def _corner_xy(self, corner, w):
        x0, y0, x1, y1 = work_area(self.root)
        x = x1 - w if corner.endswith("right") else x0
        y = y0 if corner.startswith("top") else y1 - self.h
        return x, y

    def _set_width(self, px):
        # Keep the bar's right edge where it is if it's docked on the right.
        x0, _, x1, _ = work_area(self.root)
        right_docked = self.root.winfo_x() + self.root.winfo_width() >= x1 - 2
        x = x1 - px if right_docked else self.root.winfo_x()
        self._set("width", px)
        self.root.geometry("%dx%d+%d+%d" % (px, self.h, x, self.root.winfo_y()))
        self.root.after(50, self._remember_pos)

    def _dock(self, corner):
        w = self.root.winfo_width()
        x, y = self._corner_xy(corner, w)
        self.root.geometry("%dx%d+%d+%d" % (w, self.h, x, y))
        self._set("corner", corner)
        self.root.after(50, self._remember_pos)

    def _toggle_startup(self):
        if not set_startup(self.v_startup.get()):
            self.v_startup.set(startup_enabled())

    def _toggle_league(self, k):
        self.cfg["enabled"][k] = self.v_leagues[k].get()
        self._save_soon()

    def _all_leagues(self, on):
        for k, v in self.v_leagues.items():
            v.set(on)
            self.cfg["enabled"][k] = on
        self._save_soon()

    def _college_only(self):
        for k, v in self.v_leagues.items():
            on = k in ("ncaaf", "ncaam", "ncaaw")
            v.set(on)
            self.cfg["enabled"][k] = on
        self._save_soon()

    def _names(self):
        self._set("name_style", self.v_names.get())
        self._refresh_visible(force=True)

    def _show_tv(self):
        self._set("show_tv", self.v_tv.get())
        if self.v_tv.get():
            threading.Thread(target=self.hub.tv.refresh, daemon=True).start()
        self._refresh_visible(force=True)

    def _situation(self):
        self._set("show_situation", self.v_sit.get())
        self._refresh_visible(force=True)

    def _topmost(self):
        self._set("topmost", self.v_top.get())
        self._apply_window_attrs()

    def _opacity(self, a):
        self._set("opacity", a)
        self._apply_window_attrs()

    # ---- mouse -------------------------------------------------------------
    def _popup(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _edge_cursor(self, e):
        rw = int(self.right["width"])
        self.right.config(cursor="sb_h_double_arrow" if e.x >= rw - 4 else "hand2")

    def _press(self, e):
        resize = e.widget is self.right and e.x >= int(self.right["width"]) - 4
        self.drag = ("resize" if resize else "move", e.x_root, e.y_root,
                     self.root.winfo_x(), self.root.winfo_y(), self.root.winfo_width())

    def _motion(self, e):
        if not self.drag:
            return
        mode, x0, y0, wx, wy, ww = self.drag
        if mode == "move":
            self.root.geometry("+%d+%d" % (wx + e.x_root - x0, wy + e.y_root - y0))
        else:
            self.root.geometry("%dx%d" % (max(300, ww + e.x_root - x0), self.h))

    def _release(self, e):
        d, self.drag = self.drag, None
        if not d:
            return
        moved = abs(e.x_root - d[1]) + abs(e.y_root - d[2]) > 4
        if d[0] == "resize":
            self._set("width", self.root.winfo_width())
        elif not moved and e.widget is self.right:
            # A click (not a drag) on the button panel: left half = menu, right half = close.
            if e.x < int(self.right["width"]) // 2:
                self._popup(e)
            else:
                self.quit()
            return
        if moved:
            self._remember_pos()

    def _remember_pos(self):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        self._save_soon()

    def _wheel(self, e):
        self._set_speed(self.cfg["speed"] + (10 if e.delta > 0 else -10))

    def _open_game(self, e):
        for item in self.canvas.find_overlapping(e.x - 1, 0, e.x + 1, self.h):
            for c in self.cards:
                if c.tag in self.canvas.gettags(item):
                    g = self.by_id.get(c.gid)
                    if g and g.get("link"):
                        webbrowser.open(g["link"])
                    return

    # ---- data --------------------------------------------------------------
    def _pull_now(self):
        self.data_version = -1
        self._apply_snapshot()

    def _pull_data(self):
        self._apply_snapshot()
        self.root.after(250, self._pull_data)

    def _apply_snapshot(self):
        version, games = self.hub.snapshot()
        if version != self.data_version:
            self.data_version = version
            self.games = games
            self.by_id = {g["id"]: g for g in games}
            self._refresh_visible()
            self.left.itemconfig(self.count_item, text=str(len(games)))
            self._layout_left()

    def _each_second(self):
        age = self.hub.freshness()
        color = FG if age is not None and age < 20 else "#444444"
        self.left.itemconfig(self.dot_item, fill=color)
        self.root.after(1000, self._each_second)

    # ---- card rendering ----------------------------------------------------
    def _segments(self, g):
        segs = []
        style = self.cfg["name_style"]
        for side in ("away", "home"):
            t = g[side]
            if t["rank"]:
                segs.append(("small", "#%d" % t["rank"], RANK_FG, 3))
            segs.append(("name", t["abbr"] if style == "abbr" else display_name(g["league"], t), NAME_FG, 6))
            gap = 5 if t["set_pts"] is not None else 16
            segs.append(("score", t["score"], SCORE_FG, gap))
            if t["set_pts"] is not None:
                segs.append(("small", "(%d)" % t["set_pts"], DIM_FG, 16))
        segs.append(("status", g["status"], STATUS_FG, 8))
        if g["extra"] and self.cfg["show_situation"]:
            segs.append(("small", g["extra"], DIM_FG, 8))
        if self.cfg.get("show_tv", True):
            tv = self.hub.tv.channel(g)
            if tv:
                segs.append(("small", tv, DIM_FG, 0))
        return segs

    def _header_segments(self, sport):
        return [("pill", SPORT_LABEL[sport], None)]

    def _marker_segments(self):
        """Start of every loop: time of the last data refresh."""
        segs = [("name", "Updated " + fmt_time(self.hub.last_refresh()), NAME_FG, 10)]
        if not self.games:
            segs.append(("small", "No games in progress", DIM_FG, 0))
        return segs

    def _draw(self, x, gid):
        cv, ymid = self.canvas, self.h // 2
        tag = "c%d" % self.seq
        self.seq += 1
        card = Card(tag, gid, x)
        tags = (tag, "scroll")
        card.bg = cv.create_rectangle(x, 0, x, self.h, fill="", outline="", tags=tags)
        if gid == self.MARKER:
            segs = self._marker_segments()
        elif gid.startswith(self.HEADER):
            segs = self._header_segments(gid[len(self.HEADER):])
        else:
            segs = self._segments(self.by_id[gid])
        card.sig = repr(segs) if gid in self.by_id else None
        cx = x + 14
        for s in segs:
            if s[0] == "pill":
                t = cv.create_text(cx, ymid, anchor="w", text=s[1], font=self.f_pill, fill=FG, tags=tags)
                cx = cv.bbox(t)[2] + 10
            else:
                kind, text, color, gap = s
                t = cv.create_text(cx, ymid, anchor="w", text=text, font=self.fonts[kind], fill=color, tags=tags)
                cx = cv.bbox(t)[2] + gap
        cx += 14
        cv.create_line(cx, 6, cx, self.h - 6, fill=SEP_FG, width=2, tags=tags)
        cx += 2
        card.w = cx - x
        cv.coords(card.bg, x, 0, cx, self.h)
        return card

    def _refresh_visible(self, force=False):
        """Update cards already on screen in place; shift later cards if width changes."""
        for i, c in enumerate(self.cards):
            g = self.by_id.get(c.gid)
            if g is None:
                continue   # game ended: leave it frozen until it scrolls off, never re-added
            if not force and repr(self._segments(g)) == c.sig:
                continue
            self.canvas.delete(c.tag)
            new = self._draw(c.x, c.gid)
            self.cards[i] = new
            delta = new.w - c.w
            if delta:
                for c2 in self.cards[i + 1:]:
                    self.canvas.move(c2.tag, delta, 0)
                    c2.x += delta

    def _next_gid(self):
        games = self.games
        if self.need_marker or not games:
            self.need_marker = False
            self.cursor = None
            return self.MARKER
        if self.cursor is None:
            nxt = 0
        else:
            gid, key = self.cursor
            idx = next((i for i, g in enumerate(games) if g["id"] == gid), None)
            if idx is not None:
                nxt = idx + 1
            else:   # cursor game ended: resume at the next game in sort order
                nxt = next((i for i, g in enumerate(games) if sort_key(g) > key), len(games))
        if nxt >= len(games):          # end of loop: next loop starts with the marker
            self.cursor = None
            return self.MARKER
        g = games[nxt]
        self.cursor = (g["id"], sort_key(g))
        return g["id"]

    def _reset_crawl(self):
        self.canvas.delete("all")
        self.cards = []
        self.cursor = None
        self.tail_sport = None
        self.need_marker = True

    def _frame(self):
        now = time.perf_counter()
        dt = min(now - self.last_frame, 0.1)
        self.last_frame = now
        moving = not self.paused and not (self.hover and self.cfg["pause_on_hover"]) and not self.drag
        if moving:
            self.acc += self.cfg["speed"] * dt
            dx = int(self.acc)
            if dx:
                self.acc -= dx
                self.canvas.move("scroll", -dx, 0)
                for c in self.cards:
                    c.x -= dx
        while self.cards and self.cards[0].x + self.cards[0].w < 0:
            self.canvas.delete(self.cards.pop(0).tag)
        width = self.canvas.winfo_width() or self.root.winfo_width()
        if not self.started:
            # Wait for the first college football/basketball poll (or 6 s), then fill the bar at once.
            ready = all(f.last_ok or f.errors for f in self.hub.feeds
                        if f.lg["priority"] and self.cfg["enabled"].get(f.lg["key"], True))
            if not (ready and self.data_version > 0) and time.monotonic() - self.t_start < 6:
                self.root.after(15, self._frame)
                return
            self.started = True
            self._pull_now()
        tail = self.cards[-1].x + self.cards[-1].w if self.cards else (0 if len(self.cards) == 0 and self.seq == 0 else width)
        guard = 0
        while tail < width + 40 and guard < 50:
            gid = self._next_gid()
            if gid == self.MARKER and self.cards and self.cards[-1].gid == self.MARKER and len(self.cards) == 1:
                break   # only the "no games" marker: don't tile it
            if gid == self.MARKER:
                self.tail_sport = None
            else:
                sport = LEAGUE[self.by_id[gid]["league"]]["sport"]
                if sport != self.tail_sport:      # sport header, BottomLine style
                    self.tail_sport = sport
                    hdr = self._draw(tail, self.HEADER + sport)
                    self.cards.append(hdr)
                    tail += hdr.w
            card = self._draw(tail, gid)
            self.cards.append(card)
            tail += card.w
            guard += 1
        self.root.after(15, self._frame)

    # ---- lifecycle ---------------------------------------------------------
    def quit(self):
        try:
            self._remember_pos()
            save_config(self.cfg)
            self.hub.stop()
            self.root.destroy()
        finally:
            os._exit(0)   # don't wait for any in-flight network request

    def run(self):
        self.root.mainloop()


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def _team_label(g, side):
    t = g[side]
    return ("#%d " % t["rank"] if t["rank"] else "") + display_name(g["league"], t)


def write_html(path, games, updated, tv=None):
    """Save the --once results as a simple, self-contained HTML page."""
    import html
    esc = html.escape
    rows, sport = [], None
    for g in games:
        sp = LEAGUE[g["league"]]["sport"]
        if sp != sport:
            sport = sp
            rows.append('<tr class="group"><th colspan="6">%s</th></tr>' % esc(SPORT_LABEL[sp]))
        a, h = g["away"], g["home"]
        status = g["status"] + (" \u00b7 " + g["extra"] if g["extra"] else "")
        rows.append(
            '<tr><td class="team">%s</td><td class="score">%s</td>'
            '<td class="team">%s</td><td class="score">%s</td><td class="status">%s</td>'
            '<td class="tv">%s</td></tr>'
            % (esc(_team_label(g, "away")), esc(a["score"]), esc(_team_label(g, "home")), esc(h["score"]),
               esc(status), esc(tv.channel(g) if tv else g.get("espn_tv", ""))))
    if not rows:
        rows.append('<tr><td colspan="6" class="none">No games in progress</td></tr>')
    stamp = datetime.fromtimestamp(updated).strftime("%A, %B %d, %Y \u00b7 %I:%M:%S %p") if updated else "never"
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Scores</title>
<style>
  body {{ background:#000; color:#fff; font:15px/1.4 "Segoe UI", -apple-system, Helvetica, Arial, sans-serif; margin:24px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .updated {{ color:#bbb; margin:0 0 18px; }}
  table {{ border-collapse:collapse; }}
  td, th {{ padding:4px 14px 4px 0; text-align:left; white-space:nowrap; }}
  tr.group th {{ padding-top:16px; border-bottom:1px solid #444; letter-spacing:.04em; font-size:13px; }}
  td.score {{ font-weight:700; text-align:right; padding-right:22px; font-variant-numeric:tabular-nums; }}
  td.status, td.tv {{ color:#bbb; }}
  td.none {{ color:#bbb; padding-top:12px; }}
</style></head>
<body>
<h1>Live Scores</h1>
<p class="updated">Updated {stamp} &middot; {count} game{plural} in progress</p>
<table>
{rows}
</table>
</body></html>
""".format(stamp=esc(stamp.replace(" 0", " ")), count=len(games), plural="" if len(games) == 1 else "s",
           rows="\n".join(rows))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def print_once(html_path="live_scores.html"):
    """Fetch every league once, print the live list, and save it as an HTML page."""
    cfg = load_config()
    hub = DataHub(cfg)
    feeds = [f for f in hub.feeds if cfg["enabled"].get(f.lg["key"], True)]
    pool = ThreadPoolExecutor(8)
    cities = pool.submit(refresh_shared_cities)
    guide = pool.submit(hub.tv.refresh, True) if cfg.get("show_tv", True) else None
    list(pool.map(hub._run, feeds))
    cities.result()
    if guide:
        guide.result()
    _, games = hub.snapshot()
    updated = hub.last_refresh()
    print("Updated %s  -  %d game%s in progress" % (fmt_time(updated), len(games), "" if len(games) == 1 else "s"))
    sport = None
    for g in games:
        if LEAGUE[g["league"]]["sport"] != sport:
            sport = LEAGUE[g["league"]]["sport"]
            print("\n%s" % SPORT_LABEL[sport])
        a, h = g["away"], g["home"]
        status = g["status"] + ("  (%s)" % g["extra"] if g["extra"] else "")
        line = "  %-26s %3s   %-26s %3s   %-14s" % (_team_label(g, "away"), a["score"], _team_label(g, "home"),
                                                     h["score"], status)
        if cfg.get("show_tv", True):
            line += "  %s" % hub.tv.channel(g)
        print(line)
    if not games:
        print("\nNo games in progress.")
    errs = [f.key for f in feeds if f.errors]
    if errs:
        print("\n(could not reach: %s)" % ", ".join(errs))
    write_html(html_path, games, updated, hub.tv if cfg.get("show_tv", True) else None)
    print("\nSaved %s" % os.path.abspath(html_path))


def main():
    if "--once" in sys.argv:
        path = "live_scores.html"
        if "--html" in sys.argv and sys.argv.index("--html") + 1 < len(sys.argv):
            path = sys.argv[sys.argv.index("--html") + 1]
        print_once(path)
        return
    if "--startup-on" in sys.argv or "--startup-off" in sys.argv:
        on = "--startup-on" in sys.argv
        ok = set_startup(on)
        print(("Live Ticker will start automatically when you log in." if on else
               "Live Ticker will no longer start automatically.") if ok else "Sorry, that didn't work.")
        return
    if "--version" in sys.argv:
        print(APP_NAME, VERSION)
        return
    TickerApp().run()


if __name__ == "__main__":
    main()
