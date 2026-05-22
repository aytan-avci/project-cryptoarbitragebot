import { useMemo } from 'react';
import {
  AppBar,
  Box,
  Chip,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Toolbar,
  Typography,
  useTheme,
  Tooltip,
} from '@mui/material';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import DashboardIcon from '@mui/icons-material/Dashboard';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import ShieldIcon from '@mui/icons-material/Shield';
import ReceiptIcon from '@mui/icons-material/Receipt';
import ArticleIcon from '@mui/icons-material/Article';
import SettingsIcon from '@mui/icons-material/Settings';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import BlockIcon from '@mui/icons-material/Block';

import type { KillSwitchState } from '../types';

const DRAWER_WIDTH = 240;

interface TopBarProps {
  mode: 'light' | 'dark';
  onToggleTheme: () => void;
  killSwitch: KillSwitchState;
}

export function TopBar({ mode, onToggleTheme, killSwitch }: TopBarProps) {
  const theme = useTheme();
  const engaged = killSwitch.engaged;

  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={{
        zIndex: t => t.zIndex.drawer + 1,
        bgcolor: engaged ? theme.palette.custom.killSwitch : 'background.paper',
        color: engaged ? '#FFFFFF' : 'text.primary',
        borderBottom: 1,
        borderColor: 'divider',
        transition: 'background-color 200ms ease-out',
      }}
    >
      <Toolbar variant="dense" sx={{ gap: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
          Arbitrage Agent
        </Typography>
        <Typography variant="caption" sx={{ opacity: 0.7 }}>
          paper · v0.0.1
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Tooltip
          title={
            engaged
              ? `Engaged: ${killSwitch.reason ?? 'unknown'} at ${killSwitch.engaged_at_utc ?? '?'}`
              : 'Read-only — engage via CLI for now (Faz 7 wires the toggle)'
          }
        >
          <Chip
            icon={engaged ? <BlockIcon /> : <CheckCircleIcon />}
            label={engaged ? 'KILL-SWITCH ENGAGED' : 'Kill-switch: OFF'}
            color={engaged ? 'default' : 'success'}
            variant={engaged ? 'filled' : 'outlined'}
            sx={
              engaged
                ? { bgcolor: 'rgba(0,0,0,0.3)', color: '#FFFFFF', '& .MuiChip-icon': { color: '#FFFFFF' } }
                : {}
            }
          />
        </Tooltip>
        <IconButton size="small" onClick={onToggleTheme} sx={{ color: 'inherit' }}>
          {mode === 'dark' ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
        </IconButton>
      </Toolbar>
    </AppBar>
  );
}

const NAV_ITEMS = [
  { label: 'Overview', icon: DashboardIcon, active: true },
  { label: 'Opportunities', icon: TrendingUpIcon, active: false },
  { label: 'Risk Decisions', icon: ShieldIcon, active: false },
  { label: 'Fills', icon: ReceiptIcon, active: false },
  { label: 'Audit Log', icon: ArticleIcon, active: false },
  { label: 'Settings', icon: SettingsIcon, active: false },
];

export function LeftRail() {
  const items = useMemo(() => NAV_ITEMS, []);
  return (
    <Drawer
      variant="permanent"
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
          borderRight: 1,
          borderColor: 'divider',
        },
      }}
    >
      <Toolbar variant="dense" />
      <List dense>
        {items.map(({ label, icon: Icon, active }) => (
          <ListItem key={label} disablePadding>
            <ListItemButton selected={active}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Icon fontSize="small" />
              </ListItemIcon>
              <ListItemText primary={label} primaryTypographyProps={{ variant: 'body2' }} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Drawer>
  );
}

interface KillSwitchBannerProps {
  killSwitch: KillSwitchState;
}

export function KillSwitchBanner({ killSwitch }: KillSwitchBannerProps) {
  const theme = useTheme();
  if (!killSwitch.engaged) return null;
  return (
    <Box
      sx={{
        bgcolor: theme.palette.custom.killSwitch,
        color: '#FFFFFF',
        p: 2,
        mb: 2,
        borderRadius: 1,
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
      }}
    >
      <BlockIcon />
      <Box>
        <Typography variant="body1" sx={{ fontWeight: 600 }}>
          KILL-SWITCH ENGAGED
        </Typography>
        <Typography variant="caption" sx={{ opacity: 0.9 }}>
          {killSwitch.reason ?? 'no reason recorded'} ·{' '}
          {killSwitch.engaged_at_utc
            ? `since ${killSwitch.engaged_at_utc}`
            : 'time unknown'}{' '}
          · operator action required to reset.
        </Typography>
      </Box>
    </Box>
  );
}

interface ShellProps {
  topBar: React.ReactNode;
  children: React.ReactNode;
}

export function Shell({ topBar, children }: ShellProps) {
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      {topBar}
      <LeftRail />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          maxWidth: { xl: 1536 },
          mx: 'auto',
          width: '100%',
        }}
      >
        <Toolbar variant="dense" />
        <Stack spacing={3}>{children}</Stack>
      </Box>
    </Box>
  );
}
