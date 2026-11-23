"""Data fetching: football-data.co.uk results; The Odds API fixtures (/events), prices (/odds) and scores (/scores)."""
import csv
import datetime as dt
import os
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
API = "https://api.the-odds-api.com/v4/sports"
PUBLISHED_URL = "https://robosynapse.github.io/best_parlay/data/predictions.json"
UA = {"User-Agent": "best_parlay/1.0 (private hobby project)"}
FIRST_SEASON = 2016  # 2016/17: the backtest starts 2019-07 with a 3-year training window
SCORES_MIN_CREDITS = 150

# code -> (name, football-data file, Odds API sport key). "MEX" is the all-seasons file; others are per-season.
LEAGUES = {
    "mex": ("Liga MX", "MEX", "soccer_mexico_ligamx"),
    "epl": ("Premier League", "E0", "soccer_epl"),
    "esp": ("LaLiga", "SP1", "soccer_spain_la_liga"),
    "ger": ("Bundesliga", "D1", "soccer_germany_bundesliga"),
    "ita": ("Serie A", "I1", "soccer_italy_serie_a"),
    "fra": ("Ligue 1", "F1", "soccer_france_ligue_one"),
}

# Other sources' names (normalised by _norm) -> football-data.co.uk names. Only used when the target is a
# known team of the league being mapped, so one global dict is safe. canon() also has a word-subset fallback.
ALIASES = {
    # Liga MX
    "america": "Club America", "club america": "Club America", "cf america": "Club America",
    "leon": "Club Leon", "club leon": "Club Leon",
    "guadalajara": "Guadalajara Chivas", "chivas": "Guadalajara Chivas",
    "chivas guadalajara": "Guadalajara Chivas", "cd guadalajara": "Guadalajara Chivas",
    "fc juarez": "Juarez", "juarez": "Juarez",
    "tijuana": "Club Tijuana", "xolos": "Club Tijuana",
    "santos": "Santos Laguna",
    "pumas unam": "UNAM Pumas", "pumas": "UNAM Pumas", "unam": "UNAM Pumas",
    "atletico de san luis": "Atl. San Luis", "atletico san luis": "Atl. San Luis", "san luis": "Atl. San Luis",
    "tigres": "Tigres UANL",
    "mazatlan": "Mazatlan FC",
    "atlante fc": "Atlante",
    "cf monterrey": "Monterrey", "cf pachuca": "Pachuca", "deportivo toluca": "Toluca",
    "queretaro fc": "Queretaro", "club puebla": "Puebla", "club necaxa": "Necaxa", "atlas fc": "Atlas",
    # Premier League
    "manchester united": "Man United", "manchester city": "Man City", "nottingham forest": "Nott'm Forest",
    "wolverhampton wanderers": "Wolves", "wolverhampton": "Wolves", "west bromwich albion": "West Brom",
    "sheffield utd": "Sheffield United",
    # LaLiga
    "atletico madrid": "Ath Madrid", "club atletico de madrid": "Ath Madrid", "athletic bilbao": "Ath Bilbao",
    "athletic club": "Ath Bilbao", "espanyol": "Espanol", "rcd espanyol": "Espanol", "sporting gijon": "Sp Gijon",
    # Bundesliga
    "eintracht frankfurt": "Ein Frankfurt", "borussia monchengladbach": "M'gladbach",
    "borussia moenchengladbach": "M'gladbach", "monchengladbach": "M'gladbach", "hamburger sv": "Hamburg",
    "1 fc cologne": "FC Koln", "fc cologne": "FC Koln",
    # Serie A
    "inter milan": "Inter", "internazionale": "Inter", "fc internazionale": "Inter", "ac milan": "Milan",
    "chievo verona": "Chievo",
    # Ligue 1
    "paris saint germain": "Paris SG", "psg": "Paris SG", "saint etienne": "St Etienne",
    "as saint etienne": "St Etienne", "olympique lyonnais": "Lyon", "stade rennais": "Rennes",
    "stade rennais fc": "Rennes",
}


def gh_annotate(level, msg):
    """Print a GitHub Actions annotation (shown on the public run page). Upstream text can't inject commands."""
    print(f"::{level}::" + str(msg).replace("\r", " ").replace("\n", " ").replace("::", ":"))


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", " ").replace("-", " ").split())


