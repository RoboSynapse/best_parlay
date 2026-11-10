"""Data fetching: football-data.co.uk results, ESPN fixtures, optional The Odds API prices."""
import csv
import datetime as dt
import os
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "MEX.csv"
CSV_URL = "https://www.football-data.co.uk/new/MEX.csv"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard"
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


def _stage(slug):
    slug = (slug or "").lower()
    if "play" in slug or "repechaje" in slug:
        return "playin"
    if "final" in slug or "liguilla" in slug:  # quarterfinals, semifinals, finals
        return "liguilla"
    return "regular"


def _espn(params):
    r = requests.get(ESPN_URL, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "events" not in data:
        raise ValueError(f"ESPN: no events key ({str(data)[:100]})")
    return data["events"]


def fetch_fixtures(known, days=10, today=None):
    """Upcoming (not started) fixtures in the next `days` days, with canonical team names."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    dates = [today + dt.timedelta(i) for i in range(days + 1)]
    try:
        events = _espn({"dates": f"{dates[0]:%Y%m%d}-{dates[-1]:%Y%m%d}"})
    except Exception as e:  # ESPN date ranges have been flaky (HTTP 400): fall back to one call per day
        print(f"ESPN range query failed ({e}); querying day by day")
        events = []
        for d in dates:
            try:
                events += _espn({"dates": f"{d:%Y%m%d}"})
            except Exception as e2:
                print(f"WARNING: ESPN {d}: {e2}")
    fixtures, seen = [], set()
    for e in events:
        try:
            if e["id"] in seen or e["status"]["type"]["state"] != "pre":
                continue
            seen.add(e["id"])
            teams = {c["homeAway"]: c["team"]["displayName"] for c in e["competitions"][0]["competitors"]}
            home, away = canon(teams["home"], known), canon(teams["away"], known)
            if not home or not away:
                print(f"!!! UNMAPPED ESPN TEAM NAME: {teams} -> add it to ALIASES in pipeline/fetch.py")
                continue
            kickoff = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            fixtures.append({"id": f"espn-{e['id']}", "kickoff": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "stage": _stage(e.get("season", {}).get("slug")), "home": home, "away": away})
        except (KeyError, TypeError, ValueError) as err:
            print(f"WARNING: skipping malformed ESPN event: {err}")
    fixtures.sort(key=lambda f: f["kickoff"])
    return fixtures


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
                print(f"!!! UNMAPPED ODDS API TEAM NAME: {ev['home_team']} / {ev['away_team']}")
                continue
            best, n = {}, 0
            for bk in ev.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk.get("key") != "h2h":
                        continue
                    n += 1
                    for o in mk.get("outcomes", []):
                        side = "draw" if o["name"] == "Draw" else "home" if o["name"] == ev["home_team"] else "away"
                        best[side] = max(best.get(side, 0.0), float(o["price"]))
            if len(best) == 3:
                out[(home, away)] = {**{k: round(v, 3) for k, v in best.items()}, "source": f"best-of-{n}"}
        return out
    except Exception as e:  # don't print str(e): request errors include the URL with the API key
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"WARNING: Odds API failed ({type(e).__name__}, HTTP {status}), continuing without market odds")
        return {}
