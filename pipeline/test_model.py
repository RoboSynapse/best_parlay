import numpy as np
from scipy.optimize import check_grad

import model


def test_grid_sums_to_one():
    for lam, mu, rho in [(1.5, 1.1, -0.1), (2.8, 0.6, 0.1), (0.4, 0.4, 0.0)]:
        g = model.score_grid(lam, mu, rho)
        assert abs(g.sum() - 1) < 1e-3  # truncation at 10 goals; tau moves mass between low scores, never creates it
        assert abs(model.probs_1x2(lam, mu, rho).sum() - 1) < 1e-12


def test_tau_correction():
    base = model.score_grid(1.3, 1.0, 0.0)
    g = model.score_grid(1.3, 1.0, -0.1)  # negative rho: more 0-0 and 1-1, fewer 1-0 and 0-1
    assert g[0, 0] > base[0, 0] and g[1, 1] > base[1, 1]
    assert g[1, 0] < base[1, 0] and g[0, 1] < base[0, 1]
    assert np.allclose(g[2:, :], base[2:, :]) and np.allclose(g[:, 2:], base[:, 2:])
    assert model.probs_1x2(1.3, 1.0, -0.1)[1] > model.probs_1x2(1.3, 1.0, 0.0)[1]


def _synthetic(n=12, seasons=6, seed=0):
    rng = np.random.default_rng(seed)
    att, dfc = rng.normal(0, 0.3, n), rng.normal(0, 0.2, n)
    att -= att.mean(); dfc -= dfc.mean()
    hi, ai = [], []
    for _ in range(seasons):
        for i in range(n):
            for j in range(n):
                if i != j:
                    hi.append(i); ai.append(j)
    hi, ai = np.array(hi), np.array(ai)
    true = np.concatenate([[0.1, 0.3, -0.08], att, dfc, np.zeros(n)])
    lam, mu = model.rates(true, n, hi, ai)
    return hi, ai, rng.poisson(lam), rng.poisson(mu), true


def test_gradient():
    n = 6
    hi, ai, x, y, _ = _synthetic(n, 1)
    w = np.linspace(0.5, 1, len(x))
    p = np.random.default_rng(1).normal(0, 0.2, 3 + 3 * n)
    err = check_grad(lambda q: model.objective(q, n, hi, ai, x, y, w)[0],
                     lambda q: model.objective(q, n, hi, ai, x, y, w)[1], p)
    assert err < 1e-3


def test_fit_recovers_params():
    n = 12
    hi, ai, x, y, true = _synthetic(n, seasons=20)
    p = model.fit(hi, ai, x, y, np.zeros(len(x)), n, xi=0.0, team_home=False)
    c, h, rho, att, dfc, _ = model.unpack(p, n)
    _, th, _, tatt, tdfc, _ = model.unpack(true, n)
    assert abs(h - th) < 0.1
    assert abs(rho - -0.08) < 0.1
    assert np.corrcoef(att, tatt)[0, 1] > 0.9 and np.corrcoef(dfc, tdfc)[0, 1] > 0.8
    assert np.abs((att - att.mean()) - tatt).max() < 0.15


def test_fair_probs_prefers_pinnacle():
    import fetch
    pin = {"home": 2.0, "draw": 3.5, "away": 4.0}
    f = fetch.fair_probs({"pinnacle": pin, "soft": {"home": 1.8, "draw": 3.2, "away": 3.6}})
    assert f["source"] == "pinnacle" and abs(f["home"] + f["draw"] + f["away"] - 1) < 1e-3
    assert abs(f["home"] - (1 / 2.0) / (1 / 2.0 + 1 / 3.5 + 1 / 4.0)) < 1e-4
    assert fetch.fair_probs({"a": pin, "b": pin})["source"] == "consensus-2"


def test_fixtures_fail_loudly_without_leaking_the_key(monkeypatch):
    import fetch, pytest
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        fetch.fetch_fixtures(["Toluca"])
    monkeypatch.setenv("ODDS_API_KEY", "SECRET123")
    def down(*a, **k):
        raise ConnectionError("https://api.example/events?apiKey=SECRET123")
    monkeypatch.setattr(fetch.requests, "get", down)
    with pytest.raises(RuntimeError) as e:  # never publish an empty fixture list over good data
        fetch.fetch_fixtures(["Toluca"])
    assert "SECRET123" not in str(e.value) and e.value.__suppress_context__


def test_fixtures_parse_events(monkeypatch):
    import datetime as dt, fetch
    now = dt.datetime(2026, 11, 22, 12, tzinfo=dt.timezone.utc)
    events = [
        {"id": "a1", "commence_time": "2026-11-23T02:00:00Z", "home_team": "Club America", "away_team": "Toluca"},
        {"id": "b2", "commence_time": "2026-11-22T11:00:00Z", "home_team": "Toluca", "away_team": "Club America"},  # in play
        {"id": "c3", "commence_time": "2026-11-24T02:00:00Z", "home_team": "Nowhere FC", "away_team": "Toluca"},  # unmapped
        {"id": "d4"},  # malformed
    ]
    class R:
        def raise_for_status(self): pass
        def json(self): return events
    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: R())
    fx = fetch.fetch_fixtures(["Club America", "Toluca"], now=now)
    assert fx == [{"id": "odds-a1", "kickoff": "2026-11-23T02:00:00Z", "home": "Club America", "away": "Toluca"}]


def test_gh_annotate_cannot_be_hijacked(capsys):
    import fetch
    fetch.gh_annotate("warning", "Evil FC\n::set-output name=x::y")
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.startswith("::warning::") and out.count("::") == 2