def canon(name, known):
    """Map an external team name to a known football-data name, or None (caller should complain).

    Fallback: the one known name whose words are all in the external name ("Newcastle United" -> "Newcastle");
    ambiguous ("Inter Milan" -> Inter or Milan) -> None."""
    k = _norm(name)
    if ALIASES.get(k) in known:
        return ALIASES[k]
    by_norm = {_norm(t): t for t in known}
    if k in by_norm:
        return by_norm[k]
    words = set(k.split())
    hits = [t for n, t in by_norm.items() if set(n.split()) <= words]
    return hits[0] if len(hits) == 1 else None


def _num(s):
    try:
        v = float(s)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _date(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):  # dd/mm/yy up to 2016/17
        try:
            return dt.datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    raise ValueError(s)


def _download(url, path, refresh):
    """Cache url at path; re-download only when refresh. Raises on HTTP errors (CI fails, last deploy stays)."""
    if refresh or not path.exists():
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)


def parse_csv(path, season=""):
    """Played matches from one football-data CSV (both layouts). The CSV is untrusted: parse only."""
    out = []
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            try:
                d = _date(row["Date"])
                hg, ag = int(row.get("HG") or row["FTHG"]), int(row.get("AG") or row["FTAG"])
                home, away = (row.get("Home") or row["HomeTeam"]).strip(), (row.get("Away") or row["AwayTeam"]).strip()
            except (KeyError, ValueError, AttributeError, TypeError):
                continue  # unplayed / malformed row
            if not home or not away or hg < 0 or ag < 0:
                continue
            odds = [_num(row.get(c)) for c in ("PSCH", "PSCD", "PSCA")]
            if None in odds:
                odds = [_num(row.get(c)) for c in ("AvgCH", "AvgCD", "AvgCA")]
            out.append({"date": d, "season": row.get("Season") or season, "home": home, "away": away,
                        "hg": hg, "ag": ag, "odds": None if None in odds else odds})
    return out


def load_matches(league, download=True, today=None):
    """Played matches of a league (dicts), oldest first. download=True refreshes only the current season's file."""
    src = LEAGUES[league][1]
    if src == "MEX":
        path = RAW / league / "MEX.csv"
        _download("https://www.football-data.co.uk/new/MEX.csv", path, download)
        out = parse_csv(path)
    else:
        today = today or dt.date.today()
        cur = today.year if today.month >= 7 else today.year - 1
        out = []
        for y in range(FIRST_SEASON, cur + 1):
            yyzz = f"{y % 100:02d}{(y + 1) % 100:02d}"
            path = RAW / league / f"{yyzz}.csv"
            try:
                _download(f"https://www.football-data.co.uk/mmz4281/{yyzz}/{src}.csv", path, download and y == cur)
            except requests.HTTPError as e:
                if y != cur or e.response is None or e.response.status_code != 404:
                    raise
                gh_annotate("notice", f"{league}: no {yyzz} season file yet")  # July, before the new file appears
                continue
            out += parse_csv(path, f"{y}/{y + 1}")
    out.sort(key=lambda m: m["date"])
    return out


def _api_get(league, endpoint, what, **params):
    """GET an Odds API endpoint for the league's sport. Errors never show str(e): it has the URL with the key."""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError(f"ODDS_API_KEY is required ({what})")
    try:
        r = requests.get(f"{API}/{LEAGUES[league][2]}/{endpoint}", headers=UA, timeout=30,
                         params={"apiKey": key, **params})
        r.raise_for_status()
        return r.json(), r.headers.get("x-requests-remaining")
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        raise RuntimeError(f"Odds API {endpoint} failed for {league} ({type(e).__name__}, HTTP {status})") from None


def fetch_fixtures(league, known, days=10, now=None):
    """Not-started fixtures in the next `days` days from The Odds API /events (free: no quota cost).

    Raises without a key or on any request error, so CI fails and Pages keeps the last good deploy."""
    now = now or dt.datetime.now(dt.timezone.utc)
    iso = "%Y-%m-%dT%H:%M:%SZ"
    events, _ = _api_get(league, "events", "fixtures come from The Odds API", commenceTimeFrom=now.strftime(iso),
                         commenceTimeTo=(now + dt.timedelta(days)).strftime(iso))
    fixtures = []
    for ev in events:
        try:
            kickoff = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            if kickoff <= now:  # /events also lists games in play
                continue
            home, away = canon(ev["home_team"], known), canon(ev["away_team"], known)
            if not home or not away:
                gh_annotate("warning", f"{league}: unmapped team name (fixture dropped): {ev['home_team']} / {ev['away_team']} -> add it to ALIASES")
                continue
            fixtures.append({"id": f"odds-{ev['id']}", "league": league, "kickoff": kickoff.strftime(iso),
                             "home": home, "away": away})
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            print(f"WARNING: skipping malformed Odds API event: {err!r}")
    fixtures.sort(key=lambda f: f["kickoff"])
    return fixtures


