# Dashboard — Vite + React + MUI v6

Operator monitoring UI for the crypto-arbitrage bot. Polls
`logs/decisions.jsonl` for the live audit trail and renders the
opportunity / decision / fill pipeline.

## Quick start

```bash
# from the project root, run the bot at least once so logs/ exists
.venv/bin/python -m arbitrage_agent

# from this dashboard/ directory
cd dashboard
npm install      # one-time
npm run dev      # serves on http://127.0.0.1:3005  (falls through to 3006/...)
```

Then open http://127.0.0.1:3005/ in a browser.

## What you see

| Section | Source |
|---|---|
| AppBar kill-switch chip | polls `/api/kill-switch` → `logs/kill_switch.json` (read-only) |
| KPI tiles | computed from current audit log (P&L, opps, approval %, exchanges) |
| Recent Opportunities table | `opportunity_detected` + matching `risk_decision` events |
| Recent Fills table | `fill` events |
| Order lifecycle reference | cosmetic chip key from `DESIGN_LANGUAGE.md § 4.4` |
| Theme toggle | switches between `darkTheme` and `lightTheme` per `DESIGN_LANGUAGE.md § 3` |

## Refresh cadence

- `/logs/decisions.jsonl` polled every **2 seconds**
- `/api/kill-switch` polled every **2 seconds**

Run the bot in a loop to watch the dashboard fill up:

```bash
PIPELINE_ITERATIONS=10 .venv/bin/python -m arbitrage_agent
```

Or run it once per second from a separate terminal:

```bash
while true; do .venv/bin/python -m arbitrage_agent >/dev/null 2>&1; sleep 1; done
```

## Architecture

- **Vite** for dev server + bundler. Custom middleware in
  `vite.config.ts` serves `/logs/*` and `/api/kill-switch` from the
  project root — no symlinks, no copying.
- **TypeScript** strict mode.
- **React 18** (StrictMode in dev).
- **MUI v6** with Material design colour tokens from
  `specs/DESIGN_LANGUAGE.md § 3` baked into custom `createTheme` palettes
  (both light and dark).
- **No DataGrid** — regular MUI `Table` is sufficient for current
  audit-log volume; switch when row counts > 1000.
- **No router** yet — single Overview page. LeftRail nav items are
  visual; routing arrives in a later faz.

## Old smoke

`dashboard/smoke.html` is the pre-React design-language preview kept
for visual diff. Open it directly in a browser (no server). It uses
vanilla HTML + CSS to show all of `DESIGN_LANGUAGE.md`'s decisions
without React; the current build implements the subset relevant to the
real audit trail.

## Production build (not needed for the smoke)

```bash
npm run build       # type-check + bundle to dist/
npm run preview     # serve dist/ for verification
```

`dist/` is gitignored. Real deployment is a Faz 8+ topic.

## Known gaps (deferred)

- Latency tier + WS connection chips are omitted — they need a live
  ingestion data source which Faz 7 brings.
- The kill-switch chip is read-only here; engaging from the UI requires
  a POST endpoint (Faz 7 backend addition).
- P&L arithmetic uses JavaScript `Number` for display; production
  needs a Decimal library for tax-grade accuracy.
- No empty-state placeholder for stale data yet (we poll, so it's
  always fresh while the dev server runs).
