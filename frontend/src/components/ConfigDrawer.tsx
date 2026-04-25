import {
  Drawer, Box, Typography, TextField, Select, MenuItem, Autocomplete,
  FormControl, InputLabel, Button, Divider, IconButton, CircularProgress,
  FormControlLabel, Checkbox, Slider, Alert,
} from '@mui/material';
import {
  useIndicators, useSignalTypes, useAssetTypes, useConjunctions, useDataColumns, useApps,
} from '../api/refdata';
import { useProducts } from '../api/inst';
import type { AssetTypeRow } from '../types/refdata';
import { countSteps } from '../utils/grid';
import type { BacktestConfig, FactorConfig } from '../types/backtest';
import ProductSelector from './config/ProductSelector';
import FactorCard from './config/FactorCard';

interface Props {
  open: boolean;
  onClose: () => void;
  config: BacktestConfig;
  onChange: (c: BacktestConfig) => void;
  onRun: () => void;
  isRunning: boolean;
}

export default function ConfigDrawer({ open, onClose, config, onChange, onRun, isRunning }: Props) {
  // ── REFDATA ──
  const { data: indicators = [] } = useIndicators();
  const { data: signalTypes = [] } = useSignalTypes();
  const { data: assetTypes = [] } = useAssetTypes();
  const { data: conjunctions = [] } = useConjunctions();
  const { data: dataColumns = [] } = useDataColumns();
  const { data: apps = [] } = useApps();
  const { data: products = [] } = useProducts();

  const set = (patch: Partial<BacktestConfig>) => onChange({ ...config, ...patch });

  // ── factor list mutators ──
  const updateFactor = (i: number, patch: Partial<FactorConfig>) =>
    set({ factors: config.factors.map((f, idx) => idx === i ? { ...f, ...patch } : f) });

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

  const removeFactor = (i: number) =>
    set({ factors: config.factors.filter((_, idx) => idx !== i) });

  // ── derived UI state ──
  const selectedAssetType: AssetTypeRow | null =
    assetTypes.find(a => a.display_name === config.assetType) ?? null;

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
      <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', top: 12, right: 12 }}>✕</IconButton>

      {/* Header */}
      <Box mb={3}>
        <Typography variant="h6" fontWeight={700}>Configure Backtest</Typography>
        <Typography variant="body2" color="text.secondary" mt={0.5}>
          Set the backtest parameters and factor grid below, then run the optimization.
        </Typography>
      </Box>

      {/* Row 1: trading product + base params */}
      <Box sx={{ display: 'flex', gap: 1.5, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
        <ProductSelector
          value={{
            symbol: config.symbol,
            vendorSymbol: config.vendorSymbol,
            dataSource: config.dataSource,
          }}
          onChange={patch => {
            const out: Partial<BacktestConfig> = {};
            if ('symbol' in patch) out.symbol = patch.symbol ?? '';
            if ('vendorSymbol' in patch) out.vendorSymbol = patch.vendorSymbol ?? '';
            if ('dataSource' in patch) out.dataSource = patch.dataSource ?? '';
            set(out);
          }}
          onProductPicked={(product) => {
            const at = assetTypes.find(a => a.asset_type_id === product.asset_type_id);
            if (at) set({ assetType: at.display_name, tradingPeriod: at.trading_period });
          }}
          products={products}
          apps={apps}
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

      {config.factors.some(f => !f.symbol && !f.vendor_symbol) && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          alert_internal_cusip not configured on {config.factors
            .map((f, i) => (!f.symbol && !f.vendor_symbol) ? `Factor ${i + 1}` : null)
            .filter(Boolean).join(', ')
          } — will use main product.
        </Typography>
      )}

      <Divider sx={{ mb: 2 }} />

      {/* Factor cards */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {config.factors.map((factor, i) => (
          <Box key={i} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Conjunction divider between factor 1 and factor 2 */}
            {i === 1 && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
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
            <FactorCard
              index={i}
              total={config.factors.length}
              factor={factor}
              onChange={patch => updateFactor(i, patch)}
              onRemove={() => removeFactor(i)}
              indicators={indicators}
              signalTypes={signalTypes}
              dataColumns={dataColumns}
              products={products}
              apps={apps}
            />
          </Box>
        ))}
        {config.factors.length < 2 && (
          <Button variant="outlined" size="small" onClick={addFactor} sx={{ alignSelf: 'flex-start' }}>
            + Add Factor
          </Button>
        )}
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Footer */}
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
