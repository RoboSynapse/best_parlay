"""CI entry point: fetch data, fit with the backtested settings, write web/data/predictions.json.

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
    _, h, rho, *_ = model.unpack(p, len(idx))

    fixtures = fetch.fetch_fixtures(known)
    odds = fetch.fetch_odds(known) if fixtures else {}
    print(f"{len(fixtures)} upcoming fixtures, {len(odds)} with market odds")
    for f in fixtures:
        lam, mu = model.rates(p, len(idx), np.array([idx[f["home"]]]), np.array([idx[f["away"]]]))
        f.update({"lambda": round(float(lam[0]), 4), "mu": round(float(mu[0]), 4), "rho": round(float(rho), 4),
                  "market": odds.get((f["home"], f["away"]))})

    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "league": "Liga MX",
        "model": {"name": "dixon-coles", "xi": xi, "rho": round(float(rho), 4), "home_adv": round(float(h), 4),
                  "n_matches": n_fit},
        "backtest": {k: bt[k] for k in BT_KEYS},
        "fixtures": fixtures,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"wrote {OUT}: rho={rho:.3f} home_adv={h:.3f} n_matches={n_fit}")


if __name__ == "__main__":
    main()
