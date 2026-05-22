# INDEX — Project-Crypto-Arbitrage-Bot

> **Content catalog.** Every meaningful `.md` in the repo, with a one-line
> summary. Agents should read this FIRST when looking for where a topic
> lives — beats a fresh `grep` of the whole repo (Karpathy 1.2).
>
> Maintainer rule: update on every `.md` add / rename / delete.

---

## Root (project-level state)

| File | One-liner |
|---|---|
| [`CLAUDE.md`](../CLAUDE.md) | Agent constitution. Four Karpathy Principles. Decision Loop. Read-first contract. |
| [`README.md`](../README.md) | Human-facing overview, repo structure, getting-started. |
| [`STATUS.md`](../STATUS.md) | Current session state. Bridge across `/compact` and new sessions. |
| [`MEMORY.md`](../MEMORY.md) | Long-term project memory. Decisions, gotchas, operator preferences. |

## specs/ (design & process)

| File | One-liner |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | ADD-based architecture decisions. The "why" of the system shape. |
| [`QUALITY_ATTRIBUTES.md`](QUALITY_ATTRIBUTES.md) | Numbered QA scenarios (perf, reliability, security…). Every architectural decision traces to one. |
| [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) | Folder & module layout. |
| [`WORKFLOW.md`](WORKFLOW.md) | Dev → paper → live promotion path. |
| [`PROMPT_TEMPLATES.md`](PROMPT_TEMPLATES.md) | Tested prompts for Claude Code on this repo. |
| [`GLOSSARY.md`](GLOSSARY.md) | Domain terminology (spread, slippage, funding…). |
| [`DESIGN_LANGUAGE.md`](DESIGN_LANGUAGE.md) | Operator-dashboard visual & interaction system. Deferred to v2. |
| [`SECURITY.md`](SECURITY.md) | Security model — 15 controls (C1-C8 + S1-S7), per-faz gates, incident response. |
| [`INDEX.md`](INDEX.md) | This file. |
| [`LOG.md`](LOG.md) | Chronological append-only event log. |
| [`karpathy-wiki.md`](karpathy-wiki.md) | Karpathy's LLM-Wiki pattern (canonical reference, Obsidian-readable). |

## skills/ (per-module operating manuals)

| File | One-liner |
|---|---|
| [`market-data-ingestion/SKILL.md`](../skills/market-data-ingestion/SKILL.md) | Exchange data feeds (WS + REST), normalization, in-memory bus contract. |
| [`exchange-integration/SKILL.md`](../skills/exchange-integration/SKILL.md) | Adding/configuring exchanges; ExchangeAdapter protocol; PaperExchange contract. |
| [`arbitrage-detection/SKILL.md`](../skills/arbitrage-detection/SKILL.md) | Strategy engine; Strategy protocol; spatial/triangular/funding specifics. |
| [`risk-management/SKILL.md`](../skills/risk-management/SKILL.md) | Pre-trade checks, position limits, kill-switch. `RiskDecision(approved=True)` gate. |
| [`execution-engine/SKILL.md`](../skills/execution-engine/SKILL.md) | Order lifecycle, idempotent retry, partial-fill handling, leg reconciliation. |

## Tooling / config (referenced for completeness, not browsed for content)

| File | One-liner |
|---|---|
| `.claude/rules/karpathy-guidelines.md` | Karpathy LLM-Wiki gist, project-wide rule body for Claude Code (referenced from CLAUDE.md § 5). |
| `.gitignore` | Ignore `.DS_Store`, Python build artifacts, `.env`, SQLite DBs, IDE folders. |
| `.gitleaks.toml` | gitleaks scanner config — custom regex for binance/bybit/HMAC patterns (SECURITY.md S1). |
| `.pre-commit-config.yaml` | pre-commit hook → gitleaks on staged files (SECURITY.md S1). |
| `.github/workflows/security.yml` | CI workflow re-runs gitleaks on push + PR (SECURITY.md S1). |
| `scripts/check_env_example.py` | Pre-commit lint — `.env.example` values must stay empty / on allowlist (SECURITY.md S1 strengthening, 2026-05-22 incident response). |
| `pyproject.toml` | PEP 621 project metadata + deps (uv-managed, hatchling-built). |
| `.env.example` | Template for `.env`. Real `.env` is gitignored. |
| `dashboard/index.html` | Design-language smoke (mock data; pure HTML/CSS). Real build in step a of c→a→b plan. |
| `dashboard/README.md` | How to open the smoke + review checklist. |
