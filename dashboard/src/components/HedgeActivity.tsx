// Faz (C) — Hedger activity panel.
//
// Renders the last N `hedger_result` audit events: status chip, counter
// venue/side/qty, remaining exposure, plain-English reason. The
// happy-path `no_imbalance` outcomes are filtered out so the operator
// only sees events that required intervention.

import {
  Box,
  Card,
  CardContent,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  useTheme,
  type Theme,
} from '@mui/material';

import { MONO_FONT } from '../theme';
import { hedgerResults } from '../dataModel';
import type { HedgeStatus, LogEvent } from '../types';

interface HedgeActivityProps {
  events: LogEvent[];
}

const STATUS_LABEL: Record<HedgeStatus, string> = {
  no_imbalance: 'no imbalance',
  filled: 'filled',
  partial: 'partial',
  aborted_slippage: 'aborted (slippage)',
  no_market_data: 'no market data',
  placement_failed: 'placement failed',
};

function statusColor(status: HedgeStatus, palette: Theme['palette']): string {
  switch (status) {
    case 'filled':
      return palette.custom.order.filled;
    case 'partial':
      return palette.custom.order.partial;
    case 'aborted_slippage':
    case 'placement_failed':
      return palette.custom.order.rejected;
    case 'no_market_data':
      return palette.custom.order.cancelled;
    case 'no_imbalance':
    default:
      return palette.custom.order.pending;
  }
}

export function HedgeActivity({ events }: HedgeActivityProps) {
  const theme = useTheme();
  // Skip happy-path events; operator only cares when the hedger
  // actually intervened.
  const active = hedgerResults(events).filter(h => h.status !== 'no_imbalance');

  if (active.length === 0) {
    return (
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 500, mb: 1 }}>
          Hedge Activity{' '}
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ ml: 1 }}
          >
            no neutralisations in current log
          </Typography>
        </Typography>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="body2" color="text.secondary">
              All executed opportunities filled cleanly. The hedger will appear
              here the moment a leg comes back partial / rejected / failed.
            </Typography>
          </CardContent>
        </Card>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 500, mb: 1 }}>
        Hedge Activity{' '}
        <Typography
          component="span"
          variant="caption"
          color="text.secondary"
          sx={{ ml: 1 }}
        >
          {active.length} neutralisation{active.length === 1 ? '' : 's'} in
          current log
        </Typography>
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Opportunity</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Counter-leg</TableCell>
              <TableCell align="right">Counter Qty</TableCell>
              <TableCell align="right">Limit Price</TableCell>
              <TableCell align="right">Remaining</TableCell>
              <TableCell>Reason</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {active
              .slice()
              .reverse()
              .slice(0, 25)
              .map((h, i) => {
                const color = statusColor(h.status, theme.palette);
                const remaining = parseFloat(h.remaining_exposure);
                const remainingColor =
                  Math.abs(remaining) < 1e-12
                    ? theme.palette.custom.pnl.flat
                    : theme.palette.custom.order.rejected;
                const counter = h.counter_leg;
                return (
                  <TableRow key={`${h.opportunity_id}-${i}`} hover>
                    <TableCell
                      sx={{ fontFamily: MONO_FONT, whiteSpace: 'nowrap' }}
                    >
                      {h.opportunity_id.slice(0, 8)}…
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={STATUS_LABEL[h.status]}
                        variant="outlined"
                        sx={{ borderColor: color, color }}
                      />
                    </TableCell>
                    <TableCell>
                      {counter ? (
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="body2">
                            {counter.exchange}
                          </Typography>
                          <Chip
                            size="small"
                            label={counter.side}
                            variant="outlined"
                            sx={{
                              borderColor:
                                counter.side === 'buy'
                                  ? theme.palette.custom.order.filled
                                  : theme.palette.custom.order.rejected,
                              color:
                                counter.side === 'buy'
                                  ? theme.palette.custom.order.filled
                                  : theme.palette.custom.order.rejected,
                            }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {counter.symbol}
                          </Typography>
                        </Stack>
                      ) : (
                        <Typography variant="caption" color="text.secondary">
                          —
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                      {counter ? counter.quantity : '—'}
                    </TableCell>
                    <TableCell align="right" sx={{ fontFamily: MONO_FONT }}>
                      {counter
                        ? parseFloat(counter.limit_price).toLocaleString(
                            undefined,
                            { minimumFractionDigits: 2, maximumFractionDigits: 2 },
                          )
                        : '—'}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ fontFamily: MONO_FONT, color: remainingColor }}
                    >
                      {h.remaining_exposure}
                    </TableCell>
                    <TableCell
                      sx={{ maxWidth: 360, fontSize: '0.8125rem' }}
                    >
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}
                      >
                        {h.reason}
                      </Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
