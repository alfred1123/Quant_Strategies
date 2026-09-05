import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CreateInstrumentDialog from './CreateInstrumentDialog';
import { useCreateInstrument, useVenueSymbols } from '../../api/inst';
import { useAssetTypes, useExchangeApps } from '../../api/refdata';
import type { VenueSymbol } from '../../types/refdata';

vi.mock('../../api/inst', () => ({
  useCreateInstrument: vi.fn(),
  useVenueSymbols: vi.fn(),
}));
vi.mock('../../api/refdata', () => ({
  useAssetTypes: vi.fn(),
  useExchangeApps: vi.fn(),
}));

/** What ccxt reports for Bybit, including the id that is two markets. */
const BYBIT_SYMBOLS: VenueSymbol[] = [
  { vendor_symbol: 'BTCUSDT', base: 'BTC', quote: 'USDT', market_types: ['spot', 'swap'] },
  { vendor_symbol: 'ETHUSDT', base: 'ETH', quote: 'USDT', market_types: ['spot', 'swap'] },
  { vendor_symbol: 'SOLUSDC', base: 'SOL', quote: 'USDC', market_types: ['spot'] },
];

let createMutate: ReturnType<typeof vi.fn>;
let onSuccess: Mock<() => void>;

function setup({
  isPending = false,
  rejectWith = null,
  venueSymbols = BYBIT_SYMBOLS,
  symbolsFetching = false,
  symbolsFailed = false,
}: {
  isPending?: boolean;
  /** The API refusing the insert — a duplicate cusip is the common one. */
  rejectWith?: Error | null;
  venueSymbols?: VenueSymbol[];
  symbolsFetching?: boolean;
  /** The exchange unreachable — the field has to stay usable regardless. */
  symbolsFailed?: boolean;
} = {}) {
  vi.mocked(useVenueSymbols).mockReturnValue({
    data: venueSymbols,
    isFetching: symbolsFetching,
    isError: symbolsFailed,
  } as unknown as ReturnType<typeof useVenueSymbols>);
  createMutate = rejectWith
    ? vi.fn().mockRejectedValue(rejectWith)
    : vi.fn().mockResolvedValue({});
  vi.mocked(useCreateInstrument).mockReturnValue({
    mutateAsync: createMutate,
    isPending,
  } as unknown as ReturnType<typeof useCreateInstrument>);
  vi.mocked(useExchangeApps).mockReturnValue({
    data: [
      { app_id: 34, display_name: 'Bybit' },
      { app_id: 35, display_name: 'Binance' },
    ],
  } as unknown as ReturnType<typeof useExchangeApps>);
  vi.mocked(useAssetTypes).mockReturnValue({
    data: [
      { asset_type_id: 2, name: 'CRYPTO', display_name: 'Crypto' },
      { asset_type_id: 1, name: 'EQUITY', display_name: 'Equity' },
    ],
  } as unknown as ReturnType<typeof useAssetTypes>);

  onSuccess = vi.fn();
  render(<CreateInstrumentDialog open onClose={vi.fn()} onSuccess={onSuccess} />);
}

/** Pick from one of the two dropdowns, both of which come from REFDATA. */
async function pick(label: string, option: string) {
  await userEvent.click(screen.getByRole('combobox', { name: label }));
  await userEvent.click(await screen.findByRole('option', { name: option }));
}

const type = (label: string, value: string) =>
  userEvent.type(screen.getByRole('textbox', { name: label }), value);

const symbolBox = () => screen.getByRole('combobox', { name: 'Venue symbol' });

/** Free text into the ccxt-backed field, then close whatever it suggested. */
async function typeSymbol(value: string) {
  await userEvent.type(symbolBox(), value);
  await userEvent.keyboard('{Escape}');
}

const submitButton = () => screen.getByRole('button', { name: 'Add instrument' });

