# LOG — Project-Crypto-Arbitrage-Bot

> **Append-only chronological record.** One line per event. Newest at the
> bottom. Parsable: every entry header begins with `## [YYYY-MM-DD] <type> |`.
>
> Types:
> - `decision` — a frozen choice was made
> - `ingest` — a new source was processed into the wiki
> - `lint` — health-check / contradiction sweep
> - `refactor` — structure-only change, no behavior delta
> - `bug-found` / `bug-fixed` — incident lifecycle
> - `setup` — infrastructure / scaffolding work

---

## [2026-05-20] setup | Initial repo organization complete
Flat root reorganized into `specs/` (7 design docs) + `skills/` (5 module
manuals) + `.cursor/rules/` (Karpathy gist as a Cursor rule). The "stray"
root `SKILL.md` was identified as `market-data-ingestion` via its frontmatter
and routed to the correct folder. `mnt/` archive removed after verification.
`.DS_Store` files purged; `.gitignore` created.

## [2026-05-20] decision | MUI v6 frozen for future operator dashboard
React + MUI v6+ chosen for the (deferred) operator monitoring UI. Stack
rationale, theme tokens (light + dark), domain color semantics (P&L,
latency, WS state, order lifecycle, kill-switch), density, motion,
accessibility — all fixed in `specs/DESIGN_LANGUAGE.md`. Decision pre-made
so dashboard work is unblocked when v2 starts.

## [2026-05-20] bug-found | `crypto-arbitrage-agent.zip` vanished mid-session
Zip was present at session start (51606 B, mtime May 19 21:39), absent after
unrelated `mv` / `rm -rf mnt` / `.DS_Store` purge. No command targeted it.

## [2026-05-20] bug-fixed | Zip restored from `~/Downloads/files/` (SHA-256 verified)
Identical-size, identical-mtime copy located in user Downloads. Restored via
`cp -p`; SHA-256 `a5a9e11a…cdf704` matches both copies. Project root state
restored to spec.

## [2026-05-20] decision | Karpathy LLM-Wiki pattern adopted (light form)
Four wiki files (`STATUS.md`, `MEMORY.md`, `specs/INDEX.md`, `specs/LOG.md`)
introduced as project-level memory layer. `CLAUDE.md § 4` Decision Loop
prepended with a "step 0 — ORIENT" reading the wiki. New `CLAUDE.md § 9 —
Wiki Maintenance Protocol` codifies update triggers.

## [2026-05-20] setup | Wiki layer files created
`STATUS.md`, `MEMORY.md`, `specs/INDEX.md`, `specs/LOG.md` written with
initial content. Operator-triggered lint (no fixed schedule) approved as the
maintenance cadence.

## [2026-05-20] correction | Zip "bug" was misdiagnosis — operator deleted it intentionally
The two earlier `bug-found` / `bug-fixed` entries above re: the disappearing
`crypto-arbitrage-agent.zip` are **not** an external system bug. The operator
deleted the zip intentionally; its contents were already fully extracted into
`specs/` and `skills/`, so the original "do not delete" constraint had gone
stale. The restored copy has been removed from the repo. Prior log entries
are kept (append-only); see `MEMORY.md § Gotchas` for the Karpathy 1.1
lesson extracted from this incident.

## [2026-05-20] refactor | `.cursor/` → `.claude/rules/karpathy-guidelines.md`
Cursor-specific folder replaced with Claude Code-native location. Cursor
frontmatter (`description`, `globs`, `alwaysApply`) stripped; replaced with
an HTML comment header noting purpose and pointing back to `CLAUDE.md § 5`.
Body of the gist preserved byte-identical (verified by `diff`). `.cursor/`
removed. CLAUDE.md § 5 gained one row pointing to the new path. INDEX.md and
MEMORY.md path references updated.

## [2026-05-20] decision | Operator-gated iterative protocol adopted
Going forward, every action submits a **Report** + **Smoke Tests** block;
operator reviews via the interface; the next action only starts after
explicit approval. Memory MD files (STATUS, MEMORY, INDEX, LOG) updated
after every action per CLAUDE.md § 9.3.

## [2026-05-20] refactor | Faz 0 — `specs/PROJECT_STRUCTURE.md` stale `docs/` → `specs/`
Two stale `docs/` references in `PROJECT_STRUCTURE.md` (the top-level tree
at L20 and the rule table at L111) corrected to `specs/`. Scope explicitly
limited to PROJECT_STRUCTURE.md per operator approval; 9 additional stale
`docs/` references in `PROMPT_TEMPLATES.md` flagged in the report for a
separate decision.

## [2026-05-20] decision | Python stack — uv + hatchling + PEP 621 floor versions
Package manager: `uv`. Build backend: `hatchling`. Dependency style: floor
(`pkg>=X.Y`) with `uv.lock` for reproducibility. Dev deps in
`[project.optional-dependencies] dev`. See `MEMORY.md § Decisions`.

## [2026-05-20] setup | Faz 1 — bootstrap (pyproject + .env.example + src/ + tests scaffolding)
Created: `pyproject.toml` (PEP 621, hatchling, pytest+pytest-asyncio dev
deps), `.env.example` (EXECUTION_MODE + key placeholders + LOG_LEVEL),
extended `.gitignore` (Python/venv/.env/SQLite/IDE), `src/arbitrage_agent/
{__init__.py, __main__.py}` and `tests/conftest.py`. `python -m
arbitrage_agent` smoke test passes for both paper and live modes (single
JSON line). No runtime deps imported yet (Karpathy 1.2 — add as faz uses
them).

## [2026-05-20] lint | Faz 1 smoke test (in project-local `.venv`) — 8/8 PASS
`python3.11 -m venv .venv && pip install -e ".[dev]"` succeeded. All 8 smoke
checks (Python version, install, paper/live module runs, empty pytest,
docs/-cleanliness in PROJECT_STRUCTURE.md, wiki layer freshness, tree)
returned the expected output. Project-isolated; system Python and other
projects untouched.

## [2026-05-20] decision | Domain types — NewType + frozen-dataclass+slots, Decimal-only, tz-aware UTC
`ExchangeId` / `OpportunityId` = `NewType[str]`. `Symbol` = frozen+slots
dataclass with `from_string('BASE/QUOTE')` factory. `Price` / `Volume` =
`NewType[Decimal]` with factories that reject float by signature. Events
(`MarketSnapshot`, `Opportunity`, `RiskDecision`, `Fill`) = frozen+slots
dataclasses. `OrderSide = Literal["buy","sell"]`. `now_utc()` helper for
tz-aware UTC timestamps. Operator approved Symbol dataclass, default
Decimal precision, tz-aware `datetime` on 2026-05-20.

## [2026-05-20] setup | Faz 2 — domain types implemented (27 tests PASS, stdlib-only verified)
`src/arbitrage_agent/domain/{__init__.py, ids.py, money.py, events.py}` +
`tests/unit/domain/{test_ids.py, test_money.py, test_events.py}`. 27/27
pytest passing. AST-based isolation check confirms `domain/` imports only
from stdlib + sibling `domain.*` modules (no third-party, no cross-module
`arbitrage_agent.*` imports outside `domain.*`).

