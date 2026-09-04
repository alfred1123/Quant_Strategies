import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { screen, fireEvent } from '@testing-library/react';
import ConfigDrawer from './ConfigDrawer';
import { renderWithProviders } from '../test/wrapper';
import type { BacktestConfig } from '../types/backtest';
import type {
  AppRow, AssetTypeRow, ConjunctionRow, DataColumnRow, IndicatorRow,
  ProductRow, SignalTypeRow, TmIntervalRow,
} from '../types/refdata';
import type { Coverage } from '../types/marketData';

// ── REFDATA + product hook mocks ──────────────────────────────────────────
// We stub the data hooks at module boundary so the drawer renders with a
// stable, predictable list of options. Keeping the mocks near the test (not
// in a global setup) means each new test file is free to vary the data.

const indicators: IndicatorRow[] = [
  { method_name: 'sma', display_name: 'SMA', win_min: 5, win_max: 100, win_step: 5, sig_min: 0.25, sig_max: 2.5, sig_step: 0.25, is_bounded_ind: 'N' },
];
const signalTypes: SignalTypeRow[] = [{ name: 'momentum', display_name: 'Momentum' }];
const assetTypes: AssetTypeRow[] = [
  { asset_type_id: 1, name: 'crypto', display_name: 'Crypto', trading_period: 365 },
  { asset_type_id: 2, name: 'equity_hk', display_name: 'Equity HK', trading_period: 252 },
];
const conjunctions: ConjunctionRow[] = [{ name: 'AND', display_name: 'AND' }];
const dataColumns: DataColumnRow[] = [{ column_name: 'price', display_name: 'Price' }];
const apps: AppRow[] = [
  { app_id: 1, name: 'yahoo', display_name: 'Yahoo Finance', class_name: 'YahooFinance', is_exchange_ind: 'N', description: null },
  { app_id: 34, name: 'bybit', display_name: 'Bybit', class_name: 'Bybit', is_exchange_ind: 'Y', description: null },
];
const tmIntervals: TmIntervalRow[] = [
  { tm_interval_id: 1, name: 'DAILY', display_name: 'Daily', period_length: '1 day', description: null },
  { tm_interval_id: 2, name: '1H', display_name: 'Hourly', period_length: '01:00:00', description: null },
];
const products: ProductRow[] = [
  { product_id: 10, product_vid: 1, internal_cusip: '00434.hkex', display_nm: 'Boyaa Interactive', asset_type_id: 2, exchange: 'HKEX', ccy: 'HKD', description: null },
  { product_id: 11, product_vid: 1, internal_cusip: 'btcusdt.crypto', display_nm: 'Bitcoin / Tether', asset_type_id: 1, exchange: null, ccy: 'USDT', description: null },
];

vi.mock('../api/refdata', () => ({
  useIndicators: () => ({ data: indicators }),
  useSignalTypes: () => ({ data: signalTypes }),
  useAssetTypes: () => ({ data: assetTypes }),
  useConjunctions: () => ({ data: conjunctions }),
  useDataColumns: () => ({ data: dataColumns }),
  useApps: () => ({ data: apps }),
  useTmIntervals: () => ({ data: tmIntervals }),
  intervalLabel: (row: TmIntervalRow) => row.display_name?.trim() || row.name,
}));

vi.mock('../api/inst', () => ({
  useProducts: () => ({ data: products }),
  useProductXrefs: () => ({ data: [] }),
}));

/** What the coverage endpoint answers, and who it was asked about. */
let storedCoverage: Coverage | undefined;
const coverageAsked = vi.fn();

vi.mock('../api/marketData', () => ({
  useStoredCoverage: (key: Record<string, unknown>) => {
    coverageAsked(key);
    return { data: storedCoverage };
  },
}));

const BYBIT_COVERAGE: Coverage = {
  first_bar: '2020-03-25T00:00:00Z',
  last_bar: '2026-08-29T00:00:00Z',
  gaps: 0,
  error: null,
};

/** The same pair hourly: the first bar is 10:00, not midnight. */
const BYBIT_HOURLY_COVERAGE: Coverage = {
  first_bar: '2020-03-25T10:00:00+00:00',
  last_bar: '2026-09-03T14:00:00+00:00',
  gaps: 0,
  error: null,
};

