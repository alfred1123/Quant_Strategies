import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { BrokerAccount, CreateCredentialPayload, RotateCredentialPayload } from '../types/credentials';

export const CREDENTIALS_QUERY_KEY = ['credentials'] as const;

interface CredentialListResponse {
  credentials: BrokerAccount[];
}

async function listCredentials(): Promise<BrokerAccount[]> {
  const { data } = await apiClient.get<CredentialListResponse>('/credentials');
  return data.credentials;
}

export function useBrokerAccounts() {
  return useQuery({
    queryKey: CREDENTIALS_QUERY_KEY,
    queryFn: listCredentials,
  });
}

export function useCreateCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CreateCredentialPayload) => {
      const { data } = await apiClient.post<BrokerAccount>('/credentials', payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CREDENTIALS_QUERY_KEY }),
  });
}

export function useRotateCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ api_credential_id, ...body }: RotateCredentialPayload & { api_credential_id: number }) => {
      const { data } = await apiClient.put<BrokerAccount>(`/credentials/${api_credential_id}`, body);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CREDENTIALS_QUERY_KEY }),
  });
}

export function useRevokeCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (api_credential_id: number) => {
      await apiClient.delete(`/credentials/${api_credential_id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CREDENTIALS_QUERY_KEY }),
  });
}
