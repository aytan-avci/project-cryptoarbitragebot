import { useEffect, useMemo, useState } from 'react';
import { CssBaseline, ThemeProvider } from '@mui/material';

import { KillSwitchBanner, Shell, TopBar } from './components/Layout';
import { Overview } from './components/Overview';
import { useAuditLog, useKillSwitch } from './dataModel';
import { darkTheme, lightTheme } from './theme';

type Mode = 'light' | 'dark';

function readSavedMode(): Mode {
  try {
    const v = localStorage.getItem('aa.theme');
    return v === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

export default function App() {
  const [mode, setMode] = useState<Mode>(readSavedMode);
  const theme = useMemo(() => (mode === 'dark' ? darkTheme : lightTheme), [mode]);
  const { events, loading, error } = useAuditLog(500);
  const killSwitch = useKillSwitch(2_000);

  useEffect(() => {
    try {
      localStorage.setItem('aa.theme', mode);
    } catch {
      // localStorage unavailable — accept and move on
    }
    document.title = killSwitch.engaged
      ? '[KILL] Arbitrage Agent — Operator Dashboard'
      : 'Arbitrage Agent — Operator Dashboard';
  }, [mode, killSwitch.engaged]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Shell
        topBar={
          <TopBar
            mode={mode}
            onToggleTheme={() => setMode(m => (m === 'dark' ? 'light' : 'dark'))}
            killSwitch={killSwitch}
          />
        }
      >
        <KillSwitchBanner killSwitch={killSwitch} />
        <Overview events={events} loading={loading} error={error} />
      </Shell>
    </ThemeProvider>
  );
}
