import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route, Navigate } from 'react-router-dom';
import TradeLayout from './TradeLayout';
import TradeConfigPage from '../pages/trade/TradeConfigPage';
import TradeApplyPage from '../pages/trade/TradeApplyPage';
import { renderWithProviders } from '../test/wrapper';
import * as authModule from '../api/auth';

vi.mock('../api/auth', () => ({
  ME_QUERY_KEY: ['auth', 'me'],
  useMe: vi.fn(),
  useLogin: () => ({ mutate: vi.fn(), isPending: false }),
  useLogout: () => ({ mutate: vi.fn(), isPending: false }),
}));

function TradeRoutes() {
  return (
    <Routes>
      <Route path="/trade" element={<TradeLayout />}>
        <Route index element={<Navigate to="config" replace />} />
        <Route path="config" element={<TradeConfigPage />} />
        <Route path="apply" element={<TradeApplyPage />} />
      </Route>
    </Routes>
  );
}

describe('TradeLayout', () => {
  beforeEach(() => {
    vi.mocked(authModule.useMe).mockReturnValue({
      data: { username: 'alice' },
      isLoading: false,
    } as ReturnType<typeof authModule.useMe>);
  });

  it('shows Config stub at /trade/config', () => {
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/config'] });
    expect(screen.getByText(/Phase 1\.5/)).toBeInTheDocument();
    expect(screen.getByText('Execution log')).toBeInTheDocument();
  });

  it('navigates to Trade stub via sidebar', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/config'] });

    const sidebar = screen.getByRole('navigation', { name: 'Trade sections' });
    await user.click(within(sidebar).getByRole('link', { name: 'Trade' }));
    expect(screen.getByText(/Phase 1\.6 \/ 1\.7/)).toBeInTheDocument();
  });

  it('shows mode switch with Trade active at /trade/config', () => {
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/config'] });
    expect(screen.getByRole('group', { name: 'Application mode' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Trade mode' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Backtest mode' })).toHaveAttribute('href', '/backtest');
  });
});
