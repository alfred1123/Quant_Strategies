import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { ProductRow } from '../types/refdata';

async function fetchProducts(): Promise<ProductRow[]> {
  const { data } = await apiClient.get<ProductRow[]>('/inst/products');
  return data;
}

export const useProducts = () =>
  useQuery({
    queryKey: ['inst', 'products'],
    queryFn: fetchProducts,
    staleTime: Infinity,
  });
