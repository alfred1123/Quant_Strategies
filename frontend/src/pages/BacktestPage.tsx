import { useState } from 'react';
import {
  AppBar, Toolbar, Typography, Button, Box, Alert,
  Chip, Divider, CircularProgress, LinearProgress,
  Tabs, Tab, Paper, Stack,
} from '@mui/material';
import ConfigDrawer from '../components/ConfigDrawer';
import Top10Table from '../components/Top10Table';
import MetricsCards from '../components/MetricsCards';
import HeatmapChart from '../components/HeatmapChart';
import EquityCurveChart from '../components/EquityCurveChart';
import { runOptimizeStream, runPerformance } from '../api/backtest';
import type {
  BacktestConfig, OptimizeResponse, PerformanceResponse, Top10Row,
  OptimizeRequest, PerformanceRequest, WalkForwardResponse,
  OptimizeProgress,
} from '../types/backtest';

const DEFAULT_CONFIG: BacktestConfig = {
  symbol: 'btcusdt.crypto',
  vendorSymbol: '',
  dataSource: 'yahoo',
  start: '2016-01-01',
  end: new Date().toISOString().slice(0, 10),
  assetType: '',
  tradingPeriod: 365,
  feeBps: 5.0,
  mode: 'single',
  indicator: '',
  strategy: '',
  windowRange: { min: 5, max: 100, step: 5 },
  signalRange: { min: 0.25, max: 2.5, step: 0.25 },
  conjunction: 'AND',
  factors: [
    {
      indicator: '',
      strategy: '',
      data_column: 'price',
      window_range: { min: 5, max: 100, step: 5 },
      signal_range: { min: 0.25, max: 2.5, step: 0.25 },
      symbol: 'btcusdt.crypto',
      data_source: 'yahoo',
    },
  ],
  walkForward: true,
  splitRatio: 0.5,
  refreshDataset: false,
};

/** vendorSymbol takes priority; falls back to product cusip */
const effectiveSymbol = (cfg: BacktestConfig) => cfg.vendorSymbol || cfg.symbol;

function buildOptimizeRequest(cfg: BacktestConfig): OptimizeRequest {
  const f0 = cfg.factors[0];
  const ds = cfg.dataSource || undefined;
  const base = {
    symbol: effectiveSymbol(cfg), start: cfg.start, end: cfg.end,
    trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps, data_source: ds,
    refresh_dataset: cfg.refreshDataset,
    walk_forward: cfg.walkForward, split_ratio: cfg.splitRatio,
  };
  if (cfg.factors.length <= 1) {
    return {
      ...base, mode: 'single' as const,
      indicator: f0.indicator, strategy: f0.strategy,
      window_range: f0.window_range, signal_range: f0.signal_range,
    };
  }
  return {
    ...base, mode: 'multi' as const,
    conjunction: cfg.conjunction, factors: cfg.factors,
  };
}

function buildPerformanceRequest(cfg: BacktestConfig, row: Top10Row): PerformanceRequest {
  const f0 = cfg.factors[0];
  const ds = cfg.dataSource || undefined;
  if (cfg.factors.length <= 1) {
    return {
      symbol: effectiveSymbol(cfg), start: cfg.start, end: cfg.end,
      mode: 'single', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
      data_source: ds, refresh_dataset: cfg.refreshDataset,
      indicator: f0.indicator, strategy: f0.strategy,
      window: row.window as number, signal: row.signal as number,
    };
  }
  const windows = Object.keys(row).filter(k => k.startsWith('window_')).map(k => row[k] as number);
  const signals = Object.keys(row).filter(k => k.startsWith('signal_')).map(k => row[k] as number);
  return {
    symbol: effectiveSymbol(cfg), start: cfg.start, end: cfg.end,
    mode: 'multi', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
    data_source: ds, refresh_dataset: cfg.refreshDataset,
    conjunction: cfg.conjunction, factors: cfg.factors,
    windows, signals,
  };
}

function rowLabel(row: Top10Row, cfg: BacktestConfig): string {
  if (cfg.factors.length <= 1) return `window=${row.window ?? '-'}, signal=${row.signal ?? '-'}`;
  return Object.keys(row)
    .filter(k => k.startsWith('window_') || k.startsWith('signal_'))
    .map(k => `${k}=${row[k]}`)
    .join(', ');
}

function overfitColor(ratio: number | null): 'success' | 'warning' | 'error' | 'default' {
  if (ratio == null || isNaN(ratio)) return 'default';
  if (ratio < 0.3) return 'success';
  if (ratio < 0.5) return 'warning';
  return 'error';
}

function overfitLabel(ratio: number | null): string {
  if (ratio == null || isNaN(ratio)) return 'N/A';
  if (ratio < 0.3) return 'Low Risk';
  if (ratio < 0.7) return 'Moderate';
  return 'High Risk';
}

function formatMetric(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return 'N/A';
  return v.toFixed(4);
}