/** The five fields without which there is no instrument to insert. */
async function fillRequired({ cusip = 'btcusdt.crypto' } = {}) {
  await pick('Venue', 'Bybit');
  await typeSymbol('BTCUSDT');
  await type('Internal CUSIP', cusip);
  await type('Display name', 'Bitcoin / USDT');
  await pick('Asset type', 'Crypto');
}

describe('CreateInstrumentDialog required fields', () => {
  beforeEach(() => vi.clearAllMocks());

  it('will not submit an instrument that is missing part of its identity', () => {
    setup();

    expect(submitButton()).toBeDisabled();
  });

  it('keeps the button disabled until the venue symbol is given too', async () => {
    // The product fields alone look like a complete form, and a product with
    // no xref is invisible to every venue-scoped list — so it is not one.
    setup();

    await pick('Venue', 'Bybit');
    await type('Internal CUSIP', 'btcusdt.crypto');
    await type('Display name', 'Bitcoin / USDT');
    await pick('Asset type', 'Crypto');

    expect(submitButton()).toBeDisabled();

    await typeSymbol('BTCUSDT');

    // `waitFor`, not a bare assertion: the last keystroke's re-render is what
    // enables the button, and under a loaded suite it has occasionally not
    // committed by the next line.
    await waitFor(() => expect(submitButton()).toBeEnabled());
  });

  it('does not require the fields that are genuinely optional', async () => {
    // `exchange` is meaningless for crypto spot and a description is prose.
    setup();

    await fillRequired();

    await waitFor(() => expect(submitButton()).toBeEnabled());
  });
});

describe('CreateInstrumentDialog venue symbol lookup', () => {
  beforeEach(() => vi.clearAllMocks());

  it('asks for nothing until a venue says which exchange to ask', async () => {
    // The tickers are a property of the venue, so there is no list to fetch
    // and nothing meaningful to offer before one is picked.
    setup();

    expect(vi.mocked(useVenueSymbols)).toHaveBeenLastCalledWith(null);

    await pick('Venue', 'Bybit');

    expect(vi.mocked(useVenueSymbols)).toHaveBeenLastCalledWith(34);
  });

  it('re-asks the new venue when the venue changes', async () => {
    // Bybit's tickers are not Binance's, and a stale list would suggest
    // symbols the chosen exchange has never printed.
    setup();

    await pick('Venue', 'Bybit');
    await pick('Venue', 'Binance');

    expect(vi.mocked(useVenueSymbols)).toHaveBeenLastCalledWith(35);
  });

  it('offers what the venue prints, and says what each ticker covers', async () => {
    // One Bybit id is both the spot pair and the perpetual. The xref cannot
    // record which, so the option has to show that rather than pick one.
    setup();
    await pick('Venue', 'Bybit');

    await userEvent.type(symbolBox(), 'ETH');

    const option = await screen.findByRole('option', { name: /ETHUSDT/ });
    expect(option).toHaveTextContent('ETH/USDT · spot, swap');
  });

  it('completes a partial ticker to the venue\'s own spelling', async () => {
    // The point of the lookup: ETHUSD is not a Bybit symbol and would create
    // an instrument that captures nothing.
    setup();
    await pick('Venue', 'Bybit');

    await userEvent.type(symbolBox(), 'ETHUSD');
    await userEvent.tab();

    await waitFor(() => expect(symbolBox()).toHaveValue('ETHUSDT'));
  });

  it('still accepts a ticker the venue has not listed', async () => {
    // ccxt's table is a snapshot, and a pair listed this morning is absent
    // from it. Refusing would make that the user's problem.
    setup();
    await pick('Venue', 'Bybit');
    await typeSymbol('BRANDNEWUSDT');
    await type('Internal CUSIP', 'brandnewusdt.crypto');
    await type('Display name', 'Brand New / Tether');
    await pick('Asset type', 'Crypto');

    await waitFor(() => expect(submitButton()).toBeEnabled());
    await userEvent.click(submitButton());

    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    expect(createMutate.mock.calls[0][0].vendor_symbol).toBe('BRANDNEWUSDT');
  });

  it('says the venue is unreachable rather than looking like an empty list', async () => {
    // An empty dropdown and a failed lookup are indistinguishable otherwise,
    // and only one of them means "type it yourself".
    setup({ venueSymbols: [], symbolsFailed: true });
    await pick('Venue', 'Bybit');

    expect(
      screen.getByText(/could not be reached — type the ticker yourself/),
    ).toBeInTheDocument();
  });
});

