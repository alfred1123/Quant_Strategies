import { Box, CircularProgress, ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import BacktestPage from './pages/BacktestPage';
import LoginPage from './pages/LoginPage';
import ErrorBoundary from './components/ErrorBoundary';
import { useMe } from './api/auth';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0d0f1a',
      paper: '#131929',
    },
    primary: {
      main: '#4d8ef0',
    },
    divider: '#1e2d45',
  },
});

/**
 * Top-level route guard (login.md §9.1).
 *
 * Single mount-time `GET /auth/me` call:
 *   - loading → centered spinner
 *   - null    → <LoginPage />
 *   - user    → <BacktestPage />
 *
 * The axios 401 interceptor mutates the same query, so a session expiring
 * mid-use immediately demotes the SPA back to the login screen.
 */
function Gate() {
  const me = useMe();

  if (me.isLoading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }
  if (!me.data) return <LoginPage />;
  return <BacktestPage currentUser={me.data} />;
}

export default function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <ErrorBoundary>
        <Gate />
      </ErrorBoundary>
    </ThemeProvider>
  );
}
