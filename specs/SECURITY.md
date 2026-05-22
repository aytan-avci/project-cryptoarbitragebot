# SECURITY.md — Crypto Arbitrage Agent Security Model

> **Read before any change to:** `exchanges/*`, `risk/*`, `config.py`,
> `.env*`, or any file that touches authentication, signing, or order
> placement.
> Operator-reviewable single source of truth. Every control below is
> either **implemented**, **partially implemented**, or **planned** —
> status is explicit. A new faz must not be merged if it introduces a
> regression in any **implemented** control.

---

## 0. Purpose & Non-Purpose

**Purpose.** Catalogue every defence the bot maintains against
financial loss caused by **code bugs, credential leaks, exchange
misbehaviour, and operator mistakes**. Each control has a *mechanism*
(what enforces it) and a *test* (how we know it's still enforced).

**Non-purpose.** This document does not cover:

- Network-layer security (firewall, VPN, OS hardening) — operator's
  ops layer.
- Smart-contract risk (no on-chain interaction yet; out of MVP scope).
- Custodial / cold-storage of crypto funds — operator's wallet
  practice.
- Compliance / KYC / tax reporting — operator's jurisdiction.
- Generic web-app security for the dashboard once it leaves
  `127.0.0.1` — separate Faz 8+ topic.

---

## 1. Threat Model

### 1.1 Assets we defend

1. **Trading capital** sitting at exchanges (the largest asset).
2. **API credentials** (trade-only, but a leak still enables
   unauthorised trades).
3. **The audit trail** (`logs/decisions.jsonl`) — tampering with it
   hides losses.
4. **The decision pipeline integrity** — a bypassed risk gate equals
   uncapped loss.

### 1.2 Threat actors

- **Adversarial market** (slippage, MEV, partial-fill traps) — the
  baseline; every trade is against an adversary.
- **Exchange bugs / outages / API changes** — vendor risk.
- **Code bugs** (us) — the most likely loss source.
- **Credential leakage** — via git history, log redaction misses,
  malicious dependency.
- **Operator misclicks** — wrong `.env`, wrong base URL, wrong size.
- **Malicious local processes** — assumed out of scope; the machine
  running the bot is trusted (Faz 8+ revisits when remote dashboards
  enter).
- **Remote attacker** — out of MVP scope (bot binds 127.0.0.1; no
  inbound network surface).

### 1.3 Out-of-scope adversaries (today)

- Side-channel timing attacks on the local process.
- Memory dumping of the running process.
- Compromise of the developer's machine.

These become in-scope when the bot moves to a server or to live
mainnet (Faz 7g). At that point this document needs the §6 deferred
items closed.

---

## 2. The 15 Controls

Each row carries five fields:

- **What** — one-sentence definition.
- **Why** — the loss class it prevents.
- **Mechanism** — what code/policy/setting enforces it.
- **Test** — how we verify the mechanism still works.
- **Status** — `IMPLEMENTED` / `PARTIAL` / `PLANNED`.

---

### 2.1 Constitution Controls (CLAUDE.md § 2)

These are non-negotiable. Reviewed every faz.

#### C1 — Withdrawal API permissions forbidden

- **What.** Every API key the bot uses must be trade-only (no
  withdraw, no transfer).
- **Why.** Compromise of a trade-only key caps loss at "open positions
  on the venue"; a withdraw-enabled key empties the account.
- **Mechanism.**
  - Policy (operator): exchange-side key permission ticked OFF when
    the key is created.
  - Runtime probe (Faz 7b): startup calls `GET /api/v3/account` (or
    venue equivalent); if `canWithdraw=true`, the adapter **refuses to
    initialise** and emits a structlog `agent.startup_refused` event.
  - IP whitelist: required on the exchange side (operator
    responsibility, documented in `.env.example`).
  - Key rotation: monthly cadence (operator policy; no code
    enforcement).
- **Test.**
  - Faz 7b unit test: probe returning `canWithdraw=true` must raise
    `PermanentFailure` and prevent adapter construction.
  - Operator audit: quarterly review of key permissions on each venue.
- **Status.** **PLANNED (Faz 7b).** No live key is used yet; current
  Faz 7a adapter touches only public REST.

#### C2 — Risk Layer is the only path to an exchange

- **What.** No order can be placed without a `RiskDecision(approved=
  True)` whose `opportunity_id` matches the order's parent opportunity.
- **Why.** Bypassing the risk gate uncaps loss (position, exposure,
  freshness, kill-switch are all enforced inside the gate).
- **Mechanism.**
  - The `ExchangeAdapter.place_order` protocol signature **requires**
    a `RiskDecision` argument.
  - `execution.engine.execute` validates `decision.approved is True`
    **and** `decision.opportunity_id == opportunity.id` before any
    adapter is touched. Either failure raises `ValueError`.
  - `PaperExchange.place_order` repeats the `approved` check at the
    adapter boundary (defence in depth).
  - All future live adapters (Binance Faz 7b, Bybit Faz 7d+) MUST
    repeat the same boundary check.
- **Test.**
  - `tests/unit/execution/test_engine.py::test_unapproved_decision_raises`
  - `tests/unit/execution/test_engine.py::test_mismatched_opportunity_id_raises`
  - `tests/unit/exchanges/test_paper.py::TestPlaceOrder::test_rejected_decision_raises_valueerror`
  - **Planned (Faz 7b)**: equivalent test on BinanceAdapter.
- **Status.** **IMPLEMENTED** (paper); **PLANNED** for each live
  adapter.

#### C3 — Paper-trade is the default; live requires an explicit flag

- **What.** `EXECUTION_MODE=paper` is the default; live trading
  requires `EXECUTION_MODE=live` AND (for mainnet) the additional
  control S4.
- **Why.** Prevents accidentally placing live orders during
  development.
- **Mechanism.**
  - `Settings.execution_mode: Literal["paper","live"] = "paper"` —
    pydantic rejects any other value at startup.
  - Faz 7-S adds **S3** decorator: every authenticated adapter method
    checks `settings.execution_mode == "live"` at call time and raises
    `PermissionError` otherwise.
- **Test.**
  - `tests/unit/test_config.py::test_invalid_mode_rejected`
  - **Planned (S3)**: decorator-enforced runtime check.
- **Status.** **IMPLEMENTED (2026-05-21).** S3 decorator wraps every
  authenticated method on `BinanceAdapter`; S4 model_validator refuses
  `EXECUTION_MODE=live` + mainnet base URL unless `LIVE_TRADING_
  CONFIRMED=true`.

#### C4 — Audit log of every decision

- **What.** Every detected opportunity, every risk decision, every
  fill, and (Faz 7a+) every snapshot is appended to
  `logs/decisions.jsonl`.
- **Why.** Without an audit trail, losses cannot be diagnosed and tax
  cannot be reported.
- **Mechanism.**
  - `persistence.decision_log.DecisionLog.{append_opportunity,
    append_decision, append_fill, append_snapshot}` — JSONL one event
    per line, `default=str` for Decimal/datetime safety.
  - `orchestration.pipeline.run` calls these on every iteration.
- **Test.**
  - `tests/unit/persistence/test_decision_log.py` — full coverage.
  - `tests/integration/test_pipeline.py` — verifies the event sequence
    written end-to-end.
- **Status.** **IMPLEMENTED.**

#### C5 — Fees + slippage subtracted before profitability check

- **What.** Strategy's `expected_net_profit` must be net of taker
  fees and slippage; risk gate's `min_profit_threshold_usd` is a
  redundant lower bound.
- **Why.** Most "opportunities" are negative after costs; a strategy
  emitting gross spread leaks money continuously.
- **Mechanism.**
  - `SpatialArbitrage._net_profit` subtracts fees (`taker_fee_bps`
    × both legs) and `slippage_usd_per_leg × 2`.
  - `risk.gate.evaluate` repeats the `expected_net_profit ≥ min` check.
- **Test.**
  - `tests/unit/strategies/test_spatial.py::TestRejections` covers
    "tiny gap fees eat" path.
  - `tests/unit/risk/test_gate.py::TestProfitabilityCheck` covers
    threshold rejection.
- **Status.** **IMPLEMENTED.**

#### C6 — No secrets in code or commits

- **What.** API keys, signatures, passwords never appear in source
  files, git history, log streams, or audit logs.
- **Why.** A leaked secret is a leaked account.
- **Mechanism.**
  - `.env` in `.gitignore` (root) — keys never enter the working tree.
  - `.env.example` documents required vars with empty values only.
  - `observability.logging_setup._redact_secrets` masks any field
    whose key matches `{api_key, api_secret, password, secret, token}`
    needles. **S2 expands** this needle list.
  - `Settings.binance_api_key: str | None = None` — pydantic-settings
    reads from env, never reads from file outside of `.env`.
  - **S1 adds** pre-commit `gitleaks` + GitHub Actions secondary scan.
- **Test.**
  - `tests/unit/observability/test_logging_setup.py::test_redacts_known_secret_keys`
  - **Planned (S1)**: `gitleaks` exits non-zero on leaked secret patterns;
    CI blocks merge.
  - Manual quarterly: `git log -p | grep -E "(api_key|secret).{,20}=.{,80}[a-zA-Z0-9]{20,}"` — should be empty.
- **Status.** **IMPLEMENTED (2026-05-21).** Redaction + gitignore +
  `.gitleaks.toml` + pre-commit hook + `.github/workflows/security.yml`
  all wired. Operator one-time setup: `brew install gitleaks` then
  `pre-commit install`.

#### C7 — No eval, no string-built SQL, no untrusted subprocess

- **What.** No use of `eval()` / `exec()`; no SQL string concatenation;
  no `subprocess.Popen(..., shell=True)` on untrusted input.
- **Why.** Standard injection vectors. Even local privilege escalation
  is a real risk on a multi-user dev machine.
- **Mechanism.**
  - Code review.
  - **Planned (S1, part of gitleaks/lint setup)**: AST-based scan in
    CI for `eval`, `exec`, `subprocess.*shell=True`, raw SQL string
    formatting.
- **Test.**
  - Manual review per PR.
  - **Planned**: CI lint job.
- **Status.** **IMPLEMENTED** (no instances in codebase as of
  2026-05-21); **PARTIAL** for prevention of regressions.

#### C8 — MVP supports one strategy

- **What.** The MVP ships with `SpatialArbitrage` as the sole live
  strategy; triangular and funding remain docstring placeholders.
- **Why.** A multi-strategy bot before each strategy is hardened is a
  multiplier on risk surface area.
- **Mechanism.**
  - Code: `strategies/{triangular,funding_rate}.py` are
    docstring-only.
  - Pipeline: `SpatialArbitrage` is the only strategy constructed.
- **Test.**
  - `tests/unit/test_imports.py::test_every_module_imports` —
    placeholders import but instantiating them returns None or raises.
- **Status.** **IMPLEMENTED.**

---

### 2.2 Defence-in-depth Controls (Faz 7-S)

#### S1 — Pre-commit + CI secret scanning

- **What.** Every commit is scanned by `gitleaks` locally
  (pre-commit) and again in GitHub Actions (CI).
- **Why.** C6 mechanism #1 (.gitignore) only protects what is gitignored;
  a secret accidentally committed to a tracked file (e.g., a markdown
  example with a real key) slips through. Two scans catch it.
- **Mechanism.**
  - `.gitleaks.toml` — config tuned to our patterns (Binance/Bybit
    key formats; HMAC base64 secrets).
  - `.pre-commit-config.yaml` — runs `gitleaks` on staged files.
  - `.github/workflows/security.yml` — CI job runs `gitleaks detect`
    on the full repo plus history.
- **Test.**
  - Deliberate "leak" PR with a placeholder secret pattern; CI must
    block.
- **Status.** **IMPLEMENTED (2026-05-21).** `.gitleaks.toml` ships
  with 5 custom rules (binance + bybit key/secret patterns + bare
  HMAC SHA-256 hex digest) on top of gitleaks's default ruleset.
  `.pre-commit-config.yaml` runs gitleaks on staged files; CI
  workflow re-runs on every push + PR.

#### S2 — Expanded secret redaction needles

- **What.** `_SECRET_KEY_NEEDLES` extends to cover `signature`, `hmac`,
  `private_key`, `bearer`, `auth`, `credential`, `passphrase`,
  `salt`, plus byte-typed values that match a base64/hex shape.
- **Why.** Faz 7b introduces request signing — HMAC digests would
  leak under the current narrow needle list.
- **Mechanism.**
  - `observability.logging_setup._SECRET_KEY_NEEDLES` updated.
  - A second processor `_redact_bytes_like_values` masks any value
    that is `bytes` or looks like a base64 / hex digest (regex match
    on string values ≥ 32 chars matching `[A-Za-z0-9+/=]{32,}|[a-f0-9]{32,}`).
- **Test.**
  - `tests/unit/observability/test_logging_setup.py` adds cases for
    each new needle and the bytes-redact behaviour.
- **Status.** **IMPLEMENTED (2026-05-21).** Needle set extended to 14
  entries (added: `pwd`, `signature`, `hmac`, `private_key`, `bearer`,
  `auth`, `credential`, `passphrase`, `salt`). New `_redact_byte_values`
  processor masks any `bytes` / `bytearray` value regardless of field
  name. String-shape redaction deliberately NOT added (would clash with
  UUIDs and order-ids that legitimately look like hex strings).

#### S3 — Live-mode programmatic guard at adapter boundary

- **What.** Every authenticated adapter method (`place_order`,
  `cancel_order`, `fetch_balance`, `fetch_fills`) checks
  `Settings.execution_mode == "live"` and raises `PermissionError`
  otherwise — independent of any upstream check.
- **Why.** Belt-and-suspenders for C3. A future bug in the
  pipeline that constructs an OrderIntent under paper-mode and calls
  a live adapter must fail at the adapter, not silently send a real
  order.
- **Mechanism.**
  - Decorator `@requires_live_mode` in `exchanges/base.py` wraps the
    target methods.
  - Settings instance passed to adapter constructor (or read via a
    module-level `get_settings()`); decorator reads
    `execution_mode` at call time.
- **Test.**
  - For each live adapter (Faz 7b+), test that the method raises
    `PermissionError` when `execution_mode="paper"`.
- **Status.** **IMPLEMENTED (2026-05-21).** `requires_live_mode`
  decorator in `exchanges/base.py` reads `EXECUTION_MODE` from `os.
  environ` at call time and raises `PermissionError` if not `"live"`.
  Applied to BinanceAdapter's `place_order`, `cancel_order`,
  `fetch_balance`, `fetch_fills`. Future live adapters (Bybit Faz 7d,
  …) apply the same decorator.

#### S4 — Mainnet requires `LIVE_TRADING_CONFIRMED=true`

- **What.** Combining `EXECUTION_MODE=live` with a non-testnet base
  URL (`api.binance.com`, not `testnet.binance.vision`) requires an
  additional explicit env var `LIVE_TRADING_CONFIRMED=true`.
- **Why.** Operator misconfig protection. Forgetting to point at
  testnet during development cannot result in real-money orders.
- **Mechanism.**
  - Pydantic `@field_validator("execution_mode")` on Settings: if
    `execution_mode=="live"` and base_url is mainnet and
    `LIVE_TRADING_CONFIRMED!="true"`, raise `ValueError` at
    Settings construction (startup refusal).
- **Test.**
  - `tests/unit/test_config.py` adds three cases: testnet+live OK,
    mainnet+live without flag → ValidationError, mainnet+live with
    flag → OK.
- **Status.** **IMPLEMENTED (2026-05-21).**
  `@model_validator(mode="after")` on `Settings._confirm_mainnet_live`
  refuses construction when `execution_mode="live"` AND
  `binance_enabled=true` AND base URL is mainnet
  (`binance.com` without `testnet`) AND `LIVE_TRADING_CONFIRMED!="true"`.
  Six test cases in `tests/unit/test_config.py::TestMainnet
  Confirmation` cover every combination.

#### S5 — Withdrawal-permission probe at adapter startup

- **What.** Live authenticated adapters call the venue's
  account-info endpoint at construction; refuse to operate if the
  key has withdrawal permission.
- **Why.** Enforces C1 at runtime, not just by operator policy.
- **Mechanism.**
  - Binance: `GET /api/v3/account` returns `canWithdraw`.
  - Bybit: `GET /v5/user/query-api` returns `permissions`.
  - Adapter constructor (or first-call lazy init) probes; on
    `canWithdraw=true`, raise `PermanentFailure("withdraw permission
    detected — refusing per CLAUDE.md C1")` and abort startup.
- **Test.**
  - aiohttp stub server returning `canWithdraw=true` triggers
    `PermanentFailure` at construction.
- **Status.** **PLANNED (Faz 7b — when Binance auth lands).**

#### S6 — HMAC constant-time signature handling

- **What.** Any signature comparison or generation uses
  `hmac.compare_digest` and `hmac.new` from stdlib; no homegrown
  signing, no `==` comparison of digests.
- **Why.** Timing-side-channel attacks against signature verification
  are real, even on localhost (though our threat model deems them
  out-of-scope today, the cost of using stdlib correctly is zero).
- **Mechanism.**
  - Faz 7b's BinanceAdapter signing code uses `hmac.new(key,
    payload, hashlib.sha256).hexdigest()` only; verification (if
    ever needed) uses `hmac.compare_digest`.
  - No third-party signing lib unless absolutely necessary.
- **Test.**
  - Code review checklist (Faz 7b PR).
- **Status.** **PLANNED (Faz 7b).**

#### S7 — 30-day testnet probation before mainnet

- **What.** A new live adapter must run on testnet for at least 30
  consecutive days with zero auto-paged incidents before mainnet is
  enabled.
- **Why.** The bot's behaviour against an exchange under load is not
  fully knowable until it has run for weeks. Testnet probation
  surfaces edge cases (auth flow, rate-limit behaviour, error codes)
  cheaply.
- **Mechanism.**
  - Operator policy + documentation in
    `dashboard/README.md` and `.env.example`.
  - **Future**: an automated "days since first testnet trade" counter
    in `logs/` consulted before S4 allows mainnet (Faz 7g).
- **Test.**
  - Operator certifies before mainnet PR is merged.
- **Status.** **IMPLEMENTED (Faz 7g-d).** `arbitrage_agent/risk/
  testnet_evidence.py` provides `record(venue, now, path)`,
  `load(path)`, and `attest_mainnet_eligibility(...)`. The Binance
  adapter calls `record("binance-testnet", now_utc())` after every
  successful `_ensure_no_withdraw_permission()` when the base URL
  contains "testnet". `Settings._confirm_mainnet_live` invokes
  `attest_mainnet_eligibility` after the S4 confirmation check;
  insufficient evidence → `ValidationError` at startup. Emergency
  bypass: `S7_OVERRIDE_TESTNET_PROBATION=true` (operator must record
  rationale in `MEMORY.md § Decisions & Why`).

---

## 3. Per-Faz Gates

Before merging the named faz, the corresponding gates must be **green**.
"Green" means: the test exists, runs in CI, and passes.

| Faz | Required gates |
|---|---|
| **7d (Bybit live REST)** | C1 (no auth yet — still public REST), C2 paper, C6, S1, S2 |
| **7c (WS subscription)** | All of 7d + reconnect tests + drop-test for partial frames |
| **7b (Binance TESTNET auth)** | All of 7d + C1 runtime (S5) + C3 (S3 decorator) + S4 (testnet base URL pinned) + S6 (HMAC compare_digest) + S7 declaration (testnet from this date) |
| **7e (Reconciler)** | All of 7b + hedger budget enforcement |
| **7f (Position + orders/min limits)** | All of 7e + position-cap unit tests |
| **7g (MAINNET)** | All of 7f + S7 30-day record + operator manual approval recorded in `MEMORY.md § Decisions` |

A faz attempted out of this sequence is a process violation regardless
of code quality.

---

## 4. Operator Responsibilities

Things the code cannot enforce; the operator must do:

1. **Create trade-only API keys** on each exchange. Never click the
   withdraw permission.
2. **IP-whitelist** the keys on the exchange side.
3. **Rotate keys monthly** (or after any suspicion).
4. **Run the bot as a non-root user** on a machine with disk
   encryption.
5. **Backup `logs/decisions.jsonl` off-machine daily** — tax + audit
   continuity.
6. **Read every PR diff that touches `exchanges/`, `risk/`, or
   `config.py`** before merging.
7. **Engage the kill-switch** at any sign of unexpected behaviour
   (`python -c "from pathlib import Path; from arbitrage_agent.risk
   import kill_switch; kill_switch.engage(Path('logs/kill_switch.json
   '), reason='operator manual')"`).
8. **Read this document quarterly** and verify status of each control
   has not regressed.

---

## 5. Incident Response

### 5.1 Suspected credential leak

1. Engage kill-switch immediately (see § 4 item 7).
2. Revoke the affected API key on the exchange's web UI.
3. Inspect `git log -p -- .env*` and grep recent commits for the
   key pattern.
4. Inspect `logs/decisions.jsonl` for unauthorised order events.
5. Create a new key with trade-only + IP whitelist; update `.env`.
6. Append an incident entry to `specs/LOG.md` with timestamp and
   actions taken.
7. Run `gitleaks` against the full history to verify no other leak.

### 5.2 Runaway loop / oscillation

1. Engage kill-switch.
2. Inspect `logs/decisions.jsonl` for the last N rejections — usually
   the same `reason` repeats, pointing to the bug.
3. Fix the underlying logic; do not just tighten the threshold.

### 5.3 Exchange API change

1. The adapter will emit `TemporaryFailure` or `PermanentFailure`
   from the new error path; the pipeline logs and continues (or halts
   depending on the exception class).
2. If `PermanentFailure`, kill-switch fires automatically (Faz 7e —
   auto-trigger).
3. Update the adapter to map the new error; add a unit test against
   the new response shape.

---

## 6. Deferred Items

These controls are recognised but not yet implemented; they are
required by specific gates above.

- **Audit log hash chaining** — each line carries SHA-256 of
  `prev_line || self`. Tampering with the middle of the log breaks
  the chain. Required for Faz 7g.
- **CI lint for `eval`/`exec`/`subprocess shell=True`** — required
  for C7's "prevent regression" mechanism. Part of S1.
- **Static-analysis enforcement of "only `risk/gate.py` constructs
  `RiskDecision`"** — currently enforced by code review. SKILL.md
  risk-management § The Cardinal Rule mandates a "static analysis fails
  the build" mechanism; we'll add `ast` lint in CI. Required for Faz 7b
  PR.
- **Process-level resource limits** (`ulimit`, systemd cgroup memory
  cap) — operator's deployment-time concern; documented in deployment
  guide (Faz 8).
- **Dashboard authentication** — currently `127.0.0.1`-only bind is
  sufficient. Required for Faz 8+ if the dashboard ever leaves
  localhost.

---

## 7. Change Log

Each time a control's *status* changes (planned → implemented,
implemented → broken, etc.), append a line here AND a row to
`specs/LOG.md`. The two stay synchronised.

| Date | Control | From → To | Reason / PR |
|---|---|---|---|
| 2026-05-21 | C1 | — → PLANNED | Faz 7a public-only; live key probe arrives with Faz 7b. |
| 2026-05-21 | C2 | — → IMPLEMENTED (paper) | Faz 4 + 5b + 6 deliver paper-side enforcement. |
| 2026-05-21 | C3 | — → PARTIAL | Default+pydantic done; programmatic decorator (S3) planned. |
| 2026-05-21 | C4 | — → IMPLEMENTED | Faz 6 + 7a fills in `append_snapshot`. |
| 2026-05-21 | C5 | — → IMPLEMENTED | Faz 5b + 5c. |
| 2026-05-21 | C6 | — → PARTIAL | Redaction + gitignore; S1 gitleaks planned. |
| 2026-05-21 | C7 | — → IMPLEMENTED | No instances in codebase; CI prevention planned (S1). |
| 2026-05-21 | C8 | — → IMPLEMENTED | Only SpatialArbitrage instantiated. |
| 2026-05-21 | S1–S7 | — → PLANNED | This document is the design; implementation Faz 7-S steps 2–5 + Faz 7b. |
| 2026-05-21 | C3 | PARTIAL → IMPLEMENTED | S3 decorator + S4 validator merged; programmatic guard now active. |
| 2026-05-21 | C6 | PARTIAL → IMPLEMENTED | S1 gitleaks config + pre-commit hook + CI workflow merged. |
| 2026-05-21 | S1 | PLANNED → IMPLEMENTED | `.gitleaks.toml`, `.pre-commit-config.yaml`, `.github/workflows/security.yml`. |
| 2026-05-21 | S2 | PLANNED → IMPLEMENTED | `_SECRET_KEY_NEEDLES` extended (14 needles) + `_redact_byte_values` processor. |
| 2026-05-21 | S3 | PLANNED → IMPLEMENTED | `@requires_live_mode` in `exchanges/base.py`; applied to BinanceAdapter's 4 authenticated methods. |
| 2026-05-21 | S4 | PLANNED → IMPLEMENTED | `@model_validator(mode='after')` in `Settings`; `LIVE_TRADING_CONFIRMED=true` required for mainnet+live combo. |
| 2026-05-22 | INCIDENT | C6 / S1 | Real Binance key pasted into `.env.example` template. Pre-existing gitleaks allowlist whitelisted that file → defence bypassed. Response: revoked key, sanitised template, removed allowlist entry, added `scripts/check_env_example.py` + pre-commit hook + 6 unit tests. Repo not yet `git init`'d so no history leak. See `MEMORY.md § Gotchas 2026-05-22` for full IR. |
| 2026-05-22 | S1 | IMPLEMENTED → STRENGTHENED | `.env.example` removed from gitleaks allowlist. New `scripts/check_env_example.py` pre-commit hook lints template emptiness independently of gitleaks. |
| 2026-05-22 | C1 | PLANNED → IMPLEMENTED | S5 `_ensure_no_withdraw_permission()` probe in `BinanceAdapter` calls `GET /api/v3/account` lazily on first auth call; refuses to operate if `canWithdraw=true`. Cached after success. |
| 2026-05-22 | S5 | PLANNED → IMPLEMENTED | `BinanceAdapter._ensure_no_withdraw_permission()`. Test `test_withdraw_permission_rejected` exercises the rejection path. |
| 2026-05-22 | S6 | PLANNED → IMPLEMENTED | `BinanceAdapter._sign()` uses `hmac.new(secret, query, hashlib.sha256).hexdigest()` — stdlib only, no third-party signing libs. `hmac.compare_digest` reserved for future verification paths. |
| 2026-05-22 | S7 | PLANNED → DOCUMENTED | Operator policy doc in `README.md` + `.env.example` + `MEMORY.md`; 30-day testnet probation before mainnet PR is mergeable per § 3 Per-Faz Gates. Automated enforcement deferred to Faz 7g. |
| 2026-05-22 | RISK gate check #10 | DEFERRED → IMPLEMENTED | Faz 7g-a adds `min_required_balance` (10th SKILL.md check). Absent-in-tracker = skip; populated = bites. |
| 2026-05-22 | Daily-loss kill-switch | PLANNED → IMPLEMENTED | Faz 7g-a — `tracker.daily_pnl_usd` tracks realised P&L with UTC day rollover; `pipeline._maybe_engage_daily_loss_kill` engages kill-switch on durable disk AND in-memory tracker when breach detected. SKILL.md § The Kill-Switch — Realized P&L trigger satisfied. |
| 2026-05-22 | C4 / Audit chain | IMPLEMENTED → TAMPER-EVIDENT | Faz 7g-b — `persistence/decision_log.py` emits SHA-256 hash-chained JSONL (`_prev_hash` + `_hash` per line, GENESIS = `"0"*64`). `verify_chain(path)` + `scripts/verify_audit_chain.py` CLI detect insert/delete/reorder/content-tamper with line numbers; exit 1 on tamper for CI/cron. Smoke proved a single mutated field on line 15 of a 30-line log is caught. Crypto = stdlib `hashlib.sha256` only (S6 compliant). |
| 2026-05-22 | Hedger / QA-1.3 | DEFERRED → IMPLEMENTED | Faz 7g-c — `execution/hedger.py` real neutralisation flow (cancel + counter-leg + slippage budget). New `hedge_max_slippage_bps` setting (50bps default). Hedger places counter-leg only when current market is within budget of the VWAP of the unwind side's fills; otherwise emits `hedger.aborted_slippage` and surfaces open exposure to the operator. SKILL.md "hedger is the only code that may place an order without an upstream Opportunity" honored: synthetic `RiskDecision(reason="hedge for opportunity X")` carries the original `opportunity_id` for end-to-end audit traceability. |
| 2026-05-22 | S7 | DOCUMENTED → IMPLEMENTED | Faz 7g-d — `risk/testnet_evidence.py` records every successful Binance-testnet authenticated probe into `logs/testnet_evidence.json` (first_seen + last_seen + venues). `Settings._confirm_mainnet_live` now invokes `attest_mainnet_eligibility(min_days=30)`; <30 testnet days raises `ValidationError` at startup, refusing mainnet+live. Bypass: `S7_OVERRIDE_TESTNET_PROBATION=true` (loud, requires `MEMORY.md` rationale row). `S7_MIN_TESTNET_DAYS` env lets CI exercise the gate's success path. Smoke proved both rejection (no evidence) and acceptance (31-day seeded evidence). |
