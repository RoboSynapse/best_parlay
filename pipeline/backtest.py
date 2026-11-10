"""Walk-forward backtest: weekly refit on the previous 3 years, predict the coming week.

Grid over xi and per-team home advantage; best by RPS is written to pipeline/backtest_result.json
(committed, read by build.py).  Usage: python pipeline/backtest.py
"""
import datetime as dt
import json
import time
from pathlib import Path

import numpy as np

import fetch
import model

START = dt.date(2019, 7, 1)  # a Monday
XIS = [0.0010, 0.0018, 0.0030, 0.0045, 0.0065]
OUT = Path(__file__).resolve().parent / "backtest_result.json"


def rps(p, o):
    """Ranked probability score for ordered outcomes (home, draw, away); o is a one-hot vector."""
    return 0.5 * ((np.cumsum(p, axis=-1)[..., :2] - np.cumsum(o, axis=-1)[..., :2]) ** 2).sum(-1)


def walk_forward(matches, idx, xi, team_home):
    preds, x0 = [], None
    last = matches[-1]["date"]
    week = START
    while week <= last:
        nxt = week + dt.timedelta(7)
        test = [m for m in matches if week <= m["date"] < nxt]
        if test:
            x0, _ = model.fit_matches(matches, idx, week, xi, team_home, x0)
            lam, mu = model.rates(x0, len(idx), np.array([idx[m["home"]] for m in test]),
                                  np.array([idx[m["away"]] for m in test]))
            rho = model.unpack(x0, len(idx))[2]
            preds += [(m, model.probs_1x2(l, u, rho)) for m, l, u in zip(test, lam, mu)]
        week = nxt
    return preds


def evaluate(preds):
    """Metrics on matches that have market odds (so model and market share the same sample)."""
    preds = [(m, p) for m, p in preds if m["odds"]]
    P = np.array([p for _, p in preds])
    O = np.array([[m["hg"] > m["ag"], m["hg"] == m["ag"], m["hg"] < m["ag"]] for m, _ in preds], float)
    inv = 1 / np.array([m["odds"] for m, _ in preds])
    M = inv / inv.sum(1, keepdims=True)  # de-vig by simple normalisation
    cal = []
    pp, oo = P.ravel(), O.ravel()
    b = np.minimum((pp * 10).astype(int), 9)
    for k in range(10):
        s = b == k
        if s.any():
            cal.append({"bin": round(k / 10 + 0.05, 2), "pred": round(pp[s].mean(), 4),
                        "obs": round(oo[s].mean(), 4), "n": int(s.sum())})
    return {
        "n": len(preds), "from": str(preds[0][0]["date"]), "to": str(preds[-1][0]["date"]),
        "rps_model": round(rps(P, O).mean(), 5), "rps_market": round(rps(M, O).mean(), 5),
        "logloss_model": round(-np.log((P * O).sum(1)).mean(), 5),
        "logloss_market": round(-np.log((M * O).sum(1)).mean(), 5),
        "calibration": cal,
    }


def main():
    t0 = time.time()
    matches = fetch.load_matches(download=False)
    idx = {t: i for i, t in enumerate(sorted({m["home"] for m in matches} | {m["away"] for m in matches}))}
    grid = []
    for team_home in (False, True):
        for xi in XIS:
            t = time.time()
            r = evaluate(walk_forward(matches, idx, xi, team_home))
            grid.append({"xi": xi, "team_home": team_home, **{k: v for k, v in r.items() if k != "calibration"}})
            print(f"xi={xi:.4f} team_home={team_home!s:5}  n={r['n']}  RPS {r['rps_model']:.5f} vs market "
                  f"{r['rps_market']:.5f}  logloss {r['logloss_model']:.5f} vs {r['logloss_market']:.5f}  "
                  f"({time.time() - t:.0f}s)")
            if not grid[:-1] or r["rps_model"] < best[1]["rps_model"]:
                best = ((xi, team_home), r)
    (xi, team_home), r = best
    out = {"xi": xi, "team_home": team_home, "refit": "weekly", "window_days": model.WINDOW_DAYS,
           **r, "grid": grid, "runtime_s": round(time.time() - t0)}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"best: xi={xi} team_home={team_home}; wrote {OUT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