const baseCfg: BacktestConfig = {
  symbol: '',
  vendorSymbol: '',
  dataSource: 'yahoo',
  start: '2020-01-01',
  end: '2024-01-01',
  assetType: '',
  tmIntervalId: 1,
  tradingPeriod: 365,
  feeBps: 5,
  conjunction: 'AND',
  factors: [
    {
      indicator: 'sma',
      strategy: 'momentum',
      data_column: 'price',
      window_range: { min: 5, max: 100, step: 5 },
      signal_range: { min: 0.25, max: 2.5, step: 0.25 },
    },
  ],
  walkForward: false,
  splitRatio: 0.5,
  refreshDataset: false,
};

/**
 * Stateful test host. Mirrors how `BacktestPage` wires `useState` →
 * `setConfig` into the drawer. Without this we'd be testing a stub instead
 * of the actual React batching behavior, and the regression test below
 * would silently pass for the wrong reason.
 */
function Host({ initial, observer }: { initial: BacktestConfig; observer: (c: BacktestConfig) => void }) {
  const [cfg, setCfg] = useState<BacktestConfig>(initial);
  return (
    <ConfigDrawer
      open
      onClose={() => { /* noop */ }}
      config={cfg}
      onChange={(next) => {
        setCfg((prev) => {
          const resolved = typeof next === 'function' ? next(prev) : next;
          observer(resolved);
          return resolved;
        });
      }}
      onRun={() => { /* noop */ }}
      isRunning={false}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  storedCoverage = undefined;
});

describe('ConfigDrawer — product pick updates symbol AND asset type atomically', () => {
  it('regression: picking a product after typing a vendor symbol updates BOTH symbol and assetType', () => {
    // Repro of the stale-closure bug: when the user types a vendor symbol
    // and then picks a product, ProductSelector fires onChange (symbol +
    // vendorSymbol) AND onProductPicked (assetType + tradingPeriod) in one
    // event tick. With a non-functional `set` helper the second call would
    // close over the stale `config` and silently discard the first update.
    const observer = vi.fn();
    renderWithProviders(<Host initial={{ ...baseCfg, vendorSymbol: 'BTBT' }} observer={observer} />);

    // The drawer renders TWO ProductSelector instances (top-level + factor 1).
    // The first one is the trading product — that's the one with the bug.
    const productInputs = screen.getAllByLabelText('Product');
    const topProductInput = productInputs[0];

    // Open the dropdown and pick the only option.
    fireEvent.mouseDown(topProductInput);
    fireEvent.click(screen.getByText('Boyaa Interactive'));

    // Last observed config must have BOTH the symbol set AND the asset
    // type derived from the picked product. Pre-fix this assertion failed
    // because `assetType` updated but `symbol` was overwritten back to ''.
    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.symbol).toBe('00434.hkex');
    expect(last.assetType).toBe('Equity HK');
    expect(last.tradingPeriod).toBe(252);
    expect(last.vendorSymbol).toBe('');
  });

  it('typing a vendor symbol clears the product without touching asset type', () => {
    const observer = vi.fn();
    renderWithProviders(<Host initial={{ ...baseCfg, symbol: '00434.hkex', assetType: 'Equity HK', tradingPeriod: 252 }} observer={observer} />);

    const vendorInputs = screen.getAllByLabelText('Vendor Symbol');
    fireEvent.change(vendorInputs[0], { target: { value: 'BTBT' } });

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.vendorSymbol).toBe('BTBT');
    expect(last.symbol).toBe('');
    // Asset type should remain — the user only changed vendor symbol.
    expect(last.assetType).toBe('Equity HK');
    expect(last.tradingPeriod).toBe(252);
  });
});

/**
 * The dates a run can use come from what is captured.
 *
 * A user picked Bybit and left the default 2016-01-01 start, which predates
 * Bybit's first BTCUSDT bar by four years, and the end defaulted to today —
 * a bar that had not closed. Both were refused, and nothing on the form said
 * what would have worked.
 */
const bybitCfg: BacktestConfig = {
  ...baseCfg,
  dataSource: 'bybit',
  symbol: 'btcusdt.crypto',
  assetType: 'Crypto',
  start: '2016-01-01',
  end: '2026-08-30',
};

