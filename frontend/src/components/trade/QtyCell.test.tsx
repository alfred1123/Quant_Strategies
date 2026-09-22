import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import QtyCell from './QtyCell';
import { useUpdateDeployment } from '../../api/trade';
import type { DeploymentRow } from '../../types/trade';

vi.mock('../../api/trade', () => ({
  useUpdateDeployment: vi.fn(),
}));

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

function setup(row: DeploymentRow) {
  vi.mocked(useUpdateDeployment).mockReturnValue({
    mutateAsync,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateDeployment>);
  const onError = vi.fn();
  render(<QtyCell row={row} onError={onError} />);
  return { onError };
}

function stubConfirm(result: boolean) {
  const fn = vi.fn().mockReturnValue(result);
  window.confirm = fn;
  return fn;
}

async function editQty(value: string) {
  const user = userEvent.setup();
  const input = screen.getByRole('textbox');
  await user.clear(input);
  await user.type(input, value);
  await user.tab();
}

describe('QtyCell', () => {
  beforeEach(() => {
    mutateAsync = vi.fn().mockResolvedValue({});
    vi.mocked(useUpdateDeployment).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the stored quantity', () => {
    setup(deployment());
    expect(screen.getByRole('textbox')).toHaveValue('0.001');
  });

  it('patches the new qty on blur', async () => {
    setup(deployment());
    await editQty('0.002');
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      qty: '0.002',
    });
  });

  it('does not patch when the numeric value already matches', async () => {
    setup(deployment({ qty: '0.10' }));
    await editQty('0.1');
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('rejects a non-positive quantity and restores the stored value', async () => {
    const { onError } = setup(deployment());
    await editQty('0');
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith('Quantity must be greater than 0');
    expect(screen.getByRole('textbox')).toHaveValue('0.001');
  });

  it('refuses a quantity below the venue lot size without a round-trip', async () => {
    const { onError } = setup(deployment({ qty: '0.001', min_qty: 0.001 }));
    await editQty('0.0001');
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(
      'btcusdt.crypto trades in lots of at least 0.001 — the exchange would reject this order.',
    );
    expect(screen.getByRole('textbox')).toHaveValue('0.001');
  });

  it('accepts the venue lot size itself', async () => {
    setup(deployment({ qty: '0.01', min_qty: 0.001 }));
    await editQty('0.001');
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      qty: '0.001',
    });
  });

  it('applies no lot-size rule when the venue limits are not cached', async () => {
    setup(deployment({ qty: '0.001', min_qty: null }));
    await editQty('0.0001');
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      qty: '0.0001',
    });
  });

  it('shows the venue minimum on the input', () => {
    setup(deployment({ min_qty: 0.001 }));
    expect(screen.getByRole('textbox')).toHaveAttribute(
      'title',
      'Venue minimum 0.001',
    );
  });

  it('reverts on Escape without patching', async () => {
    setup(deployment());
    const user = userEvent.setup();
    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, '0.009');
    await user.keyboard('{Escape}');
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(input).toHaveValue('0.001');
  });

  it('confirms before changing qty on a live deployment', async () => {
    const confirm = stubConfirm(true);
    setup(deployment({ is_paper_ind: 'N' }));
    await editQty('0.002');
    expect(confirm).toHaveBeenCalled();
    expect(mutateAsync).toHaveBeenCalledWith({
      deploymentId: 'dep-1',
      qty: '0.002',
    });
  });

  it('leaves a live deployment alone when the confirmation is declined', async () => {
    stubConfirm(false);
    setup(deployment({ is_paper_ind: 'N' }));
    await editQty('0.002');
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox')).toHaveValue('0.001');
  });

  it('does not confirm a paper deployment', async () => {
    const confirm = stubConfirm(true);
    setup(deployment({ is_paper_ind: 'Y' }));
    await editQty('0.002');
    expect(confirm).not.toHaveBeenCalled();
    expect(mutateAsync).toHaveBeenCalled();
  });

  it('surfaces a failed change through onError', async () => {
    mutateAsync = vi.fn().mockRejectedValue(new Error('qty below minimum'));
    const { onError } = setup(deployment());
    await editQty('0.002');
    expect(onError).toHaveBeenCalledWith('qty below minimum');
    expect(screen.getByRole('textbox')).toHaveValue('0.001');
  });
});
