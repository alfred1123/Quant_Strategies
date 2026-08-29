import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  AccountSnapshot,
  ApplyReport,
  CreateDeploymentRequest,
  DeploymentRow,
  DryRunReport,
  DryRunRequest,
  ExecutionEventRow,
  TransactionRow,
  UpdateDeploymentRequest,
} from '../types/trade';

export const DEPLOYMENTS_QUERY_KEY = ['trade', 'deployments'] as const;

export const ACCOUNT_SNAPSHOT_QUERY_KEY = ['trade', 'account-snapshot'] as const;

export const EXECUTION_EVENTS_QUERY_KEY = ['trade', 'execution-events'] as const;

export const TRANSACTIONS_QUERY_KEY = ['trade', 'transactions'] as const;

async function listDeployments(): Promise<DeploymentRow[]> {
  const { data } = await apiClient.get<DeploymentRow[]>('/trade/deployments');
  return data;
}

async function createDeployment(req: CreateDeploymentRequest): Promise<DeploymentRow> {
  const { data } = await apiClient.post<DeploymentRow>('/trade/deployments', req);
  return data;
}

async function getDeployment(deploymentId: string): Promise<DeploymentRow> {
  const { data } = await apiClient.get<DeploymentRow>(`/trade/deployments/${deploymentId}`);
  return data;
}

async function dryRunDeployment(req: DryRunRequest): Promise<DryRunReport> {
  const { data } = await apiClient.post<DryRunReport>('/trade/deployments/dry-run', req);
  return data;
}

async function applyDeployment(deploymentId: string): Promise<ApplyReport> {
  const { data } = await apiClient.post<ApplyReport>(
    `/trade/deployments/${deploymentId}/apply`,
  );
  return data;
}

async function updateDeployment(
  deploymentId: string,
  req: UpdateDeploymentRequest,
): Promise<DeploymentRow> {
  const { data } = await apiClient.patch<DeploymentRow>(
    `/trade/deployments/${deploymentId}`,
    req,
  );
  return data;
}

async function stopDeployment(deploymentId: string): Promise<DeploymentRow> {
  const { data } = await apiClient.post<DeploymentRow>(
    `/trade/deployments/${deploymentId}/stop`,
  );
  return data;
}

async function fetchAccountSnapshot(
  apiCredentialId: number,
  paper: boolean,
): Promise<AccountSnapshot> {
  const { data } = await apiClient.get<AccountSnapshot>(
    `/trade/accounts/${apiCredentialId}/snapshot`,
    { params: { paper } },
  );
  return data;
}

async function listExecutionEvents(limit = 50): Promise<ExecutionEventRow[]> {
  const { data } = await apiClient.get<ExecutionEventRow[]>('/trade/execution-events', {
    params: { limit },
  });
  return data;
}

async function listTransactions(limit = 50): Promise<TransactionRow[]> {
  const { data } = await apiClient.get<TransactionRow[]>('/trade/transactions', {
    params: { limit },
  });
  return data;
}

/** Current user's open deployment rows (Phase 1.2). */
export function useDeployments() {
  return useQuery({
    queryKey: DEPLOYMENTS_QUERY_KEY,
    queryFn: listDeployments,
  });
}

export function useCreateDeployment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createDeployment,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DEPLOYMENTS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: EXECUTION_EVENTS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: TRANSACTIONS_QUERY_KEY });
    },
  });
}

export function useDryRun() {
  return useMutation({ mutationFn: dryRunDeployment });
}

export function useApplyDeployment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: applyDeployment,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DEPLOYMENTS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: EXECUTION_EVENTS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: TRANSACTIONS_QUERY_KEY });
    },
  });
}

export function useUpdateDeployment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deploymentId, ...req }: UpdateDeploymentRequest & { deploymentId: string }) =>
      updateDeployment(deploymentId, req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DEPLOYMENTS_QUERY_KEY });
    },
  });
}

export function useStopDeployment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: stopDeployment,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DEPLOYMENTS_QUERY_KEY });
    },
  });
}

/**
 * Live balances and open positions for one broker account.
 *
 * Each call is a rate-limited exchange round-trip with no server-side cache, so
 * it does not poll: a 30s stale window plus refetch-on-focus, and the panel
 * offers an explicit refresh. Disabled until a credential is chosen.
 */
export function useAccountSnapshot(
  apiCredentialId: number | null,
  paper: boolean,
) {
  return useQuery({
    queryKey: [...ACCOUNT_SNAPSHOT_QUERY_KEY, apiCredentialId, paper],
    queryFn: () => fetchAccountSnapshot(apiCredentialId as number, paper),
    enabled: apiCredentialId !== null,
    staleTime: 30_000,
    retry: false,
  });
}

/** Recent order attempts — respects toolbar filters client-side. */
export function useExecutionEvents(limit = 50) {
  return useQuery({
    queryKey: [...EXECUTION_EVENTS_QUERY_KEY, limit],
    queryFn: () => listExecutionEvents(limit),
    staleTime: 15_000,
    refetchInterval: 60_000,
  });
}

/** Recent broker-confirmed fills — respects toolbar filters client-side. */
export function useTransactions(limit = 50) {
  return useQuery({
    queryKey: [...TRANSACTIONS_QUERY_KEY, limit],
    queryFn: () => listTransactions(limit),
    staleTime: 15_000,
    refetchInterval: 60_000,
  });
}

export { getDeployment, listDeployments, createDeployment, fetchAccountSnapshot };
