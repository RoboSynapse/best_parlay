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
        fetch.fetch_fixtures("mex", ["Toluca"])
    monkeypatch.setenv("ODDS_API_KEY", "SECRET123")
    def down(*a, **k):
        raise ConnectionError("https://api.example/events?apiKey=SECRET123")
    monkeypatch.setattr(fetch.requests, "get", down)
    with pytest.raises(RuntimeError) as e:  # never publish an empty fixture list over good data
        fetch.fetch_fixtures("mex", ["Toluca"])
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
        headers = {}
        def raise_for_status(self): pass
        def json(self): return events
    urls = []
    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(fetch.requests, "get", lambda url, **k: urls.append(url) or R())
    fx = fetch.fetch_fixtures("mex", ["Club America", "Toluca"], now=now)
    assert fx == [{"id": "odds-a1", "league": "mex", "kickoff": "2026-11-23T02:00:00Z", "home": "Club America", "away": "Toluca"}]
    assert urls == ["https://api.the-odds-api.com/v4/sports/soccer_mexico_ligamx/events"]
    fetch.fetch_fixtures("ger", ["Club America", "Toluca"], now=now)
    assert urls[-1] == "https://api.the-odds-api.com/v4/sports/soccer_germany_bundesliga/events"


def test_gh_annotate_cannot_be_hijacked(capsys):
    import fetch
    fetch.gh_annotate("warning", "Evil FC\n::set-output name=x::y")
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.startswith("::warning::") and out.count("::") == 2


