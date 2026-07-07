import { createContext, useCallback, useContext, useMemo } from 'react';
import type { AccountFilter, BrokerAccount, BrokerFilter, TradingMode } from '../types/credentials';
import { ALL_ACCOUNTS, ALL_BROKERS } from '../types/credentials';

export interface TradeSessionState {
  brokerFilter: BrokerFilter;
  accountFilter: AccountFilter;
  tradingMode: TradingMode;
  accounts: BrokerAccount[];
  accountsLoading: boolean;
  brokerOptions: { value: string; label: string }[];
  accountOptions: { value: number; label: string; brokerLabel: string }[];
  setBrokerFilter: (v: BrokerFilter) => void;
  setAccountFilter: (v: AccountFilter) => void;
  setTradingMode: (v: TradingMode) => void;
  selectedAccount: BrokerAccount | null;
  /** REFDATA display_name lookup by app_id */
  appNameById: Map<number, string>;
}

export const TradeSessionContext = createContext<TradeSessionState | null>(null);

export function useTradeSession(): TradeSessionState {
  const ctx = useContext(TradeSessionContext);
  if (!ctx) {
    throw new Error('useTradeSession must be used within TradeSessionProvider');
  }
  return ctx;
}

/** Filter deployments / log rows by layout account + paper/live selection. */
export function useTradeSessionFilters() {
  const { accountFilter, tradingMode, brokerFilter, accounts, appNameById } = useTradeSession();

  const accountsByCredId = useMemo(() => {
    const map = new Map<number, BrokerAccount>();
    for (const a of accounts) map.set(a.api_credential_id, a);
    return map;
  }, [accounts]);

  const matchesSession = useCallback(
    (row: { api_credential_id: number; is_paper_ind: 'Y' | 'N'; app_id?: number }) => {
      if (accountFilter !== ALL_ACCOUNTS && row.api_credential_id !== accountFilter) {
        return false;
      }
      if (brokerFilter !== ALL_BROKERS) {
        const acct = accountsByCredId.get(row.api_credential_id);
        if (!acct) return false;
        const brokerName = appNameById.get(acct.app_id) ?? `App ${acct.app_id}`;
        if (brokerName !== brokerFilter) return false;
      }
      const wantPaper = tradingMode === 'paper';
      const rowPaper = row.is_paper_ind === 'Y';
      return wantPaper === rowPaper;
    },
    [accountFilter, brokerFilter, tradingMode, accountsByCredId, appNameById],
  );

  /** True when the credential lookup table is empty — filters may be inaccurate. */
  const credentialsNotLoaded = accounts.length === 0;

  return { accountFilter, tradingMode, brokerFilter, matchesSession, credentialsNotLoaded };
}