export default function BacktestPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [config, setConfig] = useState<BacktestConfig>(DEFAULT_CONFIG);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [isLoadingPerf, setIsLoadingPerf] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState<OptimizeResponse | null>(null);
  const [perfResult, setPerfResult] = useState<PerformanceResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedRow, setSelectedRow] = useState<Top10Row | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analysisTab, setAnalysisTab] = useState(0);
  const [wfResult, setWfResult] = useState<WalkForwardResponse | null>(null);
  const [optProgress, setOptProgress] = useState<OptimizeProgress | null>(null);

  const loadPerf = async (row: Top10Row, index: number, cfg: BacktestConfig) => {
    setIsLoadingPerf(true);
    setSelectedIndex(index);
    setSelectedRow(row);
    setPerfResult(null);
    try {
      const perf = await runPerformance(buildPerformanceRequest(cfg, row));
      setPerfResult(perf);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Performance calculation failed';
      console.error('[BacktestPage] loadPerf error:', e);
      setError(msg);
    } finally {
      setIsLoadingPerf(false);
    }
  };

  const validate = (): string | null => {
    if (!config.symbol.trim() && !config.vendorSymbol.trim()) return 'Product or vendor symbol is required.';
    if (!config.assetType) return 'Asset type is required.';
    for (let i = 0; i < config.factors.length; i++) {
      if (!config.factors[i].indicator) return `Factor ${i + 1}: indicator is required.`;
      if (!config.factors[i].strategy) return `Factor ${i + 1}: strategy is required.`;
    }
    return null;
  };

  const handleRun = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setIsOptimizing(true);
    setDrawerOpen(false);
    setOptimizeResult(null);
    setPerfResult(null);
    setSelectedIndex(null);
    setSelectedRow(null);
    setWfResult(null);
    setOptProgress(null);
    try {
      const result = await runOptimizeStream(
        buildOptimizeRequest(config),
        (p) => setOptProgress(p),
      );
      setOptProgress(null);
      setOptimizeResult(result);

      // Use inline performance from the stream result
      if (result.performance) {
        setPerfResult(result.performance);
        if (result.top10?.length > 0) {
          setSelectedIndex(0);
          setSelectedRow(result.top10[0]);
        }
      }

      // Use inline walk-forward from the stream result
      if (result.walk_forward) {
        setWfResult(result.walk_forward);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Optimization failed';
      console.error('[BacktestPage] handleRun error:', e);
      setError(msg);
    } finally {
      setIsOptimizing(false);
    }
  };

  const handleSelectRow = (row: Top10Row, index: number) => {
    loadPerf(row, index, config);
  };

  const downloadPerfCSV = () => {
    if (!perfResult?.perf_csv) return;
    const url = URL.createObjectURL(new Blob([perfResult.perf_csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `perf_${effectiveSymbol(config)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const viewingLabel = selectedRow
    ? `${rowLabel(selectedRow, config)}${selectedIndex === 0 ? ' (Best)' : ''}`
    : null;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Topbar */}
      <AppBar position="static" elevation={0} sx={{ bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <Typography variant="h6" color="text.primary" sx={{ flexGrow: 1, fontWeight: 700 }}>
            Quant Strategies
          </Typography>
          <Button variant="outlined" onClick={() => setDrawerOpen(true)}>
            ⚙ Configure
          </Button>
        </Toolbar>
      </AppBar>

      <ConfigDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        config={config}
        onChange={setConfig}
        onRun={handleRun}
        isRunning={isOptimizing}
      />

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
        {/* Running state */}
        {isOptimizing && (
          <Box sx={{ my: 8, textAlign: 'center' }}>
            <LinearProgress
              variant={optProgress?.trial ? 'determinate' : 'indeterminate'}
              value={optProgress?.trial ? (optProgress.trial / optProgress.total) * 100 : undefined}
              sx={{ mb: 2, maxWidth: 420, mx: 'auto' }}
            />
            <Typography color="text.secondary">
              {optProgress?.trial
                ? `Trial ${optProgress.trial} / ${optProgress.total}${optProgress.best_sharpe != null ? ` · Best Sharpe: ${optProgress.best_sharpe.toFixed(4)}` : ''}`
                : 'Running optimization…'}
            </Typography>
          </Box>
        )}

        {/* Error */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>
        )}

        {/* Empty state */}
        {!isOptimizing && !optimizeResult && !error && (
          <Box sx={{ textAlign: 'center', py: 14 }}>
            <Typography variant="h5" color="text.secondary" gutterBottom>No results yet</Typography>
            <Typography color="text.secondary" mb={3}>
              Click Configure to set parameters and run an optimization.
            </Typography>
            <Button variant="contained" size="large" onClick={() => setDrawerOpen(true)}>
              ⚙ Configure &amp; Run
            </Button>
          </Box>
        )}

        {/* Results */}
        {optimizeResult && !isOptimizing && (
          <>
            {/* Run summary bar */}
            <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
              <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center">
                <Chip label={effectiveSymbol(config)} color="primary" size="small" />
                <Chip label={`${config.start} → ${config.end}`} size="small" variant="outlined" />
                <Chip label={`${optimizeResult.valid} / ${optimizeResult.total_trials} valid trials`} size="small" variant="outlined" />
                <Chip label={`Best Sharpe: ${(optimizeResult.best?.sharpe ?? 0).toFixed(4)}`} color="success" size="small" />
                {config.factors.map((f, i) => (
                  <Chip key={i} label={`F${i + 1}: ${f.indicator} / ${f.strategy}`} size="small" variant="outlined" />
                ))}
                {config.factors.length > 1 && (
                  <Chip label={config.conjunction} size="small" color="warning" variant="outlined" />
                )}
                <Box sx={{ flexGrow: 1 }} />
                <Button size="small" variant="outlined" onClick={() => setDrawerOpen(true)}>⚙ Re-configure</Button>
              </Stack>
            </Paper>

            {/* Top 10 table */}
            <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} mb={1}>Top 10 Parameter Combinations</Typography>
              <Top10Table
                result={optimizeResult}
                selectedIndex={selectedIndex}
                onSelect={handleSelectRow}
                isLoadingPerf={isLoadingPerf}
              />
            </Paper>

            {/* Analysis panel */}
            {(isLoadingPerf || perfResult) && (
              <Paper variant="outlined" sx={{ p: 3 }}>
                {/* Analysis header */}
                <Stack direction="row" alignItems="center" spacing={2} mb={2}>
                  <Typography variant="subtitle1" fontWeight={600}>Analysis</Typography>
                  {viewingLabel && (
                    <Chip label={viewingLabel} size="small" variant="outlined" color="primary" />
                  )}
                  {isLoadingPerf && <CircularProgress size={16} />}
                  <Box sx={{ flexGrow: 1 }} />
                  {perfResult?.perf_csv && (
                    <Button size="small" variant="outlined" onClick={downloadPerfCSV}>↓ Export CSV</Button>
                  )}
                </Stack>

                {isLoadingPerf && <LinearProgress sx={{ mb: 2 }} />}

                {perfResult && !isLoadingPerf && (
                  <>
                    {/* Metrics */}
                    <MetricsCards result={perfResult} />

                    <Divider sx={{ my: 3 }} />

                    {/* Tabbed charts */}
                    <Tabs
                      value={analysisTab}
                      onChange={(_, v) => setAnalysisTab(v)}
                      sx={{ mb: 2 }}
                    >
                      <Tab label="Equity Curve" />
                      {config.factors.length <= 1 && <Tab label="Heatmap" />}
                      {wfResult && <Tab label="Walk-Forward" />}
                    </Tabs>

                    {analysisTab === 0 && (
                      <EquityCurveChart curve={perfResult.equity_curve} />
                    )}
                    {analysisTab === 1 && config.factors.length <= 1 && (
                      <HeatmapChart grid={optimizeResult.grid} mode="single" />
                    )}
                    {/* Walk-Forward tab — index depends on whether Heatmap tab exists */}
                    {analysisTab === (config.factors.length <= 1 ? 2 : 1) && wfResult && (
                      <Box>
                        {wfResult && (
                          <>
                            {/* Best params + overfitting ratio */}
                            <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center" mb={2}>
                              <Chip
                                label={`Best Window: ${Array.isArray(wfResult.best_window) ? wfResult.best_window.join(', ') : wfResult.best_window}`}
                                size="small" variant="outlined"
                              />
                              <Chip
                                label={`Best Signal: ${Array.isArray(wfResult.best_signal) ? wfResult.best_signal.join(', ') : wfResult.best_signal}`}
                                size="small" variant="outlined"
                              />
                              <Chip
                                label={`Split: ${wfResult.split_date}`}
                                size="small" variant="outlined"
                              />
                              <Chip
                                label={`Overfitting: ${wfResult.overfitting_ratio != null ? (wfResult.overfitting_ratio * 100).toFixed(1) + '%' : 'N/A'} — ${overfitLabel(wfResult.overfitting_ratio)}`}
                                size="small"
                                color={overfitColor(wfResult.overfitting_ratio)}
                              />
                            </Stack>

                            {/* IS vs OOS metrics comparison table */}
                            <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
                              <Typography variant="subtitle2" fontWeight={600} mb={1}>In-Sample vs Out-of-Sample</Typography>
                              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1 }}>
                                <Typography variant="caption" fontWeight={600}>Metric</Typography>
                                <Typography variant="caption" fontWeight={600}>In-Sample</Typography>
                                <Typography variant="caption" fontWeight={600}>Out-of-Sample</Typography>
                                {Object.keys(wfResult.is_metrics).map(key => (
                                  <Box key={key} sx={{ display: 'contents' }}>
                                    <Typography variant="body2">{key}</Typography>
                                    <Typography variant="body2">{formatMetric(wfResult.is_metrics[key])}</Typography>
                                    <Typography variant="body2">{formatMetric(wfResult.oos_metrics[key])}</Typography>
                                  </Box>
                                ))}
                              </Box>
                            </Paper>

                            {/* WF equity curve with split line */}
                            <EquityCurveChart curve={wfResult.equity_curve} splitDate={wfResult.split_date} />
                          </>
                        )}
                      </Box>
                    )}
                  </>
                )}
              </Paper>
            )}
          </>
        )}
      </Box>
    </Box>
  );
}
