/** Mirrors ``quant/schemas/deployments.py`` — Phase 1.2. */

export type DeploymentStatus = 'CREATED' | 'ACTIVE' | 'PAUSED' | 'STOPPED';

export interface DeploymentRow {
  deployment_id: string;
  deployment_vid: number;
  app_user_id: string;
  strategy_id: string;
  strategy_vid: number;
  api_credential_id: number;
  app_id: number;
  internal_cusip: string;
  qty: string;
  is_paper_ind: 'Y' | 'N';
  is_enabled_ind: 'Y' | 'N';
  deployment_status: string;
  user_id: string;
  created_at: string;
}

export interface CreateDeploymentRequest {
  deployment_id?: string;
  strategy_id: string;
  strategy_vid: number;
  api_credential_id: number;
  app_id: number;
  internal_cusip: string;
  qty: string;
  paper?: boolean;
  enabled?: boolean;
  deployment_status?: DeploymentStatus;
}
