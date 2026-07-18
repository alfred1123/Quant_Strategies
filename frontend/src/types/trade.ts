/** Mirrors ``quant/schemas/deployments.py`` — Phase 1.2+. */

export type DeploymentStatus = 'CREATED' | 'ACTIVE' | 'PAUSED' | 'STOPPED';

export type IntendedAction = 'BUY' | 'SELL' | 'HOLD' | 'OPEN_SHORT' | 'CLOSE_SHORT';

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
  confirm_live?: boolean;
  enabled?: boolean;
  deployment_status?: DeploymentStatus;
}

export interface UpdateDeploymentRequest {
  enabled?: boolean;
  deployment_status?: DeploymentStatus;
}

export interface DryRunRequest {
  strategy_id: string;
  strategy_vid: number;
  api_credential_id: number;
  app_id: number;
  internal_cusip: string;
  qty: string;
  paper?: boolean;
}

export interface DryRunReport {
  strategy_id: string;
  strategy_vid: number;
  strategy_nm: string;
  internal_cusip: string;
  vendor_symbol: string;
  app_id: number;
  paper: boolean;
  qty: string;
  signal: number;
  intended_side: IntendedAction;
  position_qty: number;
  data_as_of: string;
  notional: number | null;
}

export interface ApplyReport {
  deployment_id: string;
  deployment_vid: number;
  action: IntendedAction;
  vendor_symbol: string;
  signal: number;
  position_qty: number;
  order_success: boolean | null;
  vendor_order_id: string | null;
  filled_qty: number | null;
  avg_price: number | null;
  fee: number | null;
  message: string;
}
