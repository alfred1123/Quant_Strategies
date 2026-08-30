import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { ListedProduct, ProductRow, XrefRow } from '../types/refdata';

async function fetchProducts(): Promise<ProductRow[]> {
  const { data } = await apiClient.get<ProductRow[]>('/inst/products');
  return data;
}

async function fetchProductXrefs(productId: number): Promise<XrefRow[]> {
  const { data } = await apiClient.get<XrefRow[]>(`/inst/products/${productId}/xrefs`);
  return data;
}

async function fetchAppProducts(appId: number): Promise<ListedProduct[]> {
  const { data } = await apiClient.get<ListedProduct[]>(`/inst/apps/${appId}/products`);
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

/** Only what this venue lists — the full product list is not a useful offer. */
export const useAppProducts = (appId: number | null) =>
  useQuery({
    queryKey: ['inst', 'apps', appId, 'products'],
    queryFn: () => fetchAppProducts(appId!),
    enabled: appId != null,
    staleTime: Infinity,
  });
