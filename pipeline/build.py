"""CI entry point: fetch data, fit with the backtested settings, write web/data/predictions.json.

Usage: python pipeline/build.py   (set ODDS_API_KEY to include market odds)
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np

import fetch
import model

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "predictions.json"
BACKTEST = Path(__file__).resolve().parent / "backtest_result.json"
BT_KEYS = ["n", "from", "to", "rps_model", "rps_market", "logloss_model", "logloss_market", "calibration"]


def main():
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    bt = json.loads(BACKTEST.read_text())
    xi, team_home = bt["xi"], bt["team_home"]

    matches = fetch.load_matches()
    known = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {t: i for i, t in enumerate(known)}
    print(f"{len(matches)} matches, last {matches[-1]['date']}")

    # fit on everything up to and including today (as_of = tomorrow)
    p, n_fit = model.fit_matches(matches, idx, today + dt.timedelta(1), xi, team_home)
    c, h, rho, att, dfc, hd = model.unpack(p, len(idx))

    fixtures = fetch.fetch_fixtures(known)
    odds = fetch.fetch_odds(known) if fixtures else {}
    print(f"{len(fixtures)} upcoming fixtures, {len(odds)} with market odds")
    for f in fixtures:
        lam, mu = model.rates(p, len(idx), np.array([idx[f["home"]]]), np.array([idx[f["away"]]]))
        lam, mu = float(lam[0]), float(mu[0])
        ph, pd_, pa = model.probs_1x2(lam, mu, rho)
        f.update({"lambda": round(lam, 4), "mu": round(mu, 4), "rho": round(float(rho), 4),
                  "p": {"home": round(ph, 4), "draw": round(pd_, 4), "away": round(pa, 4)},
                  "market": odds.get((f["home"], f["away"]))})

    season = max(m["season"] for m in matches)
    current = sorted({t for m in matches if m["season"] == season for t in (m["home"], m["away"])}
                     | {t for f in fixtures for t in (f["home"], f["away"])})
    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "league": "Liga MX",
        "model": {"name": "dixon-coles", "xi": xi, "rho": round(float(rho), 4), "home_adv": round(float(h), 4),
                  "n_matches": n_fit},
        "backtest": {k: bt[k] for k in BT_KEYS},
        "teams": [{"name": t, "attack": round(float(att[idx[t]]), 4), "defence": round(float(dfc[idx[t]]), 4),
                   "home": round(float(h + hd[idx[t]]), 4)} for t in current],
        "fixtures": fixtures,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}: rho={rho:.3f} home_adv={h:.3f} n_matches={n_fit}")


if __name__ == "__main__":
    main()
