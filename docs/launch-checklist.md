# Launch checklist: Best Parlay

What to check before sharing https://robosynapse.github.io/best_parlay/ with ~5 friends.
Scope: a free static PWA with no server, accounts, payments or analytics, so enterprise items are skipped or moved to "Not needed".

Status checked on 2026-11-23 against commit `d5f646b`. All `file:line` references point to that commit;
`web/app.js` is being edited in parallel, so its line numbers may drift.
`[x]` = done, with evidence. `[ ]` = open, or not verifiable from the repo (GitHub settings, real devices).

## Top 5 before you share the link

1. **Real fixtures are live.** The site has 0 fixtures right now (`generated_at` 2026-11-23 04:27 UTC). Confirm this is a real league break and not a mapping or API problem, and check the run log for `UNMAPPED`.
2. **Stale-data banner.** Show the update time, warn when data is more than 36 h old, and replace "momios actuales" with the actual update time.
3. **Hear about failures.** Turn on failure emails, set a 50-day reminder for the 60-day schedule disable, and move the cron off the hour (runs start 6–9 h late today).
4. **Guard the stake.** Cap the suggested stake, for example at 5% of the fund, and warn when typed odds are far above the market price (catches a typo such as 18.5 for 1.85).
5. **Test on 2 phones.** Install and use the app offline on one iPhone and one Android phone (check iOS icon corners). Then ship the 4 quick a11y fixes in section 6.

---

## 1. Correctness & data

