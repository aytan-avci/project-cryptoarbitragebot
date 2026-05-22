# MEMORY — Project-Crypto-Arbitrage-Bot

> **Project-level long-term memory.** Decisions, gotchas, operator preferences
> that survive across sessions, agents (Claude Code / Cursor / others), and
> context compactions. Not personal to one Claude instance.
>
> **Append carefully.** Every entry has a date and a reason. If a decision is
> reversed, do not delete it — add a new entry that supersedes it and note
> the link. History matters; truthful evolution beats clean-looking pages.

---

## Decisions & Why

### 2026-05-20 — MUI v6 chosen for the future operator dashboard
- **What:** React + Material UI v6+ is the frozen UI stack.
- **Why:** No design team; accessibility ships as default; theming consolidated
  in one `createTheme` call. Banned: Tailwind, custom CSS frameworks, ad-hoc
  `styled-components` for layout.
- **Where:** `specs/DESIGN_LANGUAGE.md § 2`.

### 2026-05-20 — Repo uses `specs/` (not `docs/`) for design documents
- **What:** Spec docs live under `specs/`; Claude Code's `skills/` is the
  native skill location.
- **Why:** `specs/` is tool-neutral (Cursor, Claude Code, others read it the
  same); `docs/` carries website/publishing connotations we don't want.

### 2026-05-20 — Karpathy wiki pattern adopted operationally (light form)
- **What:** Four wiki files (`STATUS.md`, `MEMORY.md`, `specs/INDEX.md`,
  `specs/LOG.md`) maintained by the agent under `CLAUDE.md § 9`.
- **Why:** (1) Survive `/compact` and new sessions, (2) reduce token cost by
  skipping repo re-greps, (3) build a compounding record of decisions.
- **Where:** This file + `specs/karpathy-wiki.md` (canonical pattern reference).

### 2026-05-20 — Python tooling: uv + hatchling + PEP 621 floor versions
- **What:** `uv` is the package manager, `hatchling` is the PEP 517 build
  backend, dependencies declared in `pyproject.toml` with **floor** version
  bounds (`pkg>=X.Y`) and reproducible installs guaranteed by `uv.lock`.
  Dev dependencies live in `[project.optional-dependencies] dev`, not a
  separate `requirements-dev.txt`.
- **Why:** uv is 10–100× faster than pip/poetry, lock file is PEP-standard,
  one config file = one source of truth. Floor versions + lock = no
  version-pinning theatre (Karpathy 1.2).
- **Where:** `pyproject.toml`. Operator approved 2026-05-20.

### 2026-05-20 — Domain types: NewType for ids/money, frozen dataclass for events (spec-aligned in Faz 2.5)
- **What:** `ExchangeId` / `OpportunityId` / `OrderId` are `NewType[str]` (no
  runtime overhead, static type safety). `Symbol` is a frozen+slots dataclass
  with `from_string('BASE/QUOTE')` factory. `Price` / `Volume` are
  `NewType[Decimal]` with `price()` / `volume()` factories that **reject
  float** at the type signature. Events (`MarketSnapshot`, `OrderIntent`,
  `Opportunity`, `RiskDecision`, `Fill`) are frozen+slots dataclasses.
  `OrderSide = Literal["buy","sell"]`; `StrategyName = Literal["spatial",
  "triangular","funding"]`. Timestamps are `datetime.now(timezone.utc)` via
  `now_utc()`. **Field names match `ARCHITECTURE.md § 6` exactly**
  (`bid_size` not `bid_volume`, `timestamp_utc` not `timestamp`,
  `expected_net_profit` not `expected_pnl`, etc.).
- **Why:** Financial code where unit-bugs (price-as-volume, float drift,
  naive datetime) silently corrupt money. Static types catch class A;
  immutability catches class B; explicit Decimal catches class C; spec
  alignment catches class D (cross-module field mismatch).
- **Where:** `src/arbitrage_agent/domain/` + 50 unit tests in
  `tests/unit/domain/` (incl. spec-name regression guards). Faz 2 wrote
  intuition-named fields 2026-05-20; Faz 2.5 reconciled to spec same day.

### 2026-05-20 — Config & logging stack — pydantic-settings + structlog (PrintLoggerFactory)
- **What:** `Settings(BaseSettings)` reads `.env` from CWD + env vars
  (env > .env > defaults, case-insensitive). `EXECUTION_MODE` is a
  `Literal["paper","live"]` — invalid value triggers `ValidationError`
  before any logic runs (CLAUDE.md § 2 C3 enforcement).
  `configure_logging(level)` uses `structlog.PrintLoggerFactory` (not the
  stdlib bridge) — simpler; third-party loggers are silent for now and will
  be wired through stdlib in a later faz if needed.
- **Why:** PrintLoggerFactory keeps the path short and the test surface tiny
  (Karpathy 1.2). Stdlib bridge can come when a third-party library starts
  logging in ways we need to capture.
- **How to apply:** Always read `Settings()` once at startup; never
  re-construct inside hot paths. Always call `configure_logging` before the
  first `structlog.get_logger()`.
- **Where:** `src/arbitrage_agent/config.py`, `observability/logging_setup.py`.

### 2026-05-20 — Secret redaction is a logging-processor invariant, not caller responsibility
- **What:** `_redact_secrets` processor scans every event_dict before
  rendering and masks any field whose **key** contains `api_key`,
  `api_secret`, `password`, `secret`, or `token`. Empty / None values are
  left as-is (no leak via "***" appearing where nothing was).
- **Why:** CLAUDE.md § 2 C6. Caller forgetting to redact must not produce
  a leak. The processor is the last line of defense.
- **How to apply:** Adding a new credential field? Either name it with one
  of the existing needles, or extend `_SECRET_KEY_NEEDLES`. Never log a
  raw credential expecting the caller to mask it.
- **Where:** `src/arbitrage_agent/observability/logging_setup.py`.

### 2026-05-20 — Protocol-based interfaces (typing.Protocol + runtime_checkable)
- **What:** Cross-module contracts are `typing.Protocol` subclasses, not
  ABCs. Three Protocols defined in Faz 4: `ExchangeAdapter`
  (`exchanges/base.py`), `Strategy` + `MarketView` + `Clock`
  (`strategies/base.py`). All decorated with `@runtime_checkable` so
  `isinstance(x, Protocol)` works for tests.
- **Why:** Structural typing — adapters don't need to inherit; any class
  with the right shape qualifies. Mock objects work without ABC ceremony.
  ABCs would add a runtime layer with no information gain.
