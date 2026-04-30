import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { screen, fireEvent } from '@testing-library/react';
import ConfigDrawer from './ConfigDrawer';
import { renderWithProviders } from '../test/wrapper';
import type { BacktestConfig } from '../types/backtest';
import type {
  AppRow, AssetTypeRow, ConjunctionRow, DataColumnRow, IndicatorRow,
  ProductRow, SignalTypeRow,
} from '../types/refdata';

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
  { app_id: 1, name: 'yahoo', display_name: 'Yahoo Finance', class_name: 'YahooFinance', description: null },
];
const products: ProductRow[] = [
  { product_id: 10, product_vid: 1, internal_cusip: '00434.hkex', display_nm: 'Boyaa Interactive', asset_type_id: 2, exchange: 'HKEX', ccy: 'HKD', description: null },
];

vi.mock('../api/refdata', () => ({
  useIndicators: () => ({ data: indicators }),
  useSignalTypes: () => ({ data: signalTypes }),
  useAssetTypes: () => ({ data: assetTypes }),
  useConjunctions: () => ({ data: conjunctions }),
  useDataColumns: () => ({ data: dataColumns }),
  useApps: () => ({ data: apps }),
}));

vi.mock('../api/inst', () => ({
  useProducts: () => ({ data: products }),
  useProductXrefs: () => ({ data: [] }),
}));

const baseCfg: BacktestConfig = {
  symbol: '',
  vendorSymbol: '',
  dataSource: 'yahoo',
  start: '2020-01-01',
  end: '2024-01-01',
  assetType: '',
  tradingPeriod: 365,
  feeBps: 5,
  mode: 'single',
  indicator: '',
  strategy: '',
  windowRange: { min: 5, max: 100, step: 5 },
  signalRange: { min: 0.25, max: 2.5, step: 0.25 },
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

beforeEach(() => vi.clearAllMocks());

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
