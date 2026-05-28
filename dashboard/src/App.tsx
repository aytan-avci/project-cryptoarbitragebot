import { useEffect, useMemo, useState } from 'react';
import { CssBaseline, ThemeProvider } from '@mui/material';

import { AuditLogPage } from './components/AuditLogPage';
import { KillSwitchBanner, Shell, TopBar, type PageKey } from './components/Layout';
import { HedgeActivity } from './components/HedgeActivity';
import { Overview } from './components/Overview';
import { RuntimeStatus } from './components/RuntimeStatus';
import { SecurityStatus } from './components/SecurityStatus';
import {
  useAuditLog,
  useKillSwitch,
  useRuntimeStatus,
  useTestnetEvidence,
} from './dataModel';
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

function readSavedPage(): PageKey {
  try {
    const v = localStorage.getItem('aa.page');
    return v === 'audit-log' ? 'audit-log' : 'overview';
  } catch {
    return 'overview';
  }
}

export default function App() {
  const [mode, setMode] = useState<Mode>(readSavedMode);
  const [page, setPage] = useState<PageKey>(readSavedPage);
  const theme = useMemo(() => (mode === 'dark' ? darkTheme : lightTheme), [mode]);
  const { events, loading, error } = useAuditLog(500);
  const killSwitch = useKillSwitch(2_000);
  const testnetEvidence = useTestnetEvidence(5_000);
  const runtimeStatus = useRuntimeStatus(2_000);

  useEffect(() => {
    try {
      localStorage.setItem('aa.theme', mode);
    } catch {
      // localStorage unavailable — accept and move on
    }
  }, [mode]);

  useEffect(() => {
    try {
      localStorage.setItem('aa.page', page);
    } catch {
      // localStorage unavailable — accept and move on
    }
  }, [page]);

  useEffect(() => {
    document.title = killSwitch.engaged
      ? '[KILL] Arbitrage Agent — Operator Dashboard'
      : 'Arbitrage Agent — Operator Dashboard';
  }, [killSwitch.engaged]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Shell
        currentPage={page}
        onSelectPage={setPage}
        topBar={
          <TopBar
            mode={mode}
            onToggleTheme={() => setMode(m => (m === 'dark' ? 'light' : 'dark'))}
            killSwitch={killSwitch}
          />
        }
      >
        <KillSwitchBanner killSwitch={killSwitch} />
        {page === 'overview' ? (
          <>
            <RuntimeStatus status={runtimeStatus} />
            <Overview events={events} loading={loading} error={error} />
            <HedgeActivity events={events} />
            <SecurityStatus evidence={testnetEvidence} />
          </>
        ) : (
          <AuditLogPage events={events} loading={loading} error={error} />
        )}
      </Shell>
    </ThemeProvider>
  );
}