- **How to apply:** Adding a new cross-module contract? Use Protocol.
  Adding a value type? Use `@dataclass(frozen=True, slots=True)`. Don't
  mix the two.
- **Where:** `src/arbitrage_agent/{exchanges,strategies}/base.py`.

### 2026-05-20 — `MarketView` and `Clock` live in `strategies/`, not `domain/`
- **What:** These two interfaces are what the Strategy **consumes** (read
  surface for snapshots; injected time source). They are not data flowing
  between modules, so they don't belong in `domain/`. They live in
  `strategies/base.py` alongside the `Strategy` protocol.
- **Why:** `domain/` is for transported data (events, ids, money).
  `strategies/base.py` is for the interface contract a strategy depends
  on. Putting interface dependencies in `domain/` would let any module
  import them, which conceptually pollutes the domain layer with
  module-internal helper contracts.
- **How to apply:** Data type → `domain/`. Interface a single module
  consumes/produces → that module's `base.py`.

### 2026-05-20 — SKILL.md is normative for protocols; ARCHITECTURE.md is the sketch
- **What:** Faz 4 wrote `ExchangeAdapter` from ARCHITECTURE.md § 6 alone
  (3 members). Reading the SKILL.md before Faz 5a revealed 4 additional
  members SKILL.md mandates (`id` property, `subscribe`, `cancel_order`,
  `fetch_balance`, `fetch_fills`) plus the `SnapshotCallback` type. The
  ARCHITECTURE.md text even says *"Defined precisely in the skill files;
  sketched here."* — but I missed that line in Faz 4.
- **Lesson (Karpathy 1.1, again):** For module Protocols, the SKILL.md is
  the source of truth. ARCHITECTURE.md § 6 sketches the *data* contracts
  (events) but the *behaviour* contracts live in SKILL.md.
- **How to apply:** Before writing/extending a Protocol in any
  `<module>/base.py`, open `skills/<module>/SKILL.md § The Protocol` and
  copy every declared member. Test with `runtime_checkable` so a missing
  member fails `isinstance` at runtime.

### 2026-05-20 — PaperExchange is the canonical adapter test surface
- **What:** `PaperExchange` is the first concrete `ExchangeAdapter`. It
  uses a static price-table seeded at construction; each
  `fetch_book_snapshot` refreshes only `timestamp_utc` (via
  `dataclasses.replace`). `place_order` enforces the gate
  (`decision.approved == True`, else raise) and returns a fresh
  `OrderId`; fill simulation is deferred to Faz 5b.
- **Why:** SKILL.md § PaperExchange — "the strategy/risk/execution code
  cannot distinguish PaperExchange from BinanceAdapter." Static prices
  give deterministic tests now; real-book walk + slippage come once the
  rest of the chain (risk + strategy + engine) is in place.
- **How to apply:** Any new test that needs an exchange uses
  `PaperExchange(prices={...})` — not mocks. Mocks lie; PaperExchange
  satisfies the same Protocol the real adapters will.