## [2026-05-20] refactor | PROMPT_TEMPLATES.md — 9 stale `docs/<FILE>.md` → `specs/<FILE>.md`
Surgical `sed` substitution `docs/[A-Z][A-Z_]*\.md` → `specs/\1`. The
generic-noun reference `docs/skills the agent must read first` at L17 was
intentionally preserved (not a path). Operator approved 2026-05-20.

## [2026-05-20] decision | Faz 3 stack — pydantic-settings + structlog (PrintLoggerFactory) + secret redaction
`Settings(BaseSettings)` reads `.env` from CWD; `EXECUTION_MODE` validated as
`Literal["paper","live"]`. `configure_logging` uses
`structlog.PrintLoggerFactory` (Karpathy 1.2 — simpler than stdlib bridge;
upgrade only when needed). `_redact_secrets` processor masks fields whose
**key** contains `api_key|api_secret|password|secret|token`. See
`MEMORY.md § Decisions`.

## [2026-05-20] setup | Faz 3 — config + logging implemented (38 tests PASS)
Added runtime deps `pydantic>=2.0`, `pydantic-settings>=2.0`,
`structlog>=24.0`. New: `src/arbitrage_agent/config.py`,
`src/arbitrage_agent/observability/{__init__.py, logging_setup.py}`.
Rewrote `__main__.py` to use `Settings()` + `configure_logging()` +
`structlog.get_logger().info("agent.start", ...)`. New tests:
`tests/unit/test_config.py` (6) + `tests/unit/observability/test_logging_setup.py`
(5). Total 38/38 pytest passing. Manual smokes: secret redaction confirmed
(`binance_api_key='REAL_LEAKED_VALUE'` → `'***'` in JSON output); `.env`
loading from a temp CWD works; level filter suppresses below-threshold events.

## [2026-05-20] bug-found | Faz 2 domain types diverged from `ARCHITECTURE.md § 6`
While preparing Faz 4 (per (e), reading spec for protocol signatures), 8
field-name / shape divergences surfaced between the Faz 2 implementation
and the architecture contract. Examples: `bid_volume` vs `bid_size`,
`expected_pnl` vs `expected_net_profit`, missing `OrderIntent` /
`OrderId`, `RiskDecision.reasons:tuple` vs `reason:str`, missing
`opportunity_id` on RiskDecision. Faz 4 paused; surfaced to operator with
reconciliation proposal.

## [2026-05-20] decision | Faz 2.5 — domain reconciliation before Faz 4
Operator approved A+A: keep `Symbol` as dataclass; reconcile `domain/` to
spec field-for-field. Rationale in `MEMORY.md § Gotchas` (Karpathy 1.1
process lesson).

## [2026-05-20] setup | Faz 2.5 — domain reconciled to `ARCHITECTURE.md § 6` (50 tests PASS)
`domain/events.py` rewritten: `MarketSnapshot.bid_size/ask_size/
timestamp_utc`, new `OrderIntent`, `Opportunity(detected_at, strategy,
legs, expected_net_profit, confidence)`, `RiskDecision(opportunity_id,
reason, adjusted_quantity)`, `Fill.timestamp_utc`,
`StrategyName = Literal[...]`. `domain/ids.py` gained `OrderId` + factory.
`__init__.py` exports updated (17 names total). Tests rewritten — 12 new
behaviors covered including spec-name regression guards. Total 50/50
pytest passing; AST domain-isolation check still clean.

## [2026-05-20] decision | Faz 4 — Protocol-based interfaces; MarketView/Clock in strategies/
Cross-module contracts use `typing.Protocol` + `@runtime_checkable`, not
ABCs (structural typing, no inheritance ceremony). Interface dependencies
a module consumes (`MarketView`, `Clock`) live in that module's `base.py`,
not `domain/` (which is reserved for transported data). See
`MEMORY.md § Decisions`.

## [2026-05-20] setup | Faz 4 — module skeletons (40 .py modules, 56 tests PASS)
7 new packages (`ingestion`, `exchanges`, `strategies`, `risk`,
`execution`, `persistence`, `orchestration`) + `observability/` expanded
with `metrics`/`alerts`. 2 Protocols (`ExchangeAdapter`, `Strategy` plus
helpers `MarketView`/`Clock`), 8 concrete `NotImplementedError` skeletons
(`risk/gate.evaluate`, `risk/kill_switch.{is_engaged,engage}`,
`execution/engine.execute`, `DecisionLog`, `FillStore`,
`orchestration/{pipeline.run,lifecycle.{startup,shutdown}}`), 13
docstring-only placeholders for future-faz bodies, 1 `.gitkeep` in
`persistence/migrations/`. `tests/unit/test_imports.py` enforces (a) every
module imports cleanly, (b) discovered module set matches expected
40-module list, (c) Protocols expose their declared members, (d)
`AccountState` constructs empty, (e) `gate.evaluate` raises
`NotImplementedError`. AST checks confirm `domain/` and `strategies/`
import isolation rules hold. 56/56 pytest passing.

## [2026-05-20] bug-found | Faz 4 ExchangeAdapter narrower than SKILL.md spec
Reading `skills/exchange-integration/SKILL.md` for Faz 5a surfaced 4
missing Protocol members (`id` property, `subscribe`, `cancel_order`,
`fetch_balance`, `fetch_fills`) plus `SnapshotCallback` type alias.
ARCHITECTURE.md § 6 explicitly says "Defined precisely in the skill files;
sketched here" — the SKILL.md is normative for behaviour contracts. Faz 4
copied only the sketch. Same class of error as Faz 2 → Faz 2.5; logged
again as a MEMORY § Gotcha lesson.

## [2026-05-20] decision | Faz 5 split — 5a (PaperExchange), 5b (Risk gate), 5c (Spatial + chain)
Operator chose C2 split. Each sub-faz produces a visible artefact with its
own smoke test. (a) static price table; (b) Settings-driven limits; (d)
`name: str` field with registry override. See `MEMORY.md § Decisions`.

## [2026-05-20] decision | Faz 5b risk subset — 6 of 10 SKILL checks (deterministic ones only)
SKILL.md lists 10 decision-order checks; Faz 5b implements the 6 that are
pure functions of `(opportunity, state, limits, now_ms)`: kill-switch,
freshness, profitability, min-order-value, max-order-value, gross
exposure. Per-asset position limit, orders/min counter, balance check,
connectivity check require additional state plumbing and are deferred
(5b+/5c/6). Downsize policy also deferred — Faz 5b is all-or-nothing.
Limits are config-driven from Settings (SKILL.md § 5b QA-5.3).

