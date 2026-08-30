import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BackfillDialog from './BackfillDialog';
import { useBackfill, useBackfillPlan, useVenueDepth } from '../../api/marketData';
import type {
  BackfillPlan,
  BarSubscriptionRow,
  VenueDepth,
} from '../../types/marketData';

vi.mock('../../api/marketData', () => ({
  useBackfill: vi.fn(),
  useBackfillPlan: vi.fn(),
  useVenueDepth: vi.fn(),
}));

const BYBIT_DAILY: VenueDepth = {
  earliest: '2020-03-25T00:00:00Z',
  bars_available: 2349,
  max_backfill_bars: 10_000,
};

/** One pass finishes the job. */
const ONE_PASS: BackfillPlan = {
  start: '2020-03-25T00:00:00Z',
  end: '2026-08-29T00:00:00Z',
  bars: 2349,
  passes_remaining: 1,
  target: '2020-03-25T00:00:00Z',
};

/** An hourly series: the window stops where coverage begins, not at now. */
const FIRST_OF_MANY: BackfillPlan = {
  start: '2024-08-11T00:00:00Z',
  end: '2025-09-30T23:00:00Z',
  bars: 10_000,
  passes_remaining: 5,
  target: '2020-03-25T00:00:00Z',
};

const NOTHING_LEFT: BackfillPlan = {
  start: null,
  end: null,
  bars: 0,
  passes_remaining: 0,
  target: '2020-03-25T00:00:00Z',
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
  plan = ONE_PASS,
  row = subscription(),
}: {
  depth?: VenueDepth | null;
  plan?: BackfillPlan | null;
  row?: BarSubscriptionRow;
} = {}) {
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
  vi.mocked(useBackfillPlan).mockReturnValue({
    data: plan ?? undefined,
    isFetching: false,
  } as unknown as ReturnType<typeof useBackfillPlan>);

  render(<BackfillDialog row={row} onClose={vi.fn()} />);
}

function targetInput(): HTMLInputElement {
  return document.querySelector('input[type="date"]') as HTMLInputElement;
}

describe('BackfillDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('asks only how far back, never for an end', () => {
    // The target is the decision; the window each pass covers is arithmetic.
    setup();

    expect(document.querySelectorAll('input[type="date"]')).toHaveLength(1);
    expect(screen.queryByLabelText('To')).not.toBeInTheDocument();
  });

  it('defaults the target to the oldest bar the venue serves', async () => {
    setup();

    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));
  });

  it('prefers the venue floor over a target the subscription could never meet', async () => {
    // The row asks for 2017, which Bybit has never had. Honouring that would
    // send a start the venue must reject rather than the deepest real one.
    setup({ row: subscription({ backfill_from_ts: '2017-01-01T00:00:00Z' }) });

    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));
  });

  it('lets a narrower target override the default', async () => {
    setup();
    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));

    await userEvent.clear(targetInput());
    await userEvent.type(targetInput(), '2024-01-01');

    expect(targetInput().value).toBe('2024-01-01');
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

    expect(targetInput().value).toBe('2023-05-01');
  });
});

/**
 * The behaviour the ceiling used to make impossible.
 *
 * Every fill ran to the last closed bar, so an hourly series already holding a
 * year had no start that both reached further back and stayed under the limit
 * — the nearer the start, the more of the span was bars already stored.
 */
describe('BackfillDialog — history arrives one pass at a time', () => {
  beforeEach(() => vi.clearAllMocks());

  it('submits the planned window, not a fill to now', async () => {
    setup({ plan: FIRST_OF_MANY });

    await userEvent.click(screen.getByRole('button', { name: 'Backfill' }));

    await waitFor(() => expect(fillMutate).toHaveBeenCalled());
    expect(fillMutate.mock.calls[0][0].start).toBe('2024-08-11T00:00:00Z');
    expect(fillMutate.mock.calls[0][0].end).toBe('2025-09-30T23:00:00Z');
  });

  it('says what this pass covers and how many remain', async () => {
    setup({ plan: FIRST_OF_MANY });

    expect(
      await screen.findByText(/2024-08-11 to 2025-09-30 — 10,000 bar\(s\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/5 passes to reach 2020-03-25/)).toBeInTheDocument();
  });

  it('explains that clicking again continues where this stopped', async () => {
    setup({ plan: FIRST_OF_MANY });

    expect(
      await screen.findByText(/next pass picks up\s+where this leaves off/),
    ).toBeInTheDocument();
  });

  it('does not talk about repeating when one pass finishes it', () => {
    setup({ plan: ONE_PASS });

    expect(screen.queryByText(/picks up/)).not.toBeInTheDocument();
    expect(screen.getByText(/reaching 2020-03-25/)).toBeInTheDocument();
  });

  it('offers nothing to run once the target is reached', async () => {
    setup({ plan: NOTHING_LEFT });

    expect(
      await screen.findByText(/already reaches the target/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Backfill' })).toBeDisabled();
  });

  it('waits for the plan before offering the button', () => {
    setup({ plan: null });

    expect(screen.getByRole('button', { name: 'Backfill' })).toBeDisabled();
    expect(screen.getByText(/Working out what is left/)).toBeInTheDocument();
  });

  it('plans against the target the user chose, not the row default', async () => {
    setup();
    await userEvent.clear(targetInput());
    await userEvent.type(targetInput(), '2024-01-01');

    const lastCall = vi.mocked(useBackfillPlan).mock.calls.at(-1);
    expect(lastCall?.[1]).toBe('2024-01-01');
  });
});
