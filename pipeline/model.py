"""Dixon-Coles with exponential time decay, global + (optional, shrunk) per-team home advantage.

log lambda (home goals) = c + home + hdev[h] + att[h] + dfc[a]
log mu     (away goals) = c + att[a] + dfc[h]
dfc is "goals conceded" strength: negative = good defence.
Params are a flat vector [c, home, rho, att(n), dfc(n), hdev(n)]. Ridge priors make it identifiable.
"""
import math

import numpy as np
from scipy.optimize import minimize

SD_TEAM = 0.5    # ridge prior sd for attack/defence
SD_HOME = 0.15   # ridge prior sd for per-team home deviation
MAX_GOALS = 10
_LOGFACT = np.array([math.lgamma(k + 1) for k in range(MAX_GOALS + 1)])


def unpack(p, n):
    return p[0], p[1], p[2], p[3:3 + n], p[3 + n:3 + 2 * n], p[3 + 2 * n:3 + 3 * n]


def rates(p, n, hi, ai):
    c, h, _, att, dfc, hd = unpack(p, n)
    return np.exp(c + h + hd[hi] + att[hi] + dfc[ai]), np.exp(c + att[ai] + dfc[hi])


def objective(p, n, hi, ai, x, y, w):
    """Weighted negative log-likelihood + ridge penalty, and its gradient."""
    c, h, rho, att, dfc, hd = unpack(p, n)
    lam, mu = rates(p, n, hi, ai)
    m00, m01, m10, m11 = (x == 0) & (y == 0), (x == 0) & (y == 1), (x == 1) & (y == 0), (x == 1) & (y == 1)
    lm = lam * mu
    tau = np.select([m00, m01, m10, m11], [1 - lm * rho, 1 + lam * rho, 1 + mu * rho, 1 - rho + 0 * lam], 1.0)
    tau = np.maximum(tau, 1e-10)
    ll = np.log(tau) + x * np.log(lam) - lam + y * np.log(mu) - mu
    # d log tau / d log lam, d log mu, d rho
    ta = np.select([m00, m01], [-lm * rho, lam * rho], 0.0) / tau
    tb = np.select([m00, m10], [-lm * rho, mu * rho], 0.0) / tau
    tr = np.select([m00, m01, m10, m11], [-lm, lam, mu, -1 + 0 * lam], 0.0) / tau
    ga, gb = w * (x - lam + ta), w * (y - mu + tb)
    s2, h2 = SD_TEAM ** 2, SD_HOME ** 2
    f = -(w * ll).sum() + 0.5 * ((att ** 2).sum() + (dfc ** 2).sum()) / s2 + 0.5 * (hd ** 2).sum() / h2
    g = np.concatenate([
        [-(ga.sum() + gb.sum()), -ga.sum(), -(w * tr).sum()],
        -(np.bincount(hi, ga, n) + np.bincount(ai, gb, n)) + att / s2,
        -(np.bincount(ai, ga, n) + np.bincount(hi, gb, n)) + dfc / s2,
        -np.bincount(hi, ga, n) + hd / h2,
    ])
    return f, g


def fit(hi, ai, x, y, days_ago, n, xi, team_home, x0=None):
    """Fit params on matches (team index arrays, goals, age in days). Returns the param vector."""
    hi, ai = np.asarray(hi), np.asarray(ai)
    x, y = np.asarray(x, float), np.asarray(y, float)
    w = np.exp(-xi * np.asarray(days_ago, float))
    if x0 is None:
        x0 = np.zeros(3 + 3 * n)
        x0[0], x0[1], x0[2] = 0.2, 0.3, -0.05
    bounds = [(None, None), (None, None), (-0.2, 0.2)] + [(None, None)] * (2 * n) + \
             [(None, None) if team_home else (0.0, 0.0)] * n
    res = minimize(objective, x0, args=(n, hi, ai, x, y, w), jac=True, method="L-BFGS-B",
                   bounds=bounds, options={"maxiter": 1000})
    return res.x


WINDOW_DAYS = 3 * 365  # training window


def fit_matches(matches, idx, as_of, xi, team_home, x0=None):
    """Fit on matches with as_of - WINDOW_DAYS <= date < as_of. idx: team name -> index."""
    tr = [m for m in matches if 0 < (as_of - m["date"]).days <= WINDOW_DAYS]
    p = fit([idx[m["home"]] for m in tr], [idx[m["away"]] for m in tr], [m["hg"] for m in tr],
            [m["ag"] for m in tr], [(as_of - m["date"]).days for m in tr], len(idx), xi, team_home, x0)
    return p, len(tr)


def score_grid(lam, mu, rho, max_goals=MAX_GOALS):
    """P(home=i, away=j) for i, j in 0..max_goals (not renormalised)."""
    k = np.arange(max_goals + 1)
    px = np.exp(k * math.log(lam) - lam - _LOGFACT[:max_goals + 1])
    py = np.exp(k * math.log(mu) - mu - _LOGFACT[:max_goals + 1])
    g = np.outer(px, py)
    g[0, 0] *= 1 - lam * mu * rho
    g[0, 1] *= 1 + lam * rho
    g[1, 0] *= 1 + mu * rho
    g[1, 1] *= 1 - rho
    return g


def probs_1x2(lam, mu, rho):
    g = score_grid(lam, mu, rho)
    p = np.array([np.tril(g, -1).sum(), np.trace(g), np.triu(g, 1).sum()])
    return p / p.sum()
