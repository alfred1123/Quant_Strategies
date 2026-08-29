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
  schedule_tm_interval_id?: number | null;
  last_run_at?: string | null;
  next_due_at?: string | null;
  transact_from_ts: string;
  user_id: string;
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
  /** REFDATA.TM_INTERVAL id; null = manual apply only. */
  schedule_tm_interval_id?: number | null;
}

export interface UpdateDeploymentRequest {
  enabled?: boolean;
  deployment_status?: DeploymentStatus;
  /**
   * REFDATA.TM_INTERVAL id. Send an explicit null to drop back to manual —
   * the backend distinguishes that from an omitted field, which leaves the
   * existing schedule untouched.
   */
  schedule_tm_interval_id?: number | null;
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

/** One currency's cash on a broker account. */
export interface BalanceRow {
  code: string;
  free: number | null;
  used: number | null;
  total: number | null;
}

/** One open position, as the exchange reports it. */
export interface PositionRow {
  /** Raw exchange symbol (e.g. BTCUSDT) — matches INST.PRODUCT_XREF. */
  symbol: string;
  unified_symbol: string | null;
  /** Signed: positive long, negative short. */
  qty: number;
  side: string | null;
  entry_price: number | null;
  mark_price: number | null;
  notional: number | null;
  unrealized_pnl: number | null;
  leverage: number | null;
  liquidation_price: number | null;
}

/**
 * Live broker state for one credential. Every field comes from the exchange,
 * nothing from our tables — it shows what is actually held, including
 * positions opened by hand or left by a stopped deployment.
 */
export interface AccountSnapshot {
  api_credential_id: number;
  app_id: number;
  paper: boolean;
  balances: BalanceRow[];
  positions: PositionRow[];
}

/** One TRADE.EXECUTION_EVENT row — order attempt / HOLD diary entry. */
export interface ExecutionEventRow {
  execution_event_id: string;
  deployment_id: string;
  deployment_vid: number;
  internal_cusip: string;
  api_credential_id: number;
  app_id: number;
  is_paper_ind: 'Y' | 'N';
  signal_value: string | null;
  position_qty: string | null;
  buy_sell_cd: string;
  quantity: string | null;
  vendor_order_id: string | null;
  is_success_ind: 'Y' | 'N';
  transact_at: string;
}

/** One TRADE.TRANSACTION row — broker-confirmed fill. */
export interface TransactionRow {
  transaction_id: string;
  deployment_id: string;
  deployment_vid: number;
  internal_cusip: string;
  api_credential_id: number;
  app_id: number;
  is_paper_ind: 'Y' | 'N';
  vendor_symbol: string | null;
  buy_sell_cd: string;
  quantity: string | null;
  price: string | null;
  notional_amt: string | null;
  fee_amt: string | null;
  vendor_order_id: string | null;
  trans_ccy_cd: string;
  filled_at: string;
}
