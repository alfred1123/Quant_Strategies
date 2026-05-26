import { useQuery } from '@tanstack/react-query';
import type { BrokerAccount } from '../types/credentials';

export const CREDENTIALS_QUERY_KEY = ['credentials'] as const;

/** Phase 1.5 — returns saved broker accounts for the current user. */
async function listCredentials(): Promise<BrokerAccount[]> {
  // Stub until GET /api/v1/credentials is implemented.
  return [];
}

export function useBrokerAccounts() {
  return useQuery({
    queryKey: CREDENTIALS_QUERY_KEY,
    queryFn: listCredentials,
  });
}
