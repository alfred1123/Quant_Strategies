import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { ProductRow, XrefRow } from '../types/refdata';

async function fetchProducts(): Promise<ProductRow[]> {
  const { data } = await apiClient.get<ProductRow[]>('/inst/products');
  return data;
}

async function fetchProductXrefs(productId: number): Promise<XrefRow[]> {
  const { data } = await apiClient.get<XrefRow[]>(`/inst/products/${productId}/xrefs`);
  return data;
}

export const useProducts = () =>
  useQuery({
    queryKey: ['inst', 'products'],
    queryFn: fetchProducts,
    staleTime: Infinity,
  });

export const useProductXrefs = (productId: number | null) =>
  useQuery({
    queryKey: ['inst', 'xrefs', productId],
    queryFn: () => fetchProductXrefs(productId!),
    enabled: productId != null,
    staleTime: Infinity,
  });