Sources: [The Odds API v4 docs](https://the-odds-api.com/liveapi/guides/v4/), [GitHub: schedule event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

- [x] Model tested: grid sums to 1, tau, gradient, parameter recovery. Evidence: `pipeline/test_model.py:7-58`. Why: catches math regressions.
- [x] Backtest is walk-forward with no lookahead: weekly refit using only data dated before the test week. Evidence: `pipeline/model.py:73`, `pipeline/backtest.py:30-39`.
- [x] Backtest compared honestly to the closing market (market wins: RPS 0.2059 vs 0.2118). The app says so and only stakes against the market. Evidence: `web/app.js:189-190,281`.
- [x] Timezone: kickoffs are stored in UTC with `Z` and shown in the device's local time. Evidence: `pipeline/fetch.py:111`, `web/app.js:46`.
- [x] Started matches: dropped by the pipeline, flagged "ya comenzó" in the app, and their picks are disabled. Evidence: `pipeline/fetch.py:105`, `web/app.js:98,119,140`.
- [x] Failure modes keep the last good deploy. A failed results or fixtures download fails CI, and `deploy` needs `build`. Evidence: `pipeline/fetch.py:59,88-101`, `deploy.yml:42`.
- [x] An odds outage degrades the app instead of failing it: the market is `null` and no stake is shown. Junk prices and NaN never reach the JSON. Evidence: `pipeline/fetch.py:159,167-170`, `pipeline/build.py:52`.
- [x] Sample-data fallback is labelled on every view and stakes are disabled on it. Evidence: `web/app.js:350,190`.
- [ ] **Live data has 0 fixtures** (checked 2026-11-23 04:56 UTC). Why: a first-time visitor sees an empty app.
  How: compare with the real Liga MX calendar, and open the last run log in Actions (search `UNMAPPED`, `upcoming fixtures`).
- [ ] Unmapped team names are dropped silently and CI stays green (`pipeline/fetch.py:109`). Why: a match disappears without anyone noticing.
  How: change the `print` to `print(f"::warning::UNMAPPED ODDS API TEAM NAME: ...")` so it shows on the run summary page.
- [ ] Sanity bounds in `build.py`. Why: a bad fit would publish nonsense with a green check.
  How: after `pipeline/build.py:40` add `assert 0.1 < lam[0] < 5 and 0.1 < mu[0] < 5, f`.
- [ ] Spot-check 3 upcoming matches: model 1X2 vs Pinnacle. Why: a gap above ~15 points, or "valor" above ~15%, usually means stale odds or a wrong mapping. This also covers newly promoted or relocated teams, which get near-average ratings (`pipeline/model.py:13`).
- [ ] Re-run the backtest once per season (`python pipeline/backtest.py`, then commit `backtest_result.json`). Why: `xi` and home advantage drift over time.

## 2. Money & responsible gambling

Source: [Reglamento de la Ley Federal de Juegos y Sorteos, art. 9](https://mley.mx/Reg_LFJS/articulo/9/) (ads must say betting is forbidden to minors)

- [x] 18+ notice on every view, in the tour and in the Aviso. Evidence: `web/app.js:17,311,297`.
- [x] Help line (Línea de la Vida 800 911 2000, tappable link). Evidence: `web/app.js:18,297`. Re-dial it once to confirm it still works.
- [x] "Not a bookmaker, information only, not advice." No bookmaker links, affiliate codes or ads; the only outbound link is `tel:`. Evidence: `web/app.js:17,296-297`.
- [x] Conservative staking: quarter Kelly, $0 when there is no edge. Evidence: `web/app.js:191,217`, `web/model.js:85-88`.
- [x] Losses are stated plainly ("si fallas (x%) pierdes $y"), and odds are never pre-filled. Evidence: `web/app.js:200,141-142`.
- [ ] Cap the suggested stake. Why: a typed long-shot price can push quarter Kelly to over 10% of the fund.
  How: `web/app.js:191` becomes `bank * Math.min(kelly(pBet, c.O) / 4, 0.05)`.
- [ ] Typo guard on typed odds. Why: typing 18.5 instead of 1.85 shows a huge fake "valor".
  How: when a 1X2 leg's typed odds are more than 1.5× `f.market[side]`, show a note: "¿Seguro? Ese momio es mucho mayor que el mejor del mercado."
- [ ] "momios actuales" (`web/app.js:85`) is wrong: odds are from the last daily run.
  How: say "momios de la última actualización (ver hora arriba)".

## 3. Legal & licensing (Mexico)

Sources: [LFPDPPP 2025 (Cámara de Diputados)](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf), [Reglamento LFJS](https://www.ordenjuridico.gob.mx/Documentos/Federal/html/wo88470.html), [The Odds API terms](https://the-odds-api.com/terms-and-conditions.html). This is risk research, not legal advice.

- [x] Not an operator: the app takes no bets and holds no money, and the Aviso says to bet only with SEGOB-licensed books. Evidence: `web/app.js:296-297`.
- [x] Personal and non-commercial, and not indexed by search engines. Evidence: `web/app.js:296`, `README.md:4`, `web/index.html:8`.
- [x] Data sources credited and ESPN removed (its terms forbid scripts). The Odds API terms say attribution isn't required and forbid reselling the raw feed; this app doesn't resell it. Evidence: `web/app.js:299`, `pipeline/fetch.py:86`.
- [x] Trademarks used only to name things: no club or league logos, own ball icon, no-affiliation line. Evidence: `web/app.js:299`, `tools/make_icons.py`.
- [x] Privacy: no accounts, cookies or analytics, and data stays in localStorage; the privacy text names GitHub's IP logging. The new LFPDPPP (Mar 2025, art. 1) excludes strictly personal, non-commercial use. Evidence: `web/app.js:21-26,301`.
- [ ] Read football-data.co.uk's notes page once and save the date you read it. Why: their terms couldn't be verified for this review.
- [ ] Tell friends in the launch message that you don't collect or pool money for bets. Why: handling other people's stakes is what would make this look like organizing betting.
- **See a lawyer before** adding ads, affiliate links, paid tips or donations, opening it beyond friends, collecting any personal data, or using club logos.

## 4. Security & secrets

Sources: [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use), [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), [MDN CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)

- [x] CSP meta tag (`script-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `form-action 'none'`), and no third-party scripts or fonts. Evidence: `web/index.html:9-15`.
- [x] XSS review: every data string goes through `esc()`, ids through `encodeURIComponent`, and stored keys are validated by `isMarket`. Evidence: `web/app.js:5,79,30,369`.
- [x] Supply chain: actions pinned to full commit SHAs, Python dependencies pinned to exact versions. Evidence: `deploy.yml:25,26,37,52`, `requirements.txt`.
- [x] Least-privilege token: `contents: read`, Pages write only in the deploy job, and no `pull_request` trigger, so forks can't reach the secret. Evidence: `deploy.yml:6-14,44-46`.
- [x] API key never printed, with a test for it. Evidence: `pipeline/fetch.py:98-100,167-170`, `pipeline/test_model.py:70-81`.
- [x] HTTPS only. Evidence: the live response has `Strict-Transport-Security: max-age=31556952`.
- [ ] 2FA on the GitHub account that owns the repo. Why: that account can deploy anything to the site. How: Settings > Password and authentication. Check it in GitHub settings.
- [ ] Ruleset on `main` blocking force-push and deletion. How: repo Settings > Rules > Rulesets > New branch ruleset > target `main`, tick "Block force pushes" and "Restrict deletions". Check it in GitHub settings.
- [ ] Secret scanning, push protection and Dependabot alerts on. Why: pinned SHAs and versions never update themselves. How: Settings > Code security. Scanning is usually on by default for public repos, so confirm.
- [ ] Know how to rotate `ODDS_API_KEY`: new key in The Odds API dashboard, then Settings > Secrets and variables > Actions. Why: if it leaks, the worst case is someone burning your quota.

## 5. PWA quality

Sources: [web.dev: Add a web app manifest](https://web.dev/articles/add-manifest), [MDN: manifest `id`](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/id), [web.dev offline cookbook](https://web.dev/articles/offline-cookbook), [Apple forums: transparent touch icon turns black](https://developer.apple.com/forums/thread/713895)

- [x] Manifest has name, short_name, lang, relative start_url and scope, standalone display, and colors. It works under `/best_parlay/`. Evidence: `web/manifest.webmanifest:2-11`.
- [x] Icons: 192, 512, maskable 512 (content kept inside the safe zone), and SVG. Evidence: `web/manifest.webmanifest:13-16`, `tools/make_icons.py:37`.
- [x] Offline: app shell is cached; data is fetched network-first with the last good copy kept across versions. With no data at all, it shows labelled sample data or a "Reintentar" error. Evidence: `web/sw.js:3-8,27-37`, `web/app.js:49-55,417`.
- [x] Update flow: SW version = commit SHA, installed with `cache: 'reload'`, plus skipWaiting/claim. Evidence: `deploy.yml:36`, `web/sw.js:12-19`. A new shell appears on the second open after a deploy; data is fresh on the first.
- [x] Install steps in the tour (iOS and Android wording), hidden when already installed. Evidence: `web/app.js:305,312-315`.
- [ ] Add `id`. Why: a stable app identity if `start_url` ever changes. A relative `id` resolves against the origin, so use the full path.
  How: in `web/manifest.webmanifest` add `"id": "/best_parlay/",` (same as the current implicit id).
- [ ] iOS touch icon has transparent rounded corners (`web/index.html:13`, `tools/make_icons.py:32-36`). Why: iOS paints transparency black.
  How: point `apple-touch-icon` at a full-bleed opaque PNG, for example the maskable one (`icons/icon-maskable-512.png`).
- [ ] Network timeout for data (`web/sw.js:29`). Why: on a weak signal the app waits on "Cargando…" instead of showing cached data.
  How: race `fetch(req)` against a 4 s timer that falls back to `caches.match(url.pathname)`.
- [ ] Chrome DevTools > Application > Manifest and Service workers: no errors, "installable". Do this once on the live URL.

## 6. Accessibility (WCAG 2.2 AA)

Sources: [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [2.5.8 Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [1.4.11 Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)

- [x] `lang="es-MX"`, zoom not locked, and no CSS animations (so reduced motion is not an issue). Evidence: `web/index.html:2,5`, `web/style.css`.
- [x] Visible focus ring (accent is 4.6:1 light and 10.7:1 dark). Evidence: `web/style.css:22`.
- [x] Targets: buttons and pickers at least 44 px, `summary` 28 px (AA requires 24). Evidence: `web/style.css:67,81,86,89`.
- [x] Dialog uses native `<dialog>` with `showModal`, `aria-labelledby` and focus on the main action; Esc closes it. Evidence: `web/index.html:31`, `web/app.js:320-326`.
- [x] Icons are `aria-hidden`, icon-only buttons have labels, and the chart has `role="img"` and a label. Evidence: `web/index.html:22`, `web/app.js:230,235,260`.
- [x] Text contrast of the main tokens, computed: light muted 5.6:1, link 5.0:1, value 4.5:1; dark all ≥4.6:1. Color is never the only cue ("+x% valor" with an icon). Evidence: `web/style.css:2-11`, `web/app.js:75`.
- [ ] Past match cards use `opacity: .6`, which puts muted text at 2.4:1 in light mode (`web/style.css:46`).
  How: `.card.past { background: var(--bg); }` and drop the opacity. The "ya comenzó" label already says it.
- [ ] Heat-map numbers fail: white on mid green is 2.1:1 in light mode, and dark mode is 4.0:1 (`web/app.js:111-112`).
  How: `const al = 0.45 * g[h][a] / max;` and drop the `accent-fg` switch. That gives at least 4.6:1 in both themes.
- [ ] Input borders are 1.3:1 (1.4.11 needs 3:1) (`web/style.css:77`). How: `border: 1px solid var(--muted)`.
- [ ] The parlay-name input has only a placeholder (`web/app.js:243`). How: add `aria-label="Nombre del parlay"`.
- [ ] 10-minute screen-reader pass: VoiceOver on iPhone and TalkBack on Android, covering match, add a pick, Parlay, and the tour. Optional: `aria-live="polite"` on `#summary` so typed odds announce the result.

## 7. Performance

Sources: [Lighthouse overview](https://developer.chrome.com/docs/lighthouse/overview), [web.dev: performance budgets](https://web.dev/articles/performance-budgets-101)

- [x] Tiny payload: the whole shell is about 75 KB uncompressed (`app.js` 29 KB), with no framework, fonts or third parties. Score grids are cached per match. Evidence: `du -b web/*`, `web/app.js:36-38`.
- [x] Repeat visits come from the SW cache; Pages serves compressed files. Evidence: `web/sw.js:41`.
- [ ] Run Lighthouse (mobile) once on the live URL: `npx lighthouse https://robosynapse.github.io/best_parlay/ --view`. Target: Performance ≥ 90, Accessibility ≥ 95. Budget: keep the shell under 150 KB (`du -cb web/*.* web/icons/*`).

## 8. Cross-device testing

Sources: [web.dev Learn PWA: installation](https://web.dev/learn/pwa/installation), [WCAG 1.4.10 Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)

| Check | iPhone Safari | Android Chrome | Desktop Chrome/Edge | Desktop Firefox/Safari |
|---|---|---|---|---|
| Install + open from home screen | ☐ | ☐ | ☐ | n/a |
| Light + dark mode | ☐ | ☐ | ☐ | ☐ |
| Offline after one visit | ☐ | ☐ | ☐ | ☐ |
| Notch / home bar safe areas | ☐ | ☐ | n/a | n/a |

- [ ] iPhone: icon corners, bottom tabs clear of the home bar, phone link opens the dialer, the tour shows the "Compartir > Agregar a inicio" step.
- [ ] Android: maskable icon shape, back button moves between hash routes, the tour shows "Instalar app".
- [ ] Desktop keyboard only: Tab from a match to a pick, to Parlay, to the dialog, then Esc.
- [ ] 320 px wide (iPhone SE) and 200% text zoom: no sideways scrolling, tables readable.
- [ ] DevTools "Slow 3G": first load under ~5 s. First-ever visit with no network shows "Reintentar", not an endless "Cargando…".
- [ ] One friend reads the Spanish copy and the tour and says what confused them.

## 9. Operations

Sources: [GitHub: schedule event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [GitHub: disable and enable workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows), [The Odds API v4 docs (usage quota)](https://the-odds-api.com/liveapi/guides/v4/)

- [x] Daily schedule, plus deploy on push to `main` and manual runs. Tests run before every build. Evidence: `deploy.yml:6-11,31-32`.
- [x] Healthy so far: the last 12 runs all succeeded (13–23 Nov 2026, public Actions API).
- [x] Quota math: each `/odds` call costs 3 credits (3 regions × 1 market), `/events` is free, and `/odds` is skipped when there are no fixtures. That's ~90 credits/month for daily runs plus 3 per push or manual run, against 500 free (resets on the 1st). Remaining credits are logged. Evidence: `pipeline/fetch.py:141-143`, `pipeline/build.py:36`.
- [x] Backups and rollback: code is in GitHub plus your clone, data is regenerated daily, and the backtest result is committed. Roll back with `git revert <sha> && git push`.
- [ ] Failure emails: notifications for scheduled runs go to the user who last edited the cron line. Why: otherwise a broken build goes unnoticed. How: github.com Settings > Notifications > Actions, set Email and "Only notify for failed workflows". Check it in GitHub settings.
- [ ] Runs start 6–9 h late (actual 19:37–23:15 UTC vs cron 14:00) because the top of the hour is GitHub's peak load. Why: odds end up older than "08:00".
  How: `cron: "17 13 * * *"`. Optional: add a pre-kickoff run, `"17 13,22 * * *"`, which is about 180 credits/month.
- [ ] 60-day disable: it is documented (`deploy.yml:3`), but nothing reminds you. Why: the schedule stops silently and the data goes stale.
  How: a calendar reminder every 50 days to push any commit, or click "Enable workflow" in the Actions tab.
- [ ] Stale-data banner, which doubles as monitoring because friends will notice it. Today the header shows only the date (`web/app.js:423`).
  How: if `Date.now() - Date.parse(generated_at) > 36*3600e3`, show a `.note` like "Datos de hace X días; los momios pueden haber cambiado". Also show the time in the header.
- [ ] Low-quota warning. Look at the "remaining" number in one run log per week in the first month.
  How: after `pipeline/fetch.py:143` add `if int(r.headers.get('x-requests-remaining') or 999) < 50: print('::warning::Odds API quota low')`.

## 10. Launch day & after

Source: [GitHub: managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

- [x] First-run tutorial explains parlays, value and staking, with install steps. Evidence: `web/app.js:306-327`.
- [ ] Share only when real fixtures are showing (see Top 5, item 1).
- [ ] Launch message (WhatsApp): link, "solo mayores de 18", "es información, no consejo; no manejamos dinero", how to install, where to send feedback.
- [ ] Feedback channel: the friends' group chat, with the link pinned. After a week ask: what confused you, what did you use, what's missing.
- [ ] Tag the launch: `git tag v1.0 && git push origin v1.0`, then a GitHub Release with auto-generated notes as the changelog.
- [ ] First-week watch: daily run is green, the fixture count matches the real jornada, the model stays within ~15 points of Pinnacle, "valor" stays below ~15%, and quota is on track.
- [ ] Optional track record: keep each day's `predictions.json` (for example `actions/upload-artifact` with `retention-days: 90`) so you can compare predictions with results after a month.

## Not needed at this scale

- Accounts, auth, rate limiting, WAF: there's no server and nothing to log in to.
- Cookie banner, analytics consent: no cookies or analytics.
- Terms of service, age-verification gate: the 18+ notice and Aviso are proportionate for 5 friends with no money flow.
- `frame-ancestors` or other security headers: Pages can't set them and the page has no state-changing actions. Revisit if you move hosts.
- Uptime monitor, status page, error tracking (Sentry): five users in a group chat are the monitor, and the stale banner covers silent failures.
- CDN, bundler, minifier, image pipeline: 75 KB total.
- LICENSE file: optional. Without one the code is "all rights reserved", which is fine for a personal project.
- Push notifications, background sync, app-store wrapper: not worth the complexity for a daily-refresh page.