## [2026-05-21] bug-found | Faz 2.5 missed `valid_for_ms` from SKILL Opportunity contract
arbitrage-detection SKILL.md mandates `valid_for_ms: int` on every
Opportunity (decision-order check #3 reads `opportunity.valid_for_ms`).
Faz 2.5 reconciled MarketSnapshot etc. but missed this Opportunity field.
Faz 5c added it; risk gate switched from `limits.max_opportunity_age_ms`
to `opp.valid_for_ms` (single source of truth, Karpathy 1.2). Settings
`risk_max_opportunity_age_ms` and Limits `max_opportunity_age_ms` removed.

## [2026-05-21] decision | Faz 5c — Clock/MarketView concrete impls outside `strategies/`
`SystemClock` lives in `orchestration/clock.py` (strategies/ is AST-pure,
no `time` import allowed). `LatestSnapshotView` lives in `ingestion/bus.py`
(natural home for the bus-side data structure). Strategies remain pure;
consume only the Protocols. See `MEMORY.md § Decisions`.

## [2026-05-21] decision | Plan ordering — c→a→b (dashboard design smoke first, then real data, then live exchanges)
Operator pivoted from "Faz 7 live" to a UX-first track: (c) see a
concrete dashboard design, (a) wire real MVP data into it, then (b)
move to live exchanges. Rationale: psychological need to see something
tangible before sinking weeks into live-trading risk surface. Recorded
so future agent sessions don't re-propose Faz 7 first.

## [2026-05-21] decision | Faz 7-S inserted before Faz 7d — security-first
Operator pivoted: "security is one of the most critical steps." Audit
of CLAUDE.md C1-C8 + codebase scan found: redaction OK, gitignore OK,
no leaked secrets, BUT no pre-commit gitleaks, no live-mode programmatic
guard, no withdrawal-permission probe, no mainnet confirmation env, no
single security document. Order changed from 7d→7c→7b to 7-S→7d→7c→7b.
7-S has two steps: Adım 1 = SECURITY.md (this entry); Adım 2 =
implement S1+S2+S3+S4. See `MEMORY.md § Decisions`.

## [2026-05-22] bug-found | INCIDENT — real Binance API key pasted into `.env.example` template
Operator pasted freshly-generated Binance key + secret into the
committed `.env.example` template (intended for empty placeholders).
Repo not `git init`'d yet → no history leak; but the value lived on
disk in the wrong file. Two defence gaps surfaced:
(a) `.gitleaks.toml` had `.env.example` on the allowlist → would not
flag values there; (b) no script verified template emptiness. Both
fixed in the response.

## [2026-05-22] bug-fixed | Credential leak response — key revoked, template sanitised, defences strengthened (224 tests PASS)
**Operator action**: revoked the leaked Binance API key on the
exchange's web UI and generated a fresh trade-only key, placed in
`.env` (gitignored). The leaked value never appears in committed
artefacts.
**Code response**:
- `.env.example` restored to placeholder template with a bold "REAL
  CREDENTIALS NEVER GO HERE" header pointing at `SECURITY.md § 5.1`.
- New `.env` file (gitignored) created as the operator's working
  copy.
- `.gitleaks.toml` allowlist `paths` array: removed `.env.example`
  entry (incorrect assumption that template is always empty).
- New `scripts/check_env_example.py`: standalone Python lint
  verifying every `KEY=value` line either has empty value OR matches
  a small explicit allowlist (mode literals, documented base URLs,
  integer defaults). Masks any leaked value in its error output
  (first 4 + last 4 chars only) so the lint itself never leaks.
- Wired into `.pre-commit-config.yaml` as a `repo: local` hook.
- New `tests/unit/test_check_env_example.py` — 6 tests, including
  the canonical negative case (`test_real_looking_key_is_rejected`)
  and an output-masking check (`test_masks_long_values_in_output`).
- `MEMORY.md § Gotchas 2026-05-22` — full IR record + lesson.
- `SECURITY.md § 7 Change Log` — incident row + S1 strengthening row.
- 224/224 pytest passing (218 + 6 lint tests).

## [2026-05-22] setup | Faz 7g-d — S7 testnet probation gate automated (334 tests PASS)
**Goal**: replace operator policy + README copy for S7 with a hard
startup gate that refuses mainnet+live until ≥30 days of testnet
activity have been recorded.
**New module (`risk/testnet_evidence.py`)** — stdlib-only:
- `TestnetEvidence` frozen dataclass (first_seen_utc, last_seen_utc,
  venues, `days_observed(now)`, `is_sufficient(now, min_days)`).
- `load(path)` — missing / malformed / unparseable → empty evidence
  (gate rejects, surfacing the issue rather than crashing).
- `record(venue, now, path)` — synchronous JSON rewrite; first call
  stamps `first_seen_utc`, subsequent calls bump `last_seen_utc` and
  merge the venue into a sorted set.
- `attest_mainnet_eligibility(path, *, now, min_days)` →
  `(ok, message)`; failure message names the missing day count + first
  observed date + venue list so the operator sees an actionable error.
**Adapter integration (`exchanges/binance.py`)**:
- `_is_testnet()` → `"testnet" in self._base_url.lower()` — keyed
  on the actual URL, not a config flag, so a misconfigured mainnet
  URL can never accidentally count as testnet probation.
- `_record_testnet_evidence()` — best-effort recorder; OSError
  swallowed so disk issues never break a trade.
- `_ensure_no_withdraw_permission()` calls the recorder on BOTH the
  cached-success early-return path AND the first-success path,
  ensuring every authenticated call refreshes `last_seen_utc`.
**Config integration (`config.py`)**:
- New `risk_testnet_evidence_path: Path = Path("logs/testnet_evidence.
  json")` + `s7_min_testnet_days: int = 30`.
- `_confirm_mainnet_live` model_validator extended: after the S4
  `LIVE_TRADING_CONFIRMED` check, runs `attest_mainnet_eligibility`;
  failure → `ValueError` (Pydantic surfaces as `ValidationError` at
  `Settings()` instantiation).
- Emergency bypass: `S7_OVERRIDE_TESTNET_PROBATION=true`. Operator is
  expected to record the rationale in `MEMORY.md § Decisions & Why`.
**Tests**:
- `tests/unit/risk/test_testnet_evidence.py` (new, 11 tests —
  missing-file/empty, first-and-last-seen, first_seen-preserved,
  venue-merge, sub-day-counts-zero, full-day-after-24h, no-evidence-
  insufficient, partial-days-reports-N/M, sufficient-after-threshold,
  malformed-file-rejected, alternating-write-read-stable).
- `tests/unit/test_config.py::TestS7TestnetProbationGate` (6 new
  tests — no-evidence-blocked, too-recent-blocked, 31-days-allowed,
  explicit-override-bypasses, testnet-url-skips-gate-entirely,
  S7_MIN_TESTNET_DAYS-lowers-threshold).
- `tests/unit/exchanges/test_binance_auth.py` (2 new — testnet URL
  records evidence on probe success; mainnet URL does NOT record
  evidence, preventing self-fulfilling probation).
- `tests/unit/test_imports.py` module set expanded with the new module.
- Two pre-existing S4 mainnet-allowed tests gained `_bypass_s7` to
  isolate S4 from the new S7 gate.
**Live smoke**: `EXECUTION_MODE=live BINANCE_ENABLED=true
BINANCE_REST_BASE_URL=https://api.binance.com LIVE_TRADING_CONFIRMED=
true` against an empty cwd → `ValidationError: S7: no testnet evidence
at logs/testnet_evidence.json`. Seeding a 31-day-old evidence file →
`Settings OK — execution_mode=live`. **334/334 pytest passing** (was
315; +11 evidence unit + +6 S7 config + +2 binance recorder hook).

## [2026-05-22] setup | Faz 7g-c — real hedger (cancel + counter-leg + slippage budget, 315 tests PASS)
**Goal**: replace the Faz 7e MVP "imbalance detected, operator
investigate" log with a real neutralisation flow per
`skills/execution-engine/SKILL.md § The Hedger`.
**Module (`execution/hedger.py`)** — complete rewrite:
- `compute_net_exposure(result) -> dict[Symbol, Decimal]` — pure
  signed sum across observed fills (`buy=+vol`, `sell=-vol`). Returns
  symbols with non-zero net.
- `_best_effort_cancel(result, adapters)` — iterates partial/failed
  legs whose `order_id` is known and calls
  `adapter.cancel_order(order_id)`. `NotImplementedError` /
  `PermissionError` skipped silently (paper / wrong-mode); other
  exceptions logged via `hedger.cancel_failed` and swallowed so a
  refused cancel never blocks neutralisation.
- `_within_slippage(fair, market, side, max_bps)` — pure budget gate.
  For a sell hedge: drift = (fair − market) / fair. For a buy hedge:
  drift = (market − fair) / fair. Returns True iff drift ≤ budget.
- `async hedge(opp, result, adapters, view, max_slippage_bps) ->
  HedgeResult` — orchestrator. Picks single-symbol imbalance,
  cancels, chooses counter venue (failed leg's exchange, or first
  adapter with snapshot if none), computes fair = VWAP of the unwind
  side's fills (fallback: snapshot mid), checks slippage against
  current best bid/ask, builds counter-leg `OrderIntent`, synthesizes
  a hedge `RiskDecision(reason="hedge for opportunity X")` carrying
  the original opportunity_id (SKILL.md traceability), places via
  `adapter.place_order`, fetches fills, computes residual.
- Kept `emit_hedge_alert` as a diagnostic-only hook; pipeline no
  longer calls it.
**Domain (`domain/events.py`)**: new `HedgeStatus` literal +
`HedgeResult` frozen dataclass (opportunity_id, status, counter_leg,
fills, remaining_exposure, reason). Exported from `domain/__init__`.
**Config (`config.py`)**: new `hedge_max_slippage_bps: int = 50`
(0.50% default per SKILL.md example).
**Adapter (`exchanges/paper.py`)**: `cancel_order` flipped from
`NotImplementedError` to a no-op return — PaperExchange has no order
book to cancel from, and forcing the hedger to special-case paper
adapters would leak abstraction. Stale sentinel test in
`test_paper.py` (`test_cancel_order_not_implemented`) replaced with
`test_cancel_order_is_noop` — third instance of MEMORY's "sentinel
NotImplementedError tests die" pattern.
**Pipeline (`orchestration/pipeline.py`)**: import renamed
`emit_hedge_alert → run_hedge`. New `_handle_hedge` helper threads
hedge fills through `log_file.append_fill`, `tracker.on_fill`, and
`counters["fills"]++`, then emits `hedger.result` summary log. Both
REST-poll mode and WS mode invoke the helper in their
`if result.needs_hedge:` branches.
**Tests**: `tests/unit/execution/test_hedger.py` (new, 13 tests —
compute_net_exposure × 3 [balanced / sell-fail-long / partial-aggregate],
_within_slippage × 3 [at-budget / drift-rejects-sell / drift-rejects-buy],
hedge orchestration × 7 [no_imbalance, happy-path-counter-leg,
abort_slippage, no_market_data, cancel-failure-swallowed,
placement_failed, opportunity_id-traceability]).
`tests/integration/test_pipeline.py` gains one integration test that
drives `_handle_hedge` directly with a crafted
`buy-filled + sell-failed` ExecutionResult and asserts
(1) hedge fill in audit log, (2) tracker.net_position = 0,
(3) counters["fills"] += 1.
**Live smoke**: drove the new `_handle_hedge` end-to-end with paper
adapters → `hedger.completed status=filled, counter_side=sell,
counter_venue=bybit, fair_price=60001, executed_price=60800,
remaining_exposure=0.000`. 1-line audit JSONL verified clean by
`verify_audit_chain.py`. **315/315 pytest passing** (was 301; +13
hedger unit + +1 pipeline integration; sentinel swap is net-zero).

## [2026-05-22] setup | Faz 7g-b — audit log SHA-256 hash chain (301 tests PASS)
**Goal**: catch tampering on `logs/decisions.jsonl` — operator or audit
must be able to prove the chain wasn't edited after the fact.
**Module (`persistence/decision_log.py`)**: every appended line now
carries `_prev_hash` and `_hash`. Hash = `sha256(canonical-JSON of the
line minus its own `_hash` field)`. Canonical = `json.dumps(payload,
sort_keys=True, default=str)` — Decimal/datetime fall through `default=
str` so the hash is stable regardless of dict iteration order or
serializer version. First line uses `GENESIS_HASH = "0" * 64`.
**Restart safety**: `_restore_chain_state` reads the last 32 KB of the
existing file on `DecisionLog.__init__`, extracts the last `_hash`, and
continues the chain — restart doesn't reset to GENESIS. Corrupt tail →
silently ignored; `verify_chain` will catch the boundary on next audit.
**Verification (`verify_chain(path)`)**: returns `(ok, message,
lines_checked)`. Walks file once, catches in order: file missing,
invalid JSON, missing `_hash`/`_prev_hash`, `_prev_hash` mismatch
(insert/delete/reorder), `_hash` mismatch (content tampered). Always
reports the first violation with its line number.
**CLI (`scripts/verify_audit_chain.py`)**: thin wrapper, exit 0 clean
/ exit 1 tamper / exit 2 invalid usage. Designed for CI / cron.
**Tests**: `test_decision_log.py` gains 8 chain tests (GENESIS first
line, `_prev_hash` links subsequent lines, restart continuation, clean
log verify, content tamper detection at line 1, deleted-middle-line
detection at line 2, missing `_hash` field, missing file).
`test_verify_audit_chain.py` (new, 4 CLI tests — clean exit 0, tamper
exit 1, missing file exit 1, no args exit 2).
**Smoke**: ran `PIPELINE_ITERATIONS=5 python -m arbitrage_agent` →
30-line `logs/smoke_chain.jsonl`. `verify_audit_chain.py` exit 0,
"verified 30 line(s); chain intact". Then mutated `confidence` on line
15 (without recomputing `_hash`) → script reported `line 15: _hash
mismatch (line content tampered)`, exit 1.
**301/301 pytest passing** (was 289; +8 chain + +4 CLI).

## [2026-05-22] setup | Faz 7g-a — min_balance + daily-loss auto-kill + balance polling (289 tests PASS)
**Settings additions**: `risk_min_required_balance_usd=50`,
`risk_max_loss_per_day_usd=50`, `balance_poll_per_iterations=5`
(0 disables).
**Limits**: matching 2 fields. `limits_from_settings` updated.
**Gate (`risk/gate.py`)**: check 10 added — `min_balance: {venue}
cash={x} < {limit}` reject when tracked cash falls under cap. Absent
venue in `cash_by_exchange` skips the check (paper-safe).
**Tracker (`account_state_tracker.py`)**: `daily_pnl_usd` /
`daily_pnl_day` properties. `on_fill` updates daily P&L with UTC day
rollover (`fill_day != self._daily_pnl_day` resets the counter).
P&L formula: `(+1 if sell else -1) × price × volume − fee`. New
`set_cash(exchange, amount)` for live balance polling.
**Pipeline new helpers**:
- `_poll_balances(adapters, tracker, asset)` — best-effort
  `fetch_balance` per venue; NotImplementedError / PermissionError
  silently skipped (paper / wrong-mode); other errors logged.
- `_maybe_engage_daily_loss_kill(tracker, settings)` — fires when
  `daily_pnl_usd < -max_loss_per_day_usd`, writes durable
  `logs/kill_switch.json` AND sets tracker.kill_switch_engaged=True
  so subsequent gate evaluations reject at check #1.
Both helpers wired into REST-poll and WS modes.
**Tests**: `TestDailyPnl` (6 — empty, buy-decreases, sell-increases,
buy-then-sell-nets-fees, arb-profit-accumulates, day-rollover);
`TestSetCash` (2); `TestMinRequiredBalance` in gate tests (4);
`test_daily_loss_kill.py` (5 — no-loss/no-kill, under-cap/no-kill,
at-threshold/no-kill, exceeds/engages, idempotent-safe).
`test_limits.py` defaults updated. **289/289 pytest passing**.

## [2026-05-22] setup | Faz 7f — 3 risk gate checks + AccountStateTracker (272 tests PASS, live demo)
**Settings additions**: `risk_max_position_value_usd=500`,
`risk_max_orders_per_minute=30`, `risk_max_snapshot_age_ms=10_000`.
**Domain (`risk/limits.py`)**: `Limits` gains the same three; `AccountState`
gains `recent_order_timestamps_ms: tuple[int,...]` and
`last_snapshot_age_ms_by_venue: dict[ExchangeId,int]`.
**Gate (`risk/gate.py`)**: 3 new checks appended after the existing
6, in SKILL.md § Decision Order:
- Check 7: projected post-fill abs(position) × limit_price >
  max_position_value_usd → reject.
- Check 8: recent submissions inside the rolling 60-second window +
  current legs > max_orders_per_minute → reject.
- Check 9: any leg's venue has a tracked snapshot older than
  max_snapshot_age_ms → `venue_stale: ...` reject. Venues absent from
  the freshness dict are skipped (paper smoke runs keep working).
**New `orchestration/account_state_tracker.py`**: in-memory
`AccountStateTracker` exposes 4 update inputs (`on_snapshot`, `on_fill`,
`on_order_submitted` / `on_intent_submitted`, `set_kill_switch`) and one
output `snapshot(now_ms) → AccountState`. Position deltas signed by
side (buy +qty, sell −qty); freshness uses max-of-incoming timestamps
(out-of-order frames don't regress); order deque hard-capped at 10k
entries.
**Pipeline (both poll + ws modes)**: tracker constructed at startup;
fed `on_snapshot` per fetch, `on_intent_submitted` before execute,
`on_fill` per recorded fill; gate reads `tracker.snapshot(now_ms)`.
**Tests**: `test_account_state_tracker.py` (12 — empty default,
position accumulation, per-venue isolation, freshness latest-wins +
out-of-order resilience, deque cap, kill-switch, per-leg order
recording). `test_gate.py` extended with `TestPositionLimit` (3),
`TestOrdersPerMinute` (3), `TestVenueFreshness` (3),
`TestFaz7fOrdering` (2). `test_limits.py` + `test_config.py` updated
with new defaults. 272/272 pytest passing.
**Live demonstration**: `PIPELINE_ITERATIONS=12` paper run — first 8
approved (positions $60→$480), iterations 9-12 rejected with reason
`position_limit: binance/BTC/USDT projected abs(qty)=0.009 × 60001 =
540.009 > 500`. Risk gate stopped capital exposure exactly where the
operator-configured cap said it should.
**Deferred to Faz 7g**: SKILL.md's `min_required_balance` (needs
fetch_balance polling + treasury reconciliation), `max_loss_per_day_usd`
(kill-switch auto-trigger from cumulative realised P&L), max_open_orders
(needs adapter order-status tracking).

## [2026-05-22] setup | Faz 7e — concurrent execution + reconciler + hedger (249 tests PASS)
**Domain additions**: `OrderState = Literal["pending","submitted",
"partial","filled","cancelled","rejected","failed"]` (SKILL.md state
machine vocabulary); `LegResult` frozen dataclass (leg, order_id|None,
state, fills tuple, error_message); `ExecutionResult` frozen dataclass
(opportunity_id, legs tuple, `all_filled` + `needs_hedge` properties).
**New `execution/reconciler.py`**: pure `classify_leg(intent, error,
fills) -> OrderState`. Mapping: InvalidOrder/MarketHalted/
PermanentFailure → rejected; RateLimited/TemporaryFailure/unknown →
failed (reconciliation required); full quantity → filled; partial → 
partial; zero with no error → cancelled. Errors override fills.
**New `execution/hedger.py`**: `needs_hedge(result)` + `emit_hedge_alert
(result)` — Faz 7e MVP only logs the imbalance; auto-hedge order
placement deferred to Faz 7e+. Carries each bad leg's exchange, side,
intended/filled quantities, state, error.
**`execution/engine.py` rewrite**: `_submit_one_leg` runs `place_order`
+ `fetch_fills` under `asyncio.wait_for(timeout=opp.valid_for_ms/1000)`
per leg; `execute` launches every leg concurrently via `asyncio.gather`
and returns `ExecutionResult`. Cardinal-rule pre-flight checks
(approved + opportunity_id + adapter present) run BEFORE any submission
so no orphan legs ever ship.
**Pipeline updates** (both REST poll + WS modes): consume
`ExecutionResult`; log per-leg state vector + order_ids; route fills
from `result.legs[i].fills` to the audit log; call `emit_hedge_alert`
when `result.needs_hedge`.
**Tests**: `test_reconciler.py` (12 — every error class, fill-vs-
intent quantity boundaries, error-overrides-fills). `test_engine.py`
rewritten (9 — happy concurrent, ~50% concurrency speedup measured,
timeout marks leg failed while others still fill, adapter exception
classified, cardinal-rule guards, per-leg fill attribution). 6
obsolete sentinel tests removed. Total 249/249 pytest passing.

## [2026-05-22] bug-found | Operator network blocks Binance TLS handshake (testnet + mainnet)
Operator's environment now rejects HTTPS to `api.binance.com` and
`testnet.binance.vision` (LibreSSL `WRONG_VERSION_NUMBER` from both
curl and Python aiohttp). Bybit (`api.bybit.com`) responds normally
from the same machine, so the issue is venue-specific (geo-blocking /
ISP filtering / VPN state). Bot code is healthy — Faz 7a/7c ran fine
earlier and Faz 7b's 11 unit tests against aiohttp stub server all
pass. Operator action: VPN to a country where Binance accepts
connections, or use mobile hotspot, or wait for the block to clear.
Defence-in-depth lesson: do not assume external connectivity stays
stable; testing should always include an offline path
(`tests/unit/exchanges/test_binance_auth.py` is the reference).

## [2026-05-22] setup | Faz 7b — Binance authenticated REST + S5/S6/S7 (234 tests PASS)
**HMAC signing (S6)**: stdlib `hmac.new(secret, query, hashlib.sha256).
hexdigest()`. No third-party signing libs. `hmac.compare_digest` reserved
for future verification paths.
**Auth scaffolding**: `BinanceAdapter` constructor gained
`api_key/api_secret` params (default None). Registry passes
`Settings.binance_api_{key,secret}`. `_sign(params)` builds the URL-
encoded signed query; `_signed_request(method, path, params)` is the
low-level signed HTTP helper carrying `X-MBX-APIKEY` header.
**S5 canWithdraw probe**: `_ensure_no_withdraw_permission()` calls
`GET /api/v3/account` once per adapter lifetime; if `canWithdraw=true`,
raises `PermanentFailure` and refuses all subsequent auth ops; if
`canTrade=false`, similar rejection. Result cached on success.
**Implemented endpoints**:
- `place_order(intent, decision)` → POST /api/v3/order
  (LIMIT/GTC, params: symbol, side, type, timeInForce, quantity,
  price, newClientOrderId=opportunity_id). Approval check BEFORE
  withdraw probe to fail fast.
- `cancel_order(order_id)` → DELETE /api/v3/order using
  `origClientOrderId`.
- `fetch_balance(asset)` → reads `balances[]` from /api/v3/account.
- `fetch_fills(since)` → stub returning `[]`; Faz 7e wires symbol
  threading (Binance `/api/v3/myTrades` is per-symbol).
**Tests**: `test_binance_auth.py` — 10 cases: signature correctness +
APIKEY header, S5 rejection (withdraw / no-trade), probe caching,
place_order param formatting, unapproved-decision adapter-side reject,
withdraw-detected-before-order block, fetch_balance lookup, missing
credentials path, cancel_order client-id propagation. 2 obsolete
`NotImplementedError` sentinel tests removed (Faz 7a sentinel pattern
shed for the third and final time on Binance).
**S7 testnet probation**: documented in README + .env.example +
MEMORY.md. Automated enforcement deferred to Faz 7g (30-day evidence).
**Operator runs (testnet)**:
`EXECUTION_MODE=live BINANCE_ENABLED=true \\
 BINANCE_REST_BASE_URL=https://testnet.binance.vision \\
 .venv/bin/python -m arbitrage_agent`

## [2026-05-22] setup | Faz 7c — WebSocket subscription + event-driven pipeline (218 tests PASS, 283 live frames in 9s)
**New code**: `ingestion/reconnect.py` (`ExponentialBackoff` with jitter,
configurable initial/factor/max, attempt counter, reset()), `ingestion/
bus.py` extended with `MarketDataBus` (async pub-sub fan-out, exception
isolation per subscriber), `BinanceAdapter.subscribe` (combined-stream
`/stream?streams=btcusdt@bookTicker`, JSON frame parsing with optional
`stream` wrapper handling, reconnect loop with backoff), `BybitAdapter.
subscribe` (V5 spot WS at `wss://stream.bybit.com/v5/public/spot`, send
`subscribe` op then receive `orderbook.1.SYMBOL` frames, ack skip),
`orchestration/pipeline._run_ws` (event-driven mode: build strategy if
≥2 venues, set up `MarketDataBus`, register on_snapshot handler with
chain lock for serialization, launch adapter subscribe tasks, run for
`ws_timeout_s` seconds, clean shutdown). Settings gained
`ingestion_mode: Literal["poll","ws"]="poll"`, `ws_timeout_s=30`,
`binance_ws_base_url`, `bybit_ws_base_url`. `.env.example` placeholders
added. **Tests**: `test_reconnect.py` (6), `test_market_data_bus.py`
(5), `test_ws_subscribe.py` (6 — Binance + Bybit against aiohttp
in-process WS server with `Event`-based cancellation). Removed two
obsolete `subscribe_not_implemented` sentinels (they hung dialing the
real WS endpoints). Total 218/218 pytest passing.
**Live verification (operator-approved)**:
`BINANCE_ENABLED=true BYBIT_ENABLED=true INGESTION_MODE=ws
WS_TIMEOUT_S=10 python -m arbitrage_agent` produced **283 snapshots
in 9 seconds** (Binance 249 / Bybit 34). Real BTC top-of-book:
Binance $77,741.59/60 (spread $0.01), Bybit $77,745.80/90 (spread
$0.10). No opportunities triggered — fees+slippage exceed the
~$4 cross-venue gap at default 0.001 BTC size.
**Dashboard polling cadence reduced** 2 s → 500 ms to surface live
prices faster during WS mode.

## [2026-05-21] setup | Faz 7d — Bybit live REST adapter (203 tests PASS, two real venues live)
`exchanges/bybit.py` mirrors the Binance pattern. Differences: endpoint
`/v5/market/orderbook?category=spot` (HTTP 200 even on errors;
discriminator is `retCode` field), response shape uses `result.b` /
`result.a` for bids/asks, rate limit 120/min (Bybit allows ~600/5s
public, so 80% of one-second burst capacity is safe). Domain error
mapping subset: 10006/10018 → RateLimited; 10001/10002/10004 →
InvalidOrder; 10005/10010/10016 → PermanentFailure; unknown →
TemporaryFailure (retryable). `requires_live_mode` decorator (S3)
applied to place_order/cancel_order/fetch_balance/fetch_fills.
`exchanges/registry.py` gained a bybit branch. `config.py` has
`bybit_enabled`/`bybit_rest_base_url`/`bybit_rate_limit_per_min`; the
`@model_validator` S4 guard now covers Bybit mainnet too.
`.env.example` placeholders added. 19 new tests across
test_bybit.py (12), test_registry.py (+2), test_config.py (+3 Bybit
S4 cases). Live verification (operator-approved): BINANCE_ENABLED=true
BYBIT_ENABLED=true PIPELINE_ITERATIONS=3 produced 6 snapshots
(binance 77,111.96/97 vs bybit 77,103.80/90; ~$8 spread), strategy
emitted "no_opportunity" — fees+slippage on a 0.001 BTC trade
($0.17 cost) exceed the $0.008 gross. Mathematical proof that crypto
arb is harder than synthetic demos suggest. Total 203/203 pytest
passing.

## [2026-05-21] setup | Faz 7-S Adım 2 — S1+S2+S3+S4 implemented (184 tests PASS)
**S1 (gitleaks)**: `.gitleaks.toml` ships 5 custom rules atop default
ruleset (binance/bybit key+secret patterns, bare HMAC SHA-256 hex
digest), with allowlist for `.env.example` / `dashboard/smoke.html` /
`SECURITY.md` / `tests/`. `.pre-commit-config.yaml` invokes
`gitleaks/gitleaks@v8.18.4` with our config. `.github/workflows/
security.yml` re-runs the scan on every push and PR (full history).
Operator one-time setup: `brew install gitleaks && pip install
pre-commit && pre-commit install`.
**S2 (expanded redaction)**: `_SECRET_KEY_NEEDLES` extended to 14
entries (added: pwd, signature, hmac, private_key, bearer, auth,
credential, passphrase, salt). New `_redact_byte_values` processor
masks any `bytes` / `bytearray` value regardless of field name.
String-shape redaction deliberately omitted (would clash with UUIDs/
order-ids).
**S3 (live-mode decorator)**: `@requires_live_mode` in
`exchanges/base.py` reads `EXECUTION_MODE` from `os.environ` at call
time, raises `PermissionError` when not `live`. Applied to
BinanceAdapter's 4 authenticated methods (place_order, cancel_order,
fetch_balance, fetch_fills). PaperExchange deliberately exempt.
**S4 (mainnet confirmation)**: `Settings.@model_validator(mode="after")`
refuses construction when `execution_mode='live'` + `binance_enabled=
true` + mainnet base URL + `LIVE_TRADING_CONFIRMED!="true"`.
**SECURITY.md change log**: C3, C6, S1-S4 marked IMPLEMENTED with
dated entries. README "One-time security setup" section added.
**Tests**: 17 new (3 redact expansion + 5 byte-redact + 9 decorator).
Total 184/184 pytest passing.

