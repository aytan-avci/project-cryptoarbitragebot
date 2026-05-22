// Faz (C) — Security status panel.
//
// Renders the S7 mainnet probation gate state:
//   * days observed / 30 required
//   * eligibility chip (eligible / probationary / no evidence)
//   * first / last seen + venue list
// Sourced from `logs/testnet_evidence.json` (polled separately from
// the audit log because cadence is daily-ish, not per-iteration).

import {
  Box,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Stack,
  Typography,
  useTheme,
} from '@mui/material';

import { MONO_FONT } from '../theme';
import { summarizeTestnetEvidence } from '../dataModel';
import type { TestnetEvidence } from '../types';

interface SecurityStatusProps {
  evidence: TestnetEvidence;
}

function formatUtc(s: string | null): string {
  if (!s) return '—';
  // S7 evidence uses ISO-8601 ('2026-05-22T19:28:58.561109+00:00').
  // Show the YYYY-MM-DD HH:MM portion in mono so dates line up.
  const m = s.match(/(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : s;
}

export function SecurityStatus({ evidence }: SecurityStatusProps) {
  const theme = useTheme();
  const s7 = summarizeTestnetEvidence(evidence);

  const progress = Math.min(100, (s7.daysObserved / s7.required) * 100);
  const eligibleColor = s7.eligible
    ? theme.palette.custom.order.filled
    : s7.hasEvidence
      ? theme.palette.custom.order.partial
      : theme.palette.custom.order.rejected;
  const chipLabel = s7.eligible
    ? 'mainnet-eligible'
    : s7.hasEvidence
      ? 'probationary'
      : 'no evidence';

  const venueList = s7.venues.length > 0 ? s7.venues.join(', ') : '—';

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 500, mb: 1 }}>
        Security Status{' '}
        <Typography
          component="span"
          variant="caption"
          color="text.secondary"
          sx={{ ml: 1 }}
        >
          S7 — 30-day testnet probation
        </Typography>
      </Typography>

      <Card variant="outlined">
        <CardContent>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="flex-start"
            spacing={2}
            sx={{ flexWrap: 'wrap' }}
          >
            <Box sx={{ flex: 1, minWidth: 220 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  textTransform: 'uppercase',
                  letterSpacing: 0.5,
                  fontWeight: 500,
                }}
              >
                Probation progress
              </Typography>
              <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mt: 0.5 }}>
                <Typography
                  variant="h4"
                  sx={{ fontFamily: MONO_FONT, fontWeight: 500 }}
                >
                  {s7.daysObserved}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  / {s7.required} days
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={progress}
                sx={{
                  mt: 1,
                  height: 6,
                  borderRadius: 1,
                  backgroundColor: theme.palette.action.disabledBackground,
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: eligibleColor,
                  },
                }}
              />
            </Box>

            <Box sx={{ flex: 1, minWidth: 220 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  textTransform: 'uppercase',
                  letterSpacing: 0.5,
                  fontWeight: 500,
                }}
              >
                Status
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Chip
                  label={chipLabel}
                  variant="outlined"
                  sx={{ borderColor: eligibleColor, color: eligibleColor }}
                />
              </Box>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 1, display: 'block' }}
              >
                {s7.eligible
                  ? 'Mainnet+live transitions are permitted by the S7 gate.'
                  : s7.hasEvidence
                    ? `${s7.required - s7.daysObserved} day${
                        s7.required - s7.daysObserved === 1 ? '' : 's'
                      } remaining before mainnet is unlocked.`
                    : 'No successful testnet auth has been recorded. Mainnet+live is refused at startup.'}
              </Typography>
            </Box>
          </Stack>

          <Stack
            direction="row"
            spacing={4}
            sx={{ mt: 2, flexWrap: 'wrap' }}
          >
            <Box>
              <Typography variant="caption" color="text.secondary">
                first seen
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: MONO_FONT, whiteSpace: 'nowrap' }}
              >
                {formatUtc(s7.firstSeenUtc)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                last seen
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: MONO_FONT, whiteSpace: 'nowrap' }}
              >
                {formatUtc(s7.lastSeenUtc)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                venues
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: MONO_FONT }}
              >
                {venueList}
              </Typography>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
