---
name: execution-engine
description: Operating manual for the execution engine — order placement, lifecycle tracking, fill reconciliation, and recovery from imbalanced legs. Read this BEFORE writing any code under `src/arbitrage_agent/execution/`. Covers the order state machine, idempotent retry, partial-fill handling, and the contract between approved orders and exchange adapters.
---

# SKILL · Execution Engine

## Purpose

Take an `Opportunity` that risk has approved, and turn it into actual orders
on actual exchanges. Track each order through its lifecycle. Reconcile fills.
Recover from anything that goes wrong on the way.

This module is where **theoretical profit becomes real or evaporates**.
Most of the work here is dealing with the inconvenient truth that exchanges
do not always do what you ask.

---

## Responsibility Boundary

| In scope | Out of scope |
|---|---|
| Place orders (only with `RiskDecision(approved=True)`) | Decide what or whether to trade |
| Track order lifecycle (open, partial, filled, cancelled, rejected) | Strategy logic |
| Reconcile expected vs actual fills | Risk approval |
| Recover from imbalanced legs (hedge or wind down) | Persistence (it emits events) |
| Manage timeouts and cancellations | Anything outside its module |

---

## Quality Attributes This Module Owns

- **QA-1.3** — Partial fills on multi-leg arbitrage resolved within 30 s;
  net unhedged exposure ≤ configured limit at all times.
- **QA-3.2** — From `Opportunity` to first leg's HTTP request: p99 ≤ 250 ms.

---

## The Order Lifecycle State Machine

```
                    ┌────────────┐
                    │  PENDING   │ ← created from RiskDecision
                    └─────┬──────┘
                          │ send
                          ▼
              ┌─────────────────────┐
              │      SUBMITTED      │ ← HTTP returned an order_id
              └───┬────────────┬────┘
                  │            │
        partial   │            │ filled
                  ▼            ▼
        ┌──────────────┐  ┌──────────────┐
        │   PARTIAL    │  │    FILLED    │ ← terminal (good)
        └───┬──────────┘  └──────────────┘
            │
            │ timeout / cancel
            ▼
        ┌──────────────┐
        │  CANCELLED   │ ← terminal
        └──────────────┘

  any state → REJECTED   ← terminal (bad; reason logged)
  any state → FAILED     ← terminal (network/unknown; needs reconciliation)
```

Every transition is logged to the decision log with the order_id and
reason. The state machine is **explicit**, not implicit. No "if status ==
'maybe filled' then …" code.

---

## Placing an Opportunity

An `Opportunity` has 2–3 `OrderIntent` legs. The execution engine:

1. Validates the `RiskDecision` (approved, correct `opportunity_id`).
2. Computes the order placement order (which leg first?). Defaults:
   - **Spatial:** the leg with the **higher fill confidence** first
     (deeper book, smaller relative size). Reduces probability of one-sided
     fill.
   - **Triangular:** the leg whose failure leaves the **smallest unhedged
     exposure** first.
3. Submits the legs **concurrently** but tracks each separately.
4. Waits for terminal states or timeout (`opportunity.valid_for_ms`).
5. If any leg is `PARTIAL` or `CANCELLED` at timeout, **hand to the
   hedger** (next section).

---

## The Hedger (QA-1.3)

When a leg fails to fully fill, the system has unbalanced inventory.
The hedger's job is to **return to neutral**, accepting a degraded P&L on
that opportunity.

Rules:

- Hedge as quickly as is **safely** possible.
- Hedge at a **defined max slippage budget** (config, e.g., 0.5%).
- If the hedge cannot complete within budget, escalate: cancel further
  attempts, **log the open exposure**, **alert the operator**.
- Never let unhedged exposure grow without bound. The kill-switch fires
  if exposure exceeds the gross limit.

The hedger is the **only** code that may place an order without an
upstream `Opportunity`. The order it places carries a special
`RiskDecision` with `reason="hedge for opportunity X"` and the original
`opportunity_id` for traceability.

---

## Idempotency & Retries

Exchanges sometimes return errors that **don't** mean the order failed.
Network timeouts are notorious: the order may have been placed; you just
don't know.

Rules:

- Every `OrderIntent` carries a **client_order_id** (UUID) before placement.
- The adapter sends this ID to the exchange (`clientOrderId` parameter
  where supported).
- On network failure / timeout, the engine **does not blindly retry**.
  It calls `fetch_order_by_client_id(client_order_id)`. Either:
  - The order exists → adopt its state. Done.
  - The order does not exist → safe to retry once with the same
    client_order_id.
- Maximum retries: **1**. After that, escalate. Hidden duplicates are
  catastrophic.

---

## Limit Orders Only (MVP)

The MVP places **limit** orders, not market orders. Reasons:

- Market orders are exposed to unbounded slippage.
- Limit orders that fail to fill leave a known state (open or expired);
  market orders that partially fill leave an ambiguous state.
- The strategy engine has already chosen a price based on the order book;
  giving the exchange a different price would mean ignoring its math.

Limit orders here are **aggressive** (priced to cross the spread for
immediate fill). They are not passive maker orders.

A `Market` mode and a `Passive Maker` mode are explicit v2 features.

---

## Cancellation

- All open orders are cancelled when:
  - The opportunity's `valid_for_ms` expires
  - The kill-switch engages
  - The bot is shutting down (SIGTERM)
- Cancellation is **best-effort**: the exchange may have just filled
  the order. Reconcile after.

---

## Reconciliation

After every order reaches a terminal state, the reconciler:

1. Compares the engine's record (expected fill) against the exchange's
   record (`fetch_fills`).
2. If they match → write to fills DB, update P&L.
3. If they diverge → flag as a reconciliation incident, log everything,
   alert operator. **Do not silently "trust the exchange."**

A daily reconciliation pass also runs against the exchange's full history
to catch externally-induced state changes (e.g., manual trades on the
same account — see C1: don't share accounts).

---

## Performance Notes (QA-3.2)

- The hot path from `Opportunity` to first HTTP request must be minimal:
  no DB writes, no JSON serialization beyond what HTTP requires.
- Persistence writes happen **after** the HTTP send-attempt, not before.
  (A crashed bot can be reconciled; a bot that delayed its order by 30 ms
  to write to disk is just slow.)
- The decision log uses an async queue with a background writer thread.

---

## Anti-Patterns

| Anti-pattern | Consequence |
|---|---|
| Retrying an order indefinitely on timeout | Hidden duplicate fills |
| Treating "order not found" as success | Lost orders never reconciled |
| Catching all exceptions and continuing | Hidden bugs accumulate exposure |
| Placing a market order "as a fallback" | Unbounded slippage |
| Letting the hedger run without a budget | Death spiral on a bad book |
| State stored only in memory | Crash recovery loses orders; persist transitions |

---

## Testing This Module

- **State machine** tests: drive each transition synthetically with the
  `PaperExchange`.
- **Idempotency** test: simulate network failure between send and ack;
  assert no duplicate placement.
- **Partial fill recovery** test: leg 1 fills 100%, leg 2 fills 40%;
  hedger brings exposure back to ≤ limit within 30 s (simulated time).
- **Cancellation race** test: cancel a partially-filled order; reconciler
  matches against the actual fills.
- **Kill-switch** test: when engaged, all pending orders are cancelled
  within 2 s (QA-1.2).

Tests live in `tests/integration/execution/` (these are mostly integration
tests because the state machine is what's being verified).

---

## When to Update This Skill

- A new order type is supported (passive maker, market, IOC, FOK)
- The hedger's strategy changes (more sophisticated than "neutralize")
- The reconciliation policy changes
- A class of incidents repeats and the playbook needs documenting