## [2026-05-21] setup | Faz 7-S Adım 1 — `specs/SECURITY.md` written
Single-file threat model + 15 controls (C1-C8 from CLAUDE.md anayasası
+ S1-S7 defense-in-depth) with status (IMPLEMENTED / PARTIAL / PLANNED)
+ mechanism + test reference + per-faz gates + operator
responsibilities + incident response playbook + deferred items + change
log. Cross-references: `CLAUDE.md § 5 File Map` row added;
`specs/INDEX.md` row added; `STATUS.md § Next` reordered to include
Faz 7-S Adım 2. No code changed — pure documentation eylem. Pytest
remained 167/167 unchanged.

## [2026-05-21] setup | Faz 7a — Binance live REST adapter (read-only, 167 tests PASS, real $77k BTC fetched)
**Code**: `exchanges/binance.py` (`BinanceAdapter` with `fetch_book_snapshot`
hitting `/api/v3/depth`; other 6 protocol methods raise NotImplementedError),
`exchanges/errors.py` (domain exception hierarchy: ExchangeError +
RateLimited / InsufficientFunds / OrderNotFound / MarketHalted /
InvalidOrder / TemporaryFailure / PermanentFailure per SKILL.md § Error
Translation), `exchanges/rate_limit.py` (`TokenBucket` async, capacity +
refill rate), `exchanges/registry.py` rewritten from placeholder (
`build_live_adapters` returns Binance when `BINANCE_ENABLED=true`),
`config.py` extended with `binance_enabled` / `binance_rest_base_url` /
`binance_rate_limit_per_min`, `pyproject.toml` `aiohttp>=3.9` runtime dep,
`.env.example` with new placeholders.
**Pipeline rewrite**: `orchestration/pipeline.py` now has 3 modes:
test-injected paper, live (from registry), default synthetic paper.
Single-venue live mode short-circuits strategy evaluation (needs ≥2
venues); snapshots are still logged so the dashboard renders live prices.
`persistence/decision_log.py` gained `append_snapshot(MarketSnapshot)`.
**Dashboard**: new `SnapshotFetchedEvent` type, `latestSnapshotsByVenue()`
data helper, `Overview` new "Live Prices" Card row showing bid/ask/spread/
timestamp per venue with "live | paper" chip.
**Tests**: `tests/unit/exchanges/{test_errors.py,test_rate_limit.py,
test_binance.py,test_registry.py}` — 23 new tests including aiohttp
in-process stub server for HTTP roundtrips (no network). Integration
test_pipeline updated to reflect snapshot logging (events list now
includes `snapshot_fetched` at the head).
**Live verification (operator-approved one-time real hit)**:
`BINANCE_ENABLED=true PIPELINE_ITERATIONS=3 python -m arbitrage_agent`
fetched 3 snapshots from api.binance.com — BTC bid=$77,342.45,
ask=$77,347.75, spread=$0.01 (reality: real cross-exchange spreads are
tiny vs the $800 synthetic; honest confirmation that arb opportunities
will be rare until WS + 2+ venues land in Faz 7c+7d).
**Result**: 167/167 pytest passing; dashboard renders live BTC price via
"Live Prices" card; no opportunities/fills written (single-venue
short-circuit, as designed).

