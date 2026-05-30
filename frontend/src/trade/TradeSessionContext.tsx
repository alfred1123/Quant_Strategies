import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { AccountFilter, BrokerAccount, BrokerFilter, TradingMode } from '../types/credentials';
import { ALL_ACCOUNTS, ALL_BROKERS } from '../types/credentials';
import { useBrokerAccounts } from '../api/credentials';
import { useApps } from '../api/refdata';

interface TradeSessionState {
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

const TradeSessionContext = createContext<TradeSessionState | null>(null);

export function TradeSessionProvider({ children }: { children: ReactNode }) {
  const { data: accounts = [], isLoading: accountsLoading } = useBrokerAccounts();
  const { data: apps = [] } = useApps();
  const [brokerFilter, setBrokerFilterRaw] = useState<BrokerFilter>(ALL_BROKERS);
  const [accountFilter, setAccountFilterRaw] = useState<AccountFilter>(ALL_ACCOUNTS);
  const [tradingMode, setTradingMode] = useState<TradingMode>('paper');

  const appNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const a of apps) map.set(a.app_id, a.display_name);
    return map;
  }, [apps]);

  const brokerOptions = useMemo(() => {
    const names = [...new Set(accounts.map(a => appNameById.get(a.app_id) ?? `App ${a.app_id}`))].sort();
    return names.map(name => ({ value: name, label: name }));
  }, [accounts, appNameById]);

  const accountOptions = useMemo(() => {
    let list = accounts;
    if (brokerFilter !== ALL_BROKERS) {
      list = list.filter(a => (appNameById.get(a.app_id) ?? `App ${a.app_id}`) === brokerFilter);
    }
    return list.map(a => ({
      value: a.api_credential_id,
      label: a.label,
      brokerLabel: appNameById.get(a.app_id) ?? `App ${a.app_id}`,
    }));
  }, [accounts, brokerFilter, appNameById]);

  const setBrokerFilter = useCallback(
    (v: BrokerFilter) => {
      setBrokerFilterRaw(v);
      setAccountFilterRaw(ALL_ACCOUNTS);
    },
    [],
  );

  const setAccountFilter = useCallback((v: AccountFilter) => {
    setAccountFilterRaw(v);
  }, []);

  const selectedAccount = useMemo(() => {
    if (accountFilter === ALL_ACCOUNTS) return null;
    return accounts.find(a => a.api_credential_id === accountFilter) ?? null;
  }, [accounts, accountFilter]);

  const value = useMemo(
    (): TradeSessionState => ({
      brokerFilter,
      accountFilter,
      tradingMode,
      accounts,
      accountsLoading,
      brokerOptions,
      accountOptions,
      setBrokerFilter,
      setAccountFilter,
      setTradingMode,
      selectedAccount,
      appNameById,
    }),
    [
      brokerFilter,
      accountFilter,
      tradingMode,
      accounts,
      accountsLoading,
      brokerOptions,
      accountOptions,
      setBrokerFilter,
      setAccountFilter,
      selectedAccount,
      appNameById,
    ],
  );

  return (
    <TradeSessionContext.Provider value={value}>{children}</TradeSessionContext.Provider>
  );
}

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
