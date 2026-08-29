import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MarketDataPage from './MarketDataPage';
import { renderWithProviders } from '../test/wrapper';
import { useSubscribe, useSubscriptions } from '../api/marketData';
import { useApps, useTmIntervals } from '../api/refdata';
import { useMe } from '../api/auth';
import type { BarSubscriptionRow } from '../types/marketData';

vi.mock('../api/marketData');
vi.mock('../api/refdata', async () => {
  const actual = await vi.importActual<typeof import('../api/refdata')>('../api/refdata');
  return { ...actual, useApps: vi.fn(), useTmIntervals: vi.fn() };
});
vi.mock('../api/auth');
vi.mock('../components/market-data/SubscriptionDialog', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div>subscription dialog</div> : null),
}));
vi.mock('../components/market-data/BackfillDialog', () => ({
  default: ({ row }: { row: BarSubscriptionRow | null }) =>
    row ? <div>backfill dialog</div> : null,
}));

const ROW: BarSubscriptionRow = {
  bar_subscription_id: 'e6f1c0d2-0000-4000-8000-000000000001',
  bar_subscription_vid: 1,
  internal_cusip: 'btcusdt.crypto',
  tm_interval_id: 1,
  source_app_id: 34,
  is_enabled_ind: 'Y',
  backfill_from_ts: null,
  transact_from_ts: '2026-08-01T00:00:00Z',
  coverage: {
    first_bar: '2026-01-01T00:00:00Z',
    last_bar: '2026-08-01T00:00:00Z',
    gaps: 0,
    error: null,
  },
};

const mutateAsync = vi.fn();

function setup(rows: BarSubscriptionRow[] = [ROW]) {
  vi.mocked(useMe).mockReturnValue({ data: null } as never);
  vi.mocked(useSubscriptions).mockReturnValue({
    data: rows,
    isLoading: false,
    isError: false,
    error: null,
  } as never);
  vi.mocked(useSubscribe).mockReturnValue({ mutateAsync, isPending: false } as never);
  vi.mocked(useTmIntervals).mockReturnValue({
    data: [{ tm_interval_id: 1, name: 'DAILY', display_name: 'Daily' }],
  } as never);
  vi.mocked(useApps).mockReturnValue({
    data: [{ app_id: 34, display_name: 'Bybit', is_exchange_ind: 'Y' }],
  } as never);
  return renderWithProviders(<MarketDataPage />);
}

describe('MarketDataPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mutateAsync.mockResolvedValue(ROW);
  });

  it('names the venue and cadence rather than their ids', () => {
    setup();
    expect(screen.getByText('Bybit')).toBeInTheDocument();
    expect(screen.getByText('Daily')).toBeInTheDocument();
  });

  it('shows a continuous series as ready rather than merely subscribed', () => {
    setup();
    expect(screen.getByText('continuous')).toBeInTheDocument();
    expect(screen.getByText('2026-01-01 → 2026-08-01')).toBeInTheDocument();
  });

  it('flags a series with holes, because a backtest over it is not reproducible', () => {
    setup([{ ...ROW, coverage: { ...ROW.coverage, gaps: 4 } }]);
    expect(screen.getByText('4 gaps')).toBeInTheDocument();
  });

  it('separates "subscribed" from "has history"', () => {
    setup([
      {
        ...ROW,
        coverage: { first_bar: null, last_bar: null, gaps: null, error: null },
      },
    ]);
    expect(screen.getByText('nothing captured yet')).toBeInTheDocument();
  });

  it('keeps rendering when one venue cannot answer', () => {
    setup([
      {
        ...ROW,
        coverage: { first_bar: null, last_bar: null, gaps: null, error: 'venue gone' },
      },
    ]);
    expect(screen.getByText('unavailable')).toBeInTheDocument();
    expect(screen.getByText('btcusdt.crypto')).toBeInTheDocument();
  });

  it('warns that pausing stops the capture for everyone', async () => {
    // happy-dom has no window.confirm, so it is installed rather than spied on.
    const confirm = vi.fn().mockReturnValue(false);
    vi.stubGlobal('confirm', confirm);
    setup();

    await userEvent.click(screen.getByLabelText(/pause capture/i));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('everyone'));
    expect(mutateAsync).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('resumes without a confirmation, since resuming loses nothing', async () => {
    setup([{ ...ROW, is_enabled_ind: 'N' }]);

    await userEvent.click(screen.getByLabelText(/resume capture/i));

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        bar_subscription_id: ROW.bar_subscription_id,
        is_enabled_ind: 'Y',
      }),
    );
  });

  it('opens the backfill dialog for a row', async () => {
    setup();
    await userEvent.click(screen.getByLabelText(/backfill history/i));
    expect(screen.getByText('backfill dialog')).toBeInTheDocument();
  });

  it('tells the user why the list is empty rather than showing a bare table', () => {
    setup([]);
    expect(screen.getByText(/Nothing is being captured/i)).toBeInTheDocument();
  });
});