- **Where:** `src/arbitrage_agent/exchanges/paper.py`,
  `tests/unit/exchanges/test_paper.py` (14 tests, including
  Faz-5b-unimplemented sentinel'lar).

### 2026-05-20 — Risk gate is a pure function; kill-switch state flows in via AccountState
- **What:** `risk.gate.evaluate(opportunity, state, limits, now_ms)` is a
  pure function. Time is **injected** (`now_ms: int`). Kill-switch state
  is a field on `AccountState` (read by the orchestrator from
  `kill_switch.is_engaged(path)`, then frozen into the snapshot). The
  gate never performs I/O — SKILL.md § Anti-Patterns enforced.
- **Why:** Pure gate = deterministic tests. Injecting time and
  kill-switch state makes "engage kill-switch then call gate" trivial
  to test without monkeypatching the clock or the filesystem. Same
  testability discipline as strategies.
- **How to apply:** New risk check? Add it to `gate.evaluate` in
  decision-order. The check's input must come from `(opportunity, state,
  limits, now_ms)`; if you need new state, add a field to `AccountState`
  and have the orchestrator populate it.
- **Where:** `src/arbitrage_agent/risk/{gate,limits,kill_switch}.py`;
  31 tests in `tests/unit/risk/`.

### 2026-05-20 — Risk limits come from Settings at startup, never mid-flight
- **What:** `Settings` defines 6 risk fields (`risk_*`).
  `limits_from_settings(s)` projects them into a frozen `Limits` dataclass
  built once at startup. Hot-reload is explicitly a v2 concern (SKILL.md
  § Anti-Patterns: "Loading limits at evaluation time from disk").
- **Why:** Limit changes are operator decisions; a restart is the
  affordance that makes the change auditable. Mid-flight changes would
  break QA-5.3 and add a class of race conditions to a safety-critical
  module.
- **How to apply:** Operator wants tighter limits? Edit `.env` + restart.
  Never add a path that mutates `Limits` after construction.

### 2026-05-21 — Freshness threshold is `opportunity.valid_for_ms`, not a global cap
- **What:** SKILL.md `Opportunity` contract mandates a `valid_for_ms: int`
  field (the strategy declares each opportunity's shelf-life). The risk
  gate's freshness check uses `opportunity.valid_for_ms` directly; the
  Faz 5b global `limits.max_opportunity_age_ms` field was removed. Single
  source of truth per Karpathy 1.2.
- **Why:** Different strategies have different shelf-lives (funding-rate
  opportunities last seconds; triangular cycles must execute in ms). A
  global cap would either be too loose (defeats the point) or too tight
  (kills valid opportunities). Strategy-declared validity scales.
- **How to apply:** Adding a new strategy? Pick its `valid_for_ms` based
  on how fast its edge decays in your market data. Risk gate honours it.
- **Where:** `domain/events.py` (Opportunity field), `risk/gate.py`
  (freshness check), `risk/limits.py` (no more `max_opportunity_age_ms`),
  `config.py` (no more `risk_max_opportunity_age_ms`).

### 2026-05-21 — SystemClock lives in `orchestration/`, not `strategies/`
- **What:** `strategies/` is AST-enforced pure (no `time` import).
  `SystemClock` (the default `Clock` impl that calls `time.time()`) lives
  in `orchestration/clock.py`. The orchestrator constructs it and passes
  it into every `Strategy.evaluate(view, clock)` call.
- **Why:** Strategies must remain deterministic for replay (QA-6.2). The
  Protocol/concrete split keeps the consumer interface in `strategies/`
  and the wall-clock-reading concrete in `orchestration/` (where I/O is
  allowed).
- **How to apply:** Need a new infra concrete for a strategy-side
  Protocol (Clock, MarketView, etc.)? Implement it OUTSIDE `strategies/`
  if it touches I/O, time, or any non-pure source. Tests use small
  hand-rolled fakes (`_FixedClock(now_ms=...)` is the pattern in
  `tests/unit/strategies/test_spatial.py`).
- **Where:** `orchestration/clock.py`, `ingestion/bus.py`
  (LatestSnapshotView), `tests/unit/strategies/test_spatial.py`.

### 2026-05-21 — Defense-in-depth between strategy and risk gate is the design, not a bug
- **What:** A strategy emits `Opportunity` with its own
  `min_profit_threshold`; the risk gate has its own
  `min_profit_threshold_usd` and additional `max_order_value_usd` /
  `max_gross_exposure_usd` caps. Faz 5c smoke chain showed strategy
  emitting a $0.77 opportunity that risk REJECTS because the leg value
  ($602) exceeds the operator's $200 cap. This is intended.
- **Why:** Strategies optimise for profit; risk optimises for survival.
  Two layers protect against (a) a strategy mis-estimating profit,
  (b) a strategy emitting a too-large size, (c) operator policy change
  without code change. Either layer can independently veto.
- **How to apply:** Adding a check in one layer? Consider whether the
  other layer should also enforce it (belt-and-suspenders) or whether
  it's clearly the other layer's concern. Profit threshold appears in
  both (with different defaults allowed); order-value bounds are
  risk-only (strategies don't think about position concentration).

### 2026-05-21 — Decision log is JSONL via `default=str`; one stream, three event types
- **What:** `persistence/decision_log.py` writes one JSON line per
  `opportunity_detected` / `risk_decision` / `fill` event. Decimal,
  datetime, and Symbol fields go through `json.dumps(..., default=str)`.
  Single file at `logs/decisions.jsonl` (gitignored).
- **Why:** SKILL.md § Append-Only Decision Log + CLAUDE.md § 2 C4 (audit
  trail). JSONL is `grep`-friendly, append-cheap, replayable. SQLite +
  rotation arrive when volume needs them (Faz 7+).
- **How to apply:** New event type? Add an `append_<type>` method. Always
  include `"event"` field for `grep`-by-type. Never log raw API responses
  (CLAUDE.md § 2 C6 — secret redaction is structlog's job, not the audit
  log's, but the audit log also should not become a leak vector).

### 2026-05-21 — Execution engine enforces cardinal rule at runtime, twice
- **What:** `execution.engine.execute` rejects on (a) `decision.approved is
  False` and (b) `decision.opportunity_id != opportunity.id`. The same
  approval check exists in `PaperExchange.place_order` (and will exist in
  every real adapter). Two independent layers; either alone can veto.
- **Why:** SKILL.md § The Cardinal Rule: "no order reaches an exchange
  without `RiskDecision(approved=True)`. There is no bypass flag." The
  opportunity_id check defends against a fake-approved-decision attack
  (a `RiskDecision(approved=True, opportunity_id=arbitrary_uuid)`
  bypasses approval but fails the cross-check).
- **How to apply:** Adding a new adapter? Implement the same two checks
  at the top of `place_order`. Never trust the upstream layer's
  enforcement alone.

### 2026-05-21 — Paper fill-since polling has a known timing race; Faz 7 ingestion fixes it
- **What:** Faz 6 pipeline polls `adapter.fetch_fills(since=opp.detected_at)`
  after each iteration. PaperExchange records fills with wall-clock
  `now_utc()` timestamps while `opp.detected_at` comes from the strategy
  clock (ms resolution). Across multiple iterations within the same
  millisecond, fetch_fills can re-emit already-logged fills. Bounded:
  6 ≤ count ≤ 12 for 3 iters with both adapters.
- **Why this isn't fixed in Faz 6:** SKILL.md design has ingestion as a
  push (subscribe + on_snapshot callback). The polling pattern is a Faz 6
  stub. Faz 7 replaces it with proper event subscription, no since
  arithmetic needed.
- **How to apply:** Until Faz 7, treat fill counts in multi-iteration
  pipeline tests as bounded ranges, not exact values. Single-iteration
  tests remain exact.

### 2026-05-21 — Native aiohttp over ccxt for the first live adapter
- **What:** Binance adapter uses raw `aiohttp` against `/api/v3/depth`,
  not ccxt. Symbol mapping (`Symbol("BTC","USDT")` → `"BTCUSDT"`) is a
  3-line static method. Error translation is hand-rolled in
  `_handle_response` (mapping status codes to `errors.*`).
- **Why:** One exchange, one endpoint, public access — ccxt's 600+
  exchange abstraction is more weight than benefit. Each added adapter
  reuses the pattern. When we reach 5+ exchanges and need unified
  symbol/error/rate-limit semantics, revisit ccxt then.
- **How to apply:** New exchange → start with native aiohttp, follow
  `binance.py` as template. Only switch to ccxt if it solves a problem
  the native path can't (e.g., authenticated WS signing for a venue
  where the official lib is canonical).

### 2026-05-21 — aiohttp test server replaces vcrpy for offline HTTP tests
- **What:** Tests start an in-process `aiohttp.web` app on a random port
  via `async with _stub_server(handler) as base_url:` context manager.
  The adapter is constructed with that base URL. Tests run offline,
  deterministically, with full HTTP roundtrip semantics.
- **Why:** vcrpy + aiohttp integration is rough and adds a heavy dev
  dependency. The aiohttp test server is stdlib for the aiohttp world
  and gives more precise control over response bodies and status codes
  per test case.
- **How to apply:** Any new HTTP-based adapter → mirror
  `tests/unit/exchanges/test_binance.py` pattern. Handler is a regular
  async function returning `web.Response` / `web.json_response`.

### 2026-05-21 — Pipeline modes: test-paper, live, default-paper
- **What:** `pipeline.run(settings, *, snapshot_seeds=...)` resolves
  adapters in 3 priority levels: (1) explicit `snapshot_seeds` override
  → paper exchanges built from those seeds (test injection); (2)
  `build_live_adapters(settings)` returns non-empty → live mode; (3)
  fallback to `_default_synthetic_snapshots()` → paper exchanges with
  the historical wide-spread seeds. Single-venue live mode skips
  strategy evaluation but still logs snapshots.
- **Why:** Operator-controlled enable flags + test-controlled overrides
  + safe default. Same pipeline code handles all three. SKILL.md §
  Anti-Patterns "limits read at startup" generalises: adapter set also
  decided at startup.
- **How to apply:** Adding a new live exchange? Add `<exchange>_enabled`
  to Settings + a branch in `build_live_adapters`. Pipeline picks it up
  automatically.

### 2026-05-21 — Security model documented before authenticated trading
- **What:** `specs/SECURITY.md` catalogues 15 controls (CLAUDE.md
  anayasası C1-C8 + defense-in-depth S1-S7) with status, mechanism,
  test, and per-faz gates. Faz 7-S (security hardening) inserted in
  the roadmap **before** Faz 7d/7b. SECURITY.md is the single
  reviewable source — every status change appends both to its § 7
  Change Log AND to `specs/LOG.md`.
- **Why:** Operator flagged security as one of the most critical
  steps. Faz 7b will introduce authenticated endpoints + HMAC signing
  + real key material; doing it without the S1-S7 scaffolding in
  place means audit-after-the-fact (Karpathy 1.1 violation: assume
  nothing, surface every gap before writing the code that needs it).
- **How to apply:** Before merging Faz 7b/c/d/e/f/g, open SECURITY.md
  § 3 Per-Faz Gates and verify every required control is `IMPLEMENTED`
  (not `PARTIAL`, not `PLANNED`). A faz where a gate is red is not
  mergeable regardless of code quality.
- **Where:** `specs/SECURITY.md`; cross-ref in `CLAUDE.md § 5 File Map`.

### 2026-05-21 — Faz 7-S inserted between 7a and 7d
- **What:** Operator approved order was 7d→7c→7b. After security
  audit (audit findings in `specs/LOG.md`), inserted Faz 7-S
  (security hardening) at the head: 7-S → 7d → 7c → 7b → 7e → 7f →
  7g. 7-S has two steps: Adım 1 = SECURITY.md document (done
  2026-05-21); Adım 2 = implement S1+S2+S3+S4 (gitleaks pre-commit/CI
  + expanded redaction needles + live-mode decorator + mainnet
  confirmation env). S5+S6+S7 are bundled into Faz 7b's
  prerequisites.
- **Why:** Building the security mesh before the code that needs it
  inverts the usual "ship then patch" pattern. Cheap to add now;
  expensive to retrofit once a real key is loaded.
- **How to apply:** Treat 7-S Adım 2 as a strict gate. Do not
  proceed to Faz 7d until S1/S2/S3/S4 are merged with green tests.

### 2026-05-21 — Crypto arb spreads are tiny; synthetic demos lie
- **What:** Faz 7d's first live two-venue run (Binance vs Bybit BTC/
  USDT, REST polling) produced a $8 spread on $77,100 price. At 0.001
  BTC size the gross profit per leg = $0.008, dwarfed by fees+
  slippage ($0.17). Strategy correctly returned `no_opportunity`.
- **Why:** Two efficient venues with deep books and arbitrageurs
  worldwide eat spreads to near-zero in milliseconds. Faz 6's
  synthetic $800 spread between paper exchanges was 100× the real
  thing — useful for end-to-end testing of plumbing, dangerous for
  expectation-setting about live profitability.
- **How to apply:** When Faz 7c (WS) lands, expect even smaller
  observed spreads (better data → more arb deplented). Profit will
  come from (a) larger sizes (more risk), (b) faster execution (Faz
  7c WS + Faz 7e concurrent leg placement), (c) less-arbed venue
  pairs (Faz 7e+ adds Coinbase/Kraken), or (d) niche strategies
  (funding-rate). Spatial alone on Binance ↔ Bybit BTC is not a
  business model.

### 2026-05-21 — Bybit's retCode lives inside HTTP 200 — wrap with care
- **What:** Bybit's V5 API returns HTTP 200 even for application
  errors; the discriminator is `body.retCode`. Adapter
  `_handle_response` must read the body and check retCode BEFORE
  treating the response as success.
- **Why:** Binance uses HTTP status codes (4xx/5xx); Bybit doesn't.
  A naive `if resp.status == 200: return success` lets an error
  through silently.
- **How to apply:** Any future Bybit endpoint code (Faz 7b auth,
  Faz 7c WS) must respect the retCode contract. Future non-Bybit
  adapters may have similar quirks — always read the venue's error
  model BEFORE writing the adapter.

### 2026-05-22 — WS subscribe loops kill sentinel `NotImplementedError` tests
- **What:** Faz 5a / 7a tests included `test_subscribe_not_implemented`
  for each adapter (BinanceAdapter, BybitAdapter). When Faz 7c made
  `subscribe()` a real reconnect loop, those tests stopped raising
  NotImplementedError and instead **dialled the real exchange WS** —
  hanging pytest indefinitely. Removed the sentinels; comprehensive
  WS coverage lives in `tests/unit/exchanges/test_ws_subscribe.py`
  against an in-process aiohttp WS server.
- **Lesson:** Sentinel tests built on `NotImplementedError` become
  liabilities the moment the method is implemented. Either delete
  them with the implementation PR, or write the sentinel to assert
  a specific message ("Faz 7c") so the implementation breaks the
  assertion loudly instead of hanging.
- **How to apply:** When implementing a stubbed protocol method,
  grep tests for `test_<method>_not_implemented` and replace with
  real coverage in the same PR. Run pytest BEFORE pushing; a hang
  is a worse failure mode than a red assertion.

### 2026-05-22 — Async subscribe tasks need event-based test cancellation, not wait_for
- **What:** First attempt at WS tests used `asyncio.wait_for(
  subscribe_task, timeout=2.0)` and tried to cancel from inside the
  callback by raising `CancelledError`. Cancellation through the
  aiohttp WS context manager was not clean and produced sporadic
  hangs. Working pattern: signal completion via `asyncio.Event` set
  inside the callback; main test does `await asyncio.wait_for(
  event.wait(), timeout=2.0)`; in `finally`, call `task.cancel()`
  then a short `wait_for(task, timeout=1.0)` to give cleanup a
  bounded window.
- **Lesson:** For long-running async tasks (WS subscribe, infinite
  loops, server.serve_forever), an `Event` is the right signaling
  primitive in tests. `wait_for` on the task itself only works for
  tasks that naturally exit.
- **Where:** `tests/unit/exchanges/test_ws_subscribe.py` reference
  pattern.

### 2026-05-22 — Binance HMAC signing pattern (stdlib only, query-string based)
- **What:** `BinanceAdapter._sign(params)` builds `urlencode(params +
  {timestamp})` then computes `hmac.new(secret_bytes, query_bytes,
  hashlib.sha256).hexdigest()` and appends `&signature=<hex>` to the
  query. `X-MBX-APIKEY` header carries the public key. POST endpoints
  send params in the query string, not JSON body — Binance is unusual
  there. No third-party signing libs imported anywhere (SECURITY.md S6).
- **Why:** stdlib `hmac` is constant-time-safe by default for
  generation; `hmac.compare_digest` would be needed only on
  verification paths (we don't verify Binance's responses since
  HTTPS provides server auth).
- **How to apply:** New Binance signed endpoint? Call
  `await self._signed_request("METHOD", "/api/v3/...", {...params...})`.
  Test by extracting the signature from the request URL in an aiohttp
  stub server and comparing against `hmac.new(SECRET, params_without_sig,
  sha256).hexdigest()` — reference pattern in
  `tests/unit/exchanges/test_binance_auth.py::test_signed_request_carries_correct_hmac`.

### 2026-05-22 — S5 canWithdraw probe is lazy + cached (one network round-trip per adapter lifetime)
- **What:** First authenticated method call triggers
  `_ensure_no_withdraw_permission()`. Fetches `/api/v3/account`,
  rejects if `canWithdraw=true` (CLAUDE.md C1) or `canTrade=false`.
  Caches the success result. Subsequent auth calls skip the probe.
- **Why:** Eager startup probe would require an async init method on
  adapters, cascading through registry / pipeline. Lazy first-call
  probe ships the same protection with less ceremony.
- **How to apply:** Future authenticated adapters (Bybit Faz 7d+
  auth, Coinbase, …) follow the same pattern: their first auth call
  runs the venue's equivalent permissions probe and caches the
  result.

### 2026-05-22 — Sentinel `NotImplementedError` tests die three times: ingestion subscribe (Faz 7c), then auth (Faz 7b)
- **What:** Third instance of "sentinel test goes stale when
  implementation lands" — first Faz 5b risk gate, then Faz 7c
  subscribe(), now Faz 7b place_order/cancel_order/fetch_balance.
  Same recipe each time: comprehensive new test file (test_<thing>_
  auth.py here) replaces the sentinel; obsolete `with pytest.raises(
  NotImplementedError)` tests removed in the same PR.
- **Lesson reinforced:** Track sentinel tests in the implementation
  PR's checklist. The pattern in MEMORY.md § "WS subscribe loops kill
  sentinel NotImplementedError tests" generalises: ANY stubbed
  protocol method's sentinel must be re-checked when the body is
  written.

### 2026-05-22 — Execution returns `ExecutionResult`, not `list[OrderId]`
- **What:** Faz 7e moved from a flat `list[OrderId]` return to
  `ExecutionResult(opportunity_id, legs: tuple[LegResult,...])`. Each
  `LegResult` carries the leg, the optional order_id, the terminal
  `OrderState`, observed fills, and an error_message string. Pipeline
  consumers query `result.all_filled` / `result.needs_hedge`
  properties.
- **Why:** Concurrent placement (asyncio.gather) means each leg can
  end in a different terminal state simultaneously. A flat list erases
  that asymmetry. SKILL.md state-machine vocabulary (pending /
  submitted / partial / filled / cancelled / rejected / failed) is
  now first-class domain language.
- **How to apply:** Strategy / orchestration code consuming execution
  output uses `result.legs[i].state` and `result.needs_hedge`.
  Reconciler / hedger logic lives in `execution/reconciler.py` (pure
  classifier) + `execution/hedger.py` (log-only alert today; real
  hedge order placement in Faz 7e+).

### 2026-05-22 — Errors override fills in classification
- **What:** `reconciler.classify_leg(intent, error, fills)` returns
  `rejected` / `failed` even when `fills` is non-empty, as long as
  `error is not None`. Rationale: an adapter that raises is reporting
  an inconsistency — the fills may be stale, partial, or unrelated;
  reconciliation must determine the truth, not the engine's pre-
  emptive optimism.
- **Why:** Binance and most venues sometimes emit fill events shortly
  before raising a terminal error (e.g., REJECTED for the rest of the
  order). Treating the leg as `filled` would skip operator alert and
  mask the imbalance.
- **How to apply:** Never compute "filled" from `len(fills) > 0`.
  Always go through `classify_leg` so the error path takes priority.

### 2026-05-22 — Per-leg `asyncio.wait_for` is the right concurrency pattern for execution
- **What:** Each leg in `_submit_one_leg` wraps its `place_order` +
  `fetch_fills` calls in `asyncio.wait_for(timeout=opp.valid_for_ms/
  1000)`. On timeout the inner coroutine is cancelled and
  `TimeoutError` propagates; the leg is recorded with `error_message`
  and `classify_leg` marks it `failed`. `asyncio.gather` over the
  legs collects all results.
- **Why not gather-level timeout?** `asyncio.gather` does not support
  partial-result-on-timeout cleanly — the whole gather throws
  TimeoutError and we lose every leg's individual state. Per-leg
  `wait_for` lets every leg report its own outcome even when others
  time out.
- **How to apply:** Future execution-engine extensions (Faz 7e+ retry
  on "unknown" outcome) must keep per-leg `wait_for` and add their
  retry logic INSIDE `_submit_one_leg`. Don't introduce gather-level
  timeouts — they regress this property.

### 2026-05-22 — Risk gate is pure; orchestrator owns the mutable state
- **What:** Faz 7f added 3 SKILL.md checks (position cap, orders/min,
  venue freshness) that need state-over-time. The gate stays pure —
  it reads an immutable `AccountState` snapshot per call. The
  orchestrator runs an `AccountStateTracker` (in
  `orchestration/account_state_tracker.py`) that accumulates positions
  from fills, records order submission timestamps, and tracks the most-
  recent snapshot per venue. `tracker.snapshot(now_ms)` materialises
  an `AccountState` for the gate.
- **Why:** SKILL.md § Anti-Patterns: "Risk reading account state from
  the exchange directly | I/O inside risk = untestable. State is
  passed in." The tracker is the principled implementation of "state
  is passed in". Testing the gate against any state combination is
  just constructing a literal AccountState; testing the tracker is
  feeding it events and snapshotting.
- **How to apply:** Need a new SKILL.md risk check that depends on
  history (e.g., max_loss_per_day_usd)? Add the state field to
  `AccountState`, populate it via a new `on_*` method on
  `AccountStateTracker`, add a new check in the gate that reads it.
  Never read live state from the gate body.

### 2026-05-22 — Daily P&L tracked in the orchestrator, not the gate
- **What:** Faz 7g-a adds realised daily P&L to `AccountStateTracker`.
  `on_fill` accumulates `(+1 if sell else -1) × price × volume − fee`
  per fill; UTC day rollover resets the counter on the first fill of
  a new day. `pipeline._maybe_engage_daily_loss_kill(tracker,
  settings)` runs after every iteration's fills; on breach
  (`daily_pnl_usd < -max_loss_per_day_usd`) it writes
  `logs/kill_switch.json` AND sets `tracker.kill_switch_engaged=True`
  so the next risk_evaluate rejects at check #1 immediately.
- **Why:** The kill-switch trigger is stateful (needs cumulative P&L)
  and side-effectful (writes the durable file). Both belong in the
  orchestrator, not the gate. The gate keeps its purity contract: it
  reads `state.kill_switch_engaged` and reacts; it does not produce
  the engagement.
- **How to apply:** New kill-switch triggers (rejection rate too
  high, exception count, etc.) follow the same shape — add a
  `_maybe_engage_*` helper in pipeline that consults tracker state
  and engages on breach. Don't push trigger logic into the gate.

### 2026-05-22 — Absence in tracking dicts is "unknown", not "fail closed"
- **What:** `AccountState.last_snapshot_age_ms_by_venue` is a dict
  keyed by `ExchangeId`. The Faz 7f freshness check reads
  `state.last_snapshot_age_ms_by_venue.get(leg.exchange)` — if the
  venue is absent, the check is skipped (rather than rejecting the
  opportunity). Same pattern for `cash_by_exchange` and
  `open_position_qty`.
- **Why:** Smoke / integration tests that don't run the tracker
  loop (or paper runs where freshness isn't tracked yet) must keep
  working. Failing closed on "I don't know" would force every test
  to pre-populate the dict, multiplying boilerplate and obscuring
  intent.
- **How to apply:** New tracker-fed state field? Decide explicitly
  in the gate whether `key not in dict` means "check skipped"
  (default for proxies-of-connectivity) or "fail closed" (for
  safety-critical caps where unknown = unsafe). Document the choice
  in the gate's docstring.

### 2026-05-22 — Audit log canonicalisation belongs in the writer, not in callers
- **What:** Faz 7g-b put the entire hash-chain machinery inside
  `persistence/decision_log.py`: `_serialize` (canonical JSON with
  `sort_keys=True, default=str`), `_compute_hash` (sha256 over
  canonical bytes), `_restore_chain_state` (tail-read on init),
  `_append` (inject `_prev_hash` then compute `_hash`).
  `append_opportunity` / `append_decision` / `append_fill` /
  `append_snapshot` callers never touch hashing — they build payloads
  the way they always did. Verification (`verify_chain`) and CLI
  (`scripts/verify_audit_chain.py`) live in the same module / a thin
  wrapper that imports it.
- **Why:** The chain only stays intact if EVERY writer uses the same
  canonical serialisation. Putting the responsibility on callers
  guarantees that a future event type will silently break the chain
  the first time someone forgets to call the hash helper. Centralising
  it means a new event helper inherits chain-correctness for free.
- **How to apply:** New event type? Add an `append_xxx(payload)`
  method that builds the dict and calls `self._append(payload)`. Don't
  expose `_compute_hash` to the rest of the codebase; don't accept
  pre-hashed payloads from elsewhere. If you ever need to write a
  *non-chained* JSONL log, use a different class — don't add a "skip
  hash" flag to DecisionLog.

### 2026-05-22 — Restart-safe chains require tail-reading, not cold restart from GENESIS
- **What:** When `DecisionLog` opens an existing file, it reads the
  last 32 KB (enough for any single JSONL line even with verbose
  payloads), parses the final line, and adopts its `_hash` as the new
  `_last_hash`. The next `_append` then carries that hash as its
  `_prev_hash`, so the chain continues unbroken across process
  restarts. Corrupt tail / unparseable line → silent fallback to
  GENESIS; `verify_chain` will flag the boundary on the next audit.
- **Why:** Process restarts (deploy, crash, manual stop) are routine
  for a 24/7 bot. If each restart began a fresh chain at GENESIS, a
  determined attacker could just truncate the file and replay GENESIS
  to mask removed lines; the seam wouldn't even look like tampering
  because it'd be indistinguishable from a clean cold start. Tail-
  reading makes "the chain restarted from GENESIS in the middle of
  the file" itself a detectable anomaly.
- **How to apply:** Any append-only chained store needs a tail-read
  recovery hook in its constructor; never assume the operator will
  pass `last_hash` in. Cap the read window (32 KB here) so a multi-GB
  log doesn't blow memory on init; the cap only needs to exceed the
  largest plausible single line.

### 2026-05-22 — Hedger's fair price comes from filled fills, not from the original opportunity
- **What:** Faz 7g-c picks the slippage-budget baseline as the
  volume-weighted average price of the **unwind side**'s fills — i.e.,
  the actual cost basis of the position we now need to neutralise.
  Snapshot mid is only a defensive fallback when no fills exist on the
  unwind side. The original Opportunity's expected price is **not**
  used as the baseline.
- **Why:** The opportunity's prices reflect the strategy's INTENT;
  execution may have filled at slightly different prices (partials,
  taker-vs-limit, multi-tick walks). Using intent as baseline would
  make the budget gate inconsistent with what we actually own.
  VWAP-of-fills is the true cost basis, so "stay within budget of fair"
  becomes "don't unwind for more than 50bps worse than we got in" —
  a P&L statement, not a planning artifact.
- **How to apply:** New hedger triggers (delta hedging, partial
  unwinds across multiple symbols) should compute their reference
  from observed fills, never from the trigger event. The trigger says
  WHEN to hedge; the fills say WHERE.

### 2026-05-22 — Hedger synthesizes its own RiskDecision; gate is bypassed by design
- **What:** Faz 7g-c constructs `RiskDecision(opportunity_id=opp.id,
  approved=True, reason="hedge for opportunity X")` directly inside
  `hedge()` and hands it to `adapter.place_order` without consulting
  `risk.evaluate`. The counter-leg fills carry the **original**
  `opportunity_id` so the audit trail links unwind to opening trade.
- **Why:** SKILL.md § The Hedger: "The hedger is the **only** code
  that may place an order without an upstream `Opportunity`." A
  hedge's job is to reduce exposure that the gate would otherwise
  reject (max_position_value_usd, gross_exposure, etc.); running it
  through the gate would create a deadlock — the position we need to
  unwind already breached a limit, so the gate would reject the
  unwind too. The slippage budget IS the hedger's safety contract;
  it replaces the gate for this code path. Defence-in-depth: the
  adapter (live Binance/Bybit) still applies cardinal-rule checks +
  S5 withdraw probe.
- **How to apply:** Never re-route the hedger through `risk.evaluate`
  "for safety" — it will deadlock the only escape from a breach.
  Tightening hedger safety = tightening `hedge_max_slippage_bps` +
  adding pre-place checks inside the hedger (e.g., daily-loss budget
  for the hedge itself). The cardinal-rule enforcement at the
  adapter layer remains the absolute backstop.

### 2026-05-22 — S7 testnet probation gate is keyed off URL substring, not a config flag
- **What:** Faz 7g-d's `BinanceAdapter._is_testnet()` returns
  `"testnet" in self._base_url.lower()`. The recorder writes
  `logs/testnet_evidence.json` ONLY when this returns True. The S7
  startup gate refuses mainnet+live when evidence is insufficient.
- **Why:** A boolean flag (`is_testnet=True/False`) could be set
  inconsistently with the URL — operator could leave `BINANCE_REST_
  BASE_URL=https://api.binance.com` (mainnet) but pass
  `is_testnet=True` somewhere, and the system would happily record
  mainnet activity as testnet probation, self-validating the gate.
  Deriving from the URL string means the recorder is locked to the
  same artefact that determines where requests actually go. There's
  no way for the two to disagree.
