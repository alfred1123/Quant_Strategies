import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeploymentDialog from './DeploymentDialog';
import { useCreateDeployment, useDryRun, useScheduleOptions } from '../../api/trade';
import { useJob } from '../../api/jobs';
import { useBrokerAccounts } from '../../api/credentials';
import { useProductXrefs, useProducts } from '../../api/inst';
import { useApps, useTmIntervals } from '../../api/refdata';
import type { TmIntervalRow } from '../../types/refdata';

vi.mock('../../api/trade', () => ({
  useCreateDeployment: vi.fn(),
  useDryRun: vi.fn(),
  useScheduleOptions: vi.fn(),
}));
vi.mock('../../api/jobs', () => ({ useJob: vi.fn() }));
vi.mock('../../api/credentials', () => ({ useBrokerAccounts: vi.fn() }));
vi.mock('../../api/inst', () => ({
  useProducts: vi.fn(),
  useProductXrefs: vi.fn(),
}));
// Real intervalLabel — the NAME fallback is part of what these tests cover.
vi.mock('../../api/refdata', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/refdata')>()),
  useApps: vi.fn(),
  useTmIntervals: vi.fn(),
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

let createMutate: ReturnType<typeof vi.fn>;

function setup({
  intervals = INTERVALS,
  // Both cadences schedulable by default, so the tests below exercise the
  // confirmation flows they are about rather than the fitted-cadence rule.
  schedulableIds = [1, 2],
}: { intervals?: TmIntervalRow[]; schedulableIds?: number[] | null } = {}) {
  createMutate = vi.fn().mockResolvedValue({});
  vi.mocked(useScheduleOptions).mockReturnValue({
    data: schedulableIds === null ? undefined : { tm_interval_ids: schedulableIds },
  } as unknown as ReturnType<typeof useScheduleOptions>);
  vi.mocked(useCreateDeployment).mockReturnValue({
    mutateAsync: createMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateDeployment>);
  vi.mocked(useDryRun).mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDryRun>);
  vi.mocked(useJob).mockReturnValue({
    data: undefined,
    isLoading: false,
  } as unknown as ReturnType<typeof useJob>);
  vi.mocked(useBrokerAccounts).mockReturnValue({
    data: [
      {
        api_credential_id: 7,
        app_id: 34,
        label: 'bybit-main',
        api_key_masked: '****abcd',
        is_active_ind: 'Y',
      },
    ],
  } as unknown as ReturnType<typeof useBrokerAccounts>);
  vi.mocked(useProducts).mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof useProducts>);
  vi.mocked(useProductXrefs).mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof useProductXrefs>);
  vi.mocked(useApps).mockReturnValue({
    data: [{ app_id: 34, display_name: 'Bybit' }],
  } as unknown as ReturnType<typeof useApps>);
  vi.mocked(useTmIntervals).mockReturnValue({
    data: intervals,
  } as unknown as ReturnType<typeof useTmIntervals>);

  render(
    <DeploymentDialog
      open
      onClose={vi.fn()}
      selection={{ strategyId: 'strat-1', strategyVid: 5, strategyNm: 'Mean reversion' }}
    />,
  );
  return userEvent.setup();
}

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByLabelText('Account'));
  await user.click(screen.getByRole('option', { name: /bybit-main/ }));
  await user.type(screen.getByLabelText('Product'), 'btcusdt.crypto');
  await user.type(screen.getByLabelText('Quantity'), '0.001');
}

async function pickSchedule(
  user: ReturnType<typeof userEvent.setup>,
  optionName: string,
) {
  await user.click(screen.getByLabelText('Schedule'));
  await user.click(screen.getByRole('option', { name: optionName }));
}

