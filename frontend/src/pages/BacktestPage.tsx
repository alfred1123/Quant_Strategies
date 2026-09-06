import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AppBar, Toolbar, Typography, Button, Box, Alert,
  Chip, Divider, CircularProgress, LinearProgress,
  Tabs, Tab, Paper, Stack,
} from '@mui/material';
import TuneRoundedIcon from '@mui/icons-material/TuneRounded';
import FileDownloadRoundedIcon from '@mui/icons-material/FileDownloadRounded';
import InsightsRoundedIcon from '@mui/icons-material/InsightsRounded';
import ConfigDrawer from '../components/ConfigDrawer';
import JobsTable from '../components/JobsTable';
import PromotionTab from '../components/PromotionTab';
import Top10Table from '../components/Top10Table';
import MetricsCards from '../components/MetricsCards';
import HeatmapChart from '../components/HeatmapChart';
import EquityCurveChart from '../components/EquityCurveChart';
import UserMenu from '../components/UserMenu';
import AppModeSwitch from '../components/AppModeSwitch';
import BrandMark from '../components/BrandMark';
import { APP_NAME } from '../constants/brand';
import { runPerformance } from '../api/backtest';
import { fetchJob, useEnqueueJob, useJobCompletionEffects } from '../api/jobs';
import { useMe } from '../api/auth';
import { useAssetTypes, useTmIntervals } from '../api/refdata';
import { useProducts } from '../api/inst';
import type {
  BacktestConfig, OptimizeResponse, PerformanceResponse, Top10Row,
  WalkForwardResponse, OptimizeProgress,
} from '../types/backtest';
import { effectiveSymbol, buildOptimizeRequest, buildPerformanceRequest, configFromOptimizeRequest } from '../utils/requestBuilders';
import { buildStrategyNm } from '../utils/strategyIdentity';
import { overfitColor, overfitLabel, formatMetric, formatDecimal, formatPercent, rowLabel } from '../utils/format';
import { firstValidationError } from '../utils/validate';