- **How to apply:** When adding a venue to S7 (Bybit testnet, future
  exchanges), follow the same pattern: `_is_testnet()` on the
  adapter returns True iff the base URL contains "testnet". Never
  introduce a separate `is_testnet` flag in `Settings` or the
  registry. The URL IS the truth.

### 2026-05-22 — Mainnet probe MUST NOT record S7 evidence, ever
- **What:** `_record_testnet_evidence()` guards on `_is_testnet()`
  before writing. A successful auth probe against mainnet must NOT
  stamp the evidence file — even though it proves credentials work.
- **Why:** If mainnet activity counted as evidence, the very first
  successful mainnet auth call would (eventually) accumulate
  evidence and self-grant the gate. The gate would never refuse
  mainnet to a key that's already operating on mainnet — the
  protection would only apply to first-time setup, which is
  exactly the case where it's most useless (the operator clearly
  intends to start mainnet trading or they wouldn't have configured
  it). S7's premise is that the SAFE environment (testnet) generates
  the evidence that unlocks the RISKY environment (mainnet). Inverting
  that breaks the model.
- **How to apply:** Any future evidence-recording code (other
  exchanges, other gates) must enforce the same asymmetry: the
  signal source and the gated environment must be DIFFERENT
  endpoints. A test that calls `_record_testnet_evidence` with a
  mainnet URL configured and asserts that NO file is written is the
  canonical regression test.