## [2026-05-21] decision | Faz 7a scope — Binance-only REST + snapshot log + dashboard Live Prices card
Single-exchange live data first. Strategy disabled in single-venue mode
(can't detect spatial arb with 1 venue); pipeline logs snapshots so
dashboard has something to show. Honest about limitation: "Faz 7d adds
Bybit; until then, no opportunities possible from real data." Other
deferrals: ccxt → kept native aiohttp (Karpathy 1.2); vcrpy → not used,
aiohttp in-process test server suffices for offline tests; live
authenticated endpoints → Faz 7b with testnet API key.

## [2026-05-21] setup | Step 2 (a) — Vite + React 18 + TS + MUI v6 dashboard with live bot data
`dashboard/` converted from single static HTML to a Vite project. Static
smoke preserved at `dashboard/smoke.html` for visual diff. New: `package.
json` (React 18.3 + MUI 6.1 + emotion + @fontsource/roboto + @fontsource/
roboto-mono + Vite 5.4 + TypeScript 5.5), `tsconfig.json` + `tsconfig.
node.json` strict mode, `vite.config.ts` with custom middleware that
serves `/logs/*` and `/api/kill-switch` from the project-root `logs/`
directory (no symlink, no file copying). React tree: `main.tsx` →
`App.tsx` (ThemeProvider + theme toggle + persisted via localStorage)
→ `components/Layout.tsx` (`TopBar` with kill-switch chip, `LeftRail`
drawer, `KillSwitchBanner`, `Shell`) → `components/Overview.tsx` (4
KPI cards: P&L with direction glyph from § 4.1, opportunities count,
approval %, unique exchanges; two MUI Tables for opportunities + fills
with mono-font numerics + outlined chips for state). `theme.ts` carries
both palettes from DESIGN_LANGUAGE.md § 3 plus `custom.{pnl,order,
killSwitch}` extensions and dense defaults (§ 8). `dataModel.ts`
provides `useAuditLog(2000ms)` + `useKillSwitch(2000ms)` polling hooks
and pure `summarize()` for KPI math. Project root `.gitignore` extended
for `dashboard/node_modules/`, `dashboard/dist/`, `dashboard/public/
logs`. `npm install` pulled 130 packages in 52 s. Live verification:
PIPELINE_ITERATIONS=5 produced 24-line audit log; Vite dev server on
3005 returned HTTP 200 for `/`, `/logs/decisions.jsonl` (6.7 KB),
`/api/kill-switch` (`{"engaged":false}`).

## [2026-05-21] setup | Step 1 (c) — Dashboard design smoke (`dashboard/index.html`)
Single-file design preview, 737 lines vanilla HTML+CSS+JS (no React, no
MUI, no build). Renders every canonical decision from
`specs/DESIGN_LANGUAGE.md` §§ 3-10: dark/light theme toggle with the
exact hex tokens from § 3, P&L positive/negative/flat with paired
direction glyphs (§ 4.1), latency tiers w/ pulse on critical-state
transition (§ 4.2 + § 10), WebSocket connection chips incl. quarantined
(§ 4.3), all 7 order lifecycle states (§ 4.4), kill-switch toggle that
turns the whole-app red + persistent error banner + `[KILL]` tab title
(§ 4.5), Roboto Mono on every numeric (§ 5), AppBar + LeftRail + Main
canonical layout (§ 6), dense default row padding (§ 8), no-data /
fetch-failed / stale state examples (§ 9), motion limited to one pulse
(§ 10). `dashboard/README.md` documents how to open + reviewer
checklist + explicit "this is a smoke, real React+MUI+Vite arrives in
step 2." HTML structure verified clean (737-line file parsed without
real errors; void-tag false positives noted).

