/** Broker credential row — mirrors ``/api/v1/credentials`` response. */

export type TradingMode = 'paper' | 'live';

export interface BrokerAccount {
  api_credential_id: number;
  api_credential_vid: number;
  app_id: number;
  label: string;
  api_key_masked: string;
  is_active_ind: 'Y' | 'N';
}

export interface CreateCredentialPayload {
  app_id: number;
  label: string;
  api_key: string;
  api_secret: string;
}

export interface RotateCredentialPayload {
  api_credential_id: number;
  api_key: string;
  api_secret: string;
}

export const ALL_BROKERS = 'all' as const;
export const ALL_ACCOUNTS = 'all' as const;

export type BrokerFilter = typeof ALL_BROKERS | string;
export type AccountFilter = typeof ALL_ACCOUNTS | number;
