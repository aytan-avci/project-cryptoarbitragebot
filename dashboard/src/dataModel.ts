import { useEffect, useState } from 'react';
import type {
  FillEvent,
  HedgerResultEvent,
  KillSwitchState,
  LogEvent,
  OpportunityEvent,
  RiskDecisionEvent,
  SnapshotFetchedEvent,
  TestnetEvidence,
} from './types';

/** Parse a `.jsonl` body into a list of events; skip blank / malformed lines. */
export function parseJsonl(body: string): LogEvent[] {
  const out: LogEvent[] = [];
  for (const line of body.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      out.push(JSON.parse(trimmed) as LogEvent);
    } catch {
      // Skip malformed lines — the bot may have been writing while we polled.
    }
  }
  return out;
}

/** Poll `logs/decisions.jsonl` on an interval. */
export function useAuditLog(intervalMs = 2_000): {
  events: LogEvent[];
  loading: boolean;
  error: string | null;
} {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch('/logs/decisions.jsonl', { cache: 'no-store' });
        if (!res.ok) {
          if (res.status === 404) {
            if (!cancelled) {
              setEvents([]);
              setError(null);
              setLoading(false);
            }
            return;
          }
          throw new Error(`HTTP ${res.status}`);
        }
        const body = await res.text();
        if (!cancelled) {
          setEvents(parseJsonl(body));
          setError(null);
          setLoading(false);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message ?? 'fetch failed');
          setLoading(false);
        }
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { events, loading, error };
}

/** Poll `logs/testnet_evidence.json` for S7 mainnet-gate state.
 * Missing file → `first_seen_utc=null`; the dashboard renders that as
 * "no probation recorded yet". */
export function useTestnetEvidence(intervalMs = 5_000): TestnetEvidence {
  const [state, setState] = useState<TestnetEvidence>({
    first_seen_utc: null,
    last_seen_utc: null,
    venues: [],
  });

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch('/logs/testnet_evidence.json', { cache: 'no-store' });
        if (!res.ok) {
          if (!cancelled) {
            setState({ first_seen_utc: null, last_seen_utc: null, venues: [] });
          }
          return;
        }
        const data = (await res.json()) as TestnetEvidence;
        if (!cancelled) setState(data);
      } catch {
        // Best-effort polling — keep previous state on transient errors.
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}

/** Poll `logs/kill_switch.json` for the durable kill-switch state. */
export function useKillSwitch(intervalMs = 2_000): KillSwitchState {
  const [state, setState] = useState<KillSwitchState>({ engaged: false });

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch('/api/kill-switch', { cache: 'no-store' });
        if (!res.ok) {
          if (!cancelled) setState({ engaged: false });
          return;
        }
        const data = (await res.json()) as KillSwitchState;
        if (!cancelled) setState(data);
      } catch {
        if (!cancelled) setState({ engaged: false });
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}

// ---- Derived summaries ----------------------------------------------------

export function opportunities(events: LogEvent[]): OpportunityEvent[] {
  return events.filter((e): e is OpportunityEvent => e.event === 'opportunity_detected');
}

export function decisions(events: LogEvent[]): RiskDecisionEvent[] {
  return events.filter((e): e is RiskDecisionEvent => e.event === 'risk_decision');
}

export function fills(events: LogEvent[]): FillEvent[] {
  return events.filter((e): e is FillEvent => e.event === 'fill');
}

export function snapshots(events: LogEvent[]): SnapshotFetchedEvent[] {
  return events.filter(
    (e): e is SnapshotFetchedEvent => e.event === 'snapshot_fetched',
  );
}

export function hedgerResults(events: LogEvent[]): HedgerResultEvent[] {
  return events.filter((e): e is HedgerResultEvent => e.event === 'hedger_result');
}

