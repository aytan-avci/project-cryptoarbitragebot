// Faz 8 — Runtime status panel (read-only).
//
// Reads logs/runtime_status.json (written by the bot) and shows
// operational state: run mode, strategy, notification config, and
// whether the loop is alive. Pure read-only — secrets never reach the
// browser because the bot writes only booleans + non-secret values.

import {
  Box,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography,
  useTheme,
  type Theme,
} from '@mui/material';
import CircleIcon from '@mui/icons-material/Circle';

import { MONO_FONT } from '../theme';
import type { RuntimeStatus as RuntimeStatusData } from '../types';

interface RuntimeStatusProps {
  status: RuntimeStatusData;
}

function freshnessSeconds(lastUpdatedUtc?: string): number | null {
  if (!lastUpdatedUtc) return null;
  const t = Date.parse(lastUpdatedUtc);
  if (!Number.isFinite(t)) return null;
  return Math.max(0, (Date.now() - t) / 1000);
}

export function RuntimeStatus({ status }: RuntimeStatusProps) {
  const theme = useTheme();
  const hasData = Object.keys(status).length > 0;

  const age = freshnessSeconds(status.last_updated_utc);
  // "Live" if the status file was refreshed within the last 15s.
  const live = age !== null && age <= 15;
  const liveColor = live
    ? theme.palette.custom.order.filled
    : theme.palette.custom.order.pending;

  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 500, mb: 1 }}>
        Runtime Status{' '}
        <Typography
          component="span"
          variant="caption"
          color="text.secondary"
          sx={{ ml: 1 }}
        >
          bot process + notification config
        </Typography>
      </Typography>

      <Card variant="outlined">
        <CardContent>
          {!hasData ? (
            <Typography variant="body2" color="text.secondary">
              No runtime status yet — start the bot
              (<code>python -m arbitrage_agent</code>). It writes
              <code> logs/runtime_status.json</code> each iteration.
            </Typography>
          ) : (
            <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }}>
              <StatusItem label="Process">
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <CircleIcon sx={{ fontSize: 12, color: liveColor }} />
                  <Typography variant="body2">
                    {live ? 'live' : 'stale'}
                    {age !== null && (
                      <Typography
                        component="span"
                        variant="caption"
                        color="text.secondary"
                        sx={{ ml: 0.5 }}
                      >
                        ({age < 60 ? `${age.toFixed(0)}s` : `${(age / 60).toFixed(0)}m`} ago)
                      </Typography>
                    )}
                  </Typography>
                </Stack>
              </StatusItem>

              <StatusItem label="Mode">
                <Chip
                  size="small"
                  label={`${status.mode ?? '—'} · ${status.loop_mode ?? '—'}`}
                  variant="outlined"
                  sx={{
                    borderColor:
                      status.mode === 'live'
                        ? theme.palette.custom.order.filled
                        : theme.palette.custom.order.pending,
                    color:
                      status.mode === 'live'
                        ? theme.palette.custom.order.filled
                        : theme.palette.custom.order.pending,
                  }}
                />
              </StatusItem>

              <StatusItem label="Strategy">
                <Typography variant="body2" sx={{ fontFamily: MONO_FONT }}>
                  {status.strategy ?? '—'}
                </Typography>
              </StatusItem>

              <StatusItem label="Email alerts">
                <NotifyChip on={status.email_configured} theme={theme} />
              </StatusItem>

              <StatusItem label="Telegram alerts">
                <NotifyChip on={status.telegram_configured} theme={theme} />
              </StatusItem>

              <StatusItem label="Iterations">
                <Typography variant="body2" sx={{ fontFamily: MONO_FONT }}>
                  {status.iterations ?? 0}
                </Typography>
              </StatusItem>
            </Stack>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}

function StatusItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: 'block', textTransform: 'uppercase', letterSpacing: 0.5 }}
      >
        {label}
      </Typography>
      <Box sx={{ mt: 0.5 }}>{children}</Box>
    </Box>
  );
}

function NotifyChip({ on, theme }: { on?: boolean; theme: Theme }) {
  return (
    <Chip
      size="small"
      label={on ? 'configured' : 'off'}
      variant="outlined"
      sx={{
        borderColor: on
          ? theme.palette.custom.order.filled
          : theme.palette.custom.order.cancelled,
        color: on
          ? theme.palette.custom.order.filled
          : theme.palette.custom.order.cancelled,
      }}
    />
  );
}
