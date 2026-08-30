import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BackfillDialog from './BackfillDialog';
import { useBackfill, useVenueDepth } from '../../api/marketData';
import type { BarSubscriptionRow, VenueDepth } from '../../types/marketData';

vi.mock('../../api/marketData', () => ({
  useBackfill: vi.fn(),
  useVenueDepth: vi.fn(),
}));

const BYBIT_DAILY: VenueDepth = {
  earliest: '2020-03-25T00:00:00Z',
  bars_available: 2349,
  max_backfill_bars: 10_000,
};

function subscription(overrides: Partial<BarSubscriptionRow> = {}): BarSubscriptionRow {
  return {
    bar_subscription_id: 'a1b2c3d4-0000-4000-8000-000000000001',
    bar_subscription_vid: 1,
    internal_cusip: 'btcusdt.crypto',
    vendor_symbol: 'BTCUSDT',
    tm_interval_id: 1,
    source_app_id: 34,
    is_enabled_ind: 'Y',
    backfill_from_ts: '2017-01-01T00:00:00Z',
    transact_from_ts: '2026-08-29T00:00:00Z',
    coverage: { first_bar: null, last_bar: null, gaps: null, error: null },
    ...overrides,
  };
}

let fillMutate: ReturnType<typeof vi.fn>;

// `null` means the venue gave no answer. Not `undefined`, which a default
// parameter would quietly replace with the happy-path fixture.
function setup({
  depth = BYBIT_DAILY,
  row = subscription(),
}: { depth?: VenueDepth | null; row?: BarSubscriptionRow } = {}) {
  fillMutate = vi.fn().mockResolvedValue({
    start: '2020-03-25T00:00:00Z',
    end: '2026-08-29T00:00:00Z',
    expected: 2349,
    missing: 0,
    inserted: 0,
    unfilled: [],
    is_continuous: true,
  });
  vi.mocked(useBackfill).mockReturnValue({
    mutateAsync: fillMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useBackfill>);
  vi.mocked(useVenueDepth).mockReturnValue({
    data: depth ?? undefined,
    isFetching: false,
  } as unknown as ReturnType<typeof useVenueDepth>);

  render(<BackfillDialog row={row} onClose={vi.fn()} />);
}

function fromInput(): HTMLInputElement {
  return document.querySelector('input[type="date"]') as HTMLInputElement;
}

describe('BackfillDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('has no "to" field, because the end was never a real choice', () => {
    // A fill always runs to the last closed bar: the forming bar cannot be
    // stored and nothing beyond it exists to fetch.
    setup();

    expect(document.querySelectorAll('input[type="date"]')).toHaveLength(1);
    expect(screen.queryByLabelText('To')).not.toBeInTheDocument();
  });

  it('defaults the start to the oldest bar the venue serves', async () => {
    setup();

    await waitFor(() => expect(fromInput().value).toBe('2020-03-25'));
  });

  it('prefers the venue floor over a target the subscription could never meet', async () => {
    // The row asks for 2017, which Bybit has never had. Honouring that would
    // send a start the venue must reject rather than the deepest real one.
    setup({ row: subscription({ backfill_from_ts: '2017-01-01T00:00:00Z' }) });

    await waitFor(() => expect(fromInput().value).toBe('2020-03-25'));
  });

  it('sends no end date at all', async () => {
    setup();
    await waitFor(() => expect(fromInput().value).toBe('2020-03-25'));

    await userEvent.click(screen.getByRole('button', { name: 'Backfill' }));

    await waitFor(() => expect(fillMutate).toHaveBeenCalled());
    expect(fillMutate.mock.calls[0][0].end).toBeNull();
    expect(fillMutate.mock.calls[0][0].start).toContain('2020-03-25');
  });

  it('warns before the click when the venue holds more than one pass can store', async () => {
    setup({ depth: { ...BYBIT_DAILY, bars_available: 56_361 } });

    expect(
      await screen.findByText(/more than the 10,000 one\s+pass can store/),
    ).toBeInTheDocument();
  });

  it('does not warn when it all fits in one pass', async () => {
    setup();
    await waitFor(() => expect(fromInput().value).toBe('2020-03-25'));

    expect(screen.queryByText(/pass can store/)).not.toBeInTheDocument();
  });

  it('lets a narrower start override the default', async () => {
    setup();
    await waitFor(() => expect(fromInput().value).toBe('2020-03-25'));

    await userEvent.clear(fromInput());
    await userEvent.type(fromInput(), '2024-01-01');

    expect(fromInput().value).toBe('2024-01-01');
  });

  it('falls back to what is already stored when the venue cannot be asked', () => {
    setup({
      depth: null,
      row: subscription({
        backfill_from_ts: null,
        coverage: {
          first_bar: '2023-05-01T00:00:00Z', last_bar: null, gaps: null, error: null,
        },
      }),
    });

    expect(fromInput().value).toBe('2023-05-01');
  });
});