describe('ConfigDrawer — the captured range decides the dates', () => {
  it('snaps the dates to what the venue has captured', () => {
    storedCoverage = BYBIT_COVERAGE;
    const observer = vi.fn();
    renderWithProviders(<Host initial={bybitCfg} observer={observer} />);

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.start).toBe('2020-03-25');
    expect(last.end).toBe('2026-08-29');
  });

  it('snaps an intraday head to the exact first bar, keeping its time', () => {
    // A real FAILED run: the first hourly bar is 10:00, the snap offered
    // 2020-03-25, and the worker refused a window reaching ten hours before
    // any bar existed. The bound is now carried to the minute rather than
    // rounded to a day the field could hold.
    storedCoverage = BYBIT_HOURLY_COVERAGE;
    const observer = vi.fn();
    renderWithProviders(
      <Host initial={{ ...bybitCfg, tmIntervalId: 2 }} observer={observer} />,
    );

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.start).toBe('2020-03-25T10:00');
    expect(last.end).toBe('2026-09-03T14:00');
    expect(screen.queryByText(/will be refused/)).toBeNull();
  });

  it('gives an intraday series inputs that can hold a time', () => {
    // A date control silently drops 10:00, which is what produced the
    // refused run in the first place.
    storedCoverage = BYBIT_HOURLY_COVERAGE;
    renderWithProviders(
      <Host initial={{ ...bybitCfg, tmIntervalId: 2 }} observer={vi.fn()} />,
    );

    expect(screen.getByLabelText('Start')).toHaveAttribute('type', 'datetime-local');
    expect(screen.getByLabelText('End')).toHaveAttribute('type', 'datetime-local');
  });

  it('leaves a daily series on plain date inputs', () => {
    // Daily bars sit on midnight, so there is no time of day to lose and
    // no reason to make the reader look at one.
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(<Host initial={bybitCfg} observer={vi.fn()} />);

    expect(screen.getByLabelText('Start')).toHaveAttribute('type', 'date');
  });

  it('asks about the traded series, at the selected interval', () => {
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(<Host initial={bybitCfg} observer={vi.fn()} />);

    expect(coverageAsked).toHaveBeenCalledWith({
      internal_cusip: 'btcusdt.crypto',
      tm_interval_id: 1,
      source_app_id: 34,
    });
  });

  it('leaves a provider source alone', () => {
    // Yahoo refetches any window on `Refresh dataset`, so what happens to be
    // cached is not a floor and must not be presented as one.
    storedCoverage = BYBIT_COVERAGE;
    const observer = vi.fn();
    renderWithProviders(
      <Host initial={{ ...baseCfg, symbol: 'btcusdt.crypto', start: '2016-01-01' }} observer={observer} />,
    );

    expect(coverageAsked).toHaveBeenCalledWith({});
    expect(observer).not.toHaveBeenCalled();
  });

  it('says what is captured once the range fits', () => {
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(
      <Host initial={{ ...bybitCfg, start: '2021-01-01', end: '2026-01-01' }} observer={vi.fn()} />,
    );

    expect(screen.getByText(/Bybit has 2020-03-25 to 2026-08-29 captured/)).toBeTruthy();
  });

  it('does not move dates the user edited afterwards', () => {
    storedCoverage = BYBIT_COVERAGE;
    const observer = vi.fn();
    renderWithProviders(<Host initial={bybitCfg} observer={observer} />);

    const startInput = screen.getByLabelText('Start');
    fireEvent.change(startInput, { target: { value: '2022-06-01' } });

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.start).toBe('2022-06-01');
  });

  it('does nothing while coverage has not answered', () => {
    storedCoverage = undefined;
    const observer = vi.fn();
    renderWithProviders(<Host initial={bybitCfg} observer={observer} />);

    expect(observer).not.toHaveBeenCalled();
  });

  it('does not snap a series with nothing captured', () => {
    storedCoverage = { first_bar: null, last_bar: null, gaps: null, error: null };
    const observer = vi.fn();
    renderWithProviders(<Host initial={bybitCfg} observer={observer} />);

    expect(observer).not.toHaveBeenCalled();
  });
});

