import {
  Drawer, Box, Typography, TextField, Select, MenuItem, Autocomplete,
  FormControl, InputLabel, Button, Divider, IconButton, CircularProgress,
  FormControlLabel, Checkbox, Slider, Alert,
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';
import { useEffect, useMemo, useRef } from 'react';
import {
  useIndicators, useSignalTypes, useAssetTypes, useConjunctions, useDataColumns, useApps,
  useTmIntervals, intervalLabel,
} from '../api/refdata';
import { useProducts } from '../api/inst';
import { useStoredCoverage } from '../api/marketData';
import type { AssetTypeRow } from '../types/refdata';
import { countSteps } from '../utils/grid';
import { barsPerDay, scaleWindowRange } from '../utils/interval';
import { validateBacktestConfig } from '../utils/validate';
import { capturedRange, rangeFits } from '../utils/capturedRange';
import type { BacktestConfig, FactorConfig } from '../types/backtest';
import ProductSelector from './config/ProductSelector';
import FactorCard from './config/FactorCard';

interface Props {
  open: boolean;
  onClose: () => void;
  config: BacktestConfig;
  /**
   * Accepts either a full replacement or a `(prev) => next` updater. The
   * updater form is REQUIRED to be safe against multiple synchronous calls
   * within a single event handler — see the `set()` helper below.
   */
  onChange: (next: BacktestConfig | ((prev: BacktestConfig) => BacktestConfig)) => void;
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
  const { data: tmIntervals = [] } = useTmIntervals();

  // ── the range the traded series can actually be run over ──
  //
  // Only exchange sources have one. A provider keeps the path it always had:
  // `Refresh dataset` refetches any window on demand, so a floor read from
  // the cache would describe what happens to be stored, not what is
  // obtainable, and would talk a user out of a range they could have had.
  const tradedApp = apps.find(a => a.name === config.dataSource);
  const isExchangeSource = tradedApp?.is_exchange_ind === 'Y';
  const sortedIntervals = useMemo(
    () => [...tmIntervals].sort((a, b) => a.tm_interval_id - b.tm_interval_id),
    [tmIntervals],
  );
  const tradedSeries = isExchangeSource && config.symbol && tradedApp && config.tmIntervalId
    ? {
      internal_cusip: config.symbol,
      tm_interval_id: config.tmIntervalId,
      source_app_id: tradedApp.app_id,
    }
    : {};
  const { data: coverage } = useStoredCoverage(tradedSeries);
  const captured = capturedRange(coverage);
  // Cadence is part of the identity: daily and hourly are separately captured
  // series with their own coverage, so switching interval must re-snap.
  const seriesId = isExchangeSource && config.symbol && tradedApp
    ? `${config.symbol}|${tradedApp.app_id}|${config.tmIntervalId}`
    : null;

  /**
   * Snap the dates to what is captured, once per series.
   *
   * Selecting a venue already rewrites other fields — picking a product sets
   * the asset type and trading period — so a selection deciding the range it
   * can be run over is the established behaviour, not a surprise. Guarded by
   * the series it last ran for, so a date edited afterwards stays edited and
   * only choosing a different series moves them again.
   */
  const snappedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!seriesId || !captured) return;
    if (snappedFor.current === seriesId) return;
    snappedFor.current = seriesId;
    onChange(prev => ({ ...prev, start: captured.first, end: captured.last }));
  }, [seriesId, captured, onChange]);

  /**
   * Seed the cadence once REFDATA arrives.
   *
   * `DEFAULT_CONFIG` cannot name one: interval ids live in the database, and
   * a run without one is refused rather than defaulted server-side. Daily is
   * the opening selection because every strategy on the platform so far is
   * daily — visible in the control, and one click from being changed.
   */
  const dailyIntervalId = tmIntervals.find(i => i.name === 'DAILY')?.tm_interval_id;
  useEffect(() => {
    if (config.tmIntervalId !== null || dailyIntervalId === undefined) return;
    onChange(prev => ({ ...prev, tmIntervalId: dailyIntervalId }));
  }, [dailyIntervalId, config.tmIntervalId, onChange]);

  /**
   * Periods per year for a cadence, from the asset type's daily figure.
   *
   * `REFDATA.ASSET_TYPE.TRADING_PERIOD` counts daily bars. Annualised return
   * scales by this number and Sharpe by its square root, so an hourly run
   * left on 365 reports both roughly 24x and 5x too low — a plausible number
   * on the wrong scale, which loses a strategy quietly.
   */
  const annualization = (dailyTradingPeriod: number, intervalId: number | null) => {
    const row = tmIntervals.find(i => i.tm_interval_id === intervalId);
    const perDay = row ? barsPerDay(row.period_length) : null;
    return perDay ? Math.round(dailyTradingPeriod * perDay) : dailyTradingPeriod;
  };

  /** Bars this cadence produces in a day; 1 when the interval is unknown. */
  const cadenceBarsPerDay = (intervalId: number | null): number => {
    const row = tmIntervals.find(i => i.tm_interval_id === intervalId);
    return (row && barsPerDay(row.period_length)) || 1;
  };

  const dailyWindowRange = (ind?: { win_min?: number; win_max?: number; win_step?: number }) => ({
    min: ind?.win_min ?? 5,
    max: ind?.win_max ?? 100,
    step: ind?.win_step ?? 5,
  });

  const rangeOutsideCapture = captured !== null
    && !rangeFits(captured, config.start, config.end);

  // A datetime control needs the room a date one does not.
  const dateFieldWidth = captured?.intraday ? 210 : 155;

  /**
   * Patch helper.
   *
   * MUST use the functional updater form. Some handlers (e.g. picking a
   * product fires both `onChange({ symbol, vendorSymbol })` AND
   * `onProductPicked(product)` → `set({ assetType, tradingPeriod })`
   * synchronously). With a plain `{ ...config, ...patch }` the second call
   * would close over the stale `config` prop and silently discard the
   * first update. Functional updates serialize correctly through React's
   * batching.
   */
  const set = (patch: Partial<BacktestConfig>) =>
    onChange(prev => ({ ...prev, ...patch }));

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
      window_range: scaleWindowRange(dailyWindowRange(first), 1, cadenceBarsPerDay(config.tmIntervalId)),
      signal_range: { min: first?.sig_min ?? 0, max: first?.sig_max ?? 0, step: first?.sig_step ?? 1 },
      symbol: config.symbol,
      vendor_symbol: config.vendorSymbol || undefined,
      data_source: config.dataSource || undefined,
    };
    set({
      factors: config.conjunction === 'FILTER'
        ? [newFactor, ...config.factors]
        : [...config.factors, newFactor],
    });
  };

  const removeFactor = (i: number) =>
    set({ factors: config.factors.filter((_, idx) => idx !== i) });

  // ── derived UI state ──
  const selectedAssetType: AssetTypeRow | null =
    assetTypes.find(a => a.display_name === config.assetType) ?? null;

  const missingFields = validateBacktestConfig(config);
  const isRunnable = missingFields.length === 0;

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
      slotProps={{ paper: { sx: { p: 3, maxHeight: '85vh', overflowY: 'auto', position: 'relative' } } }}
    >
      <IconButton onClick={onClose} size="small" aria-label="Close" sx={{ position: 'absolute', top: 12, right: 12 }}>
        <CloseRoundedIcon fontSize="small" />
      </IconButton>

      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>Configure Backtest</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
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
            if (at) set({
              assetType: at.display_name,
              tradingPeriod: annualization(at.trading_period, config.tmIntervalId),
            });
          }}
          products={products}
          apps={apps}
        />
        <FormControl size="small" sx={{ width: 130 }}>
          <InputLabel id="bar-interval-label">Bar Interval</InputLabel>
          <Select
            labelId="bar-interval-label"
            label="Bar Interval"
            value={config.tmIntervalId === null ? '' : String(config.tmIntervalId)}
            onChange={e => {
              const id = Number(e.target.value);
              onChange(prev => {
                const fromBpd = cadenceBarsPerDay(prev.tmIntervalId);
                const toBpd = cadenceBarsPerDay(id);
                return {
                  ...prev,
                  tmIntervalId: id,
                  ...(selectedAssetType
                    ? { tradingPeriod: annualization(selectedAssetType.trading_period, id) }
                    : {}),
                  factors: prev.factors.map(f => ({
                    ...f,
                    window_range: scaleWindowRange(f.window_range, fromBpd, toBpd),
                  })),
                };
              });
            }}
          >
            {sortedIntervals.map(iv => (
              <MenuItem key={iv.tm_interval_id} value={String(iv.tm_interval_id)}>
                {intervalLabel(iv)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {/*
          A date field for a daily series, a datetime field for an intraday
          one. The control has to be able to hold the bound it is given: an
          hourly series whose first bar is 10:00 cannot be expressed as a
          date, and the run is refused for the ten bars that never existed.
        */}
        <TextField
          label="Start" size="small" sx={{ width: dateFieldWidth }}
          type={captured?.intraday ? 'datetime-local' : 'date'}
          value={config.start}
          onChange={e => set({ start: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="End" size="small" sx={{ width: dateFieldWidth }}
          type={captured?.intraday ? 'datetime-local' : 'date'}
          value={config.end}
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
            else set({
              assetType: val.display_name,
              tradingPeriod: annualization(val.trading_period, config.tmIntervalId),
            });
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

      {isExchangeSource && captured && !rangeOutsideCapture && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          {tradedApp?.display_name} has {captured.first} to {captured.last} captured
          for {config.symbol} — the run reads those bars, not a provider.
        </Typography>
      )}

      {captured && rangeOutsideCapture && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button
              size="small"
              onClick={() => set({ start: captured.first, end: captured.last })}
            >
              Use captured range
            </Button>
          }
        >
          Only {captured.first} to {captured.last} is captured for {config.symbol} on{' '}
          {tradedApp?.display_name}, so this run will be refused rather than quietly
          shortened. Backfill more history on the Market data page, or narrow the range.
        </Alert>
      )}

      {config.factors.some(f => !f.symbol && !f.vendor_symbol) && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          No product set on {config.factors
            .map((f, i) => (!f.symbol && !f.vendor_symbol) ? `Factor ${i + 1}` : null)
            .filter(Boolean).join(', ')
          } — will use the main trading product.
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
                  <InputLabel id="conjunction-label">Conjunction</InputLabel>
                  <Select
                    labelId="conjunction-label"
                    value={config.conjunction}
                    label="Conjunction"
                    onChange={e => {
                      const next = String(e.target.value);
                      if (
                        next === 'FILTER'
                        && config.conjunction !== 'FILTER'
                        && config.factors.length === 2
                      ) {
                        set({
                          conjunction: next,
                          factors: [config.factors[1], config.factors[0]],
                        });
                      } else {
                        set({ conjunction: next });
                      }
                    }}>
                    {conjunctions.map(c => (
                      <MenuItem key={c.name} value={c.name}>{c.display_name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Divider sx={{ flex: 1 }} />
              </Box>
            )}
            {i === 1 && config.conjunction === 'FILTER' && (
              <Typography variant="caption" color="text.secondary">
                Gate must be non-zero; Signal supplies the trade direction.
              </Typography>
            )}
            <FactorCard
              index={i}
              total={config.factors.length}
              conjunction={config.conjunction}
              factor={factor}
              onChange={patch => updateFactor(i, patch)}
              onRemove={() => removeFactor(i)}
              indicators={indicators}
              signalTypes={signalTypes}
              dataColumns={dataColumns}
              products={products}
              apps={apps}
              barsPerDay={cadenceBarsPerDay(config.tmIntervalId)}
            />
          </Box>
        ))}
        {config.factors.length < 2 && (
          <Button variant="outlined" size="small" startIcon={<AddRoundedIcon />} onClick={addFactor} sx={{ alignSelf: 'flex-start' }}>
            Add Factor
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
          startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : <PlayArrowRoundedIcon />}
        >
          {isRunning ? 'Running…' : 'Run Optimization'}
        </Button>
      </Box>
    </Drawer>
  );
}
