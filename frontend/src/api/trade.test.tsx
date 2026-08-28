import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useAccountSnapshot, useDeployments } from './trade';
import { apiClient } from './client';

vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number | null;
    constructor(message: string, status: number | null) {
      super(message);
      this.status = status;
    }
  },
}));

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useDeployments', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
  });

  it('fetches /trade/deployments', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [
        {
          deployment_id: '11111111-1111-1111-1111-111111111111',
          deployment_vid: 1,
          app_user_id: '22222222-2222-2222-2222-222222222222',
          strategy_id: '33333333-3333-3333-3333-333333333333',
          strategy_vid: 1,
          api_credential_id: 1,
          app_id: 10,
          internal_cusip: 'btcusdt.crypto',
          qty: '0.01',
          is_paper_ind: 'Y',
          is_enabled_ind: 'Y',
          deployment_status: 'CREATED',
          transact_from_ts: '2026-05-20T12:00:00Z',
          user_id: 'alice',
        },
      ],
    });

    const { result } = renderHook(() => useDeployments(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith('/trade/deployments');
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].internal_cusip).toBe('btcusdt.crypto');
  });
});

describe('useAccountSnapshot', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
  });

  const snapshot = {
    api_credential_id: 7,
    app_id: 34,
    paper: true,
    balances: [{ code: 'USDT', free: 900, used: 100, total: 1000 }],
    positions: [],
  };

  it('fetches the snapshot for a credential with the paper flag', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: snapshot });

    const { result } = renderHook(() => useAccountSnapshot(7, true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith('/trade/accounts/7/snapshot', {
      params: { paper: true },
    });
    expect(result.current.data?.balances[0].total).toBe(1000);
  });

  it('does not call the exchange until an account is chosen', async () => {
    renderHook(() => useAccountSnapshot(null, true), { wrapper: createWrapper() });

    expect(apiClient.get).not.toHaveBeenCalled();
  });

  it('keys paper and live separately so the two do not share a cache entry', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: snapshot });
    const wrapper = createWrapper();

    const paperHook = renderHook(() => useAccountSnapshot(7, true), { wrapper });
    await waitFor(() => expect(paperHook.result.current.isSuccess).toBe(true));

    const liveHook = renderHook(() => useAccountSnapshot(7, false), { wrapper });
    await waitFor(() => expect(liveHook.result.current.isSuccess).toBe(true));

    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(vi.mocked(apiClient.get).mock.calls[1][1]).toEqual({
      params: { paper: false },
    });
  });
});
