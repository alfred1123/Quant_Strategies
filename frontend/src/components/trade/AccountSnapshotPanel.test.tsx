import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import AccountSnapshotPanel from './AccountSnapshotPanel';
import { useAccountSnapshot } from '../../api/trade';
import type { BrokerAccount } from '../../types/credentials';

vi.mock('../../api/trade', () => ({
  useAccountSnapshot: vi.fn(),
}));

const accounts = [
  {
    api_credential_id: 7,
    app_id: 34,
    label: 'bybit-main',
    api_key_masked: '****abcd',
    is_active_ind: 'Y',
  },
] as unknown as BrokerAccount[];

const appNameById = new Map([[34, 'Bybit']]);

function mockSnapshot(overrides: Record<string, unknown> = {}) {
  vi.mocked(useAccountSnapshot).mockReturnValue({
    data: {
      api_credential_id: 7,
      app_id: 34,
      paper: true,
      balances: [{ code: 'USDT', free: 900, used: 100, total: 1000 }],
      positions: [
        {
          symbol: 'BTCUSDT',
          unified_symbol: 'BTC/USDT:USDT',
          qty: 0.003,
          side: 'long',
          entry_price: 60000,
          mark_price: 61000,
          notional: 183,
          unrealized_pnl: 3,
          leverage: 10,
          liquidation_price: 54000,
        },
      ],
    },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useAccountSnapshot>);
}

function renderPanel(apiCredentialId: number | null = 7, tradingMode: 'paper' | 'live' = 'paper') {
  return render(
    <AccountSnapshotPanel
      apiCredentialId={apiCredentialId}
      tradingMode={tradingMode}
      accounts={accounts}
      appNameById={appNameById}
      onSelectAccount={vi.fn()}
    />,
  );
}

describe('AccountSnapshotPanel', () => {
  beforeEach(() => {
    vi.mocked(useAccountSnapshot).mockReset();
  });

  it('shows cash split into available, in use, and total', () => {
    mockSnapshot();
    renderPanel();

    expect(screen.getByText('USDT')).toBeInTheDocument();
    expect(screen.getByText('900.00')).toBeInTheDocument();
    expect(screen.getByText('1,000.00')).toBeInTheDocument();
  });

  it('shows the open position with its side and unrealised pnl', () => {
    mockSnapshot();
    renderPanel();

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('Long')).toBeInTheDocument();
    expect(screen.getByText('3.00')).toBeInTheDocument();
    expect(screen.getByText('10×')).toBeInTheDocument();
  });

  it('renders a short position as Short with an unsigned size', () => {
    mockSnapshot({
      data: {
        api_credential_id: 7,
        app_id: 34,
        paper: true,
        balances: [],
        positions: [
          {
            symbol: 'BTCUSDT',
            unified_symbol: null,
            qty: -0.002,
            side: 'short',
            entry_price: null,
            mark_price: null,
            notional: null,
            unrealized_pnl: null,
            leverage: null,
            liquidation_price: null,
          },
        ],
      },
    });
    renderPanel();

    expect(screen.getByText('Short')).toBeInTheDocument();
    expect(screen.getByText('0.002')).toBeInTheDocument();
  });

  it('says flat rather than showing an empty table', () => {
    mockSnapshot({
      data: {
        api_credential_id: 7,
        app_id: 34,
        paper: true,
        balances: [],
        positions: [],
      },
    });
    renderPanel();

    expect(screen.getByText(/Flat — no open positions/)).toBeInTheDocument();
  });

  it('labels which environment answered', () => {
    mockSnapshot();
    renderPanel(7, 'live');

    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('asks for an account instead of reading one when the toolbar is on all accounts', () => {
    mockSnapshot({ data: undefined });
    renderPanel(null);

    expect(screen.getByText(/Pick one account/)).toBeInTheDocument();
  });

  it('surfaces a broker error', () => {
    mockSnapshot({
      data: undefined,
      isError: true,
      error: new Error('authentication failed during fetch_balance'),
    });
    renderPanel();

    expect(screen.getByText(/authentication failed/)).toBeInTheDocument();
  });
});
