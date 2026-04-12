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
import { runOptimize, runPerformance } from '../api/backtest';
import type {
  BacktestConfig, OptimizeResponse, PerformanceResponse, Top10Row,
  OptimizeRequest, PerformanceRequest,
} from '../types/backtest';

const DEFAULT_CONFIG: BacktestConfig = {
  symbol: 'BTC-USD',
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
    },
  ],
};

function buildOptimizeRequest(cfg: BacktestConfig): OptimizeRequest {
  const f0 = cfg.factors[0];
  if (cfg.factors.length <= 1) {
    return {
      symbol: cfg.symbol, start: cfg.start, end: cfg.end,
      mode: 'single', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
      indicator: f0.indicator, strategy: f0.strategy,
      window_range: f0.window_range, signal_range: f0.signal_range,
    };
  }
  return {
    symbol: cfg.symbol, start: cfg.start, end: cfg.end,
    mode: 'multi', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
    conjunction: cfg.conjunction, factors: cfg.factors,
  };
}

function buildPerformanceRequest(cfg: BacktestConfig, row: Top10Row): PerformanceRequest {
  const f0 = cfg.factors[0];
  if (cfg.factors.length <= 1) {
    return {
      symbol: cfg.symbol, start: cfg.start, end: cfg.end,
      mode: 'single', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
      indicator: f0.indicator, strategy: f0.strategy,
      window: row.window as number, signal: row.signal as number,
    };
  }
  const windows = Object.keys(row).filter(k => k.startsWith('window_')).map(k => row[k] as number);
  const signals = Object.keys(row).filter(k => k.startsWith('signal_')).map(k => row[k] as number);
  return {
    symbol: cfg.symbol, start: cfg.start, end: cfg.end,
    mode: 'multi', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
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
    if (!config.symbol.trim()) return 'Symbol is required.';
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
    try {
      const result = await runOptimize(buildOptimizeRequest(config));
      setOptimizeResult(result);
      if (result.top10?.length > 0) {
        await loadPerf(result.top10[0], 0, config);
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

  const downloadCSV = () => {
    if (!optimizeResult || !optimizeResult.top10.length) return;
    const rows = optimizeResult.top10;
    const keys = Object.keys(rows[0]);
    const csv = [keys.join(','), ...rows.map(r => keys.map(k => r[k]).join(','))].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `top10_${config.symbol}.csv`;
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
            <LinearProgress sx={{ mb: 2, maxWidth: 420, mx: 'auto' }} />
            <Typography color="text.secondary">Running optimization…</Typography>
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
                <Chip label={config.symbol} color="primary" size="small" />
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
                <Button size="small" variant="outlined" onClick={downloadCSV}>↓ Export CSV</Button>
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
                    </Tabs>

                    {analysisTab === 0 && (
                      <EquityCurveChart curve={perfResult.equity_curve} />
                    )}
                    {analysisTab === 1 && config.factors.length <= 1 && (
                      <HeatmapChart grid={optimizeResult.grid} mode="single" />
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
