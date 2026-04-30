import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { useIndicators, useSignalTypes, useAssetTypes, useConjunctions, useDataColumns, useApps } from './refdata';
import { apiClient } from './client';

vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    defaults: { baseURL: '/api/v1' },
  },
}));

const mockedGet = vi.mocked(apiClient.get);

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => vi.clearAllMocks());

const hookTable: [string, typeof useIndicators][] = [
  ['useIndicators', useIndicators],
  ['useSignalTypes', useSignalTypes],
  ['useAssetTypes', useAssetTypes],
  ['useConjunctions', useConjunctions],
  ['useDataColumns', useDataColumns],
  ['useApps', useApps],
];

describe.each(hookTable)('%s', (_name, hook) => {
  it('fetches data via apiClient.get', async () => {
    const rows = [{ id: 1 }];
    mockedGet.mockResolvedValue({ data: rows });

    const { result } = renderHook(hook, { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(rows);
  });
});
