import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import ExecutionLogPanel from './ExecutionLogPanel';
import { renderWithProviders } from '../../test/wrapper';
import * as tradeModule from '../../api/trade';

vi.mock('../../api/trade', () => ({
  useExecutionEvents: vi.fn(),
  useTransactions: vi.fn(),
}));

vi.mock('../../trade/useTradeSession', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../trade/useTradeSession')>();
  return {
    ...actual,
    useTradeSessionFilters: () => ({
      matchesSession: () => true,
      credentialsNotLoaded: false,
    }),
  };
});

describe('ExecutionLogPanel', () => {
  beforeEach(() => {
    vi.mocked(tradeModule.useExecutionEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof tradeModule.useExecutionEvents>);
    vi.mocked(tradeModule.useTransactions).mockReturnValue({
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof tradeModule.useTransactions>);
  });

  it('shows empty state for attempts', () => {
    renderWithProviders(<ExecutionLogPanel />);
    expect(screen.getByText('Execution log')).toBeInTheDocument();
    expect(
      screen.getByText(/No order attempts yet/),
    ).toBeInTheDocument();
  });

  it('renders attempt rows', () => {
    vi.mocked(tradeModule.useExecutionEvents).mockReturnValue({
      data: [
        {
          execution_event_id: 'evt-1',
          deployment_id: 'dep-1',
          deployment_vid: 1,
          internal_cusip: 'btcusdt.crypto',
          api_credential_id: 1,
          app_id: 10,
          is_paper_ind: 'Y',
          signal_value: '1.2',
          position_qty: '0',
          buy_sell_cd: 'BUY',
          quantity: '0.01',
          vendor_order_id: 'ord-1',
          is_success_ind: 'Y',
          transact_at: '2026-08-29T10:00:00Z',
        },
      ],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof tradeModule.useExecutionEvents>);

    renderWithProviders(<ExecutionLogPanel />);
    expect(screen.getByText('btcusdt.crypto')).toBeInTheDocument();
    expect(screen.getByText('Attempts (1)')).toBeInTheDocument();
  });
});
