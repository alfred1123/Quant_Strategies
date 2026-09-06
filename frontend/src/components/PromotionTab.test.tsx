import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PromotionTab from './PromotionTab';
import { renderWithProviders } from '../test/wrapper';
import { usePromotions } from '../api/promotion';
import { useMe } from '../api/auth';
import { useSetStrategyLogicalDelete } from '../api/jobs';
import { usePromotionMetrics, usePromotionStates } from '../api/refdata';
import type { PromotionRow } from '../types/promotion';
import type { PromotionMetricRow, PromotionStateRow } from '../types/refdata';

vi.mock('../api/promotion', () => ({ usePromotions: vi.fn() }));
vi.mock('../api/auth', () => ({ useMe: vi.fn() }));
vi.mock('../api/jobs', () => ({
  useSetStrategyLogicalDelete: vi.fn(),
}));
vi.mock('../api/refdata', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/refdata')>()),
  usePromotionMetrics: vi.fn(),
  usePromotionStates: vi.fn(),
}));
vi.mock('./trade/DeploymentDialog', () => ({
  default: () => null,
}));

const SOFT: PromotionMetricRow[] = [
  {
    promotion_metric_id: 1,
    name: 'sharpe_compare',
    display_name: 'Sharpe Ratio',
    metric_key: 'Sharpe Ratio',
    direction: 'higher_is_better',
    requirement_type: 'SOFT',
    priority: 0,
    threshold: null,
    description: null,
  },
];

const STATES: PromotionStateRow[] = [
  { promotion_state_id: 1, name: 'KEPT', display_name: 'Kept', description: null },
  { promotion_state_id: 2, name: 'PROMOTED', display_name: 'Promoted', description: null },
];

function prow(overrides: Partial<PromotionRow> = {}): PromotionRow {
  return {
    promotion_id: 'p1',
    queue_id: 'q1',
    strategy_id: 's1',
    strategy_vid: 1,
    strategy_nm: 'btcusdt.crypto@bybit:DAILY ← price FILTER Volume',
    is_best_ind: 'Y',
    logical_delete_ind: 'N',
    outcome: 'KEPT',
    compared_vid: null,
    gate_results: [
      { name: 'sharpe_gate', passed: true, value: 5.07, threshold: 0 },
    ],
    sharpe_ratio: 5.0709,
    calmar_ratio: 79.93,
    max_drawdown: 0.0225,
    total_return: 0.1184,
    annualized_return: 1.8001,
    user_id: 'u1',
    created_at: '2026-09-05T00:00:00Z',
    ...overrides,
  };
}

function setup(rows: PromotionRow[]) {
  vi.mocked(usePromotions).mockReturnValue({
    data: rows,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof usePromotions>);
  vi.mocked(useMe).mockReturnValue({
    data: { username: 'u1', app_user_id: 'u1' },
  } as unknown as ReturnType<typeof useMe>);
  vi.mocked(usePromotionMetrics).mockReturnValue({
    data: SOFT,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof usePromotionMetrics>);
  vi.mocked(usePromotionStates).mockReturnValue({
    data: STATES,
  } as unknown as ReturnType<typeof usePromotionStates>);
  vi.mocked(useSetStrategyLogicalDelete).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useSetStrategyLogicalDelete>);
}

describe('PromotionTab comparison panel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows baseline copy when compared_vid is null', async () => {
    setup([prow({ compared_vid: null })]);
    renderWithProviders(<PromotionTab />);
    await userEvent.click(screen.getByText('v1'));
    expect(screen.getByText(/Baseline VID — no other version to compare/)).toBeInTheDocument();
    expect(screen.queryByText('This VID')).not.toBeInTheDocument();
    expect(screen.queryByText(/vs v1/)).not.toBeInTheDocument();
  });

  it('treats compared_vid equal to this VID as no baseline', async () => {
    setup([prow({ compared_vid: 1, strategy_vid: 1 })]);
    renderWithProviders(<PromotionTab />);
    await userEvent.click(screen.getByText('v1'));
    expect(screen.getByText(/Baseline VID — no other version to compare/)).toBeInTheDocument();
    expect(screen.queryByText('This VID')).not.toBeInTheDocument();
  });

  it('renders the soft table when compared against a different VID', async () => {
    const v1 = prow({
      promotion_id: 'p-v1',
      strategy_vid: 1,
      compared_vid: null,
      sharpe_ratio: 1.1,
    });
    const v2 = prow({
      promotion_id: 'p-v2',
      strategy_vid: 2,
      is_best_ind: 'N',
      outcome: 'PROMOTED',
      compared_vid: 1,
      sharpe_ratio: 1.5,
    });
    setup([v2, v1]);
    renderWithProviders(<PromotionTab />);
    await userEvent.click(screen.getByText('v2'));
    expect(screen.getByText('This VID')).toBeInTheDocument();
    expect(screen.getByText('Best v1')).toBeInTheDocument();
    expect(screen.getByText('vs v1')).toBeInTheDocument();
  });

  it('omits a logically deleted best VID from Recommended', () => {
    setup([prow({ logical_delete_ind: 'Y' })]);
    renderWithProviders(<PromotionTab />);
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument();
    expect(screen.getByText('Removed')).toBeInTheDocument();
  });

  it('removes the recommended lineage when the owner clicks Remove', async () => {
    const mutate = vi.fn();
    setup([prow()]);
    vi.mocked(useSetStrategyLogicalDelete).mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useSetStrategyLogicalDelete>);
    renderWithProviders(<PromotionTab />);
    const removeButtons = screen.getAllByRole('button', { name: 'Remove' });
    await userEvent.click(removeButtons[0]);
    expect(mutate).toHaveBeenCalledWith({
      strategyId: 's1',
      logicalDeleteInd: 'Y',
    });
  });
});
