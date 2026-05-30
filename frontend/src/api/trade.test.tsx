import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useDeployments } from './trade';
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
          internal_cusip: 'btc-usd.crypto',
          qty: '0.01',
          is_paper_ind: 'Y',
          is_enabled_ind: 'Y',
          deployment_status: 'CREATED',
          user_id: 'alice',
          created_at: '2026-05-20T12:00:00Z',
        },
      ],
    });

    const { result } = renderHook(() => useDeployments(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith('/trade/deployments');
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].internal_cusip).toBe('btc-usd.crypto');
  });
});