## [2026-05-21] setup | Faz 6 — paper-trade MVP runs end-to-end (144 tests PASS, `python -m arbitrage_agent` works)
`config.py` gained `pipeline_iterations` + `pipeline_decision_log_path`.
`persistence/decision_log.py` JSONL append-only writer with three event
types (opportunity_detected, risk_decision, fill). `exchanges/paper.py`
`place_order` now records a synthetic Fill at the intent's limit price
and `fetch_fills(since)` returns matching fills; new `taker_fee_bps`
ctor arg. `execution/engine.py` `execute(opp, decision, adapters)`
places legs sequentially with cardinal-rule enforcement (approved +
opportunity_id match). `orchestration/pipeline.py` async `run(settings)`
wires it all: builds adapters from seeded snapshots, runs the strategy,
gates risk, executes, collects fills, logs both to structlog (stdout)
and JSONL (file). `__main__.py` calls `asyncio.run(pipeline.run(...))`
and emits start/complete events. README "Getting Started" section
documents `pip install -e ".[dev]"` + `python -m arbitrage_agent` with
expected output and env-var overrides. 19 new tests: DecisionLog (6),
execute (5), pipeline integration (4), paper fill emission (4). Live
smoke: bot detected $0.66 opportunity, risk approved, 2 fills written,
4-line audit log produced. Total 144/144 pytest passing.

