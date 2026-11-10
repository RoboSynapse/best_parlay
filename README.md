# best_parlay

Liga MX match probabilities (Dixon–Coles) and a parlay builder, as a PWA for a handful of friends.
Free stack only: football-data.co.uk + ESPN public JSON (+ optional The Odds API free tier), GitHub Actions, GitHub Pages.

```
pipeline/   Python: fetch data, fit model, walk-forward backtest, write web/data/predictions.json
web/        PWA (vanilla HTML/CSS/JS, no build step), served by GitHub Pages
.github/    one workflow: run pipeline on a schedule, deploy web/ to Pages
```

## Data contract: `web/data/predictions.json`

The pipeline writes it; the app only reads it. The app builds score grids on-device from `lambda`, `mu`, `rho`.

```json
{
  "generated_at": "2026-11-09T12:00:00Z",
  "league": "Liga MX",
  "model": { "name": "dixon-coles", "xi": 0.0018, "rho": -0.08, "home_adv": 0.30, "n_matches": 1200 },
  "backtest": {
    "n": 2400, "from": "2019-07-01", "to": "2026-11-01",
    "rps_model": 0.205, "rps_market": 0.201, "logloss_model": 1.03, "logloss_market": 1.02,
    "calibration": [ { "bin": 0.35, "pred": 0.352, "obs": 0.341, "n": 410 } ]
  },
  "teams": [ { "name": "Toluca", "attack": 0.21, "defence": -0.12, "home": 0.41 } ],
  "fixtures": [
    {
      "id": "espn-123456",
      "kickoff": "2026-11-14T02:00:00Z",
      "stage": "regular",
      "home": "Toluca", "away": "America",
      "lambda": 1.62, "mu": 1.05, "rho": -0.08,
      "p": { "home": 0.48, "draw": 0.26, "away": 0.26 },
      "market": { "home": 2.05, "draw": 3.40, "away": 3.60, "source": "best-of-N" }
    }
  ]
}
```

- `market` is `null` when no odds are available (decimal odds otherwise).
- `stage`: `"regular"`, `"playin"` or `"liguilla"`.
- `calibration`: home/draw/away probabilities pooled into bins; `pred` = mean predicted, `obs` = observed frequency.
- Team names are the canonical ones from football-data.co.uk `MEX.csv`.
