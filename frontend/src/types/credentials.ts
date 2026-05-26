/** Broker credential row — mirrors future ``/api/v1/credentials`` (Phase 1.5). */

export type TradingMode = 'paper' | 'live';

export interface BrokerAccount {
  api_credential_id: number;
  app_id: number;
  /** REFDATA.APP display name, e.g. Bybit, Futu */
  broker_name: string;
  label: string;
  /** Whether this credential is for testnet / paper endpoints */
  is_paper_ind: 'Y' | 'N';
  api_key_masked: string;
  is_active_ind: 'Y' | 'N';
}

export const ALL_BROKERS = 'all' as const;
export const ALL_ACCOUNTS = 'all' as const;

export type BrokerFilter = typeof ALL_BROKERS | string;
export type AccountFilter = typeof ALL_ACCOUNTS | number;
