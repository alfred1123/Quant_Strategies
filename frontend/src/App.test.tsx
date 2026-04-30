import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import App from './App';
import { renderWithProviders } from './test/wrapper';
import * as authModule from './api/auth';

vi.mock('./api/auth', () => ({
  ME_QUERY_KEY: ['auth', 'me'],
  useMe: vi.fn(),
  useLogin: () => ({ mutate: vi.fn(), isPending: false }),
  useLogout: () => ({ mutate: vi.fn() }),
}));

vi.mock('./pages/BacktestPage', () => ({
  default: ({ currentUser }: { currentUser: { username: string } }) => (
    <div data-testid="backtest-page">Backtest for {currentUser.username}</div>
  ),
}));

describe('App / Gate', () => {
  it('shows loading spinner when auth is loading', () => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof authModule.useMe>);

    renderWithProviders(<App />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('shows LoginPage when not authenticated', () => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof authModule.useMe>);

    renderWithProviders(<App />);
    expect(screen.getByText('Sign in to continue')).toBeInTheDocument();
  });

  it('shows BacktestPage when authenticated', () => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: { username: 'alice' },
      isLoading: false,
    } as unknown as ReturnType<typeof authModule.useMe>);

    renderWithProviders(<App />);
    expect(screen.getByTestId('backtest-page')).toBeInTheDocument();
    expect(screen.getByText('Backtest for alice')).toBeInTheDocument();
  });
});
