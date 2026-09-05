import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  CreatedInstrument,
  CreateInstrumentRequest,
  ListedProduct,
  ProductRow,
  VenueSymbol,
  XrefRow,
} from '../types/refdata';

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

async function fetchVenueSymbols(appId: number): Promise<VenueSymbol[]> {
  const { data } = await apiClient.get<VenueSymbol[]>(
    `/inst/apps/${appId}/venue-symbols`,
  );
  return data;
}

async function createInstrument(
  req: CreateInstrumentRequest,
): Promise<CreatedInstrument> {
  const { data } = await apiClient.post<CreatedInstrument>('/inst/products', req);
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

/**
 * Tickers the venue itself prints, for the one field nothing stored can check.
 *
 * Outside the `['inst', ...]` keys above on purpose: those are platform rows
 * that `useCreateInstrument` invalidates, and this is the exchange's own list,
 * which adding an instrument does not change.
 *
 * `retry: false` because a venue that cannot answer should leave the field as
 * plain free text immediately — the symbol is typeable regardless, and retrying
 * an unreachable exchange only delays the form. Cached for the session: a few
 * thousand markets are one download, and they do not change while a dialog is
 * open.
 */
export const useVenueSymbols = (appId: number | null) =>
  useQuery({
    queryKey: ['venue-symbols', appId],
    queryFn: () => fetchVenueSymbols(appId!),
    enabled: appId != null,
    staleTime: Infinity,
    retry: false,
  });

/**
 * Create a product and the first venue symbol that maps to it.
 *
 * Invalidates every `inst` read because the insert is exactly what changes
 * them: the new product belongs in the product list, and its xref makes it
 * appear in the venue-scoped one a subscription is picked from. Those queries
 * hold `staleTime: Infinity` — nothing else will ever refetch them, so without
 * this the instrument stays invisible until the page is reloaded.
 */
export function useCreateInstrument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createInstrument,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inst'] });
    },
  });
}