## [2026-05-21] setup | Faz 5c — SpatialArbitrage + Clock + MarketView + end-to-end chain (125 tests PASS)
`domain/events.py` gained `Opportunity.valid_for_ms`. `config.py` gained
6 spatial settings (`size_btc`, `taker_fee_bps`, `slippage_usd_per_leg`,
`min_profit_threshold_usd`, `valid_for_ms`, `confidence`); removed
`risk_max_opportunity_age_ms`. `risk/limits.py` removed
`max_opportunity_age_ms`. `risk/gate.py` freshness uses
`opp.valid_for_ms`. New: `orchestration/clock.py` (SystemClock),
`ingestion/bus.py` (LatestSnapshotView), `strategies/spatial.py`
(SpatialArbitrage with bps-fee + constant-slippage model + buy-first leg
ordering). 24 new tests across orchestration/clock (4),
ingestion/bus (6), strategies/spatial (14, incl. purity tests). 41 source
modules total. Smoke chain demonstrated 3 scenarios: aggressive size →
strategy emits $0.77 opp / risk rejects $602 leg; tiny spread → strategy
returns None; operator widens limits → full approve path through gate.

## [2026-05-20] setup | Faz 5b — Risk gate + limits + kill-switch (101 tests PASS)
`config.py` gained 6 risk Settings (4 Decimal limits + `_max_opportunity_
age_ms: int` + `_kill_switch_path: Path`). `risk/limits.py` exposes
`Limits` frozen dataclass + `limits_from_settings()`; `AccountState` now
includes `kill_switch_engaged: bool = False`. `risk/kill_switch.py` is a
functional sync-I/O module (`is_engaged`, `engage`, `reset`; malformed
file → treated as not-engaged). `risk/gate.evaluate(opp, state, limits,
now_ms)` runs 6 checks in spec'd order; first failure stops; opportunity
_id always carried in the decision. `test_imports.py` gate sentinel
replaced with signature regression. New: `tests/unit/risk/{test_limits,
test_kill_switch,test_gate}.py` — 31 tests covering AccountState, Limits
projection, kill-switch durability + malformed file resilience, gate
happy + 6 reject paths + decision-order + traceability. Smoke chain
demonstrated clean/kill-switch/stale/low-profit scenarios all rendering
correctly. 101/101 pytest passing.

## [2026-05-20] setup | Faz 5a — PaperExchange + ExchangeAdapter Protocol expanded (70 tests PASS)
`domain/ids.py` gained `Asset = NewType[str]`; `domain/__init__.py`
exports updated (18 names). `exchanges/base.py` rewritten to match
SKILL.md § The Protocol (7 members + `SnapshotCallback`). `exchanges/
paper.py` implemented: ctor takes optional `prices: dict[Symbol,
MarketSnapshot]` and `name` (defaults `"paper"`); `id` property returns
`ExchangeId(name)`; `fetch_book_snapshot` clones cached snapshot with
fresh `timestamp_utc`, raises `KeyError` on unseeded symbol; `place_order`
raises `ValueError` when `decision.approved is False`, otherwise returns
fresh `OrderId`; the 4 unimplemented methods raise `NotImplementedError`
(Faz 5b+). `tests/unit/exchanges/test_paper.py` — 14 tests including
runtime `isinstance(ex, ExchangeAdapter)` and Faz-5b-sentinel guards.
`tests/unit/test_imports.py` Protocol-member check expanded to all 7
spec members. AST boundary: ccxt/aiohttp only inside `exchanges/`
(confirmed clean). 70/70 pytest passing.
