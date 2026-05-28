// TypeScript mirror of the bot's domain events emitted as JSONL by
// `src/arbitrage_agent/persistence/decision_log.py`. Keep field names
// in sync with `specs/ARCHITECTURE.md § 6` exactly.

export type Side = 'buy' | 'sell';
export type StrategyName = 'spatial' | 'triangular' | 'funding';

export interface SymbolPair {
  base: string;
  quote: string;
}

export interface OrderIntent {
  exchange: string;
  symbol: SymbolPair;
  side: Side;
  quantity: string; // Decimal as string — preserves precision
  limit_price: string;
}

export interface OpportunityEvent {
  event: 'opportunity_detected';
  id: string;
  detected_at: string; // ISO-ish string, e.g. "2026-05-21 09:36:59.274071+00:00"
  strategy: StrategyName;
  expected_net_profit_usd: string;
  confidence: number;
  valid_for_ms: number;
  legs: OrderIntent[];
}

export interface RiskDecisionEvent {
  event: 'risk_decision';
  opportunity_id: string;
  approved: boolean;
  reason: string;
  adjusted_quantity: string | null;
}

export interface FillEvent {
  event: 'fill';
  opportunity_id: string;
  exchange: string;
  symbol: string; // serialized as "BTC/USDT"
  side: Side;
  price: string;
  volume: string;
  fee: string;
  timestamp_utc: string;
}

export interface SnapshotFetchedEvent {
  event: 'snapshot_fetched';
  exchange: string;
  symbol: string;
  bid: string;
  ask: string;
  bid_size: string;
  ask_size: string;
  timestamp_utc: string;
}

// Hedger outcome — emitted by `DecisionLog.append_hedger_result` once
// per opportunity that needed neutralisation (Faz 7g-c + dashboard
// enrichment).
export type HedgeStatus =
  | 'no_imbalance'
  | 'filled'
  | 'partial'
  | 'aborted_slippage'
  | 'no_market_data'
  | 'placement_failed';

export interface HedgerResultEvent {
  event: 'hedger_result';
  opportunity_id: string;
  status: HedgeStatus;
  remaining_exposure: string;
  reason: string;
  counter_leg: {
    exchange: string;
    symbol: string;
    side: Side;
    quantity: string;
    limit_price: string;
  } | null;
  fills_count: number;
}

export type LogEvent =
  | OpportunityEvent
  | RiskDecisionEvent
  | FillEvent
  | SnapshotFetchedEvent
  | HedgerResultEvent;

export interface KillSwitchState {
  engaged: boolean;
  reason?: string;
  engaged_at_utc?: string;
  reset_at_utc?: string;
}

// S7 testnet evidence — mirrors `risk/testnet_evidence.py` schema.
export interface TestnetEvidence {
  first_seen_utc: string | null;
  last_seen_utc: string | null;
  venues: string[];
}

// Faz 8 — redacted runtime status the bot writes to
// logs/runtime_status.json. Contains booleans + non-secret values
// ONLY; never SMTP password / Telegram token.
export interface RuntimeStatus {
  mode?: string;                  // paper | live
  strategy?: string;              // spatial | triangular
  loop_mode?: string;             // forever | once
  email_configured?: boolean;
  telegram_configured?: boolean;
  iterations?: number;
  opportunities?: number;
  approved?: number;
  rejected?: number;
  fills?: number;
  daily_pnl_usd?: string;
  last_updated_utc?: string;
}