### 2026-05-23 — Risk gate's min_order_value_usd assumes USDT-denominated limit_price; triangular intermediate leg breaks this assumption
- **What:** Faz (B) triangular strategy emits 3 legs; one of them
  swaps base↔intermediate (e.g. ETH/BTC). The `limit_price` of that
  leg is in BTC, not USDT. The risk gate computes leg order value
  as `limit_price × quantity` and compares to
  `risk_min_order_value_usd` (USDT scale). For an ETH/BTC leg at
  `0.049 × 0.166 = 0.0081 BTC`, the gate sees `0.0081 < 20` and
  rejects — even though the leg's notional is actually ~$490.
- **Why:** The gate was designed for spot-USDT pairs where the
  quote currency IS the reporting currency. Triangular's
  intermediate hop violates this. The check is correct in spirit
  (don't open trivially-tiny orders) but uses the wrong unit.
- **How to apply:** Two paths to fix when the operator wants to run
  triangular for real:
  (a) Per-leg conversion: convert `limit_price × quantity` to USDT
      using the latest snapshot for the leg's quote-currency pair
      (e.g. multiply by BTC/USDT bid for an ETH/BTC leg). Adds a
      dependency on snapshots in the risk gate that the cardinal-
      rule check wants to avoid.
  (b) Per-strategy override: triangular config carries a
      `min_intermediate_order_value` in the intermediate currency
      (BTC) so the gate compares apples-to-apples.
  For now, document the limitation and let operators widen
  `risk_min_order_value_usd` if they consciously want to allow
  triangular runs. Default (=20 USDT) is safe — it prevents
  triangular from ever placing live trades until the gate is
  upgraded.

### 2026-05-23 — Strategy protocol owns its own symbol set + venue count requirements
- **What:** Faz (B) extended the Strategy Protocol with two
  read-only properties: `symbols: list[Symbol]` (what to fetch /
  subscribe) and `min_venues: int` (minimum adapter count).
  Pipeline reads these instead of hardcoding `BTC/USDT` and
  `len(adapters) >= 2`. Spatial → `[symbol], 2`; triangular →
  `[i/q, b/q, b/i], 1`.
- **Why:** Without this, the pipeline had a hidden coupling to
  spatial's two-venues-one-symbol shape. A second strategy would
  have either (a) required the pipeline to know each strategy's
  internals or (b) been forced into spatial's mold. The Protocol
  push delegates the question "what does this strategy need?" to
  the strategy itself — exactly where it belongs. Adding the
  funding-rate strategy later will follow the same pattern
  (single venue, perp + spot pair → `symbols = [perp_sym,
  spot_sym]`, `min_venues = 1`).
- **How to apply:** Any new strategy must implement `symbols` and
  `min_venues` properties. Don't add ad-hoc fields to Settings for
  "what symbols does strategy X want" — the strategy's own
  property is the source of truth. Pipeline + adapter glue read
  through the protocol, never around it.

### 2026-05-20 — Karpathy's Four Principles are mandatory at every loop
- **What:** Think Before Coding · Simplicity First · Surgical Changes ·
  Goal-Driven Execution.
- **Why:** These came from a different Karpathy source than `karpathy-wiki.md`;
  do not conflate. Coding discipline ≠ wiki maintenance pattern.
- **Where:** `CLAUDE.md § 1` + `.claude/rules/karpathy-guidelines.md`.

---

## Gotchas & Lessons Learned

### 2026-05-20 — Faz 2 invented domain field names instead of reading the spec
- **What:** In Faz 2 I designed `MarketSnapshot`, `Opportunity`, `RiskDecision`
  from intuition ("what a financial event should obviously look like").
  When Faz 4 needed protocol signatures and (e) directed me to
  `specs/ARCHITECTURE.md § 6`, I discovered 8 field-name / shape divergences
  from the spec: `bid_volume` vs `bid_size`, `expected_pnl` vs
  `expected_net_profit`, `Opportunity.symbol` (didn't belong), missing
  `OrderIntent`, missing `OrderId`, `RiskDecision.reasons:tuple` vs
  `reason:str`, missing `opportunity_id` on `RiskDecision`, missing
  `adjusted_quantity`. Required a Faz 2.5 reconciliation before Faz 4
  could proceed.
- **Lesson (Karpathy 1.1):** Before writing types, READ the architectural
  contracts. `ARCHITECTURE.md § 6` + the relevant `skills/<module>/SKILL.md`
  are the source of truth for cross-module data shapes. "Intuitive design"
  is not a substitute for opening the spec.
- **How to apply:** First step of any new domain/contract work — open
  `specs/ARCHITECTURE.md § 6` (and the relevant SKILL files), copy the
  type definitions, match field-for-field. Only then write code. Where the
  spec is normative, add a regression test that asserts spec-aligned
  field names (`hasattr(... , "bid_size")` AND `not hasattr(... ,
  "bid_volume")`) so a future refactor cannot silently drift back.

### 2026-05-20 — The "stray" root SKILL.md was a real one, not a duplicate
- **What:** During the reorg, the SKILL.md at the repo root turned out to be
  the missing `market-data-ingestion/SKILL.md` (frontmatter said so). The
  `mnt/` archive only contained 4 of 5 skills.
- **Lesson:** Always check frontmatter `name:` before deciding a file is a
  duplicate. Filename collisions hide identity.

### 2026-05-22 — INCIDENT: real Binance API key pasted into `.env.example` template
- **What:** Operator opened `.env.example` (the committed template)
  and pasted real freshly-minted Binance API key + secret there
  instead of into `.env` (the gitignored real-values file).
  Discovered before any commit, repo not yet `git init`'d. The values
  still lived on disk in a tracked-by-convention file; both the
  earlier `.gitleaks.toml` allowlist AND the absence of a
  template-cleanliness lint would have let this through.
- **Why both defences missed it:**
  - `.gitleaks.toml` listed `.env.example` under `[allowlist.paths]`
    on the assumption "templates are always empty". An allowlist is
    a load-bearing security decision — that assumption was untested.
  - No script verified template emptiness directly.
- **Lesson:** Allowlists are load-bearing. Every entry must be
  justified, reviewed, and tested against an adversarial case
  ("operator pastes real key here"). "Trust the template" is not a
  defence; verify it.
- **How to apply (now in place):**
  - `.env.example` REMOVED from gitleaks allowlist — gitleaks now
    catches real keys in the template.
  - New `scripts/check_env_example.py` runs as a pre-commit hook;
    every `KEY=value` line must have empty value OR match a small
    explicit allowlist (mode literals, documented base URLs, integer
    defaults). Has 6 unit tests including the canonical negative
    case (`test_real_looking_key_is_rejected`).
  - `.env.example` template now carries a bold header warning +
    pointer to SECURITY.md § 5.1.
- **Response actions executed (2026-05-22):**
  1. Operator notified — REVOKE the leaked key on Binance.
  2. `.env.example` reverted to placeholder template.
  3. New `.env` file created (gitignored) — operator put fresh key
     there. Key value never appears in any committed artefact, in
     chat transcripts, or in agent logs.
  4. `.gitleaks.toml` allowlist tightened (`.env.example` removed).
  5. New defence + tests added (`scripts/check_env_example.py` +
     6 pytests + pre-commit hook wiring).
  6. Two policy items added to operator checklist (§ Operator
     Preferences below).

### 2026-05-20 — Misdiagnosed an operator-initiated delete as a system bug
- **What:** `crypto-arbitrage-agent.zip` disappeared from the repo root twice
  mid-session. No command of mine had targeted it, so I concluded an external
  process (Spotlight / TimeMachine / iCloud) was deleting it and restored it
  both times from `~/Downloads/files/` (SHA-256 `a5a9e11a…cdf704` verified
  bit-identical). The operator then clarified they had deleted it
  intentionally — the zip's contents were already fully extracted into
  `specs/` and `skills/`, so the original "do not delete" constraint had
  gone stale.
- **Lesson (Karpathy 1.1 — Think Before Coding):** "File vanished without my
  involvement" is not evidence of a system bug. Before defaulting to
  "restore + log a recurring bug," **ask the operator** whether the absence
  is intentional, especially once the file's purpose has been consumed by
  other artifacts in the repo.
- **How to apply:** When a tracked file disappears and no command of yours
  touched it: (1) check whether its content is still load-bearing or fully
  superseded; (2) if superseded, ask before restoring; (3) treat stale
  task-level constraints (`do not delete X`) as inputs that **expire**, not
  immutable laws.

---

## Operator Preferences

### Language
- All natural-language replies in **Turkish**.
- File paths, shell commands, code, and quoted source content stay in their
  original form (usually English).

### Workflow
- **Plan-first protocol:** No file moves, deletions, or destructive commands
  before an explicit `onaylandı` / `approved`. Read-only exploration is fine.
- **Surgical diffs (Karpathy 1.3):** No "while I'm here" refactors. Touch only
  what the task requires.
- **Honest reporting:** Surface confusion and anomalies (e.g., the missing
  zip incident above) rather than papering over them.

### Tools
- Obsidian is the canonical reading surface for `specs/` + the wiki layer.
  Vault root = repo root. `.obsidian/` is gitignored (TODO if not yet).
- Claude Code reads `.claude/rules/karpathy-guidelines.md` via the CLAUDE.md
  § 5 reference; same body lives in `specs/karpathy-wiki.md` for Obsidian.

---

## Vocabulary

Project-specific terms only. General trading terms (spread, slippage, funding)
live in `specs/GLOSSARY.md`.

- **The wiki layer** — collective name for `STATUS.md`, `MEMORY.md`,
  `specs/INDEX.md`, `specs/LOG.md`. The agent maintains it per `CLAUDE.md § 9`.
- **Spec doc** — any file under `specs/`. Frozen design output, not narrative.
- **Skill file** — `skills/<module>/SKILL.md`. Per-module operating manual,
  loaded by the agent before touching that module's code.
- **The stray file** — historical: the root-level `SKILL.md` that turned out
  to be `market-data-ingestion`. Resolved 2026-05-20; term retained only as a
  reference to that incident.
