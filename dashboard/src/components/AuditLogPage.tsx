// Faz (b) — Audit Log page.
//
// Filtered + searchable view of every event in `logs/decisions.jsonl`.
// The Overview page renders a curated subset; this page is the
// operator's escape hatch when they need the raw audit trail.
//
// Filters:
//   - event type (multi-select: opportunity_detected, risk_decision,
//     fill, snapshot_fetched, hedger_result)
//   - free-text search (matches against the JSON-serialised line —
//     hits symbol, reason, opportunity_id, exchange, side, status)
//
// Each row expands to show the raw JSON payload so operator can copy/
// paste evidence into a post-mortem without leaving the dashboard.

import { useMemo, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  Collapse,
  IconButton,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
  useTheme,
  type Theme,
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';

import { MONO_FONT } from '../theme';
import type { LogEvent } from '../types';

interface AuditLogPageProps {
  events: LogEvent[];
  loading: boolean;
  error: string | null;
}

type EventTypeFilter = 'all' | LogEvent['event'];

const EVENT_TYPE_OPTIONS: { value: EventTypeFilter; label: string }[] = [
  { value: 'all', label: 'All event types' },
  { value: 'opportunity_detected', label: 'Opportunities' },
  { value: 'risk_decision', label: 'Risk decisions' },
  { value: 'fill', label: 'Fills' },
  { value: 'snapshot_fetched', label: 'Snapshots' },
  { value: 'hedger_result', label: 'Hedge results' },
];

function eventTimestamp(e: LogEvent): string {
  switch (e.event) {
    case 'fill':
    case 'snapshot_fetched':
      return e.timestamp_utc;
    case 'opportunity_detected':
      return e.detected_at;
    case 'risk_decision':
    case 'hedger_result':
      // these events don't carry their own timestamp in the JSONL —
      // we'd need the _ts embedded by structlog. Fall back to empty.
      return '';
  }
}

function eventSummary(e: LogEvent): string {
  switch (e.event) {
    case 'opportunity_detected':
      return `${e.strategy} · ${e.legs.length} leg${e.legs.length === 1 ? '' : 's'} · expected $${e.expected_net_profit_usd}`;
    case 'risk_decision':
      return `${e.approved ? 'approved' : 'rejected'} · ${e.reason}`;
    case 'fill':
      return `${e.side} ${e.volume} ${e.symbol} @ ${e.price} on ${e.exchange}`;
    case 'snapshot_fetched':
      return `${e.exchange} ${e.symbol} · bid=${e.bid} ask=${e.ask}`;
    case 'hedger_result':
      return `${e.status}${e.counter_leg ? ` · ${e.counter_leg.side} ${e.counter_leg.quantity} ${e.counter_leg.symbol} on ${e.counter_leg.exchange}` : ''}`;
  }
}

function eventColor(e: LogEvent, palette: Theme['palette']): string {
  switch (e.event) {
    case 'opportunity_detected':
      return palette.custom.order.submitted;
    case 'risk_decision':
      return e.approved ? palette.custom.order.filled : palette.custom.order.rejected;
    case 'fill':
      return palette.custom.order.filled;
    case 'snapshot_fetched':
      return palette.custom.order.pending;
    case 'hedger_result':
      return e.status === 'filled' ? palette.custom.order.filled
        : e.status === 'aborted_slippage' || e.status === 'placement_failed' ? palette.custom.order.rejected
        : palette.custom.order.partial;
  }
}

export function AuditLogPage({ events, loading, error }: AuditLogPageProps) {
  const theme = useTheme();
  const [typeFilter, setTypeFilter] = useState<EventTypeFilter>('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  // Filter events. We re-derive on every render — events is bounded
  // by the audit log's wallclock-lifetime size, so this stays fast
  // for thousands of entries.
  const filtered = useMemo(() => {
    let out = events;
    if (typeFilter !== 'all') {
      out = out.filter(e => e.event === typeFilter);
    }
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      out = out.filter(e => JSON.stringify(e).toLowerCase().includes(needle));
    }
    // Newest first.
    return out.slice().reverse();
  }, [events, typeFilter, search]);

  const paged = useMemo(
    () => filtered.slice(page * rowsPerPage, (page + 1) * rowsPerPage),
    [filtered, page, rowsPerPage],
  );

  if (error) {
    return (
      <Card>
        <CardContent>
          <Typography color="error" variant="body1" sx={{ fontWeight: 500 }}>
            Fetch failed — {error}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Typography variant="body2" color="text.secondary">
            Loading audit trail…
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 500, mb: 1 }}>
        Audit Log{' '}
        <Typography
          component="span"
          variant="caption"
          color="text.secondary"
          sx={{ ml: 1 }}
        >
          {events.length} total · {filtered.length} after filters
        </Typography>
      </Typography>

      {/* ── Filter bar ─────────────────────────────────────────────── */}
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
            <Box sx={{ minWidth: 240 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mb: 0.5 }}
              >
                Event type
              </Typography>
              <Select
                fullWidth
                size="small"
                value={typeFilter}
                onChange={e => {
                  setTypeFilter(e.target.value as EventTypeFilter);
                  setPage(0);
                }}
              >
                {EVENT_TYPE_OPTIONS.map(opt => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </MenuItem>
                ))}
              </Select>
            </Box>
            <Box sx={{ flex: 1, minWidth: 240 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mb: 0.5 }}
              >
                Search (symbol, reason, opportunity_id, exchange, side, status…)
              </Typography>
              <TextField
                fullWidth
                size="small"
                placeholder="e.g. BTC/USDT, kill_switch_engaged, aborted_slippage"
                value={search}
                onChange={e => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
              />
            </Box>
          </Stack>
        </CardContent>
      </Card>

      {/* ── Empty state ────────────────────────────────────────────── */}
      {filtered.length === 0 && (
        <Card>
          <CardContent>
            <Typography variant="body2" color="text.secondary">
              {events.length === 0
                ? 'No audit events yet — run the bot to populate logs/decisions.jsonl.'
                : 'No events match the current filters.'}
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* ── Results table ──────────────────────────────────────────── */}
      {filtered.length > 0 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 32 }} />
                <TableCell>Timestamp (UTC)</TableCell>
                <TableCell>Event</TableCell>
                <TableCell>Summary</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paged.map((e, idx) => {
                const globalIdx = page * rowsPerPage + idx;
                const color = eventColor(e, theme.palette);
                const expanded = expandedRow === globalIdx;
                return (
                  <>
                    <TableRow
                      key={`${globalIdx}-row`}
                      hover
                      onClick={() => setExpandedRow(expanded ? null : globalIdx)}
                      sx={{ cursor: 'pointer', '& > *': { borderBottom: 'unset' } }}
                    >
                      <TableCell>
                        <IconButton size="small">
                          {expanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                        </IconButton>
                      </TableCell>
                      <TableCell sx={{ fontFamily: MONO_FONT, whiteSpace: 'nowrap' }}>
                        {prettyTime(eventTimestamp(e))}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={e.event}
                          variant="outlined"
                          size="small"
                          sx={{ borderColor: color, color }}
                        />
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.8125rem' }}>
                        {eventSummary(e)}
                      </TableCell>
                    </TableRow>
                    <TableRow key={`${globalIdx}-detail`}>
                      <TableCell
                        colSpan={4}
                        sx={{ py: 0, borderBottom: expanded ? undefined : 'unset' }}
                      >
                        <Collapse in={expanded} timeout="auto" unmountOnExit>
                          <Box
                            sx={{
                              my: 1,
                              p: 1.5,
                              bgcolor: theme.palette.action.hover,
                              borderRadius: 1,
                              fontFamily: MONO_FONT,
                              fontSize: '0.75rem',
                              whiteSpace: 'pre',
                              overflow: 'auto',
                              maxHeight: 320,
                            }}
                            component="pre"
                          >
                            {JSON.stringify(e, null, 2)}
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </>
                );
              })}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            rowsPerPageOptions={[25, 50, 100, 250]}
            count={filtered.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            onRowsPerPageChange={e => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
          />
        </TableContainer>
      )}
    </Box>
  );
}

function prettyTime(s: string): string {
  if (!s) return '—';
  const m = s.match(/(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?/);
  if (!m) return s;
  return m[3] ? `${m[1]} ${m[2]}.${m[3].padEnd(3, '0').slice(0, 3)}` : `${m[1]} ${m[2]}`;
}
