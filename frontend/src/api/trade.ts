import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  ApplyReport,
  CreateDeploymentRequest,
  DeploymentRow,
  DryRunReport,
  DryRunRequest,
  UpdateDeploymentRequest,
} from '../types/trade';

export const DEPLOYMENTS_QUERY_KEY = ['trade', 'deployments'] as const;

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

export { getDeployment, listDeployments, createDeployment };
