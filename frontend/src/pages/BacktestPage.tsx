import { useState } from 'react';
import {
  AppBar, Toolbar, Typography, Button, Box, Alert,
  Chip, Divider, CircularProgress, LinearProgress,
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
  factors: [],
};

function buildOptimizeRequest(cfg: BacktestConfig): OptimizeRequest {
  if (cfg.mode === 'single') {
    return {
      symbol: cfg.symbol, start: cfg.start, end: cfg.end,
      mode: 'single', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
      indicator: cfg.indicator, strategy: cfg.strategy,
      window_range: cfg.windowRange, signal_range: cfg.signalRange,
    };
  }
  return {
    symbol: cfg.symbol, start: cfg.start, end: cfg.end,
    mode: 'multi', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
    conjunction: cfg.conjunction, factors: cfg.factors,
  };
}

function buildPerformanceRequest(cfg: BacktestConfig, row: Top10Row): PerformanceRequest {
  if (cfg.mode === 'single') {
    return {
      symbol: cfg.symbol, start: cfg.start, end: cfg.end,
      mode: 'single', trading_period: cfg.tradingPeriod, fee_bps: cfg.feeBps,
      indicator: cfg.indicator, strategy: cfg.strategy,
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

function rowLabel(row: Top10Row, mode: 'single' | 'multi'): string {
  if (mode === 'single') return `window=${row.window ?? '-'}, signal=${row.signal ?? '-'}`;
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

  const loadPerf = async (row: Top10Row, index: number, cfg: BacktestConfig) => {
    setIsLoadingPerf(true);
    setSelectedIndex(index);
    setSelectedRow(row);
    setPerfResult(null);
    try {
      const perf = await runPerformance(buildPerformanceRequest(cfg, row));
      setPerfResult(perf);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Performance calculation failed');
    } finally {
      setIsLoadingPerf(false);
    }
  };

  const handleRun = async () => {
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
      if (result.top10.length > 0) {
        await loadPerf(result.top10[0], 0, config);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Optimization failed');
    } finally {
      setIsOptimizing(false);
    }
  };

  const handleSelectRow = (row: Top10Row, index: number) => {
    loadPerf(row, index, config);
  };

  const downloadCSV = () => {
    if (!optimizeResult) return;
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
    ? `${rowLabel(selectedRow, config.mode)}${selectedIndex === 0 ? ' (Best)' : ''}`
    : null;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: '#f5f7fa' }}>
      {/* Topbar */}
      <AppBar position="static" elevation={0} sx={{ bgcolor: 'white', borderBottom: '1px solid #e0e0e0' }}>
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
            {/* Summary chips */}
            <Box sx={{ display: 'flex', gap: 1, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
              <Chip label={config.symbol} color="primary" />
              <Chip label={`${optimizeResult.valid} / ${optimizeResult.total_trials} trials`} />
              <Chip label={`Best Sharpe: ${(optimizeResult.best.sharpe ?? 0).toFixed(4)}`} color="success" />
              <Box sx={{ flexGrow: 1 }} />
              <Button size="small" onClick={downloadCSV}>↓ CSV</Button>
            </Box>

            {/* Top 10 table */}
            <Box sx={{ bgcolor: 'white', borderRadius: 2, p: 2, mb: 3, boxShadow: 1 }}>
              <Typography variant="subtitle1" fontWeight={600} mb={1}>Top 10 Results</Typography>
              <Top10Table
                result={optimizeResult}
                selectedIndex={selectedIndex}
                onSelect={handleSelectRow}
                isLoadingPerf={isLoadingPerf}
              />
            </Box>

            {/* Analysis panel */}
            {(isLoadingPerf || perfResult) && (
              <Box sx={{ bgcolor: 'white', borderRadius: 2, p: 3, boxShadow: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Analysis</Typography>
                  {viewingLabel && (
                    <Chip label={viewingLabel} size="small" variant="outlined" color="primary" />
                  )}
                  {isLoadingPerf && <CircularProgress size={16} />}
                </Box>

                {isLoadingPerf && <LinearProgress />}

                {perfResult && !isLoadingPerf && (
                  <>
                    <MetricsCards result={perfResult} />
                    <Divider sx={{ my: 3 }} />
                    <HeatmapChart grid={optimizeResult.grid} mode={config.mode} />
                    <Divider sx={{ my: 3 }} />
                    <EquityCurveChart curve={perfResult.equity_curve} />
                  </>
                )}
              </Box>
            )}
          </>
        )}
      </Box>
    </Box>
  );
}
