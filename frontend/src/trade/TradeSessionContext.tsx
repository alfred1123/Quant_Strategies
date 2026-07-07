import {
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { AccountFilter, BrokerFilter, TradingMode } from '../types/credentials';
import { ALL_ACCOUNTS, ALL_BROKERS } from '../types/credentials';
import { useBrokerAccounts } from '../api/credentials';
import { useApps } from '../api/refdata';
import { TradeSessionContext, type TradeSessionState } from './useTradeSession';

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
