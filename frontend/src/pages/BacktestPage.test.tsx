import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BacktestPage from './BacktestPage';
import { renderWithProviders } from '../test/wrapper';
import { fetchJob } from '../api/jobs';

vi.mock('../api/jobs', () => ({
  fetchJob: vi.fn(),
  useEnqueueJob: () => ({ isPending: false }),
  useJobCompletionEffects: () => {},
}));
vi.mock('../api/auth', () => ({
  useMe: () => ({ data: null }),
}));
vi.mock('../api/refdata', () => ({
  useAssetTypes: () => ({ data: [] }),
  useTmIntervals: () => ({ data: [] }),
}));
vi.mock('../api/inst', () => ({
  useProducts: () => ({ data: [] }),
}));
vi.mock('../components/JobsTable', () => ({
  default: ({ onView }: { onView?: (id: string) => void }) => (
    <button type="button" onClick={() => onView?.('q-1')}>View job</button>
  ),
}));
vi.mock('../components/ConfigDrawer', () => ({ default: () => null }));
vi.mock('../components/PromotionTab', () => ({ default: () => null }));
vi.mock('../components/Top10Table', () => ({ default: () => null }));

function jobResult(walkForwardError: string | null) {
  return {
    config_json: null,
    result: {
      total_trials: 4,
      valid: 2,
      best: { sharpe: 1.2 },
      top10: [],
      grid: [],
      walk_forward: null,
      walk_forward_error: walkForwardError,
    },
  };
}

describe('BacktestPage walk-forward failure', () => {
  beforeEach(() => {
    vi.mocked(fetchJob).mockReset();
  });

  it('shows the failure when a stored result names one', async () => {
    vi.mocked(fetchJob).mockResolvedValue(jobResult('oos window is empty') as never);
    const user = userEvent.setup();
    renderWithProviders(<BacktestPage />);
    await user.click(screen.getByRole('tab', { name: 'Queue' }));
    await user.click(screen.getByRole('button', { name: 'View job' }));
    expect(await screen.findByText('Walk-forward did not finish: oos window is empty')).toBeInTheDocument();
  });

  it('stays quiet when the split was not run', async () => {
    vi.mocked(fetchJob).mockResolvedValue(jobResult(null) as never);
    const user = userEvent.setup();
    renderWithProviders(<BacktestPage />);
    await user.click(screen.getByRole('tab', { name: 'Queue' }));
    await user.click(screen.getByRole('button', { name: 'View job' }));
    expect(await screen.findByText(/Best Sharpe/)).toBeInTheDocument();
    expect(screen.queryByText(/Walk-forward did not finish/)).not.toBeInTheDocument();
  });
});
