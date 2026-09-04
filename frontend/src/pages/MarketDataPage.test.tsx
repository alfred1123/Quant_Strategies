import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
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
  vendor_symbol: 'BTCUSDT',
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

const PAUSED: BarSubscriptionRow = {
  ...ROW,
  bar_subscription_id: 'e6f1c0d2-0000-4000-8000-000000000002',
  internal_cusip: 'ethusdt.crypto',
  vendor_symbol: 'ETHUSDT',
  is_enabled_ind: 'N',
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

const capturingTable = () => screen.getByRole('table', { name: 'Capturing series' });
const pausedTable = () => screen.getByRole('table', { name: 'Paused series' });
const searchBox = () => screen.getByPlaceholderText(/Search by product/);

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

  it('separates a finished capture from a merely hole-free one', () => {
    // The bybit hourly series: the target is the venue's floor at 10:00, and
    // the store has reached it. Ten bars sit between midnight and that floor
    // and never existed, so there is nothing left to fetch — "continuous"
    // reads as a backfill somebody forgot to run.
    setup([
      {
        ...ROW,
        backfill_from_ts: '2020-03-25T10:00:00Z',
        coverage: { ...ROW.coverage, first_bar: '2020-03-25T10:00:00Z' },
      },
    ]);
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.queryByText('continuous')).not.toBeInTheDocument();
  });

  it('still says continuous while a capture is short of its target', () => {
    setup([
      {
        ...ROW,
        backfill_from_ts: '2020-03-25T10:00:00Z',
        coverage: { ...ROW.coverage, first_bar: '2026-01-01T00:00:00Z' },
      },
    ]);
    expect(screen.getByText('continuous')).toBeInTheDocument();
    expect(screen.queryByText('completed')).not.toBeInTheDocument();
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

describe('MarketDataPage paused series', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mutateAsync.mockResolvedValue(ROW);
  });

  it('keeps paused series out of the capturing list', () => {
    // "What is accruing right now" is the operational question, and a status
    // column makes the reader filter by eye on every visit.
    setup([ROW, PAUSED]);

    const capturing = capturingTable();
    expect(within(capturing).getByText('btcusdt.crypto')).toBeInTheDocument();
    expect(within(capturing).queryByText('ethusdt.crypto')).not.toBeInTheDocument();
    expect(screen.getByText('Capturing (1)')).toBeInTheDocument();
  });

  it('lists paused series separately, with their own count', () => {
    setup([ROW, PAUSED]);

    expect(within(pausedTable()).getByText('ethusdt.crypto')).toBeInTheDocument();
    expect(screen.getByText('Paused (1)')).toBeInTheDocument();
  });

  it('hides the paused section entirely when nothing is paused', () => {
    setup([ROW]);

    expect(screen.queryByRole('table', { name: 'Paused series' })).not.toBeInTheDocument();
  });

  it('says what being paused costs, since the gap is not recoverable later', () => {
    setup([ROW, PAUSED]);

    expect(screen.getByText(/only recoverable as far/i)).toBeInTheDocument();
  });
});

describe('MarketDataPage product identity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mutateAsync.mockResolvedValue(ROW);
  });

  it('shows the ticker the venue prints beside our identifier', () => {
    // `btcusdt.crypto` cannot be looked up on an exchange, so on its own it is
    // unverifiable by the person deciding whether the right series is captured.
    setup();

    expect(screen.getByText('btcusdt.crypto')).toBeInTheDocument();
    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
  });

  it('flags a product the venue no longer maps', () => {
    // Capture is broken, and the list is where somebody would look to find out.
    setup([{ ...ROW, vendor_symbol: null }]);

    expect(screen.getByText('not listed on this venue')).toBeInTheDocument();
  });
});

describe('MarketDataPage search', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mutateAsync.mockResolvedValue(ROW);
  });

  it('filters on the internal cusip', async () => {
    setup([ROW, PAUSED]);

    await userEvent.type(searchBox(), 'ethusdt');

    expect(screen.queryByText('btcusdt.crypto')).not.toBeInTheDocument();
    expect(screen.getByText('ethusdt.crypto')).toBeInTheDocument();
  });

  it('filters on the vendor symbol too', async () => {
    // Nobody reliably remembers which of the two identifiers they know.
    setup([ROW, PAUSED]);

    await userEvent.type(searchBox(), 'ETHUSDT');

    expect(screen.queryByText('btcusdt.crypto')).not.toBeInTheDocument();
    expect(screen.getByText('ethusdt.crypto')).toBeInTheDocument();
  });

  it('says how many rows the search is hiding', async () => {
    setup([ROW, PAUSED]);

    await userEvent.type(searchBox(), 'ethusdt');

    expect(screen.getByText('1 series hidden by the search.')).toBeInTheDocument();
  });

  it('says so when a search matches nothing rather than looking empty', async () => {
    setup([ROW]);

    await userEvent.type(searchBox(), 'zzz');

    expect(
      screen.getByText('No capturing series matches that search.'),
    ).toBeInTheDocument();
  });
});

/**
 * "Continuous" only speaks about holes inside what is stored, so a series a
 * month into a six-year target rendered exactly as green as a finished one.
 */
describe('MarketDataPage distance from the target', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mutateAsync.mockResolvedValue(ROW);
  });

  it('says how far short of the target the capture still is', () => {
    setup([
      {
        ...ROW,
        backfill_from_ts: '2020-03-25T00:00:00Z',
        coverage: { ...ROW.coverage, first_bar: '2025-10-01T00:00:00Z' },
      },
    ]);

    expect(screen.getByText('2,016 days short')).toBeInTheDocument();
  });

  it('stays quiet once the target is reached', () => {
    setup([
      {
        ...ROW,
        backfill_from_ts: '2020-03-25T00:00:00Z',
        coverage: { ...ROW.coverage, first_bar: '2020-03-25T00:00:00Z' },
      },
    ]);

    expect(screen.queryByText(/days short/)).not.toBeInTheDocument();
  });

  it('does not call a capture reaching further back than asked a shortfall', () => {
    setup([
      {
        ...ROW,
        backfill_from_ts: '2024-01-01T00:00:00Z',
        coverage: { ...ROW.coverage, first_bar: '2020-03-25T00:00:00Z' },
      },
    ]);

    expect(screen.queryByText(/days short/)).not.toBeInTheDocument();
  });

  it('says nothing when no target was ever set', () => {
    setup([{ ...ROW, backfill_from_ts: null }]);

    expect(screen.queryByText(/days short/)).not.toBeInTheDocument();
  });

  it('says nothing when there is no capture to measure against', () => {
    setup([
      {
        ...ROW,
        backfill_from_ts: '2020-03-25T00:00:00Z',
        coverage: { first_bar: null, last_bar: null, gaps: null, error: null },
      },
    ]);

    expect(screen.queryByText(/days short/)).not.toBeInTheDocument();
  });
});
