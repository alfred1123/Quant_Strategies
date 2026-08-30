import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SubscriptionDialog from './SubscriptionDialog';
import { useSubscribe, useVenueDepth } from '../../api/marketData';
import { useAppProducts } from '../../api/inst';
import { useExchangeApps, useTmIntervals } from '../../api/refdata';
import type { VenueDepth } from '../../types/marketData';

vi.mock('../../api/marketData', () => ({
  useSubscribe: vi.fn(),
  useVenueDepth: vi.fn(),
}));
vi.mock('../../api/inst', () => ({ useAppProducts: vi.fn() }));
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
const LISTED = [
  { internal_cusip: 'btcusdt.crypto', display_nm: 'Bitcoin', vendor_symbol: 'BTCUSDT' },
  { internal_cusip: 'ethusdt.crypto', display_nm: 'Ethereum', vendor_symbol: 'ETHUSDT' },
  { internal_cusip: 'solusdt.crypto', display_nm: 'Solana', vendor_symbol: 'SOLUSDT' },
];

function setup({
  depth = BYBIT_DAILY,
  isFetching = false,
  listed = LISTED,
  productsFetching = false,
}: {
  depth?: VenueDepth | null;
  isFetching?: boolean;
  listed?: typeof LISTED;
  productsFetching?: boolean;
} = {}) {
  subscribeMutate = vi.fn().mockResolvedValue({});
  vi.mocked(useSubscribe).mockReturnValue({
    mutateAsync: subscribeMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSubscribe>);
  vi.mocked(useVenueDepth).mockReturnValue({
    data: depth ?? undefined,
    isFetching,
  } as unknown as ReturnType<typeof useVenueDepth>);
  vi.mocked(useAppProducts).mockReturnValue({
    data: listed,
    isFetching: productsFetching,
  } as unknown as ReturnType<typeof useAppProducts>);
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
    data: [
      { app_id: 34, display_name: 'Bybit' },
      { app_id: 35, display_name: 'Binance' },
    ],
  } as unknown as ReturnType<typeof useExchangeApps>);

  render(<SubscriptionDialog open onClose={vi.fn()} onSuccess={vi.fn()} />);
}

/** The date input renders without an accessible label role, so reach for it. */
function targetInput(): HTMLInputElement {
  return document.querySelector('input[type="date"]') as HTMLInputElement;
}

const productBox = () => screen.getByRole('combobox', { name: 'Product' });

/** Pick from one of the two plain dropdowns. */
async function pick(label: string, option: string) {
  await userEvent.click(screen.getByRole('combobox', { name: label }));
  await userEvent.click(await screen.findByRole('option', { name: option }));
}

/** The venue gates the product list, so it has to be chosen first. */
const chooseVenue = () => pick('Venue', 'Bybit');

/** Choose venue, product and interval — the three that identify a series. */
async function chooseSeries() {
  await chooseVenue();
  // Product is a search box; the other two are short enough to stay dropdowns.
  await userEvent.click(productBox());
  await userEvent.click(await screen.findByRole('option', { name: /Bitcoin/ }));
  await pick('Bar interval', 'Daily');
}

describe('SubscriptionDialog product scoping', () => {
  beforeEach(() => vi.clearAllMocks());

  it('will not offer products before a venue narrows them', async () => {
    // The unscoped list is every instrument the platform knows, most of which
    // the chosen exchange has never listed. That is not a searchable set.
    setup();

    expect(productBox()).toBeDisabled();
    expect(
      screen.getByText(/Pick a venue first — it decides which products exist here/),
    ).toBeInTheDocument();
  });

  it('asks only for the products the chosen venue lists', async () => {
    setup();

    await chooseVenue();

    expect(vi.mocked(useAppProducts)).toHaveBeenLastCalledWith(34);
  });

  it('says how many the venue lists, so the search has a known size', async () => {
    setup();

    await chooseVenue();

    expect(
      await screen.findByText('3 products listed on this venue.'),
    ).toBeInTheDocument();
  });

  it('names the fix when a venue lists nothing at all', async () => {
    setup({ listed: [] });

    await chooseVenue();

    expect(await screen.findByText(/INST.PRODUCT_XREF/)).toBeInTheDocument();
  });

  it('drops the chosen product when the venue changes under it', async () => {
    // The same product is not listed everywhere; keeping it would submit a
    // pair that has no xref.
    setup();
    await chooseSeries();
    expect(productBox()).toHaveValue('Bitcoin (btcusdt.crypto) BTCUSDT');

    await pick('Venue', 'Binance');

    expect(productBox()).toHaveValue('');
    expect(vi.mocked(useAppProducts)).toHaveBeenLastCalledWith(35);
  });
});

describe('SubscriptionDialog product search', () => {
  beforeEach(() => vi.clearAllMocks());

  it('narrows the list as you type, rather than making you scroll it', async () => {
    setup();
    await chooseVenue();

    await userEvent.type(productBox(), 'ether');

    expect(await screen.findByText('Ethereum')).toBeInTheDocument();
    expect(screen.queryByText('Bitcoin')).not.toBeInTheDocument();
  });

  it('searches on the cusip too, not just the display name', async () => {
    setup();
    await chooseVenue();

    await userEvent.type(productBox(), 'solusdt');

    expect(await screen.findByText('Solana')).toBeInTheDocument();
    expect(screen.queryByText('Bitcoin')).not.toBeInTheDocument();
  });

  it('searches on the symbol the venue prints', async () => {
    // The ticker on the exchange screen is often the only one to hand.
    setup();
    await chooseVenue();

    await userEvent.type(productBox(), 'ETHUSDT');

    expect(await screen.findByText('Ethereum')).toBeInTheDocument();
    expect(screen.queryByText('Bitcoin')).not.toBeInTheDocument();
  });

  it('shows the cusip and venue symbol beside the name', async () => {
    setup();
    await chooseVenue();

    await userEvent.click(productBox());

    expect(await screen.findByText('btcusdt.crypto · BTCUSDT')).toBeInTheDocument();
  });

  it('says so when nothing matches instead of showing an empty list', async () => {
    setup();
    await chooseVenue();

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
