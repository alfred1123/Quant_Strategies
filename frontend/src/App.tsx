import { Box, CircularProgress, ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
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

function FullPageSpinner() {
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <CircularProgress />
    </Box>
  );
}

/**
 * Wrapper that protects a route behind authentication.
 * While the auth check is in-flight it shows a spinner; once resolved,
 * unauthenticated visitors are redirected to `/login`.
 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const location = useLocation();

  if (me.isLoading) return <FullPageSpinner />;
  if (!me.data) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

/**
 * Wrapper for the login route. Already-authenticated users are bounced
 * back to wherever they came from (or `/` by default).
 */
function GuestOnly({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const location = useLocation();

  if (me.isLoading) return <FullPageSpinner />;

  if (me.data) {
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/';
    return <Navigate to={from} replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <ErrorBoundary>
          <Routes>
            <Route
              path="/login"
              element={
                <GuestOnly>
                  <LoginPage />
                </GuestOnly>
              }
            />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <BacktestPage />
                </RequireAuth>
              }
            />
            {/* Any unknown path → redirect to root (which checks auth) */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </ThemeProvider>
    </BrowserRouter>
  );
}