describe('CreateInstrumentDialog submit', () => {
  beforeEach(() => vi.clearAllMocks());

  it('submits the product and its first venue symbol in one call', async () => {
    // Two rows, one request: created separately, the product would be reachable
    // by nothing between the two calls, and by nothing at all if the second
    // never happened.
    setup();
    await fillRequired();

    await userEvent.click(submitButton());

    await waitFor(() => expect(createMutate).toHaveBeenCalledTimes(1));
    expect(createMutate.mock.calls[0][0]).toMatchObject({
      internal_cusip: 'btcusdt.crypto',
      display_nm: 'Bitcoin / USDT',
      asset_type_id: 2,
      app_id: 34,
      vendor_symbol: 'BTCUSDT',
    });
  });

  it('carries the optional fields when they are filled', async () => {
    setup();
    await fillRequired();
    await type('Currency', 'USDT');
    await type('Description', 'Bitcoin against Tether');

    await userEvent.click(submitButton());

    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    expect(createMutate.mock.calls[0][0]).toMatchObject({
      ccy: 'USDT',
      description: 'Bitcoin against Tether',
    });
  });

  it('lowercases and trims the cusip before submitting it', async () => {
    // The cusip is an identifier, so a stray capital does not make a typo —
    // it makes a second product for an instrument the platform already has.
    setup();
    await fillRequired({ cusip: '  BTCUSDT.Crypto  ' });

    await userEvent.click(submitButton());

    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    expect(createMutate.mock.calls[0][0].internal_cusip).toBe('btcusdt.crypto');
  });

  it('sends a blank exchange as null rather than an empty string', async () => {
    // Decision #21: EXCHANGE is the listing venue of an equity and must be
    // NULL on .crypto spot. An empty string would record a venue of "".
    setup();
    await fillRequired();

    await userEvent.click(submitButton());

    await waitFor(() => expect(createMutate).toHaveBeenCalled());
    const sent = createMutate.mock.calls[0][0];
    expect(sent.exchange).toBeNull();
    expect(sent.description).toBeNull();
  });

  it('closes only once the insert has actually succeeded', async () => {
    setup();
    await fillRequired();

    await userEvent.click(submitButton());

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });
});

describe('CreateInstrumentDialog failure', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows a refused insert in the form instead of closing over it', async () => {
    // A duplicate cusip is the expected failure, and the fix is to edit the
    // field — which is impossible if the dialog has already gone.
    setup({ rejectWith: new Error('INTERNAL_CUSIP btcusdt.crypto already exists') });
    await fillRequired();

    await userEvent.click(submitButton());

    expect(
      await screen.findByText(/btcusdt.crypto already exists/),
    ).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('says something even when the failure carries no message', async () => {
    setup({ rejectWith: null });
    createMutate.mockRejectedValue('nope');
    await fillRequired();

    await userEvent.click(submitButton());

    expect(
      await screen.findByText('Could not create the instrument'),
    ).toBeInTheDocument();
  });
});

describe('CreateInstrumentDialog while submitting', () => {
  beforeEach(() => vi.clearAllMocks());

  it('locks both buttons while the insert is in flight', async () => {
    // A second click would attempt a second product for the same cusip, and
    // cancelling mid-insert leaves the caller unable to see what happened.
    setup({ isPending: true });
    await fillRequired();

    expect(submitButton()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});
