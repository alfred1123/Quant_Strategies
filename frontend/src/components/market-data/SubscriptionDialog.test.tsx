import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SubscriptionDialog from './SubscriptionDialog';
import { useSubscribe, useVenueDepth } from '../../api/marketData';
import { useProducts } from '../../api/inst';
import { useExchangeApps, useTmIntervals } from '../../api/refdata';
import type { VenueDepth } from '../../types/marketData';

vi.mock('../../api/marketData', () => ({
  useSubscribe: vi.fn(),
  useVenueDepth: vi.fn(),
}));
vi.mock('../../api/inst', () => ({ useProducts: vi.fn() }));
// Real intervalLabel — only the data hooks are stubbed.
vi.mock('../../api/refdata', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/refdata')>()),
  useExchangeApps: vi.fn(),
  useTmIntervals: vi.fn(),
}));

const BYBIT_DAILY: VenueDepth = {
  earliest: '2020-03-25T00:00:00Z',
  bars_available: 2349,
  max_backfill_bars: 10_000,
};

let subscribeMutate: ReturnType<typeof vi.fn>;

// `null` means the venue gave no answer. Not `undefined`, which a default
// parameter would quietly replace with the happy-path fixture.
function setup({
  depth = BYBIT_DAILY,
  isFetching = false,
}: { depth?: VenueDepth | null; isFetching?: boolean } = {}) {
  subscribeMutate = vi.fn().mockResolvedValue({});
  vi.mocked(useSubscribe).mockReturnValue({
    mutateAsync: subscribeMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSubscribe>);
  vi.mocked(useVenueDepth).mockReturnValue({
    data: depth ?? undefined,
    isFetching,
  } as unknown as ReturnType<typeof useVenueDepth>);
  vi.mocked(useProducts).mockReturnValue({
    data: [
      { internal_cusip: 'btcusdt.crypto', display_nm: 'Bitcoin' },
      { internal_cusip: 'ethusdt.crypto', display_nm: 'Ethereum' },
      { internal_cusip: 'solusdt.crypto', display_nm: 'Solana' },
    ],
  } as unknown as ReturnType<typeof useProducts>);
  vi.mocked(useTmIntervals).mockReturnValue({
    data: [
      {
        tm_interval_id: 1,
        name: 'DAILY',
        display_name: 'Daily',
        period_length: '1 day, 0:00:00',
        description: null,
      },
    ],
  } as unknown as ReturnType<typeof useTmIntervals>);
  vi.mocked(useExchangeApps).mockReturnValue({
    data: [{ app_id: 34, display_name: 'Bybit' }],
  } as unknown as ReturnType<typeof useExchangeApps>);

  render(<SubscriptionDialog open onClose={vi.fn()} onSuccess={vi.fn()} />);
}

/** The date input renders without an accessible label role, so reach for it. */
function targetInput(): HTMLInputElement {
  return document.querySelector('input[type="date"]') as HTMLInputElement;
}

const productBox = () => screen.getByRole('combobox', { name: 'Product' });

/** Choose product, interval and venue — the three that identify a series. */
async function chooseSeries() {
  // Product is a search box; the other two are short enough to stay dropdowns.
  await userEvent.click(productBox());
  await userEvent.click(await screen.findByRole('option', { name: /Bitcoin/ }));

  for (const [label, option] of [
    ['Bar interval', 'Daily'],
    ['Venue', 'Bybit'],
  ]) {
    await userEvent.click(screen.getByRole('combobox', { name: label }));
    await userEvent.click(await screen.findByRole('option', { name: option }));
  }
}

describe('SubscriptionDialog product search', () => {
  beforeEach(() => vi.clearAllMocks());

  it('narrows the list as you type, rather than making you scroll it', async () => {
    // The options are the whole instrument universe; a plain dropdown does not
    // scale past the first screenful.
    setup();

    await userEvent.type(productBox(), 'ether');

    expect(await screen.findByText('Ethereum')).toBeInTheDocument();
    expect(screen.queryByText('Bitcoin')).not.toBeInTheDocument();
  });

  it('searches on the cusip too, not just the display name', async () => {
    setup();

    await userEvent.type(productBox(), 'solusdt');

    expect(await screen.findByText('Solana')).toBeInTheDocument();
    expect(screen.queryByText('Bitcoin')).not.toBeInTheDocument();
  });

  it('shows the cusip beside the name, since the name alone is ambiguous', async () => {
    setup();

    await userEvent.click(productBox());

    expect(await screen.findByText('btcusdt.crypto')).toBeInTheDocument();
  });

  it('says so when nothing matches instead of showing an empty list', async () => {
    setup();

    await userEvent.type(productBox(), 'nonesuch');

    expect(await screen.findByText('No options')).toBeInTheDocument();
  });

  it('submits the cusip of the product picked from the search', async () => {
    setup();
    await chooseSeries();

    await userEvent.click(screen.getByRole('button', { name: 'Subscribe' }));

    await waitFor(() => expect(subscribeMutate).toHaveBeenCalled());
    expect(subscribeMutate.mock.calls[0][0].internal_cusip).toBe('btcusdt.crypto');
  });
});

describe('SubscriptionDialog capture target', () => {
  beforeEach(() => vi.clearAllMocks());

  it('defaults the target to the oldest bar the venue serves', async () => {
    // The whole point: nobody should have to guess how far back Bybit goes.
    // Left to a typed date, 2017 looks as reasonable as 2020 and is wrong.
    setup();

    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));
  });

  it('says how many bars that is, so the interval cost is visible', () => {
    setup();

    expect(
      screen.getByText(/serves bars from 2020-03-25 — 2,349 of them/),
    ).toBeInTheDocument();
    expect(screen.getByText(/One backfill covers all of it/)).toBeInTheDocument();
  });

  it('warns when the venue holds more than one fill can take', () => {
    setup({
      depth: { ...BYBIT_DAILY, bars_available: 56_361 },
    });

    expect(screen.getByText(/several passes/)).toBeInTheDocument();
  });

  it('flags a target the venue can never reach', async () => {
    setup();
    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));

    await userEvent.clear(targetInput());
    await userEvent.type(targetInput(), '2017-01-01');

    // Unreachable is not a gap awaiting backfill — it is history that does not
    // exist, and the row would show a shortfall nothing could ever close.
    expect(
      await screen.findByText(/nothing before it can ever be captured/),
    ).toBeInTheDocument();
  });

  it('keeps a date the user chose rather than overwriting it', async () => {
    setup();
    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));

    await userEvent.clear(targetInput());
    await userEvent.type(targetInput(), '2022-06-01');

    expect(targetInput().value).toBe('2022-06-01');
  });

  it('says it is asking while the venue has not answered', () => {
    setup({ depth: null, isFetching: true });

    expect(screen.getByText(/Asking the venue how far back it goes/)).toBeInTheDocument();
  });

  it('submits the venue floor as the target', async () => {
    setup();
    await chooseSeries();
    await waitFor(() => expect(targetInput().value).toBe('2020-03-25'));

    await userEvent.click(screen.getByRole('button', { name: 'Subscribe' }));

    await waitFor(() => expect(subscribeMutate).toHaveBeenCalled());
    const sent = subscribeMutate.mock.calls[0][0];
    expect(sent.backfill_from_ts).toContain('2020-03-25');
  });
});
