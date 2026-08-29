import { Box, CircularProgress, ThemeProvider, CssBaseline } from '@mui/material';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router';
import BacktestPage from './pages/BacktestPage';
import LoginPage from './pages/LoginPage';
import MarketDataPage from './pages/MarketDataPage';
import TradeLayout from './layouts/TradeLayout';
import TradeConfigPage from './pages/trade/TradeConfigPage';
import TradeApplyPage from './pages/trade/TradeApplyPage';
import ErrorBoundary from './components/ErrorBoundary';
import { useMe } from './api/auth';
import { theme } from './theme';

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
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/backtest';
    return <Navigate to={from} replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider theme={theme}>
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
            <Route path="/" element={<Navigate to="/backtest" replace />} />
            <Route
              path="/backtest"
              element={
                <RequireAuth>
                  <BacktestPage />
                </RequireAuth>
              }
            />
            <Route
              path="/market-data"
              element={
                <RequireAuth>
                  <MarketDataPage />
                </RequireAuth>
              }
            />
            <Route
              path="/trade"
              element={
                <RequireAuth>
                  <TradeLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="config" replace />} />
              <Route path="config" element={<TradeConfigPage />} />
              <Route path="apply" element={<TradeApplyPage />} />
            </Route>
            {/* Any unknown path → redirect to root (which checks auth) */}
            <Route path="*" element={<Navigate to="/backtest" replace />} />
          </Routes>
        </ErrorBoundary>
      </ThemeProvider>
    </BrowserRouter>
  );
}
