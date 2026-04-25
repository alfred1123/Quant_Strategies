import {
  Autocomplete, Box, FormControl, InputLabel, MenuItem, Select, Stack, TextField, Typography,
} from '@mui/material';
import { useProductXrefs } from '../../api/inst';
import type { AppRow, ProductRow } from '../../types/refdata';

/**
 * Neutral camelCase shape used by the shared selector. Both the trading
 * config (BacktestConfig.symbol/vendorSymbol/dataSource) and each factor
 * (FactorConfig.symbol/vendor_symbol/data_source) adapt to this at the
 * call site.
 */
export interface ProductSelectorValue {
  symbol?: string;        // internal_cusip
  vendorSymbol?: string;  // vendor symbol override
  dataSource?: string;    // app.name
}

interface Props {
  value: ProductSelectorValue;
  onChange: (patch: Partial<ProductSelectorValue>) => void;
  products: ProductRow[];
  apps: AppRow[];
  /** Optional side-effect when a product is picked from the dropdown
   *  (used by the trading row to also auto-set asset type). */
  onProductPicked?: (product: ProductRow) => void;
  productWidth?: number;
  vendorWidth?: number;
  dataSourceWidth?: number;
}

/**
 * Single source of truth for the Product / Data Source / Vendor Symbol
 * triplet. Used by both the trading row and every factor row in
 * ConfigDrawer. Any UI / behavior change goes here only.
 *
 * Behavior contract:
 *   - Picking a Product clears VendorSymbol (resolved from xrefs instead).
 *   - Typing in Product clears VendorSymbol (free-solo raw text).
 *   - Picking or typing in VendorSymbol clears Product (vendor wins).
 *   - When a Product is selected and Data Source is set, the displayed
 *     vendor symbol is resolved from the xref table; user can override
 *     by typing in the Vendor Symbol box.
 */
export default function ProductSelector({
  value, onChange, products, apps, onProductPicked,
  productWidth = 300, vendorWidth = 200, dataSourceWidth = 150,
}: Props) {
  const selectedProduct = products.find(p => p.internal_cusip === value.symbol) ?? null;
  const productInputValue = selectedProduct
    ? `${selectedProduct.display_nm} (${selectedProduct.internal_cusip})`
    : (value.symbol ?? '');

  const { data: xrefs = [] } = useProductXrefs(selectedProduct?.product_id ?? null);
  const resolvedVendor = xrefs.find(x => {
    const app = apps.find(a => a.name === value.dataSource);
    return app && x.app_id === app.app_id;
  })?.vendor_symbol ?? '';

  const vendorOptions = xrefs.map(x => x.vendor_symbol);
  const displayedVendor = value.vendorSymbol || resolvedVendor;

  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Autocomplete<ProductRow, false, false, true>
        size="small" freeSolo sx={{ width: productWidth }}
        slotProps={{ listbox: { sx: { maxHeight: 360, minWidth: 320 } } }}
        options={products}
        value={selectedProduct}
        inputValue={productInputValue}
        getOptionLabel={(opt) => typeof opt === 'string' ? opt : `${opt.display_nm} (${opt.internal_cusip})`}
        isOptionEqualToValue={(opt, val) => {
          if (typeof opt === 'string' || typeof val === 'string') return opt === val;
          return opt.internal_cusip === val.internal_cusip;
        }}
        onChange={(_, val) => {
          if (!val) {
            onChange({ symbol: undefined, vendorSymbol: undefined });
          } else if (typeof val === 'string') {
            onChange({ symbol: val, vendorSymbol: undefined });
          } else {
            onChange({ symbol: val.internal_cusip, vendorSymbol: undefined });
            onProductPicked?.(val);
          }
        }}
        onInputChange={(_, val, reason) => {
          if (reason === 'input') onChange({ symbol: val, vendorSymbol: undefined });
        }}
        renderInput={(params) => <TextField {...params} label="Product" />}
        renderOption={(props, opt) => (
          <li {...props} key={opt.internal_cusip}>
            <Box>
              <Typography variant="body2">{opt.display_nm}</Typography>
              <Typography variant="caption" color="text.secondary">{opt.internal_cusip}</Typography>
            </Box>
          </li>
        )}
      />
      <FormControl size="small" sx={{ width: dataSourceWidth }}>
        <InputLabel>Data Source</InputLabel>
        <Select
          value={value.dataSource ?? ''}
          label="Data Source"
          onChange={e => onChange({ dataSource: e.target.value || undefined })}
        >
          {apps.map(a => (
            <MenuItem key={a.app_id} value={a.name}>{a.display_name}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <Autocomplete<string, false, false, true>
        size="small" freeSolo sx={{ width: vendorWidth }}
        options={vendorOptions}
        value={displayedVendor || null}
        inputValue={displayedVendor}
        onInputChange={(_, val, reason) => {
          // Typing a vendor symbol clears the product (vendor wins).
          if (reason === 'input') onChange({ vendorSymbol: val || undefined, symbol: undefined });
        }}
        onChange={(_, val) => {
          if (!val) onChange({ vendorSymbol: undefined, symbol: undefined });
          else onChange({ vendorSymbol: val, symbol: undefined });
        }}
        renderInput={(params) => (
          <TextField {...params} label="Vendor Symbol" slotProps={{ inputLabel: { shrink: true } }} />
        )}
      />
    </Stack>
  );
}
