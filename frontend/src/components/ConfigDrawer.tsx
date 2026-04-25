import React from 'react';
import {
  Drawer, Box, Typography, TextField, Select, MenuItem, Autocomplete,
  FormControl, InputLabel, Button, Divider, IconButton, Stack, CircularProgress,
  FormControlLabel, Checkbox, Slider, Alert,
} from '@mui/material';
import { useIndicators, useSignalTypes, useAssetTypes, useConjunctions, useDataColumns, useApps } from '../api/refdata';
import { useProducts, useProductXrefs } from '../api/inst';
import type { ProductRow, AssetTypeRow, AppRow } from '../types/refdata';
import { countSteps } from '../utils/grid';
import type { BacktestConfig, FactorConfig, RangeParam } from '../types/backtest';

/** Self-contained row for factor Product / Data Source / Vendor Symbol with own xref hook. */
function FactorProductRow({
  factor, index, products, apps, updateFactor,
}: {
  factor: FactorConfig;
  index: number;
  products: ProductRow[];
  apps: AppRow[];
  updateFactor: (i: number, patch: Partial<FactorConfig>) => void;
}) {
  const factorProduct = products.find(p => p.internal_cusip === factor.symbol) ?? null;
  const { data: factorXrefs = [] } = useProductXrefs(factorProduct?.product_id ?? null);
  const factorVendorOptions = factorXrefs.map(x => x.vendor_symbol);
  const resolvedFactorVendor = factorXrefs.find(x => {
    const app = apps.find(a => a.name === factor.data_source);
    return app && x.app_id === app.app_id;
  })?.vendor_symbol ?? '';
  const displayedFactorVendor = factor.vendor_symbol || resolvedFactorVendor;

  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Autocomplete<ProductRow, false, false, true>
        size="small" freeSolo sx={{ width: 300 }}
        slotProps={{ listbox: { sx: { maxHeight: 360, minWidth: 320 } } }}
        options={products}
        value={factorProduct}
        inputValue={
          (() => {
            const fp = products.find(p => p.internal_cusip === factor.symbol);
            return fp ? `${fp.display_nm} (${fp.internal_cusip})` : (factor.symbol || '');
          })()
        }
        getOptionLabel={(opt) => typeof opt === 'string' ? opt : `${opt.display_nm} (${opt.internal_cusip})`}
        isOptionEqualToValue={(opt, val) => opt.internal_cusip === val.internal_cusip}
        onChange={(_, val) => {
          if (!val) updateFactor(index, { symbol: undefined, vendor_symbol: undefined });
          else if (typeof val === 'string') updateFactor(index, { symbol: val, vendor_symbol: undefined });
          else updateFactor(index, { symbol: val.internal_cusip, vendor_symbol: undefined });
        }}
        onInputChange={(_, val, reason) => {
          if (reason === 'input') updateFactor(index, { symbol: val, vendor_symbol: undefined });
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
      <FormControl size="small" sx={{ width: 150 }}>
        <InputLabel>Data Source</InputLabel>
        <Select
          value={factor.data_source || ''}
          label="Data Source"
          onChange={e => updateFactor(index, { data_source: e.target.value || undefined })}
        >
          {apps.map(a => (
            <MenuItem key={a.app_id} value={a.name}>{a.display_name}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <Autocomplete<string, false, false, true>
        size="small" freeSolo sx={{ width: 200 }}
        options={factorVendorOptions}
        value={displayedFactorVendor || null}
        inputValue={displayedFactorVendor}
        onInputChange={(_, val, reason) => {
          // Typing a vendor symbol clears the factor product (mirrors trading-row behavior).
          if (reason === 'input') updateFactor(index, { vendor_symbol: val || undefined, symbol: undefined });
        }}
        onChange={(_, val) => {
          if (!val) updateFactor(index, { vendor_symbol: undefined, symbol: undefined });
          else updateFactor(index, { vendor_symbol: val, symbol: undefined });
        }}
        renderInput={(params) => <TextField {...params} label="Vendor Symbol" slotProps={{ inputLabel: { shrink: true } }} />}
      />
    </Stack>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  config: BacktestConfig;
  onChange: (c: BacktestConfig) => void;
  onRun: () => void;
  isRunning: boolean;
}

export default function ConfigDrawer({ open, onClose, config, onChange, onRun, isRunning }: Props) {
  const { data: indicators = [] } = useIndicators();
  const { data: signalTypes = [] } = useSignalTypes();
  const { data: assetTypes = [] } = useAssetTypes();
  const { data: conjunctions = [] } = useConjunctions();
  const { data: dataColumns = [] } = useDataColumns();
  const { data: apps = [] } = useApps();
  const { data: products = [] } = useProducts();

  const selectedProduct = products.find(p => p.internal_cusip === config.symbol) ?? null;
  // Controlled input text for the Product Autocomplete
  const productInputValue = selectedProduct
    ? `${selectedProduct.display_nm} (${selectedProduct.internal_cusip})`
    : config.symbol; // freeSolo raw text, or '' when vendorSymbol clears it
  const { data: xrefs = [] } = useProductXrefs(selectedProduct?.product_id ?? null);
  const resolvedSymbol = xrefs.find(x => {
    const app = apps.find(a => a.name === config.dataSource);
    return app && x.app_id === app.app_id;
  })?.vendor_symbol ?? '';

  // All unique vendor symbols from xrefs for autocomplete
  const vendorSymbolOptions = xrefs.map(x => x.vendor_symbol);

  // Warn when a product is selected but has no xref for the chosen data source
  const hasXrefMismatch = !!selectedProduct && !!config.dataSource && !resolvedSymbol;

  // Displayed vendor symbol: manual override takes priority, then resolved from product+app
  const displayedVendor = config.vendorSymbol || resolvedSymbol;

  // Selected asset type object for Autocomplete
  const selectedAssetType = assetTypes.find(a => a.display_name === config.assetType) ?? null;

  const set = (patch: Partial<BacktestConfig>) => onChange({ ...config, ...patch });

  const handleIndicatorChange = (method_name: string) => {
    const ind = indicators.find(i => i.method_name === method_name);
    if (ind) {
      set({
        indicator: method_name,
        windowRange: { min: ind.win_min, max: ind.win_max, step: ind.win_step },
        signalRange: { min: ind.sig_min, max: ind.sig_max, step: ind.sig_step },
      });
    } else {
      set({ indicator: method_name });
    }
  };

  const handleFactorIndicatorChange = (i: number, method_name: string) => {
    const ind = indicators.find(x => x.method_name === method_name);
    const updated = config.factors.map((f, idx) => {
      if (idx !== i) return f;
      return {
        ...f,
        indicator: method_name,
        ...(ind
          ? {
              window_range: { min: ind.win_min, max: ind.win_max, step: ind.win_step } as RangeParam,
              signal_range: { min: ind.sig_min, max: ind.sig_max, step: ind.sig_step } as RangeParam,
            }
          : {}),
      };
    });
    set({ factors: updated });
  };

  const addFactor = () => {
    if (config.factors.length >= 2) return;
    const first = indicators[0];
    const newFactor: FactorConfig = {
      indicator: first?.method_name ?? '',
      strategy: signalTypes[0]?.name ?? '',
      data_column: 'price',
      window_range: { min: first?.win_min ?? 5, max: first?.win_max ?? 100, step: first?.win_step ?? 5 },
      signal_range: { min: first?.sig_min ?? 0, max: first?.sig_max ?? 0, step: first?.sig_step ?? 1 },
      symbol: config.symbol,
      vendor_symbol: config.vendorSymbol || undefined,
      data_source: config.dataSource || undefined,
    };
    set({ factors: [...config.factors, newFactor] });
  };

  const removeFactor = (i: number) => set({ factors: config.factors.filter((_, idx) => idx !== i) });

  const isFactorBounded = (factor: FactorConfig): boolean => {
    const ind = indicators.find(x => x.method_name === factor.indicator);
    return ind?.is_bounded_ind === 'Y';
  };

  const updateFactor = (i: number, patch: Partial<FactorConfig>) => {
    set({ factors: config.factors.map((f, idx) => idx === i ? { ...f, ...patch } : f) });
  };

  const completeFactor = (f: FactorConfig) => Boolean(f.indicator && f.strategy);

  const missingFields: string[] = [];
  if (!config.symbol.trim() && !config.vendorSymbol.trim()) missingFields.push('Product or Vendor Symbol');
  if (!config.assetType) missingFields.push('Asset Type');
  config.factors.forEach((f, i) => {
    const label = config.factors.length > 1 ? `Factor ${i + 1} ` : '';
    if (!f.indicator) missingFields.push(`${label}Indicator`);
    if (!f.strategy) missingFields.push(`${label}Strategy`);
  });

  const isRunnable = missingFields.length === 0 && config.factors.length >= 1;

  const totalTrials = config.factors.reduce(
    (acc, f) => acc * countSteps(f.window_range) * countSteps(f.signal_range),
    1,
  );
  const OPTUNA_MAX_TRIALS = 10_000;
  const cappedTrials = Math.min(totalTrials, OPTUNA_MAX_TRIALS);
  const isCapped = totalTrials > OPTUNA_MAX_TRIALS;

  return (
    <Drawer
      anchor="top"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { p: 3, maxHeight: '85vh', overflowY: 'auto', position: 'relative' } }}
    >
      {/* Close button — top right corner */}
      <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', top: 12, right: 12 }}>✕</IconButton>

      {/* Header */}
      <Box mb={3}>
        <Typography variant="h6" fontWeight={700}>Configure Backtest</Typography>
        <Typography variant="body2" color="text.secondary" mt={0.5}>Set the backtest parameters and factor grid below, then run the optimization.</Typography>
      </Box>

      {/* Row 1: base params */}
      <Box sx={{ display: 'flex', gap: 1.5, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
        <Autocomplete<ProductRow, false, false, true>
          size="small" freeSolo sx={{ width: 300 }}
          slotProps={{ listbox: { sx: { maxHeight: 360, minWidth: 320 } } }}
          options={products}
          value={selectedProduct}
          inputValue={productInputValue}
          getOptionLabel={(opt) => typeof opt === 'string' ? opt : `${opt.display_nm} (${opt.internal_cusip})`}
          isOptionEqualToValue={(opt, val) => opt.internal_cusip === val.internal_cusip}
          onChange={(_, val) => {
            if (!val) {
              set({ symbol: '', vendorSymbol: '' });
            } else if (typeof val === 'string') {
              set({ symbol: val, vendorSymbol: '' });
            } else {
              const at = assetTypes.find(a => a.asset_type_id === val.asset_type_id);
              set({
                symbol: val.internal_cusip, vendorSymbol: '',
                ...(at ? { assetType: at.display_name, tradingPeriod: at.trading_period } : {}),
              });
            }
          }}
          onInputChange={(_, val, reason) => {
            if (reason === 'input') set({ symbol: val, vendorSymbol: '' });
            // 'reset' and 'clear' are handled by the controlled inputValue
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
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Data Source</InputLabel>
          <Select
            value={config.dataSource} label="Data Source"
            onChange={e => set({ dataSource: e.target.value })}
          >
            {apps.map(a => (
              <MenuItem key={a.app_id} value={a.name}>{a.display_name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Autocomplete<string, false, false, true>
          size="small" freeSolo sx={{ width: 200 }}
          options={vendorSymbolOptions}
          value={displayedVendor || null}
          inputValue={displayedVendor}
          onInputChange={(_, val, reason) => {
            if (reason === 'input') set({ vendorSymbol: val, symbol: '' });
          }}
          onChange={(_, val) => {
            if (!val) set({ vendorSymbol: '', symbol: '' });
            else set({ vendorSymbol: val, symbol: '' });
          }}
          renderInput={(params) => <TextField {...params} label="Vendor Symbol" slotProps={{ inputLabel: { shrink: true } }} />}
        />
        <TextField
          label="Start" size="small" type="date" value={config.start} sx={{ width: 155 }}
          onChange={e => set({ start: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="End" size="small" type="date" value={config.end} sx={{ width: 155 }}
          onChange={e => set({ end: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Autocomplete<AssetTypeRow, false, false, false>
          size="small" sx={{ width: 180 }}
          options={assetTypes}
          value={selectedAssetType}
          getOptionLabel={(opt) => opt.display_name}
          isOptionEqualToValue={(opt, val) => opt.display_name === val.display_name}
          onChange={(_, val) => {
            if (!val) set({ assetType: '', tradingPeriod: 365 });
            else set({ assetType: val.display_name, tradingPeriod: val.trading_period });
          }}
          renderInput={(params) => <TextField {...params} label="Asset Type" />}
        />
        <TextField
          label="Fee (bps)" size="small" type="number" value={config.feeBps} sx={{ width: 100 }}
          onChange={e => set({ feeBps: Number(e.target.value) })}
        />
        <FormControlLabel
          control={
            <Checkbox
              size="small" checked={config.refreshDataset}
              onChange={e => set({ refreshDataset: e.target.checked })}
            />
          }
          label={<Typography variant="body2">Refresh dataset</Typography>}
          title="When checked, refetch all product+factor data from the provider and store a new version. When unchecked, serve from cache only."
        />
        <FormControlLabel
          control={
            <Checkbox
              size="small" checked={config.walkForward}
              onChange={e => set({ walkForward: e.target.checked })}
            />
          }
          label={<Typography variant="body2">Walk-Forward</Typography>}
        />
        {config.walkForward && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 200 }}>
            <Typography variant="body2" noWrap>Split</Typography>
            <Slider
              size="small" min={0.2} max={0.8} step={0.05}
              value={config.splitRatio}
              onChange={(_, v) => set({ splitRatio: v as number })}
              valueLabelDisplay="auto"
              valueLabelFormat={v => `${Math.round(v * 100)}%`}
              sx={{ minWidth: 100 }}
            />
            <Typography variant="caption" color="text.secondary" noWrap>
              {Math.round(config.splitRatio * 100)}% train
            </Typography>
          </Box>
        )}
      </Box>

      {hasXrefMismatch && !config.vendorSymbol && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          No vendor symbol mapping for <strong>{selectedProduct?.display_nm}</strong> on <strong>{config.dataSource}</strong>. Enter a vendor symbol manually or choose a different data source.
        </Alert>
      )}

      {config.factors.some(f => !f.symbol && !f.vendor_symbol) && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          alert_internal_cusip not configured on {config.factors
            .map((f, i) => (!f.symbol && !f.vendor_symbol) ? `Factor ${i + 1}` : null)
            .filter(Boolean).join(', ')
          } — will use main product.
        </Typography>
      )}

      <Divider sx={{ mb: 2 }} />

      {/* Factor configuration */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {config.factors.map((factor, i) => {
          const factorTrials = countSteps(factor.window_range) * countSteps(factor.signal_range);
          return (
            <React.Fragment key={i}>
              {/* Conjunction block — sits between factor 1 and factor 2 */}
              {i === 1 && (
                <Box key="conjunction" sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Divider sx={{ flex: 1 }} />
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Conjunction</InputLabel>
                    <Select value={config.conjunction} label="Conjunction"
                      onChange={e => set({ conjunction: e.target.value })}>
                      {conjunctions.map(c => (
                        <MenuItem key={c.name} value={c.name}>{c.display_name}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Divider sx={{ flex: 1 }} />
                </Box>
              )}

              <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2, bgcolor: 'background.paper' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="caption" fontWeight={600}>
                    Factor {i + 1}
                    <Typography component="span" variant="caption" color="text.secondary" fontWeight={400}>
                      {' '}— {factorTrials.toLocaleString()} grid pts
                    </Typography>
                  </Typography>
                  {config.factors.length > 1 && (
                    <IconButton size="small" onClick={() => removeFactor(i)} title="Remove factor">✕</IconButton>
                  )}
                </Box>
                <Stack spacing={1}>
                  {/* Factor-level product override (pair trade) */}
                  <FactorProductRow
                    factor={factor} index={i} products={products} apps={apps}
                    updateFactor={updateFactor}
                  />
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <FormControl size="small" sx={{ minWidth: 120, flex: 1 }}>
                      <InputLabel>Data Column</InputLabel>
                      <Select value={factor.data_column} label="Data Column"
                        onChange={e => updateFactor(i, { data_column: e.target.value })}>
                        {dataColumns.map(dc => (
                          <MenuItem key={dc.column_name} value={dc.column_name}>{dc.display_name}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl size="small" sx={{ minWidth: 180, flex: 2 }}>
                      <InputLabel>Indicator</InputLabel>
                      <Select value={factor.indicator} label="Indicator"
                        onChange={e => handleFactorIndicatorChange(i, e.target.value)}>
                        {indicators.map(ind => (
                          <MenuItem key={ind.method_name} value={ind.method_name}>{ind.display_name}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl size="small" sx={{ minWidth: 140, flex: 1.5 }}>
                      <InputLabel>Strategy</InputLabel>
                      <Select value={factor.strategy} label="Strategy"
                        onChange={e => updateFactor(i, { strategy: e.target.value })}>
                        {signalTypes.map(s => (
                          <MenuItem key={s.name} value={s.name}>{s.display_name}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <TextField label="Win Min" size="small" type="number" value={factor.window_range.min} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, min: Number(e.target.value) } })} />
                    <TextField label="Win Max" size="small" type="number" value={factor.window_range.max} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, max: Number(e.target.value) } })} />
                    <TextField label="Win Step" size="small" type="number" value={factor.window_range.step} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, step: Number(e.target.value) } })} />
                    <TextField label="Sig Min" size="small" type="number" value={factor.signal_range.min} sx={{ width: 80 }}
                      disabled={isFactorBounded(factor)}
                      slotProps={{ inputLabel: { shrink: true } }}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, min: Number(e.target.value) } })} />
                    <TextField label="Sig Max" size="small" type="number" value={factor.signal_range.max} sx={{ width: 80 }}
                      disabled={isFactorBounded(factor)}
                      slotProps={{ inputLabel: { shrink: true } }}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, max: Number(e.target.value) } })} />
                    <TextField label="Sig Step" size="small" type="number" value={factor.signal_range.step} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, step: Number(e.target.value) } })} />
                  </Stack>
                </Stack>
              </Box>
            </React.Fragment>
          );
        })}
        {config.factors.length < 2 && (
          <Button variant="outlined" size="small" onClick={addFactor} sx={{ alignSelf: 'flex-start' }}>+ Add Factor</Button>
        )}
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Footer: missing fields + trial count + Run */}
      {missingFields.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Cannot run — missing: <strong>{missingFields.join(', ')}</strong>
        </Alert>
      )}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        {isRunnable && (
          <Typography variant="caption" color="text.secondary">
            {cappedTrials.toLocaleString()} trials{isCapped ? ` (capped from ${totalTrials.toLocaleString()} combos)` : ''}
          </Typography>
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Button
          variant="contained"
          size="large"
          onClick={onRun}
          disabled={isRunning || !isRunnable}
          startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          {isRunning ? 'Running…' : 'Run Optimization'}
        </Button>
      </Box>
    </Drawer>
  );
}
