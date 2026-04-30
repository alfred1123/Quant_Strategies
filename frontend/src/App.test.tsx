import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme } from '@mui/material';
import type { ReactNode } from 'react';
import App from './App';
import * as authModule from './api/auth';

vi.mock('./api/auth', () => ({
  ME_QUERY_KEY: ['auth', 'me'],
  useMe: vi.fn(),
  useLogin: () => ({ mutate: vi.fn(), isPending: false }),
  useLogout: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('./pages/BacktestPage', () => ({
  default: () => <div data-testid="backtest-page">Backtest</div>,
}));

/**
 * App bundles its own BrowserRouter, so we only wrap with QueryClient +
 * ThemeProvider here (no extra router). BrowserRouter in happy-dom
 * defaults to "/" which is the root route.
 */
function renderApp(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const theme = createTheme({ palette: { mode: 'dark' } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={theme}>{ui}</ThemeProvider>
    </QueryClientProvider>,
  );
}

describe('App routing', () => {
  it('shows loading spinner when auth is loading', () => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof authModule.useMe>);

    renderApp(<App />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('shows LoginPage when not authenticated (redirects to /login)', () => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof authModule.useMe>);

    renderApp(<App />);
    expect(screen.getByText('Sign in to continue')).toBeInTheDocument();
  });

  it('shows BacktestPage when authenticated', () => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: { username: 'alice' },
      isLoading: false,
    } as unknown as ReturnType<typeof authModule.useMe>);

    renderApp(<App />);
    expect(screen.getByTestId('backtest-page')).toBeInTheDocument();
  });
});