/** Latest snapshot per (exchange, symbol). */
export function latestSnapshotsByVenue(
  events: LogEvent[],
): Map<string, SnapshotFetchedEvent> {
  const out = new Map<string, SnapshotFetchedEvent>();
  for (const s of snapshots(events)) {
    const key = `${s.exchange}|${s.symbol}`;
    const existing = out.get(key);
    if (!existing || s.timestamp_utc > existing.timestamp_utc) {
      out.set(key, s);
    }
  }
  return out;
}

export interface HedgerSummary {
  total: number;
  filled: number;
  partial: number;
  aborted: number;
  placementFailed: number;
  noMarketData: number;
}

export interface DashboardSummary {
  pnlUsd: number;
  pnlDirection: 'positive' | 'negative' | 'flat';
  opportunitiesCount: number;
  approvedCount: number;
  rejectedCount: number;
  approvalRate: number;
  fillsCount: number;
  uniqueExchanges: number;
  hedger: HedgerSummary;
}

export function summarize(events: LogEvent[]): DashboardSummary {
  const opps = opportunities(events);
  const dec = decisions(events);
  const f = fills(events);
  const hr = hedgerResults(events);

  const approved = dec.filter(d => d.approved).length;
  const rejected = dec.length - approved;

  // Realised P&L = Σ (sell value − buy value − fees), grouped by opportunity.
  // parseFloat is lossy but adequate for display; production needs Decimal.
  let pnl = 0;
  for (const fill of f) {
    const signed = (fill.side === 'sell' ? 1 : -1) * parseFloat(fill.price) * parseFloat(fill.volume);
    pnl += signed - parseFloat(fill.fee);
  }
  const dir: DashboardSummary['pnlDirection'] =
    pnl > 0.001 ? 'positive' : pnl < -0.001 ? 'negative' : 'flat';

  // `no_imbalance` is the happy path — exclude from the operator-facing
  // counters; only flag events where the hedger actually intervened.
  const active = hr.filter(h => h.status !== 'no_imbalance');
  const hedger: HedgerSummary = {
    total: active.length,
    filled: active.filter(h => h.status === 'filled').length,
    partial: active.filter(h => h.status === 'partial').length,
    aborted: active.filter(h => h.status === 'aborted_slippage').length,
    placementFailed: active.filter(h => h.status === 'placement_failed').length,
    noMarketData: active.filter(h => h.status === 'no_market_data').length,
  };

  return {
    pnlUsd: pnl,
    pnlDirection: dir,
    opportunitiesCount: opps.length,
    approvedCount: approved,
    rejectedCount: rejected,
    approvalRate: dec.length ? approved / dec.length : 0,
    fillsCount: f.length,
    uniqueExchanges: new Set(f.map(x => x.exchange)).size,
    hedger,
  };
}

/** S7 derived view — days observed since first testnet activity and
 * whether the mainnet gate (≥30 days) is satisfied. */
export interface S7Summary {
  daysObserved: number;
  required: number;
  eligible: boolean;
  hasEvidence: boolean;
  firstSeenUtc: string | null;
  lastSeenUtc: string | null;
  venues: string[];
}

export function summarizeTestnetEvidence(ev: TestnetEvidence): S7Summary {
  const required = 30;
  if (!ev.first_seen_utc) {
    return {
      daysObserved: 0,
      required,
      eligible: false,
      hasEvidence: false,
      firstSeenUtc: null,
      lastSeenUtc: null,
      venues: [],
    };
  }
  const first = Date.parse(ev.first_seen_utc);
  const days = Number.isFinite(first)
    ? Math.max(0, Math.floor((Date.now() - first) / 86_400_000))
    : 0;
  return {
    daysObserved: days,
    required,
    eligible: days >= required,
    hasEvidence: true,
    firstSeenUtc: ev.first_seen_utc,
    lastSeenUtc: ev.last_seen_utc,
    venues: ev.venues,
  };
}

export function joinDecisionsToOpps(
  events: LogEvent[],
): Array<OpportunityEvent & { decision: RiskDecisionEvent | undefined }> {
  const decisionById = new Map(decisions(events).map(d => [d.opportunity_id, d]));
  return opportunities(events).map(o => ({ ...o, decision: decisionById.get(o.id) }));
}
