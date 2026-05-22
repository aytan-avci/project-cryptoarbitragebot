# CLAUDE.md — Crypto Arbitrage Agent Constitution

> This file is loaded into Claude Code's context at the start of every session.
> It is the **single source of truth** for how the agent must reason and act on this project.
> Keep it short. Keep it surgical. Keep it honest.

---

## 0. Project One-Liner

A modular, multi-exchange **crypto arbitrage bot** built with Python, designed using
**Attribute-Driven Design (ADD)** and operated by **Claude Code** under
**Andrej Karpathy's four LLM-coding principles**.

Supported strategies (pluggable, one at a time per deployment):
- **Spatial arbitrage** — buy on Exchange A, sell on Exchange B (default MVP)
- **Triangular arbitrage** — three-leg cycle inside one exchange
- **Funding-rate arbitrage** — single-venue, lowest-risk entry point

---

## 1. The Four Principles (Karpathy Discipline)

These four rules override every other instinct. When in doubt, re-read this section.

### 1.1 Think Before Coding
> *"Don't assume. Don't hide confusion. Surface tradeoffs."*

- **State assumptions explicitly.** Before writing code, list what you assume about the request.
- **Present multiple interpretations** when the prompt is ambiguous. Do not pick silently.
- **Push back when warranted.** If a simpler path exists, say so before implementing.
- **Stop when confused.** Name what is unclear and ask, rather than guessing.

### 1.2 Simplicity First
> *"Minimum code that solves the problem. Nothing speculative."*

- No abstractions for a one-off case. No premature framework.
- No configuration surface no one asked for.
- No elaborate error handling for scenarios that will not occur in MVP.
- If a senior engineer would call it overcomplicated — simplify before submitting.

### 1.3 Surgical Changes
> *"Touch only what you must. Clean up only your own mess."*

- Modify only files directly required by the task.
- Do not refactor adjacent code "while you are there."
- Do not delete or rewrite comments that you did not author unless asked.
- A diff that looks small **is** small. Large diffs require justification.

### 1.4 Goal-Driven Execution
> *"Define success criteria. Loop until verified."*

- Before starting, write the success criteria in one sentence.
- After implementing, run the verification step (test, dry-run, paper-trade).
- Do not declare a task done because the code compiles. Done = success criteria met.

---

## 2. Non-Negotiable Project Constraints

These are **hard limits**. Violating them is a critical failure.

| # | Constraint | Why |
|---|---|---|
| C1 | **Withdrawal API permissions are forbidden.** API keys must be trade-only, IP-whitelisted, and rotated. | Compromised withdrawal keys = total capital loss. |
| C2 | **No code path executes a real trade without passing through the Risk Layer.** | Bypassing risk = unbounded loss. |
| C3 | **Paper-trade mode is the default.** Live trading requires an explicit env flag `EXECUTION_MODE=live`. | Prevents accidental real money loss during dev. |
| C4 | **Every detected opportunity must be logged with full context** (timestamps, prices, fees, decision). | Audit trail for tax, debugging, and post-mortems. |
| C5 | **Fees and slippage must be subtracted before profitability check.** Gross spread is never a trade signal. | Most "opportunities" disappear after costs. |
| C6 | **No secrets in code or commits.** API keys live in `.env` (gitignored) or a secrets vault. | Leaked keys = leaked funds. |
| C7 | **No `eval`, no string-built SQL, no untrusted input to subprocess.** | Standard security hygiene. |
| C8 | **MVP supports one strategy.** Cross-strategy unification is a v2 concern. | Avoid the "universal bot that never works" trap. |

---

## 3. Tech Stack (Frozen for MVP)

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Ecosystem maturity for trading + async I/O |
| Exchange SDK | `ccxt` (unified) + native WebSocket per exchange | One API surface, but native WS for latency |
| Async runtime | `asyncio` + `aiohttp` | Concurrent exchange streams |
| Data | `pandas`, `numpy` | Standard for tickers and analysis |
| Config | `pydantic-settings` + `.env` | Typed config, no magic strings |
| Logging | `structlog` (JSON) | Machine-parseable audit trail |
| Testing | `pytest` + `pytest-asyncio` + `vcrpy` | Unit + replay HTTP fixtures |
| Persistence | SQLite (MVP) → PostgreSQL (production) | Start simple; one migration when scale demands |
| Process mgmt | `systemd` or Docker | No custom supervisor |

**Do not introduce new dependencies without justification in the PR description.**

---

## 4. The Agent Decision Loop

When Claude Code receives a task on this repo, it must follow this loop:

```
┌──────────────────────────────────────────────────────────────┐
│ 0. ORIENT      — Read STATUS.md + MEMORY.md.                 │
│ 1. READ        — CLAUDE.md, specs/ARCHITECTURE.md, relevant  │
│                  skills/*/SKILL.md.                           │
│ 2. CLARIFY     — Apply Principle 1.1. List assumptions.      │
│                  Ask questions if ambiguous. STOP.            │
│ 3. PLAN        — One paragraph. Files to touch. Success      │
│                  criteria in one sentence.                    │
│ 4. IMPLEMENT   — Apply 1.2 and 1.3. Smallest correct change. │
│ 5. VERIFY      — Apply 1.4. Run tests. Dry-run. Show output. │
│ 6. REPORT      — What changed, what was verified, what was   │
│                  intentionally NOT changed.                   │
└──────────────────────────────────────────────────────────────┘
```

Skipping step 2 is the single most common failure mode. Do not skip it.

---

## 5. File Map (Where to Look)

