import {
  Box,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Typography,
  useTheme,
} from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import RemoveIcon from '@mui/icons-material/Remove';

import { MONO_FONT } from '../theme';
import {
  fills as filterFills,
  joinDecisionsToOpps,
  latestSnapshotsByVenue,
  summarize,
} from '../dataModel';
import type { LogEvent } from '../types';

interface OverviewProps {
  events: LogEvent[];
  loading: boolean;
  error: string | null;
}

const ORDER_STATES = [
  'pending',
  'submitted',
  'partial',
  'filled',
  'cancelled',
  'rejected',
  'failed',
] as const;

export function Overview({ events, loading, error }: OverviewProps) {
  const theme = useTheme();
  const summary = summarize(events);
  const fills = filterFills(events);
  const opps = joinDecisionsToOpps(events);
  const liveSnapshots = Array.from(latestSnapshotsByVenue(events).values());

  if (error) {
    return (
      <Card>
        <CardContent>
          <Typography color="error" variant="body1" sx={{ fontWeight: 500 }}>
            Fetch failed — {error}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Is the Vite dev server still running? Is{' '}
            <code>logs/decisions.jsonl</code> accessible at the project root?
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

  if (events.length === 0) {
    return (
      <Card>
        <CardContent sx={{ textAlign: 'center', py: 4 }}>
          <Typography variant="h6" gutterBottom>
            No data yet
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Run <code>python -m arbitrage_agent</code> from the project root.
            The dashboard polls <code>logs/decisions.jsonl</code> every 500 ms and
            will refresh as soon as the file appears.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // ── KPI tiles ─────────────────────────────────────────────────────────
  const pnlColor =
    summary.pnlDirection === 'positive'
      ? theme.palette.custom.pnl.positive
      : summary.pnlDirection === 'negative'
        ? theme.palette.custom.pnl.negative
        : theme.palette.custom.pnl.flat;
  const PnlGlyph =
    summary.pnlDirection === 'positive'
      ? TrendingUpIcon
      : summary.pnlDirection === 'negative'
        ? TrendingDownIcon
        : RemoveIcon;

  return (
    <>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', lg: 'repeat(4, 1fr)' },
          gap: 2,
        }}
      >
        <KpiCard label="Realised P&L (session)">
          <Stack direction="row" alignItems="center" spacing={1}>
            <PnlGlyph sx={{ color: pnlColor }} />
            <Typography
              variant="h4"
              sx={{ fontFamily: MONO_FONT, color: pnlColor, fontWeight: 500 }}
            >
              {summary.pnlDirection === 'negative' ? '−' : summary.pnlDirection === 'positive' ? '+' : '±'}
              ${Math.abs(summary.pnlUsd).toFixed(3)}
            </Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            from {summary.fillsCount} fill{summary.fillsCount === 1 ? '' : 's'}
          </Typography>
        </KpiCard>

        <KpiCard label="Opportunities">
          <Typography variant="h4" sx={{ fontFamily: MONO_FONT, fontWeight: 500 }}>
            {summary.opportunitiesCount}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            from current audit log
          </Typography>
        </KpiCard>

        <KpiCard label="Approval Rate">
          <Typography variant="h4" sx={{ fontFamily: MONO_FONT, fontWeight: 500 }}>
            {(summary.approvalRate * 100).toFixed(0)}%
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {summary.approvedCount} approved · {summary.rejectedCount} rejected
          </Typography>
        </KpiCard>

        <KpiCard label="Active Adapters">
          <Typography variant="h4" sx={{ fontFamily: MONO_FONT, fontWeight: 500 }}>
            {summary.uniqueExchanges}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            exchanges seen in fills
          </Typography>
        </KpiCard>
      </Box>

      {/* ── Live Snapshots (Faz 7a) ──────────────────────────────────── */}
      {liveSnapshots.length > 0 && (
        <Section
          title="Live Prices"
          subtitle={`top of book per venue · ${liveSnapshots.length} venue${
            liveSnapshots.length === 1 ? '' : 's'
          } seen`}
        >
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: '1fr',
                sm: 'repeat(2, 1fr)',
                lg: 'repeat(4, 1fr)',
              },
              gap: 2,
            }}
          >
            {liveSnapshots.map(snap => {
              const spread = parseFloat(snap.ask) - parseFloat(snap.bid);
              const isLive = snap.exchange === 'binance' || snap.exchange === 'bybit';
              return (
                <Card variant="outlined" key={`${snap.exchange}-${snap.symbol}`}>
                  <CardContent>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="center"
                    >
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          textTransform: 'uppercase',
                          letterSpacing: 0.5,
                          fontWeight: 500,
                        }}
                      >
                        {snap.exchange} · {snap.symbol}
                      </Typography>
                      <Chip
                        label={isLive ? 'live' : 'paper'}
                        variant="outlined"
                        sx={{
                          borderColor: isLive
                            ? theme.palette.custom.order.filled
                            : theme.palette.custom.order.pending,
                          color: isLive
                            ? theme.palette.custom.order.filled
                            : theme.palette.custom.order.pending,
                        }}
                      />
                    </Stack>
                    <Stack
                      direction="row"
                      spacing={2}
                      sx={{ mt: 1, fontFamily: MONO_FONT }}
                    >
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          bid
                        </Typography>
                        <Typography variant="h6" sx={{ fontFamily: MONO_FONT }}>
                          {parseFloat(snap.bid).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          ask
                        </Typography>
                        <Typography variant="h6" sx={{ fontFamily: MONO_FONT }}>
                          {parseFloat(snap.ask).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </Typography>
                      </Box>
                    </Stack>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: 1, display: 'block' }}
                    >
                      spread:{' '}
                      <span style={{ fontFamily: MONO_FONT }}>
                        ${spread.toFixed(2)}
                      </span>{' '}
                      · {prettyTime(snap.timestamp_utc)}
                    </Typography>
                  </CardContent>
                </Card>
              );
            })}
          </Box>
        </Section>
      )}

      {/* ── Recent Opportunities ─────────────────────────────────────── */}
      <Section title="Recent Opportunities" subtitle={`${opps.length} total in current log`}>
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Detected (UTC)</TableCell>
                <TableCell>Strategy</TableCell>
                <TableCell align="right">Legs</TableCell>
                <TableCell align="right">Expected Net (USD)</TableCell>
                <TableCell align="right">Confidence</TableCell>
                <TableCell>Decision</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {opps
                .slice()
                .reverse()
                .slice(0, 25)
                .map(o => {
                  const net = parseFloat(o.expected_net_profit_usd);
                  const sign = net > 0 ? '+' : net < 0 ? '−' : '±';
                  const pnlDir =
                    net > 0
                      ? theme.palette.custom.pnl.positive
                      : net < 0
                        ? theme.palette.custom.pnl.negative
                        : theme.palette.custom.pnl.flat;
                  const Glyph =
                    net > 0 ? TrendingUpIcon : net < 0 ? TrendingDownIcon : RemoveIcon;
                  const decisionLabel = o.decision
                    ? o.decision.approved
                      ? `approved · ${o.decision.reason}`
                      : `rejected · ${o.decision.reason}`
                    : 'pending';
                  const decisionColor = !o.decision
                    ? theme.palette.custom.order.pending
                    : o.decision.approved
                      ? theme.palette.custom.order.filled
                      : theme.palette.custom.order.rejected;
                  return (
                    <TableRow key={o.id} hover>
                      <TableCell sx={{ fontFamily: MONO_FONT, whiteSpace: 'nowrap' }}>
                        {prettyTime(o.detected_at)}
                      </TableCell>
                      <TableCell>{o.strategy}</TableCell>
                      <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                        {o.legs.length}
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{ fontFamily: MONO_FONT, color: pnlDir, whiteSpace: 'nowrap' }}
                      >
                        <Glyph fontSize="inherit" sx={{ verticalAlign: 'middle', mr: 0.5 }} />
                        {sign}${Math.abs(net).toFixed(3)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                        {o.confidence.toFixed(2)}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={decisionLabel}
                          variant="outlined"
                          sx={{ borderColor: decisionColor, color: decisionColor }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      {/* ── Recent Fills ──────────────────────────────────────────────── */}
      <Section title="Recent Fills" subtitle={`${fills.length} total in current log`}>
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Timestamp (UTC)</TableCell>
                <TableCell>Exchange</TableCell>
                <TableCell>Symbol</TableCell>
                <TableCell>Side</TableCell>
                <TableCell align="right">Price</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Fee (USD)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {fills
                .slice()
                .reverse()
                .slice(0, 25)
                .map((f, i) => {
                  const sideColor =
                    f.side === 'buy'
                      ? theme.palette.custom.order.filled
                      : theme.palette.custom.order.rejected;
                  return (
                    <TableRow key={`${f.opportunity_id}-${i}`} hover>
                      <TableCell sx={{ fontFamily: MONO_FONT, whiteSpace: 'nowrap' }}>
                        {prettyTime(f.timestamp_utc)}
                      </TableCell>
                      <TableCell>{f.exchange}</TableCell>
                      <TableCell>{f.symbol}</TableCell>
                      <TableCell>
                        <Chip
                          label={f.side}
                          variant="outlined"
                          sx={{ borderColor: sideColor, color: sideColor }}
                        />
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                        {parseFloat(f.price).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                        {f.volume}
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                        {parseFloat(f.fee).toFixed(3)}
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      {/* ── Order lifecycle chip key ──────────────────────────────────── */}
      <Section
        title="Order Lifecycle State Reference"
        subtitle="cosmetic key — Faz 7 wires real lifecycle to the Fills table"
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {ORDER_STATES.map(state => {
            const color =
              theme.palette.custom.order[state as keyof typeof theme.palette.custom.order];
            return (
              <Chip
                key={state}
                label={state}
                variant="outlined"
                sx={{ borderColor: color, color }}
              />
            );
          })}
        </Stack>
      </Section>
    </>
  );
}

// ─── Small helpers ──────────────────────────────────────────────────────

function KpiCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 500 }}
        >
          {label}
        </Typography>
        <Box sx={{ mt: 0.5 }}>{children}</Box>
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 500, mb: 1 }}>
        {title}
        {subtitle && (
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ ml: 1 }}
          >
            {subtitle}
          </Typography>
        )}
      </Typography>
      {children}
    </Box>
  );
}

function prettyTime(s: string): string {
  // Bot emits "2026-05-21 09:36:59.274071+00:00". Show HH:MM:SS.fff portion.
  const m = s.match(/(\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?/);
  if (!m) return s;
  return m[2] ? `${m[1]}.${m[2].padEnd(3, '0').slice(0, 3)}` : m[1];
}
