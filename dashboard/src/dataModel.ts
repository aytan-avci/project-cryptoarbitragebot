import { useEffect, useState } from 'react';
import type {
  FillEvent,
  KillSwitchState,
  LogEvent,
  OpportunityEvent,
  RiskDecisionEvent,
  SnapshotFetchedEvent,
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

export interface DashboardSummary {
  pnlUsd: number;
  pnlDirection: 'positive' | 'negative' | 'flat';
  opportunitiesCount: number;
  approvedCount: number;
  rejectedCount: number;
  approvalRate: number;
  fillsCount: number;
  uniqueExchanges: number;
}

export function summarize(events: LogEvent[]): DashboardSummary {
  const opps = opportunities(events);
  const dec = decisions(events);
  const f = fills(events);

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

  return {
    pnlUsd: pnl,
    pnlDirection: dir,
    opportunitiesCount: opps.length,
    approvedCount: approved,
    rejectedCount: rejected,
    approvalRate: dec.length ? approved / dec.length : 0,
    fillsCount: f.length,
    uniqueExchanges: new Set(f.map(x => x.exchange)).size,
  };
}

export function joinDecisionsToOpps(
  events: LogEvent[],
): Array<OpportunityEvent & { decision: RiskDecisionEvent | undefined }> {
  const decisionById = new Map(decisions(events).map(d => [d.opportunity_id, d]));
  return opportunities(events).map(o => ({ ...o, decision: decisionById.get(o.id) }));
}
