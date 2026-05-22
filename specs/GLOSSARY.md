# GLOSSARY.md — Domain Terms

> Trading vocabulary used throughout this repo. Read this if a term in
> `ARCHITECTURE.md` or `QUALITY_ATTRIBUTES.md` is unfamiliar.

---

## Arbitrage Strategies

**Arbitrage** — Buying an asset on one venue and selling it on another (or
via a sequence of trades) to profit from a price difference, after costs.

**Spatial arbitrage** — Buy BTC on Exchange A at price $X, sell on Exchange B
at price $X + Δ. Δ must cover both venues' fees plus transfer cost (or
require pre-funded balances on both venues).

**Triangular arbitrage** — Inside one exchange, follow a cycle of three
trading pairs (e.g., USDT → BTC → ETH → USDT) and end with more USDT than
you started. Has no withdrawal risk because no funds leave the exchange.

**Funding-rate arbitrage** — On a perpetual futures venue, take opposite
positions in the spot and perpetual markets to collect the funding rate
(paid by long-biased traders to short-biased traders, or vice versa, every
8 hours typically). Market-neutral; the lowest-risk strategy.

**CEX–DEX arbitrage** — Exploit price difference between a centralized
exchange (CEX, e.g., Binance) and a decentralized exchange (DEX, e.g.,
Uniswap). Higher returns, but exposed to gas fees and MEV (front-running by
other bots watching the mempool). Out of MVP scope.

**Statistical arbitrage** — Trade on statistical relationships between
correlated assets that have temporarily diverged. Not the same as the
arbitrage above; carries directional risk. Out of MVP scope.

---

## Market Microstructure

**Spread** — The difference between the best bid and best ask on a single
order book. *Bid-ask spread.* A small spread = high liquidity.

**Slippage** — The difference between the expected price of a trade and the
price at which it actually fills. Caused by order book depth: a large order
"walks the book" and fills at worse prices than the top of book.

**Order book** — The list of all open buy orders (bids) and sell orders
(asks) on an exchange for a given pair, sorted by price.

**Depth** — How much volume sits at each price level of the order book.
Thin depth = high slippage on size.

**Top of book** — The best bid and best ask. The price you see is usually
this.

**Market order** — Buy/sell whatever it takes to fill immediately. Pays the
spread, exposed to slippage. **Not used in this bot's MVP.**

**Limit order** — Buy/sell only at a stated price or better. May not fill.
Default in this bot.

**Maker / Taker** — A maker adds liquidity (a limit order that sits on the
book); a taker removes liquidity (any order that fills against an existing
order). Maker fees are usually lower than taker fees.

**Fill** — The actual execution of part or all of an order.

**Partial fill** — Part of the order executed, part remains open. Hazardous
in multi-leg arbitrage (see `QUALITY_ATTRIBUTES.md § QA-1.3`).

---

## Costs

**Trading fee** — Per-trade fee charged by the exchange, usually as a
percentage. Two tiers: maker and taker.

**Withdrawal fee** — Fee to move crypto off the exchange. Sometimes a
flat amount in the asset.

**Gas fee** — On-chain transaction fee, for DEX operations or
cross-exchange transfers via blockchain.

**Network confirmation time** — Minutes-to-hours wait for an on-chain
transfer between exchanges. **Why spatial arbitrage needs pre-funded
balances on both venues.**

---

## Bot Operations

**Latency** — Time elapsed between two events. *Detection latency* =
WebSocket tick → opportunity emitted. *Execution latency* = decision →
order on exchange. Both are critical (see `QA-3`).

**Throughput** — How many ticks/orders/decisions per second the system
sustains.

**Tick** — A single market data update (new trade, new top-of-book quote,
or new order).

**Snapshot** — A point-in-time view of one or more order books, used to
make a decision.

**Replay** — Run the system against recorded ticks instead of live data,
to test logic deterministically.

**Paper trading** — Run the system with real market data but simulated
fills. No real capital at risk.

**Live trading** — Real orders, real capital.

**Kill switch** — A mechanism that halts all new orders and cancels open
orders. Triggered by error rate, P&L deviation, or manual operator action.

**Reconcile** — Verify that the bot's internal record of orders/positions
matches the exchange's record. Mismatches are bugs or external events
(e.g., manual trades on the same account).

**Backtest** — Replay historical data through a strategy to estimate past
performance. Always **optimistic** vs. live (perfect fills, no latency,
no impact). Useful as a sanity floor, not a profit forecast.

**Walk-forward test** — Out-of-sample backtest: train/tune on data window
A, test on later window B. Less prone to overfitting than simple backtest.

---

## Risk Concepts

**Position** — Net holding in an asset. Long = positive, short = negative.

**Exposure** — Dollar value of positions, gross or net. *Gross exposure*
sums absolute values; *net exposure* sums signed.

**Position limit** — Maximum allowed exposure per asset.

**Drawdown** — Decline from a peak. Max drawdown is a key risk metric.

**Sharpe ratio** — Return divided by volatility. > 0 means returns exceed
the volatility cost; > 1 is good; > 2 is excellent. Backtest Sharpe is
usually 2–3× the live Sharpe.

**Inventory risk** — When market making or arbitrage, you may end up
holding an asset longer than intended because one leg didn't fill. The
price risk on that holding is inventory risk.

---

## System Concepts

**Order book WebSocket / Trade WebSocket** — Real-time feeds. Order book
WS pushes depth changes; trade WS pushes executed trades.

**REST API** — Request/response endpoint for placing orders, querying
balances, etc.

**Rate limit** — Maximum API calls per second/minute the exchange
permits. Exceeding triggers a temporary ban.

**IP whitelist** — Exchange security feature: API keys only work from
specific IPs.

**API key permissions** — Per-key flags: *read*, *trade*, *withdraw*.
This project forbids the *withdraw* flag.

---

## ADD-Specific

**Quality attribute (QA)** — A non-functional property of a system:
performance, security, modifiability, reliability, testability,
observability, etc. **The drivers of architecture in ADD.**

**Quality attribute scenario** — A six-part testable statement of a QA
requirement: source, stimulus, environment, artifact, response, measure.
See `QUALITY_ATTRIBUTES.md`.

**Architectural driver** — A requirement (functional, QA, or constraint)
that has a significant influence on the architecture.

**Architectural tactic** — A design decision that promotes one QA. E.g.,
"asynchronous messaging" tactic promotes performance/responsiveness.

**Architectural pattern** — A larger-scale solution shape that bundles
several tactics. E.g., the **Pipes and Filters** pattern used in this
system's ingestion → strategy → risk → execution flow.

**Architecturally significant requirement (ASR)** — A requirement that
shapes the architecture, as opposed to one that can be satisfied
post-design (a feature within an existing module).

**Trade-off** — The cost paid in one QA to gain another. ADD requires
trade-offs be named explicitly (`ARCHITECTURE.md § 8`).
