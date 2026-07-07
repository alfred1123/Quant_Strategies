import { createTheme } from '@mui/material';

/**
 * AlgoDaemon dark theme — single source of design tokens.
 *
 * Deep-navy surfaces with a cool blue accent; softened corners, no
 * shouting-caps buttons, and consistent hairline borders instead of shadows.
 */

const FONT_STACK = [
  'Inter',
  'ui-sans-serif',
  'system-ui',
  '-apple-system',
  '"Segoe UI"',
  'Roboto',
  'Helvetica',
  'Arial',
  'sans-serif',
].join(', ');

export const MONO_FONT_STACK = [
  '"JetBrains Mono"',
  'ui-monospace',
  '"SF Mono"',
  'Menlo',
  'Consolas',
  'monospace',
].join(', ');

export const theme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0d0f1a',
      paper: '#131929',
    },
    primary: {
      main: '#4d8ef0',
      light: '#7fadf5',
      dark: '#2f6fd0',
    },
    success: { main: '#34c98e' },
    error: { main: '#f0616d' },
    warning: { main: '#e8a33d' },
    divider: '#1e2d45',
    text: {
      primary: '#e6ebf5',
      secondary: '#93a1bc',
    },
  },
  shape: {
    borderRadius: 10,
  },
  typography: {
    fontFamily: FONT_STACK,
    h5: { fontWeight: 700, letterSpacing: '-0.01em' },
    h6: { fontWeight: 700, letterSpacing: '-0.01em' },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        '*::-webkit-scrollbar': { width: 10, height: 10 },
        '*::-webkit-scrollbar-thumb': {
          backgroundColor: '#2a3a58',
          borderRadius: 8,
          border: '2px solid #0d0f1a',
        },
        '*::-webkit-scrollbar-track': { background: 'transparent' },
        body: {
          scrollbarColor: '#2a3a58 transparent', // Firefox
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 8 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        outlined: { backgroundImage: 'none' },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          fontSize: '0.875rem',
          minHeight: 44,
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        root: { minHeight: 44 },
        indicator: { height: 3, borderRadius: '3px 3px 0 0' },
      },
    },
    MuiTooltip: {
      defaultProps: { arrow: true },
    },
  },
});
