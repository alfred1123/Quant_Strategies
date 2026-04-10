import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { IndicatorRow, SignalTypeRow, AssetTypeRow, ConjunctionRow } from '../types/refdata';

async function fetchTable<T>(table: string): Promise<T[]> {
  const { data } = await apiClient.get<T[]>(`/refdata/${table}`);
  return data;
}

export const useIndicators = () =>
  useQuery({
    queryKey: ['refdata', 'indicator'],
    queryFn: () => fetchTable<IndicatorRow>('indicator'),
    staleTime: Infinity,
  });

export const useSignalTypes = () =>
  useQuery({
    queryKey: ['refdata', 'signal_type'],
    queryFn: () => fetchTable<SignalTypeRow>('signal_type'),
    staleTime: Infinity,
  });

export const useAssetTypes = () =>
  useQuery({
    queryKey: ['refdata', 'asset_type'],
    queryFn: () => fetchTable<AssetTypeRow>('asset_type'),
    staleTime: Infinity,
  });

export const useConjunctions = () =>
  useQuery({
    queryKey: ['refdata', 'conjunction'],
    queryFn: () => fetchTable<ConjunctionRow>('conjunction'),
    staleTime: Infinity,
  });
