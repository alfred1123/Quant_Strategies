import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DryRunReportDialog from './DryRunReportDialog';
import type { DryRunReport } from '../../types/trade';

function report(overrides: Partial<DryRunReport> = {}): DryRunReport {
  return {
    strategy_id: 'f2b1c0de-0000-4000-8000-000000000001',
    strategy_vid: 3,
    strategy_nm: 'btc momentum',
    internal_cusip: 'btcusdt.crypto',
    vendor_symbol: 'BTCUSDT',
    app_id: 34,
    paper: true,
    qty: '0.01',
    signal: 1,
    intended_side: 'BUY',
    position_qty: 0,
    data_as_of: '2026-08-29',
    notional: 600,
    bar_source: 'price_bar:bybit',
    ...overrides,
  };
}

describe('DryRunReportDialog', () => {
  it('names the venue whose bars produced the signal', () => {
    // The report is a preview of the live apply, which reads the same series.
    // Stating it is what lets a reader tell a real HOLD from a HOLD computed
    // off prices the order would never have touched.
    render(<DryRunReportDialog report={report()} onClose={vi.fn()} />);

    expect(screen.getByText('Price source')).toBeInTheDocument();
    expect(screen.getByText('bybit exchange bars')).toBeInTheDocument();
  });

  it('says provider for a broker with no market-data venue', () => {
    render(
      <DryRunReportDialog report={report({ bar_source: 'provider' })} onClose={vi.fn()} />,
    );

    expect(screen.getByText('Market data provider')).toBeInTheDocument();
  });
});
