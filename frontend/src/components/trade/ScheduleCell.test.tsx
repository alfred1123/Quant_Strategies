import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ScheduleCell from './ScheduleCell';
import { useTmIntervals } from '../../api/refdata';
import { useScheduleOptions, useUpdateDeployment } from '../../api/trade';
import type { DeploymentRow } from '../../types/trade';
import type { TmIntervalRow } from '../../types/refdata';

// Keep the real intervalLabel so its NAME fallback is exercised, not stubbed.
vi.mock('../../api/refdata', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/refdata')>()),
  useTmIntervals: vi.fn(),
}));

vi.mock('../../api/trade', () => ({
  useUpdateDeployment: vi.fn(),
  useScheduleOptions: vi.fn(),
}));

const INTERVALS: TmIntervalRow[] = [
  {
    tm_interval_id: 1,
    name: 'DAILY',
    display_name: 'Daily',
    period_length: '1 day, 0:00:00',
    description: null,
  },
  {
    tm_interval_id: 2,
    name: '1H',
    display_name: 'Hourly',
    period_length: '1:00:00',
    description: null,
  },
];

function deployment(overrides: Partial<DeploymentRow> = {}): DeploymentRow {
  return {
    deployment_id: 'dep-1',
    deployment_vid: 3,
    app_user_id: 'user-1',
    strategy_id: 'strat-1',
    strategy_vid: 5,
    api_credential_id: 7,
    app_id: 34,
    internal_cusip: 'btcusdt.crypto',
    qty: '0.001',
    is_paper_ind: 'Y',
    is_enabled_ind: 'Y',
    deployment_status: 'ACTIVE',
    schedule_tm_interval_id: null,
    last_run_at: null,
    next_due_at: null,
    transact_from_ts: '2026-08-01T00:00:00Z',
    user_id: 'user-1',
    ...overrides,
  };
}

let mutateAsync: ReturnType<typeof vi.fn>;

function setup(
  row: DeploymentRow,
  {
    intervals = INTERVALS,
    schedulableIds = [1, 2],
  }: { intervals?: TmIntervalRow[]; schedulableIds?: number[] } = {},
) {
  vi.mocked(useTmIntervals).mockReturnValue({
    data: intervals,
  } as unknown as ReturnType<typeof useTmIntervals>);
  vi.mocked(useScheduleOptions).mockReturnValue({
    data: { tm_interval_ids: schedulableIds },
  } as unknown as ReturnType<typeof useScheduleOptions>);
  vi.mocked(useUpdateDeployment).mockReturnValue({
    mutateAsync,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateDeployment>);
  const onError = vi.fn();
  render(<ScheduleCell row={row} onError={onError} />);
  return { onError };
}

async function choose(optionName: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox'));
  await user.click(screen.getByRole('option', { name: optionName }));
}

// happy-dom ships no window.confirm, so there is nothing to spy on.
function stubConfirm(result: boolean) {
  const fn = vi.fn().mockReturnValue(result);
  window.confirm = fn;
  return fn;
}

describe('ScheduleCell', () => {
  beforeEach(() => {
    mutateAsync = vi.fn().mockResolvedValue({});
    vi.mocked(useTmIntervals).mockReset();
    vi.mocked(useScheduleOptions).mockReset();
    vi.mocked(useUpdateDeployment).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads Manual when no cadence is set', () => {
    setup(deployment());
    expect(screen.getByRole('combobox')).toHaveTextContent('Manual');
  });

  it('shows the cadence label and the next due time when scheduled', () => {
    setup(
      deployment({
        schedule_tm_interval_id: 2,
        next_due_at: '2026-08-29T14:00:00Z',
      }),
    );
    expect(screen.getByRole('combobox')).toHaveTextContent('Hourly');
    expect(screen.getByText(/^Next /)).toBeInTheDocument();
  });

  it('hides the next due time for a manual deployment', () => {
    setup(deployment({ next_due_at: '2026-08-29T14:00:00Z' }));
    expect(screen.queryByText(/^Next /)).not.toBeInTheDocument();
  });

  it('falls back to NAME when the database predates DISPLAY_NAME', () => {
    setup(deployment({ schedule_tm_interval_id: 1 }), {
      intervals: [{ ...INTERVALS[0], display_name: null }],
    });
    expect(screen.getByRole('combobox')).toHaveTextContent('DAILY');
  });

  it('disables a cadence the strategy was not fitted on', async () => {
    setup(deployment(), { schedulableIds: [1] });
    await userEvent.setup().click(screen.getByRole('combobox'));
    expect(screen.getByRole('option', { name: 'Hourly' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('option', { name: 'Daily' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('patches the chosen interval id', async () => {
    setup(deployment());
    await choose('Hourly');
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      schedule_tm_interval_id: 2,
    });
  });

  it('sends an explicit null to go back to manual', async () => {
    setup(deployment({ schedule_tm_interval_id: 2 }));
    await choose('Manual');
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      schedule_tm_interval_id: null,
    });
  });

  it('does not patch when the cadence already matches', async () => {
    setup(deployment({ schedule_tm_interval_id: 2 }));
    await choose('Hourly');
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('confirms before automating a live deployment', async () => {
    const confirm = stubConfirm(true);
    setup(deployment({ is_paper_ind: 'N' }));
    await choose('Hourly');
    expect(confirm).toHaveBeenCalled();
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      schedule_tm_interval_id: 2,
    });
  });

  it('leaves a live deployment alone when the confirmation is declined', async () => {
    stubConfirm(false);
    setup(deployment({ is_paper_ind: 'N' }));
    await choose('Hourly');
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('does not confirm when a live deployment returns to manual', async () => {
    const confirm = stubConfirm(true);
    setup(deployment({ is_paper_ind: 'N', schedule_tm_interval_id: 2 }));
    await choose('Manual');
    expect(confirm).not.toHaveBeenCalled();
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      schedule_tm_interval_id: null,
    });
  });

  it('surfaces a failed change through onError', async () => {
    mutateAsync = vi.fn().mockRejectedValue(new Error('interval not found'));
    const { onError } = setup(deployment());
    await choose('Daily');
    expect(onError).toHaveBeenCalledWith('interval not found');
  });

  it('renders plain text while REFDATA has not arrived', () => {
    setup(deployment({ schedule_tm_interval_id: 2 }), { intervals: [] });
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
  });
});