const DEFAULT_CONFIG: BacktestConfig = {
  symbol: 'btcusdt.crypto',
  vendorSymbol: '',
  dataSource: 'yahoo',
  start: '2016-01-01',
  end: new Date().toISOString().slice(0, 10),
  assetType: '',
  // Interval ids live in REFDATA, so none can be named here. ConfigDrawer
  // seeds the control with DAILY once the table loads.
  tmIntervalId: null,
  tradingPeriod: 365,
  feeBps: 10.0,
  conjunction: 'AND',
  factors: [
    {
      indicator: '',
      strategy: '',
      data_column: 'price',
      // Daily-bar REFDATA defaults. ConfigDrawer scales min/max/step when
      // the bar interval is not daily (hourly Win Max = 100 × 24).
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

/** True when an Error is the result of an AbortController.abort() call. */
function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === 'AbortError';
}

export default function BacktestPage() {
  const { data: currentUser } = useMe();
  const { data: tmIntervals } = useTmIntervals();
  const { data: products = [] } = useProducts();
  const { data: assetTypes = [] } = useAssetTypes();
  const enqueue = useEnqueueJob();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [config, setConfig] = useState<BacktestConfig>(DEFAULT_CONFIG);
  const [isOptimizing] = useState(false);
  const [isLoadingPerf, setIsLoadingPerf] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState<OptimizeResponse | null>(null);
  const [perfResult, setPerfResult] = useState<PerformanceResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedRow, setSelectedRow] = useState<Top10Row | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analysisTab, setAnalysisTab] = useState(0);
  const [pageTab, setPageTab] = useState(0);
  const [wfResult, setWfResult] = useState<WalkForwardResponse | null>(null);
  const [optProgress] = useState<OptimizeProgress | null>(null);

  // ── Lifecycle: cancel any in-flight async work on unmount or new run ──
  // optimizeAbort tears down the SSE fetch; perfAbort tears down the per-row
  // POST. perfReqId protects against the late-arriving-response race
  // (click row A, click row B before A returns: A's response is dropped).
  const optimizeAbort = useRef<AbortController | null>(null);
  const perfAbort = useRef<AbortController | null>(null);
  const perfReqId = useRef(0);
  /** Queue id from the latest Run — auto-open Promotion when it completes. */
  const watchCompletionQueueId = useRef<string | null>(null);

  const handleJobCompleted = useCallback((queueId: string) => {
    if (watchCompletionQueueId.current === queueId) {
      watchCompletionQueueId.current = null;
      setPageTab(2);
    }
  }, []);

  useJobCompletionEffects(handleJobCompleted);

  useEffect(() => {
    // Cancel anything still running when the page unmounts. Copy the ref
    // containers (not .current) so the cleanup reads the latest controllers.
    const optAbort = optimizeAbort;
    const prfAbort = perfAbort;
    return () => {
      optAbort.current?.abort();
      prfAbort.current?.abort();
    };
  }, []);

  const loadPerf = async (row: Top10Row, index: number, cfg: BacktestConfig) => {
    // Cancel the previous perf request and bump the request id so any late
    // response from it is discarded even if it slips past the abort.
    perfAbort.current?.abort();
    const ctrl = new AbortController();
    perfAbort.current = ctrl;
    const reqId = ++perfReqId.current;

    setIsLoadingPerf(true);
    setSelectedIndex(index);
    setSelectedRow(row);
    setPerfResult(null);
    try {
      const perf = await runPerformance(buildPerformanceRequest(cfg, row), ctrl.signal);
      if (reqId !== perfReqId.current) return; // a newer request superseded us
      setPerfResult(perf);
    } catch (e: unknown) {
      if (isAbortError(e) || reqId !== perfReqId.current) return;
      const msg = e instanceof Error ? e.message : 'Performance calculation failed';
      console.error('[BacktestPage] loadPerf error:', e);
      setError(msg);
    } finally {
      if (reqId === perfReqId.current) setIsLoadingPerf(false);
    }
  };

  const hydrateConfig = (raw: Record<string, unknown> | null | undefined) =>
    configFromOptimizeRequest(raw, DEFAULT_CONFIG, { products, assetTypes });

  const handleCloneEdit = (_strategyId: string, configJson: Record<string, unknown>) => {
    setConfig(hydrateConfig(configJson));
    setDrawerOpen(true);
  };

  // Re-backtest from the Promotion tab: pull the decision's frozen config off
  // its queue row, prefill the drawer, and hand the user back to Backtest.
  const handleReBacktest = async (queueId: string) => {
    setError(null);
    try {
      const detail = await fetchJob(queueId);
      if (detail.config_json) {
        setConfig(hydrateConfig(detail.config_json));
      }
      setPageTab(0);
      setDrawerOpen(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load strategy config';
      console.error('[BacktestPage] handleReBacktest error:', e);
      setError(msg);
    }
  };

  const handleViewJob = async (queueId: string) => {
    setError(null);
    try {
      const detail = await fetchJob(queueId);
      if (!detail.result) {
        setError('Job has no stored result payload.');
        return;
      }
      // Result payload is OptimizeResponse.model_dump() — cast through unknown.
      const optResult = detail.result as unknown as OptimizeResponse;
      // Restore the frozen config so summary chips + factor count match.
      if (detail.config_json) {
        setConfig(hydrateConfig(detail.config_json));
      }
      setOptimizeResult(optResult);
      setPerfResult(optResult.performance ?? null);
      setWfResult(optResult.walk_forward ?? null);
      if (optResult.top10?.length) {
        setSelectedIndex(0);
        setSelectedRow(optResult.top10[0]);
      } else {
        setSelectedIndex(null);
        setSelectedRow(null);
      }
      setAnalysisTab(0);
      setPageTab(0);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load job result';
      console.error('[BacktestPage] handleViewJob error:', e);
      setError(msg);
    }
  };

  const handleRun = async (cfg: BacktestConfig) => {
    const validationError = firstValidationError(cfg);
    if (validationError) {
      setError(validationError);
      return;
    }
    // The cadence is part of the strategy's identity, so a name cannot be
    // built without it. Refuse rather than fall back to a cadence label the
    // run was not fitted on — that is what puts an hourly run into a daily
    // lineage, where promotion compares the two on different scales.
    const cadence = tmIntervals?.find(
      (iv) => iv.tm_interval_id === cfg.tmIntervalId,
    )?.name;
    if (!cadence) {
      setError('Bar interval has not loaded yet — reopen the config and pick one.');
      return;
    }
    // Cancel any previous perf request — backtest now runs server-side
    // via BT.QUEUE, so there's no client-side SSE to abort.
    perfAbort.current?.abort();
    perfReqId.current++;

    setError(null);
    setDrawerOpen(false);
    try {
      const req = buildOptimizeRequest(cfg);
      const strategyNm = buildStrategyNm(cfg, cadence);
      const result = await enqueue.mutateAsync({
        strategy_nm: strategyNm,
        config_json: req,
        priority: 'normal',
      });
      watchCompletionQueueId.current = result.queue_id;
      // Hand off to the Queue tab — the worker will pick the job up and
      // the table will repaint via its 3s poll.
      setPageTab(1);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to enqueue backtest';
      console.error('[BacktestPage] handleRun error:', e);
      setError(msg);
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
        <Toolbar sx={{ gap: 2 }}>
          <BrandMark />
          <Typography variant="h6" color="text.primary" sx={{ fontWeight: 700, mr: 1 }}>
            {APP_NAME}
          </Typography>
          <AppModeSwitch mode="backtest" />
          <Box sx={{ flexGrow: 1 }} />
          <Button variant="outlined" startIcon={<TuneRoundedIcon />} onClick={() => setDrawerOpen(true)}>
            Configure
          </Button>
          {currentUser && <UserMenu user={currentUser} />}
        </Toolbar>
        <Tabs
          value={pageTab}
          onChange={(_, v) => setPageTab(v)}
          sx={{ px: 2, borderTop: '1px solid', borderColor: 'divider' }}
        >
          <Tab label="Backtest" />
          <Tab label="Queue" />
          <Tab label="Promotion" />
        </Tabs>
      </AppBar>

      <ConfigDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        config={config}
        onChange={setConfig}
        onRun={handleRun}
        isRunning={enqueue.isPending}
      />

      <Box sx={{ maxWidth: pageTab === 2 ? 'none' : 1200, mx: pageTab === 2 ? 0 : 'auto', p: pageTab === 2 ? 0 : 3 }}>
        {pageTab === 1 && <JobsTable onView={handleViewJob} onCloneEdit={handleCloneEdit} />}
        {pageTab === 2 && <PromotionTab onReBacktest={handleReBacktest} />}
        {pageTab === 0 && (
          <>
        {/* Running state */}
        {isOptimizing && (
          <Box sx={{ my: 8, textAlign: 'center' }}>
            <LinearProgress
              variant={optProgress?.trial ? 'determinate' : 'indeterminate'}
              value={optProgress?.trial ? (optProgress.trial / optProgress.total) * 100 : undefined}
              sx={{ mb: 2, maxWidth: 420, mx: 'auto' }}
            />
            <Typography sx={{ color: 'text.secondary' }}>
              {optProgress?.trial
                ? `Trial ${optProgress.trial} / ${optProgress.total}${optProgress.best_sharpe != null ? ` · Best Sharpe: ${formatDecimal(optProgress.best_sharpe)}` : ''}`
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
            <Box
              aria-hidden
              sx={{
                width: 72,
                height: 72,
                mx: 'auto',
                mb: 3,
                display: 'grid',
                placeItems: 'center',
                borderRadius: '20px',
                color: 'primary.light',
                bgcolor: 'rgba(77, 142, 240, 0.08)',
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <InsightsRoundedIcon sx={{ fontSize: 36 }} />
            </Box>
            <Typography variant="h5" gutterBottom>No results yet</Typography>
            <Typography sx={{ color: 'text.secondary', mb: 3, maxWidth: 420, mx: 'auto' }}>
              Set up your indicators, signal thresholds and date range, then run an
              optimization to see the best parameter combinations here.
            </Typography>
            <Button variant="contained" size="large" startIcon={<TuneRoundedIcon />} onClick={() => setDrawerOpen(true)}>
              Configure &amp; Run
            </Button>
          </Box>
        )}

        {/* Results */}
        {optimizeResult && !isOptimizing && (
          <>
            {/* Run summary bar */}
            <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
              <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
                <Chip label={effectiveSymbol(config)} color="primary" size="small" />
                <Chip label={`${config.start} → ${config.end}`} size="small" variant="outlined" />
                <Chip label={`${optimizeResult.valid} / ${optimizeResult.total_trials} valid trials`} size="small" variant="outlined" />
                <Chip label={`Best Sharpe: ${formatDecimal(optimizeResult.best?.sharpe ?? 0)}`} color="success" size="small" />
                {config.factors.map((f, i) => (
                  <Chip key={i} label={`F${i + 1}: ${f.indicator} / ${f.strategy}`} size="small" variant="outlined" />
                ))}
                {config.factors.length > 1 && (
                  <Chip label={config.conjunction} size="small" color="warning" variant="outlined" />
                )}
                <Box sx={{ flexGrow: 1 }} />
                <Button size="small" variant="outlined" startIcon={<TuneRoundedIcon />} onClick={() => setDrawerOpen(true)}>Re-configure</Button>
              </Stack>
            </Paper>

            {/* Top 10 table */}
            <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Top 10 Parameter Combinations</Typography>
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
                <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 2 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Analysis</Typography>
                  {viewingLabel && (
                    <Chip label={viewingLabel} size="small" variant="outlined" color="primary" />
                  )}
                  {isLoadingPerf && <CircularProgress size={16} />}
                  <Box sx={{ flexGrow: 1 }} />
                  {perfResult?.perf_csv && (
                    <Button size="small" variant="outlined" startIcon={<FileDownloadRoundedIcon />} onClick={downloadPerfCSV}>Export CSV</Button>
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
                            <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', alignItems: 'center', mb: 2 }}>
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
                                label={`Overfitting: ${formatPercent(wfResult.overfitting_ratio)} — ${overfitLabel(wfResult.overfitting_ratio)}`}
                                size="small"
                                color={overfitColor(wfResult.overfitting_ratio)}
                              />
                            </Stack>

                            {/* IS vs OOS metrics comparison table */}
                            <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
                              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>In-Sample vs Out-of-Sample</Typography>
                              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1 }}>
                                <Typography variant="caption" sx={{ fontWeight: 600 }}>Metric</Typography>
                                <Typography variant="caption" sx={{ fontWeight: 600 }}>In-Sample</Typography>
                                <Typography variant="caption" sx={{ fontWeight: 600 }}>Out-of-Sample</Typography>
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
          </>
        )}
      </Box>
    </Box>
  );
}