| You need… | Read… |
|---|---|
| Current session state (read FIRST every session) | `STATUS.md` |
| Long-term project memory (decisions, gotchas, prefs) | `MEMORY.md` |
| Catalog of every `.md` in the repo (one-liners) | `specs/INDEX.md` |
| Chronological event log (append-only) | `specs/LOG.md` |
| Why the architecture looks like it does | `specs/ARCHITECTURE.md` |
| Concrete quality scenarios (perf, security…) | `specs/QUALITY_ATTRIBUTES.md` |
| Folder/module layout | `specs/PROJECT_STRUCTURE.md` |
| How to develop, test, deploy | `specs/WORKFLOW.md` |
| Ready-made prompts for common tasks | `specs/PROMPT_TEMPLATES.md` |
| Term definitions (spread, slippage…) | `specs/GLOSSARY.md` |
| UI/dashboard design language (deferred to v2) | `specs/DESIGN_LANGUAGE.md` |
| Security model — every control, mechanism, test, status | `specs/SECURITY.md` |
| Karpathy LLM-Wiki pattern (project-wide rule body) | `.claude/rules/karpathy-guidelines.md` |
| How to work on a specific module | `skills/<module-name>/SKILL.md` |

---

## 6. Available Skills

Each skill is a focused operating manual for one module. Read the relevant
`SKILL.md` **before** writing code for that module.

- `skills/market-data-ingestion/SKILL.md` — Exchange data feeds (WS + REST)
- `skills/exchange-integration/SKILL.md` — Adding/configuring exchanges
- `skills/arbitrage-detection/SKILL.md` — Strategy engine (spatial/triangular/funding)
- `skills/risk-management/SKILL.md` — Pre-trade checks, position limits, kill-switch
- `skills/execution-engine/SKILL.md` — Order placement, lifecycle, reconciliation

---

## 7. What "Done" Looks Like (per PR)

A PR is mergeable when **all of these are true**:

- [ ] One-sentence success criterion stated in PR description
- [ ] Diff touches only files required for the task
- [ ] New code has tests; modified code's tests still pass
- [ ] No new top-level dependencies without justification
- [ ] No real funds touched (or explicit approval if live)
- [ ] Logs/metrics added for any new decision point
- [ ] Updated the relevant `SKILL.md` if behavior changed

---

## 8. When You Disagree With This File

This file is versioned. If a principle here conflicts with what the user is asking,
**say so explicitly** before complying or refusing. Do not silently override.
The user can amend CLAUDE.md; the agent cannot.

---

## 9. Wiki Maintenance Protocol

The repo maintains a four-file **wiki layer** so that knowledge compounds and
context survives `/compact` and new sessions. Source pattern:
`specs/karpathy-wiki.md` (reference only — this section is the project-specific
instantiation).

### 9.1 The four files

| File | Scope | Lifetime | Hard ceiling |
|---|---|---|---|
| `STATUS.md` | What is happening now | Hours / one session | ≤ 60 lines |
| `MEMORY.md` | Decisions, gotchas, prefs | Project lifetime | No ceiling; archive obsolete entries inline (do not delete history) |
| `specs/INDEX.md` | Catalog of every `.md` | Updates on structural change | One row per file |
| `specs/LOG.md` | Chronological events | Append-only, forever | No ceiling |

### 9.2 Three operations

**Ingest** — a new source enters the project (a spec, a research note, a
decision document):
1. File it in the right folder (`specs/` for design, `skills/<m>/` for module).
2. Add a row to `specs/INDEX.md` with a one-liner.
3. Append a `## [YYYY-MM-DD] ingest | <title>` entry to `specs/LOG.md`.
4. If the source froze a decision, add it to `MEMORY.md § Decisions & Why`.

**Decision** — a frozen choice is made (stack, protocol, naming convention):
1. Append to `MEMORY.md § Decisions & Why` with **what / why / where**.
2. Append `## [YYYY-MM-DD] decision | <title>` to `specs/LOG.md`.
3. Update `STATUS.md § Now` if the decision changes current direction.

**Lint** — periodic health check (operator-triggered; no fixed schedule):
1. Read `MEMORY.md` end-to-end. Flag contradictions, stale entries, missing
   `Where:` pointers.
2. Cross-check `specs/INDEX.md` against `find . -name "*.md"` — flag orphans
   and missing rows.
3. Verify every CLAUDE.md cross-reference resolves on disk.
4. Report findings to the operator; **do not auto-edit** during lint.
5. Append `## [YYYY-MM-DD] lint | <summary>` to `specs/LOG.md`.

### 9.3 Update triggers (when, not whether)

| Trigger | Files touched |
|---|---|
| Session ends | `STATUS.md` (always) |
| Session begins | Read `STATUS.md` + relevant `MEMORY.md` sections (Decision Loop step 0) |
| New `.md` added / renamed / deleted | `specs/INDEX.md` |
| Decision frozen | `MEMORY.md` + `specs/LOG.md` |
| Bug found / fixed | `MEMORY.md § Gotchas` + `specs/LOG.md` |
| Operator preference learned | `MEMORY.md § Operator Preferences` |

### 9.4 Distinction from Claude's auto-memory

The agent's personal memory under `~/.claude/projects/.../memory/` is a
**different layer** — private to one Claude Code instance, learns operator
preferences, never committed. The wiki layer in this repo is **project
memory** — shared across agents (Claude Code, Cursor, future tools),
versioned in git, survives operator changes. Both serve token reduction at
different scopes; neither replaces the other.

### 9.5 Karpathy Principle alignment

- **1.1 Think Before Coding** — STATUS.md is read first; assumptions surface in
  `Open questions`.
- **1.2 Simplicity First** — the wiki layer is four files, not a framework.
- **1.3 Surgical Changes** — every update touches only the file(s) listed in §9.3.
- **1.4 Goal-Driven Execution** — `STATUS.md § Next` is the explicit success
  criterion list; loop until checked off.
