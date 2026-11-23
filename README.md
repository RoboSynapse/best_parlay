# best_parlay

Match probabilities (Dixon–Coles) and a parlay builder for Liga MX and the top-5 European leagues, as a PWA for a handful
of friends. Free stack only: football-data.co.uk (results and historical closing odds) + The Odds API free tier (fixtures via
`/events`, which is free; odds via `/odds`; recent scores via `/scores`; set the `ODDS_API_KEY` repo secret, it is required),
GitHub Actions, GitHub Pages. Personal, non-commercial, 18+; see the app's Aviso.

```
pipeline/   Python: fetch data, fit one model per league, walk-forward backtest, write web/data/predictions.json
web/        PWA (vanilla HTML/CSS/JS, no build step), served by GitHub Pages
.github/    one workflow: run pipeline on a schedule, deploy web/ to Pages
```

## Leagues

| code | league | football-data.co.uk | The Odds API sport |
|------|--------|---------------------|--------------------|
| `mex` | Liga MX | `new/MEX.csv` (all seasons) | `soccer_mexico_ligamx` |
| `epl` | Premier League | `mmz4281/{YYZZ}/E0.csv` | `soccer_epl` |
| `esp` | LaLiga | `mmz4281/{YYZZ}/SP1.csv` | `soccer_spain_la_liga` |
| `ger` | Bundesliga | `mmz4281/{YYZZ}/D1.csv` | `soccer_germany_bundesliga` |
| `ita` | Serie A | `mmz4281/{YYZZ}/I1.csv` | `soccer_italy_serie_a` |
| `fra` | Ligue 1 | `mmz4281/{YYZZ}/F1.csv` | `soccer_france_ligue_one` |

European season files are loaded from 2016/17 (the backtest starts 2019-07 with a 3-year training window). CSVs are cached
in `data/raw/<code>/` (gitignored; CI keeps it in `actions/cache`); only the current season's file and `MEX.csv` are
re-downloaded. Each league has its own backtest, `python pipeline/backtest.py <code>` → `pipeline/backtests/<code>.json`
(committed; `build.py` reads `xi` and `team_home` from it).

Note: Pinnacle closing odds (`PSCH/PSCD/PSCA`) stopped appearing in football-data files in late 2025 / January 2026, so for recent
matches the backtest's market column falls back to average closing odds (`AvgCH/AvgCD/AvgCA`).

## Odds API quota (free plan: 500 credits/month)

- `/events` (fixtures): free.
- `/odds`, `regions=eu` (includes Pinnacle), h2h: 1 credit per league with fixtures → 6/day ≈ 180/month.
- `/scores?daysFrom=2`: 2 credits per league, only for leagues whose previously published fixtures kicked off in the last
  48 h and are not in football-data yet, and only while ≥ 150 credits remain → ~2 per league with recent matches per day.
- Every push to `main` runs the build too: up to 6 more credits (plus any `/scores`).

## Data contract: `web/data/predictions.json`

The pipeline writes it; the app only reads it. The app builds score grids on-device from `lambda`, `mu`, `rho`.

```json
{
  "generated_at": "2026-11-23T13:30:00Z",
  "leagues": [
    {
      "code": "epl", "name": "Premier League",
      "model": { "name": "dixon-coles", "xi": 0.003, "rho": -0.059, "home_adv": 0.198, "n_matches": 1120 },
      "backtest": {
        "n": 2760, "from": "2019-08-09", "to": "2026-11-08",
        "rps_model": 0.2033, "rps_market": 0.1971, "logloss_model": 0.985, "logloss_market": 0.966,
        "calibration": [ { "bin": 0.35, "pred": 0.352, "obs": 0.341, "n": 410 } ]
      }
    }
  ],
  "fixtures": [
    {
      "id": "odds-a512a48a58c4329048174217b2cc7ce0", "league": "epl",
      "kickoff": "2026-11-28T17:30:00Z",
      "home": "Arsenal", "away": "Man City",
      "lambda": 1.62, "mu": 1.05, "rho": -0.059,
      "market": {
        "home": 2.05, "draw": 3.40, "away": 3.60, "source": "best-of-7",
        "fair": { "home": 0.468, "draw": 0.276, "away": 0.256, "source": "pinnacle" }
      }
    }
  ],
  "results": [ { "league": "epl", "date": "2026-11-22", "home": "Liverpool", "away": "Everton", "hg": 2, "ag": 1 } ]
}
```

- `leagues`: one entry per league code above, in that order. `fixtures` (next 10 days) and `results` refer to them by `league`.
- `market` is `null` when no odds are available. `home/draw/away` are the best decimal prices across books (where to bet);
  `fair` holds margin-free probabilities from Pinnacle, or the mean over all books (`consensus-N`) when Pinnacle has no price.
  `fair` is the value benchmark: a price is value when `fair × odds > 1`. The backtest's market column is Pinnacle closing
  odds, or average closing odds when Pinnacle is missing (see the note above).
- `calibration`: home/draw/away probabilities pooled into bins; `pred` = mean predicted, `obs` = observed frequency.
- `results`: last 10 days, newest first; from football-data, topped up from `/scores` for games it doesn't have yet.
  `date` is the match date (`YYYY-MM-DD`; football-data's local date or the UTC kickoff date for `/scores` rows).
- Team names everywhere are football-data.co.uk's canonical names (e.g. `Man United`, `Ath Madrid`, `Paris SG`).
