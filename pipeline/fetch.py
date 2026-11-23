"""Data fetching: football-data.co.uk results; The Odds API fixtures (/events) and prices (/odds)."""
import csv
import datetime as dt
import os
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "MEX.csv"
CSV_URL = "https://www.football-data.co.uk/new/MEX.csv"
EVENTS_URL = "https://api.the-odds-api.com/v4/sports/soccer_mexico_ligamx/events"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/soccer_mexico_ligamx/odds"
UA = {"User-Agent": "best_parlay/1.0 (private hobby project)"}

# Other sources' names (accent-stripped, lowercase) -> football-data.co.uk names.
ALIASES = {
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
}


def gh_annotate(level, msg):
    """Print a GitHub Actions annotation (shown on the public run page). Upstream text can't inject commands."""
    print(f"::{level}::" + str(msg).replace("\r", " ").replace("\n", " ").replace("::", ":"))


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", " ").split())


def canon(name, known):
    """Map an external team name to the football-data name, or None (caller should complain)."""
    k = _norm(name)
    return ALIASES.get(k) or {_norm(t): t for t in known}.get(k)


def _num(s):
    try:
        v = float(s)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def load_matches(download=True):
    """Return a list of played matches (dicts), oldest first. The CSV is untrusted: parse only."""
    if download or not RAW.exists():
        r = requests.get(CSV_URL, headers=UA, timeout=60)
        r.raise_for_status()
        RAW.parent.mkdir(parents=True, exist_ok=True)
        RAW.write_bytes(r.content)
    out = []
    with open(RAW, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                d = dt.datetime.strptime(row["Date"].strip(), "%d/%m/%Y").date()
                hg, ag = int(row["HG"]), int(row["AG"])
            except (KeyError, ValueError, AttributeError):
                continue  # unplayed / malformed row
            home, away = row["Home"].strip(), row["Away"].strip()
            if not home or not away or hg < 0 or ag < 0:
                continue
            odds = [_num(row.get(c)) for c in ("PSCH", "PSCD", "PSCA")]
            if None in odds:
                odds = [_num(row.get(c)) for c in ("AvgCH", "AvgCD", "AvgCA")]
            out.append({"date": d, "season": row.get("Season", ""), "home": home, "away": away,
                        "hg": hg, "ag": ag, "odds": None if None in odds else odds})
    out.sort(key=lambda m: m["date"])
    return out


def fetch_fixtures(known, days=10, now=None):
    """Not-started fixtures in the next `days` days from The Odds API /events (free: no quota cost).

    Raises without a key or on any request error, so CI fails and Pages keeps the last good deploy.
    (Replaces ESPN, whose terms forbid automated access.)"""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY is required (fixtures come from The Odds API)")
    now = now or dt.datetime.now(dt.timezone.utc)
    iso = "%Y-%m-%dT%H:%M:%SZ"
    try:
        r = requests.get(EVENTS_URL, headers=UA, timeout=30, params={
            "apiKey": key, "commenceTimeFrom": now.strftime(iso),
            "commenceTimeTo": (now + dt.timedelta(days)).strftime(iso)})
        r.raise_for_status()
        events = r.json()
    except Exception as e:  # never show str(e): it contains the URL with the API key
        status = getattr(getattr(e, "response", None), "status_code", None)
        raise RuntimeError(f"Odds API events failed ({type(e).__name__}, HTTP {status})") from None
    fixtures = []
    for ev in events:
        try:
            kickoff = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            if kickoff <= now:  # /events also lists games in play
                continue
            home, away = canon(ev["home_team"], known), canon(ev["away_team"], known)
            if not home or not away:
                gh_annotate("warning", f"Unmapped team name (fixture dropped): {ev['home_team']} / {ev['away_team']} -> add it to ALIASES")
                continue
            fixtures.append({"id": f"odds-{ev['id']}", "kickoff": kickoff.strftime(iso), "home": home, "away": away})
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


def fetch_odds(known):
    """{(home, away): market dict} from The Odds API (one request), or {} without a key / on error."""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        return {}
    try:
        r = requests.get(ODDS_URL, headers=UA, timeout=30, params={
            "apiKey": key, "regions": "us,eu,uk", "markets": "h2h", "oddsFormat": "decimal"})
        r.raise_for_status()
        print(f"Odds API requests remaining: {r.headers.get('x-requests-remaining')}")
        out = {}
        for ev in r.json():
            home, away = canon(ev["home_team"], known), canon(ev["away_team"], known)
            if not home or not away:
                gh_annotate("warning", f"Unmapped team name (odds dropped): {ev['home_team']} / {ev['away_team']}")
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
        return out
    except Exception as e:  # don't print str(e): request errors include the URL with the API key
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"WARNING: Odds API failed ({type(e).__name__}, HTTP {status}), continuing without market odds")
        return {}