describe('ConfigDrawer — a range outside the capture is flagged, not silently run', () => {
  it('warns when a hand-typed start reaches behind the first bar', () => {
    // The snap already fitted the range on selection, so this is the case
    // that remains: the user overriding it with a date the store cannot meet.
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(<Host initial={bybitCfg} observer={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2016-01-01' } });

    expect(screen.getByText(/will be refused rather than quietly shortened/)).toBeTruthy();
  });

  it('warns when a hand-typed end reaches past the last close', () => {
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(<Host initial={bybitCfg} observer={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('End'), { target: { value: '2027-01-01' } });

    expect(screen.getByText(/will be refused rather than quietly shortened/)).toBeTruthy();
  });

  it('offers the captured range as a one-click fix', () => {
    storedCoverage = BYBIT_COVERAGE;
    const observer = vi.fn();
    renderWithProviders(<Host initial={bybitCfg} observer={observer} />);

    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2016-01-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Use captured range' }));

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.start).toBe('2020-03-25');
    expect(last.end).toBe('2026-08-29');
  });

  it('does not warn about an end of today, whose bar has not closed', () => {
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(
      <Host initial={{ ...bybitCfg, start: '2021-01-01', end: '2026-08-30' }} observer={vi.fn()} />,
    );

    expect(screen.queryByText(/will be refused/)).toBeNull();
  });
});

/**
 * The cadence is chosen, not assumed.
 *
 * Every backtest read daily bars because the interval was a constant in
 * `backtest_service`, so the hourly series the capture page had been filling
 * for weeks could not be fitted on at all.
 */
describe('ConfigDrawer — the bar interval', () => {
  function pickHourly() {
    fireEvent.mouseDown(screen.getByLabelText('Bar Interval'));
    fireEvent.click(screen.getByRole('option', { name: 'Hourly' }));
  }

  it('asks coverage about the interval that is selected', () => {
    storedCoverage = BYBIT_COVERAGE;
    renderWithProviders(
      <Host initial={{ ...bybitCfg, tmIntervalId: 2 }} observer={vi.fn()} />,
    );

    expect(coverageAsked).toHaveBeenCalledWith({
      internal_cusip: 'btcusdt.crypto',
      tm_interval_id: 2,
      source_app_id: 34,
    });
  });

  it('rescales the annualisation when the cadence changes', () => {
    // 365 daily periods a year become 8,760 hourly ones. Left at 365, Sharpe
    // and annualised return come out ~5x and ~24x too low — a believable
    // number on the wrong scale, which discards a strategy quietly.
    const observer = vi.fn();
    renderWithProviders(<Host initial={{ ...bybitCfg }} observer={observer} />);

    pickHourly();

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.tmIntervalId).toBe(2);
    expect(last.tradingPeriod).toBe(8_760);
  });

  it('keeps the asset type as the base when rescaling, not the scaled value', () => {
    // Switching hourly → daily must land back on 365, not 8,760 × 24.
    const observer = vi.fn();
    renderWithProviders(
      <Host initial={{ ...bybitCfg, tmIntervalId: 2, tradingPeriod: 8_760 }} observer={observer} />,
    );

    fireEvent.mouseDown(screen.getByLabelText('Bar Interval'));
    fireEvent.click(screen.getByRole('option', { name: 'Daily' }));

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.tradingPeriod).toBe(365);
  });

  it('seeds daily once REFDATA loads, because no id can be written in a default', () => {
    const observer = vi.fn();
    renderWithProviders(
      <Host initial={{ ...baseCfg, tmIntervalId: null }} observer={observer} />,
    );

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.tmIntervalId).toBe(1);
  });

  it('re-snaps the dates when the cadence changes, since each is its own series', () => {
    storedCoverage = BYBIT_COVERAGE;
    const observer = vi.fn();
    renderWithProviders(
      <Host initial={{ ...bybitCfg, start: '2016-01-01' }} observer={observer} />,
    );
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2016-01-01' } });

    pickHourly();

    const last = observer.mock.calls.at(-1)?.[0] as BacktestConfig;
    expect(last.start).toBe('2020-03-25');
  });
});