MEX_CSV = """﻿Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA
Mexico,Liga MX,2026/2027,09/11/2026,02:10,Club Leon,Toluca,1,1,D,,,,3.6,3.6,1.9
Mexico,Liga MX,2026/2027,10/11/2026,02:10,Atlas,Puebla,,,,,,,,,
Mexico,Liga MX,2026/2027,bad,02:10,Atlas,Puebla,1,0,H,,,,,,
"""
EUR_OLD = """Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,PSCH,PSCD,PSCA
E0,13/08/16,Burnley,Swansea,0,1,A,2.4,3.3,3.3
E0,14/08/16,Man City,Sunderland,x,1,A,,,
,,,,,,,,,
"""
EUR_NEW = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,AvgCH,AvgCD,AvgCA
E0,15/08/2026,15:00,Arsenal,Wolves,3,0,H,1.3,5.5,9.0
"""


def test_parse_csv_layouts_and_dates(tmp_path):
    import datetime as dt, fetch
    for name, text in [("mex", MEX_CSV), ("old", EUR_OLD), ("new", EUR_NEW)]:
        (tmp_path / name).write_text(text, encoding="utf-8")
    mex = fetch.parse_csv(tmp_path / "mex")
    assert mex == [{"date": dt.date(2026, 11, 9), "season": "2026/2027", "home": "Club Leon", "away": "Toluca",
                    "hg": 1, "ag": 1, "odds": [3.6, 3.6, 1.9]}]  # PSC* empty -> AvgC*
    old = fetch.parse_csv(tmp_path / "old", "2016/2017")
    assert [(m["date"], m["home"], m["season"], m["odds"]) for m in old] == \
        [(dt.date(2016, 8, 13), "Burnley", "2016/2017", [2.4, 3.3, 3.3])]
    new = fetch.parse_csv(tmp_path / "new", "2026/2027")
    assert new[0]["date"] == dt.date(2026, 8, 15) and (new[0]["hg"], new[0]["ag"]) == (3, 0)


def test_load_matches_refreshes_only_the_current_season(tmp_path, monkeypatch):
    import datetime as dt, fetch
    monkeypatch.setattr(fetch, "RAW", tmp_path)
    (tmp_path / "epl").mkdir()
    for y in range(fetch.FIRST_SEASON, 2026):
        (tmp_path / "epl" / f"{y % 100:02d}{(y + 1) % 100:02d}.csv").write_text(EUR_OLD, encoding="utf-8")
    urls = []
    class R:
        content = EUR_NEW.encode()
        def raise_for_status(self): pass
    monkeypatch.setattr(fetch.requests, "get", lambda url, **k: urls.append(url) or R())
    m = fetch.load_matches("epl", today=dt.date(2026, 11, 23))
    assert urls == ["https://www.football-data.co.uk/mmz4281/2627/E0.csv"]
    assert len(m) == 2026 - fetch.FIRST_SEASON + 1 and m[-1]["home"] == "Arsenal"


def test_canon_aliases_and_fallback():
    import fetch
    epl = ["Man United", "Newcastle", "West Ham", "Nott'm Forest"]
    assert fetch.canon("Manchester United", epl) == "Man United"
    assert fetch.canon("Newcastle United", epl) == "Newcastle"  # word-subset fallback
    assert fetch.canon("Nottingham Forest", epl) == "Nott'm Forest"
    assert fetch.canon("Santos", epl) is None  # alias target not in this league
    ita = ["Inter", "Milan", "Roma"]
    assert fetch.canon("Inter Milan", ita) == "Inter" and fetch.canon("AC Milan", ita) == "Milan"
    assert fetch.canon("Milan Inter Roma", ita) is None  # ambiguous
    fra = ["Paris SG", "Paris FC"]
    assert fetch.canon("Paris Saint-Germain", fra) == "Paris SG" and fetch.canon("Paris FC", fra) == "Paris FC"
    assert fetch.canon("Paris", fra) is None


def test_merge_results_dedups_and_prefers_football_data():
    import build
    fd = [{"league": "epl", "date": "2026-11-21", "home": "Arsenal", "away": "Wolves", "hg": 3, "ag": 0}]
    sc = [{"league": "epl", "date": "2026-11-22", "home": "Arsenal", "away": "Wolves", "hg": 9, "ag": 9},  # same game, UTC date
          {"league": "esp", "date": "2026-11-22", "home": "Arsenal", "away": "Wolves", "hg": 1, "ag": 1},  # other league
          {"league": "epl", "date": "2026-11-23", "home": "Leeds", "away": "Fulham", "hg": 2, "ag": 2}]
    out = build.merge_results(fd, sc)
    assert [(r["league"], r["date"], r["hg"]) for r in out] == \
        [("epl", "2026-11-23", 2), ("esp", "2026-11-22", 1), ("epl", "2026-11-21", 3)]


def test_scores_guard_and_key_hygiene(monkeypatch, capsys):
    import fetch
    calls = []
    def boom(*a, **k):
        calls.append(1)
        raise ConnectionError("https://api.example/scores?apiKey=SECRET123")
    monkeypatch.setenv("ODDS_API_KEY", "SECRET123")
    monkeypatch.setattr(fetch.requests, "get", boom)
    assert fetch.fetch_scores("epl", ["Arsenal"], 149) == [] and fetch.fetch_scores("epl", ["Arsenal"], None) == []
    assert calls == []  # guard: no request, no credits spent
    assert fetch.fetch_scores("epl", ["Arsenal"], 400) == []  # request fails: warn, never raise
    out = capsys.readouterr().out
    assert calls == [1] and "SECRET123" not in out and "skipped /scores" in out and "scores failed" in out


def test_scores_parse(monkeypatch):
    import fetch
    events = [
        {"completed": True, "commence_time": "2026-11-22T15:00:00Z", "home_team": "Manchester United",
         "away_team": "Newcastle United", "scores": [{"name": "Newcastle United", "score": "1"},
                                                     {"name": "Manchester United", "score": "2"}]},
        {"completed": False, "commence_time": "2026-11-23T15:00:00Z", "home_team": "Man United",
         "away_team": "Newcastle", "scores": None},
        {"completed": True, "commence_time": "2026-11-22T15:00:00Z", "home_team": "Man United", "scores": None},  # malformed
    ]
    calls = []
    class R:
        headers = {}
        def raise_for_status(self): pass
        def json(self): return events
    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(fetch.requests, "get", lambda url, **k: calls.append((url, k["params"])) or R())
    assert fetch.fetch_scores("epl", ["Man United", "Newcastle"], 150) == [
        {"league": "epl", "date": "2026-11-22", "home": "Man United", "away": "Newcastle", "hg": 2, "ag": 1}]
    assert calls[0][0] == "https://api.the-odds-api.com/v4/sports/soccer_epl/scores" and calls[0][1]["daysFrom"] == 2


def test_odds_use_league_sport_key_and_eu_only(monkeypatch):
    import fetch
    ev = {"home_team": "Inter Milan", "away_team": "AC Milan", "bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Inter Milan", "price": 2.0}, {"name": "Draw", "price": 3.4}, {"name": "AC Milan", "price": 4.0}]}]}]}
    calls = []
    class R:
        headers = {"x-requests-remaining": "321"}
        def raise_for_status(self): pass
        def json(self): return [ev]
    monkeypatch.setenv("ODDS_API_KEY", "k")
    monkeypatch.setattr(fetch.requests, "get", lambda url, **k: calls.append((url, k["params"])) or R())
    odds, left = fetch.fetch_odds("ita", ["Inter", "Milan"])
    assert left == 321 and odds[("Inter", "Milan")]["fair"]["source"] == "pinnacle"
    assert calls == [("https://api.the-odds-api.com/v4/sports/soccer_italy_serie_a/odds",
                      {"apiKey": "k", "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"})]
