import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { CreateDeploymentRequest, DeploymentRow } from '../types/trade';

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

export { getDeployment, listDeployments, createDeployment };
