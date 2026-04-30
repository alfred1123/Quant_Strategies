import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MetricsCards from './MetricsCards';
import type { PerformanceResponse } from '../types/backtest';

function makeResult(overrides: Partial<PerformanceResponse> = {}): PerformanceResponse {
  return {
    strategy_metrics: { 'Total Return': 0.452, 'Sharpe Ratio': 1.8 },
    buy_hold_metrics: { 'Total Return': 0.2, 'Sharpe Ratio': 0.9 },
    equity_curve: [],
    perf_csv: '',
    ...overrides,
  };
}

describe('MetricsCards', () => {
  it('renders Strategy and Buy & Hold cards', () => {
    render(<MetricsCards result={makeResult()} />);
    expect(screen.getByText('Strategy')).toBeInTheDocument();
    expect(screen.getByText('Buy & Hold')).toBeInTheDocument();
  });

  it('formats percent keys with % suffix', () => {
    render(<MetricsCards result={makeResult()} />);
    expect(screen.getByText('45.2%')).toBeInTheDocument();
    expect(screen.getByText('20.0%')).toBeInTheDocument();
  });

  it('formats non-percent keys to 3 decimal places', () => {
    render(<MetricsCards result={makeResult()} />);
    expect(screen.getByText('1.800')).toBeInTheDocument();
    expect(screen.getByText('0.900')).toBeInTheDocument();
  });

  it('shows dash for NaN/null values', () => {
    render(
      <MetricsCards result={makeResult({ strategy_metrics: { 'Max Drawdown': NaN } })} />,
    );
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
