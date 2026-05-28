import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route, Navigate } from 'react-router-dom';
import TradeLayout from './TradeLayout';
import TradeConfigPage from '../pages/trade/TradeConfigPage';
import TradeApplyPage from '../pages/trade/TradeApplyPage';
import { renderWithProviders } from '../test/wrapper';
import * as authModule from '../api/auth';
import * as tradeModule from '../api/trade';
import * as credentialsModule from '../api/credentials';
import * as refdataModule from '../api/refdata';

vi.mock('../api/auth', () => ({
  ME_QUERY_KEY: ['auth', 'me'],
  useMe: vi.fn(),
  useLogin: () => ({ mutate: vi.fn(), isPending: false }),
  useLogout: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('../api/trade', () => ({
  DEPLOYMENTS_QUERY_KEY: ['trade', 'deployments'],
  useDeployments: vi.fn(),
  useCreateDeployment: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('../api/credentials', () => ({
  CREDENTIALS_QUERY_KEY: ['credentials'],
  useBrokerAccounts: vi.fn(),
}));

vi.mock('../api/refdata', () => ({
  useExchangeApps: vi.fn(),
  useApps: vi.fn(),
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
    vi.mocked(tradeModule.useDeployments).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof tradeModule.useDeployments>);
    vi.mocked(credentialsModule.useBrokerAccounts).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof credentialsModule.useBrokerAccounts>);
    const appRows = [
      { app_id: 1, name: 'yahoo', display_name: 'Yahoo Finance', class_name: 'Yahoo', is_exchange_ind: 'N' as const, description: null },
      { app_id: 2, name: 'bybit', display_name: 'Bybit', class_name: 'Bybit', is_exchange_ind: 'Y' as const, description: null },
      { app_id: 3, name: 'futu', display_name: 'Futu OpenD', class_name: 'FutuOpenD', is_exchange_ind: 'Y' as const, description: null },
    ];
    vi.mocked(refdataModule.useApps).mockReturnValue({
      data: appRows,
      isLoading: false,
    } as unknown as ReturnType<typeof refdataModule.useApps>);
    vi.mocked(refdataModule.useExchangeApps).mockReturnValue({
      data: appRows.filter(a => a.is_exchange_ind === 'Y'),
      isLoading: false,
    } as unknown as ReturnType<typeof refdataModule.useExchangeApps>);
  });

  it('shows accounts table on Config', () => {
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/config'] });
    expect(screen.getByText('Exchange accounts')).toBeInTheDocument();
    expect(screen.getByText(/No broker accounts registered/)).toBeInTheDocument();
    expect(screen.getByLabelText('Trading mode')).toBeInTheDocument();
  });

  it('navigates to Trade page via sidebar', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/config'] });

    const sidebar = screen.getByRole('navigation', { name: 'Trade sections' });
    await user.click(within(sidebar).getByRole('link', { name: 'Trade' }));
    expect(screen.getByText('Strategy picker (Phase 1.6)')).toBeInTheDocument();
    expect(screen.getByText('Deployments')).toBeInTheDocument();
  });

  it('toggles paper and live mode', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/apply'] });

    await user.click(screen.getByRole('button', { name: 'Live trading' }));
    expect(screen.getByText('Live mode')).toBeInTheDocument();
  });

  it('shows mode switch with Trade active at /trade/config', () => {
    renderWithProviders(<TradeRoutes />, { initialEntries: ['/trade/config'] });
    expect(screen.getByRole('group', { name: 'Application mode' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Trade mode' })).toHaveAttribute('aria-current', 'page');
  });
});
