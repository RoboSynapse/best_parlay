"""CI entry point: fetch data, fit each league with its backtested settings, write web/data/predictions.json.

Usage: ODDS_API_KEY=... python pipeline/build.py   (the key is required: fixtures and odds come from The Odds API)
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np

import fetch
import model

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "predictions.json"
BACKTESTS = Path(__file__).resolve().parent / "backtests"
BT_KEYS = ["n", "from", "to", "rps_model", "rps_market", "logloss_model", "logloss_market", "calibration"]
RESULT_DAYS = 10


def same_game(a, b):
    """Same league and teams, dates within a day (football-data dates are UK-local, /scores dates UTC)."""
    return (a["league"], a["home"], a["away"]) == (b["league"], b["home"], b["away"]) and \
        abs((dt.date.fromisoformat(a["date"][:10]) - dt.date.fromisoformat(b["date"][:10])).days) <= 1


def merge_results(fd, scores):
    """football-data rows first so they win over /scores duplicates; newest first."""
    out = []
    for r in fd + scores:
        if not any(same_game(r, o) for o in out):
            out.append(r)
    return sorted(out, key=lambda r: r["date"], reverse=True)


def league_block(code, today):
    """Fit one league; returns (leagues entry, fixtures, football-data results, known names, odds credits left)."""
    bt = json.loads((BACKTESTS / f"{code}.json").read_text())
    xi, team_home = bt["xi"], bt["team_home"]
    matches = fetch.load_matches(code)
    known = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {t: i for i, t in enumerate(known)}
    print(f"{code}: {len(matches)} matches, last {matches[-1]['date']}")

    # fit on everything up to and including today (as_of = tomorrow)
    p, n_fit = model.fit_matches(matches, idx, today + dt.timedelta(1), xi, team_home)
    _, h, rho, *_ = model.unpack(p, len(idx))

    fixtures = fetch.fetch_fixtures(code, known)
    odds, credits = fetch.fetch_odds(code, known) if fixtures else ({}, None)
    for f in fixtures:
        lam, mu = model.rates(p, len(idx), np.array([idx[f["home"]]]), np.array([idx[f["away"]]]))
        f.update({"lambda": round(float(lam[0]), 4), "mu": round(float(mu[0]), 4), "rho": round(float(rho), 4),
                  "market": odds.get((f["home"], f["away"]))})
    fetch.gh_annotate("notice", f"{code}: {len(fixtures)} fixtures, {sum(f['market'] is not None for f in fixtures)} with odds")
    results = [{"league": code, "date": m["date"].isoformat(), "home": m["home"], "away": m["away"],
                "hg": m["hg"], "ag": m["ag"]} for m in matches if m["date"] >= today - dt.timedelta(RESULT_DAYS)]
    league = {"code": code, "name": fetch.LEAGUES[code][0],
              "model": {"name": "dixon-coles", "xi": xi, "rho": round(float(rho), 4), "home_adv": round(float(h), 4),
                        "n_matches": n_fit},
              "backtest": {k: bt[k] for k in BT_KEYS}}
    return league, fixtures, results, known, credits


def top_up(fd_results, knowns, credits, now):
    """/scores for leagues whose last published fixtures kicked off in the last 48 h and aren't in football-data yet."""
    recent = set()
    for f in fetch.fetch_published():
        try:
            kick = dt.datetime.fromisoformat(f["kickoff"].replace("Z", "+00:00"))
            g = {"league": f["league"], "home": f["home"], "away": f["away"], "date": f["kickoff"][:10]}
            if f["league"] in knowns and now - dt.timedelta(hours=48) <= kick <= now and \
                    not any(same_game(g, r) for r in fd_results):
                recent.add(f["league"])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return [r for code in sorted(recent) for r in fetch.fetch_scores(code, knowns[code], credits)]


def main():
    now = dt.datetime.now(dt.timezone.utc)
    leagues, fixtures, fd_results, knowns, credits = [], [], [], {}, []
    for code in fetch.LEAGUES:
        league, fx, res, knowns[code], c = league_block(code, now.date())
        leagues.append(league)
        fixtures += fx
        fd_results += res
        if c is not None:
            credits.append(c)
    scores = top_up(fd_results, knowns, min(credits, default=None), now)

    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "leagues": leagues,
        "fixtures": sorted(fixtures, key=lambda f: f["kickoff"]),
        "results": merge_results(fd_results, scores),
    }
    write(out, OUT)


def write(out, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"wrote {path}: {len(out['fixtures'])} fixtures, {len(out['results'])} results")


if __name__ == "__main__":
    main()