def devig(prices):
    inv = {k: 1 / v for k, v in prices.items()}
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()}


def fair_probs(books):
    """Margin-free 1X2 probabilities: Pinnacle if it priced the match, else the mean over all books."""
    if "pinnacle" in books:
        p, src = devig(books["pinnacle"]), "pinnacle"
    else:
        ps = [devig(b) for b in books.values()]
        p, src = {k: sum(d[k] for d in ps) / len(ps) for k in ("home", "draw", "away")}, f"consensus-{len(ps)}"
    return {**{k: round(v, 4) for k, v in p.items()}, "source": src}


def _credits(h):
    try:
        return int(float(h))
    except (TypeError, ValueError):
        return None


def fetch_odds(league, known):
    """({(home, away): market dict}, credits remaining or None) from /odds (1 credit: eu region, h2h).

    ({}, None) without a key / on error: odds are optional."""
    try:
        events, remaining = _api_get(league, "odds", "odds", regions="eu", markets="h2h", oddsFormat="decimal")
    except RuntimeError as e:
        print(f"WARNING: {e}, continuing without market odds")
        return {}, None
    print(f"Odds API requests remaining: {remaining}")
    out = {}
    try:
        for ev in events:
            home, away = canon(ev["home_team"], known), canon(ev["away_team"], known)
            if not home or not away:
                gh_annotate("warning", f"{league}: unmapped team name (odds dropped): {ev['home_team']} / {ev['away_team']}")
                continue
            best, books = {}, {}
            for bk in ev.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk.get("key") != "h2h":
                        continue
                    prices = {}
                    for o in mk.get("outcomes", []):
                        side = "draw" if o["name"] == "Draw" else "home" if o["name"] == ev["home_team"] else "away"
                        prices[side] = float(o["price"])
                    if len(prices) == 3 and all(1 < v < 1000 for v in prices.values()):  # drops inf/NaN junk
                        books[bk["key"]] = prices
                        for side, p in prices.items():
                            best[side] = max(best.get(side, 0.0), p)
            if books:
                out[(home, away)] = {**{k: round(v, 3) for k, v in best.items()},
                                     "source": f"best-of-{len(books)}", "fair": fair_probs(books)}
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        print(f"WARNING: malformed Odds API odds for {league} ({type(err).__name__}), continuing without market odds")
        return {}, _credits(remaining)
    return out, _credits(remaining)


def fetch_scores(league, known, remaining):
    """Completed results of the last 2 days from /scores (2 credits), or [] (never fails the build).

    Skipped unless `remaining` credits (seen on /odds this run) >= SCORES_MIN_CREDITS."""
    if remaining is None or remaining < SCORES_MIN_CREDITS:
        gh_annotate("notice", f"{league}: skipped /scores top-up ({remaining} credits left, need {SCORES_MIN_CREDITS})")
        return []
    try:
        events, _ = _api_get(league, "scores", "scores", daysFrom=2, dateFormat="iso")
    except RuntimeError as e:
        gh_annotate("warning", f"{e}, continuing without the results top-up")
        return []
    out = []
    for ev in events:
        try:
            if not ev.get("completed"):
                continue
            goals = {s["name"]: int(s["score"]) for s in ev["scores"]}
            home, away = canon(ev["home_team"], known), canon(ev["away_team"], known)
            if not home or not away:
                gh_annotate("warning", f"{league}: unmapped team name (result dropped): {ev['home_team']} / {ev['away_team']}")
                continue
            out.append({"league": league, "date": dt.date.fromisoformat(ev["commence_time"][:10]).isoformat(), "home": home, "away": away,
                        "hg": goals[ev["home_team"]], "ag": goals[ev["away_team"]]})
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            print(f"WARNING: skipping malformed Odds API score: {err!r}")
    return out


def fetch_published():
    """Fixtures of the currently deployed predictions.json, or [] on any failure (old format: Liga MX only)."""
    try:
        r = requests.get(PUBLISHED_URL, headers=UA, timeout=20)
        r.raise_for_status()
        fx = r.json()["fixtures"]
        return [{**f, "league": f.get("league", "mex")} for f in fx if isinstance(f, dict)]
    except Exception as e:
        print(f"WARNING: could not read the published predictions ({type(e).__name__}); no results top-up")
        return []
