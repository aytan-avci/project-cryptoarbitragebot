import { createTheme, type ThemeOptions } from '@mui/material/styles';

// Custom palette extensions for domain-specific colors (DESIGN_LANGUAGE.md § 4).
declare module '@mui/material/styles' {
  interface Palette {
    custom: {
      pnl: { positive: string; negative: string; flat: string };
      order: {
        pending: string;
        submitted: string;
        partial: string;
        filled: string;
        cancelled: string;
        rejected: string;
        failed: string;
      };
      killSwitch: string;
    };
  }
  interface PaletteOptions {
    custom?: Palette['custom'];
  }
}

const sharedTypography: ThemeOptions['typography'] = {
  fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  // Mono fallback for tabular numerics (§ 5). Components opt in via `fontFamily`.
};

export const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1565C0' },
    secondary: { main: '#455A64' },
    error: { main: '#C62828' },
    warning: { main: '#EF6C00' },
    info: { main: '#0277BD' },
    success: { main: '#2E7D32' },
    background: { default: '#FAFAFA', paper: '#FFFFFF' },
    text: { primary: '#1A1A1A', secondary: '#5F6368' },
    custom: {
      pnl: { positive: '#1B5E20', negative: '#B71C1C', flat: '#5F6368' },
      order: {
        pending: '#5F6368',
        submitted: '#0277BD',
        partial: '#EF6C00',
        filled: '#1B5E20',
        cancelled: '#455A64',
        rejected: '#C62828',
        failed: '#880E4F',
      },
      killSwitch: '#C62828',
    },
  },
  typography: sharedTypography,
  components: {
    MuiTable: { defaultProps: { size: 'small' } }, // dense default (§ 8)
    MuiChip: { defaultProps: { size: 'small' } },
  },
});

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#64B5F6' },
    secondary: { main: '#90A4AE' },
    error: { main: '#EF5350' },
    warning: { main: '#FFB74D' },
    info: { main: '#4FC3F7' },
    success: { main: '#66BB6A' },
    background: { default: '#121212', paper: '#1E1E1E' },
    text: { primary: '#E8EAED', secondary: '#9AA0A6' },
    custom: {
      pnl: { positive: '#81C784', negative: '#E57373', flat: '#9AA0A6' },
      order: {
        pending: '#9AA0A6',
        submitted: '#4FC3F7',
        partial: '#FFB74D',
        filled: '#81C784',
        cancelled: '#90A4AE',
        rejected: '#EF5350',
        failed: '#F06292',
      },
      killSwitch: '#B71C1C',
    },
  },
  typography: sharedTypography,
  components: {
    MuiTable: { defaultProps: { size: 'small' } },
    MuiChip: { defaultProps: { size: 'small' } },
  },
});

export const MONO_FONT = '"Roboto Mono", "Menlo", "Consolas", monospace';