describe('DeploymentDialog schedule control', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('defaults to manual so deploying does not start automated trading', async () => {
    const user = setup();
    expect(screen.getByLabelText('Schedule')).toHaveTextContent('Manual only');
    await fillRequiredFields(user);
    await user.click(screen.getByRole('button', { name: /Deploy paper/ }));
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ schedule_tm_interval_id: null }),
    );
  });

  it('offers the cadences from REFDATA', async () => {
    const user = setup();
    await user.click(screen.getByLabelText('Schedule'));
    expect(screen.getByRole('option', { name: 'Manual only' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Daily' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Hourly' })).toBeInTheDocument();
  });

  it('disables a cadence the strategy was not fitted on', async () => {
    const user = setup({ schedulableIds: [1] });
    await user.click(screen.getByLabelText('Schedule'));
    expect(screen.getByRole('option', { name: 'Daily' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('option', { name: 'Hourly' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('says why a cadence is unavailable instead of hiding it', () => {
    setup({ schedulableIds: [1] });
    expect(screen.getByText(/not fitted on are disabled/i)).toBeInTheDocument();
  });

  it('restricts nothing until the options load', async () => {
    // The API refuses the write anyway; greying out every cadence on a failed
    // read would claim scheduling is unavailable when it is not.
    const user = setup({ schedulableIds: null });
    await user.click(screen.getByLabelText('Schedule'));
    expect(screen.getByRole('option', { name: 'Hourly' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('falls back to NAME when the database predates DISPLAY_NAME', async () => {
    const user = setup({ intervals: [{ ...INTERVALS[1], display_name: null }] });
    await user.click(screen.getByLabelText('Schedule'));
    expect(screen.getByRole('option', { name: '1H' })).toBeInTheDocument();
  });

  it('sends the chosen cadence for a paper deployment without extra confirmation', async () => {
    const user = setup();
    await fillRequiredFields(user);
    await pickSchedule(user, 'Hourly');
    await user.click(screen.getByRole('button', { name: /Deploy paper/ }));
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ schedule_tm_interval_id: 2, paper: true }),
    );
  });

  it('explains that a cadence also keeps price data up to date', async () => {
    const user = setup();
    expect(screen.getByText(/no scheduled price data/i)).toBeInTheDocument();
    await pickSchedule(user, 'Daily');
    expect(screen.getByText(/price data up to date/i)).toBeInTheDocument();
  });

  it('blocks an automated live deployment until it is confirmed separately', async () => {
    const user = setup();
    await fillRequiredFields(user);
    await user.click(screen.getByRole('button', { name: 'Live trading' }));
    await pickSchedule(user, 'Hourly');
    await user.click(screen.getByLabelText('I confirm this is a LIVE deployment'));

    const deploy = screen.getByRole('button', { name: /Deploy live/ });
    expect(deploy).toBeDisabled();

    await user.click(
      screen.getByLabelText('I confirm automatic live trading on this schedule'),
    );
    expect(deploy).toBeEnabled();
    await user.click(deploy);
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        schedule_tm_interval_id: 2,
        paper: false,
        confirm_live: true,
      }),
    );
  });

  it('asks for no schedule confirmation when a live deployment stays manual', async () => {
    const user = setup();
    await fillRequiredFields(user);
    await user.click(screen.getByRole('button', { name: 'Live trading' }));
    await user.click(screen.getByLabelText('I confirm this is a LIVE deployment'));
    expect(
      screen.queryByLabelText('I confirm automatic live trading on this schedule'),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Deploy live/ })).toBeEnabled();
  });

  it('re-arms the schedule confirmation when the mode is switched', async () => {
    const user = setup();
    await fillRequiredFields(user);
    await pickSchedule(user, 'Hourly');
    await user.click(screen.getByRole('button', { name: 'Live trading' }));
    await user.click(screen.getByLabelText('I confirm this is a LIVE deployment'));
    await user.click(
      screen.getByLabelText('I confirm automatic live trading on this schedule'),
    );
    await user.click(screen.getByRole('button', { name: 'Paper trading' }));
    await user.click(screen.getByRole('button', { name: 'Live trading' }));

    expect(
      screen.getByLabelText('I confirm automatic live trading on this schedule'),
    ).not.toBeChecked();
    expect(screen.getByRole('button', { name: /Deploy live/ })).toBeDisabled();
  });
});
