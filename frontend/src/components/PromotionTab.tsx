import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip,
  CircularProgress, Divider, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Typography, useMediaQuery,
} from '@mui/material';
import { usePromotions } from '../api/promotion';
import { usePromotionMetrics, usePromotionStates } from '../api/refdata';
import { formatMetric, toFiniteNumber } from '../utils/format';
import { readPromotionMetric } from '../utils/promotionMetric';
import type { PromotionRow } from '../types/promotion';
import type { PromotionMetricRow } from '../types/refdata';

const OUTCOME_COLOR: Record<string, 'success' | 'default' | 'warning' | 'error'> = {
  PROMOTED: 'success',
  KEPT: 'default',
  DEMOTED: 'warning',
  REJECTED: 'error',
};

interface PromotionTabProps {
  /** Clone a completed backtest's config back into the Backtest tab. */
  onReBacktest?: (queueId: string) => void;
}

/** 1 if candidate wins, -1 if best wins, 0 if tied/incomparable. */
function compareMetric(
  candidate: number | null,
  best: number | null,
  direction: string,
): number {
  if (candidate == null || best == null) return 0;
  if (candidate === best) return 0;
  const higher = candidate > best ? 1 : -1;
  return direction === 'lower_is_better' ? -higher : higher;
}

export default function PromotionTab({ onReBacktest }: PromotionTabProps = {}) {
  const promotions = usePromotions();
  const { data: states = [] } = usePromotionStates();
  const promotionMetricsQuery = usePromotionMetrics();
  const metrics = promotionMetricsQuery.data ?? [];
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const rows = useMemo(() => promotions.data ?? [], [promotions.data]);

  const outcomeLabel = useMemo(() => {
    const m = new Map(states.map((s) => [s.name, s.display_name ?? s.name]));
    return (name: string) => m.get(name) ?? name;
  }, [states]);

  // Group decisions by strategy_id (rows arrive newest-first).
  const groups = useMemo(() => {
    const byId = new Map<string, PromotionRow[]>();
    for (const r of rows) {
      const list = byId.get(r.strategy_id) ?? [];
      list.push(r);
      byId.set(r.strategy_id, list);
    }
    return Array.from(byId.entries());
  }, [rows]);

  // Recommended: highest Sharpe among current-best (IS_BEST_IND='Y') rows.
  const recommended = useMemo(() => {
    const best = rows.filter((r) => r.is_best_ind === 'Y' && toFiniteNumber(r.sharpe_ratio) != null);
    if (best.length === 0) return null;
    return best.reduce((a, b) =>
      (toFiniteNumber(b.sharpe_ratio) ?? -Infinity) > (toFiniteNumber(a.sharpe_ratio) ?? -Infinity) ? b : a,
    );
  }, [rows]);

  const selected = useMemo(
    () => rows.find((r) => r.promotion_id === selectedId) ?? null,
    [rows, selectedId],
  );

  if (promotions.isLoading) {
    return (
      <Box sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
        <PromotionRulesFlyout
          metrics={metrics}
          isLoading={promotionMetricsQuery.isLoading}
          isError={promotionMetricsQuery.isError}
          error={promotionMetricsQuery.error}
        />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Promotion</Typography>
          {promotions.isFetching && <CircularProgress size={16} />}
          <Box sx={{ flexGrow: 1 }} />
          <Typography variant="caption" color="text.secondary">
            Auto-refreshes every 10 seconds
          </Typography>
        </Stack>

        {promotions.isError && (
          <Alert severity="error">
            Failed to load promotions: {(promotions.error as Error)?.message ?? 'unknown error'}
          </Alert>
        )}

        <RecommendedBanner row={recommended} />

        {rows.length === 0 ? (
          <Alert severity="info">
            No promotion decisions yet. Run a backtest — the worker logs a decision when each job completes.
          </Alert>
        ) : (
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: '1.4fr 1fr' },
              gap: 3,
              alignItems: 'start',
            }}
          >
            <StrategyList
              groups={groups}
              selectedId={selectedId}
              onSelect={setSelectedId}
              outcomeLabel={outcomeLabel}
            />
            <ComparisonPanel
              row={selected}
              rows={rows}
              metrics={metrics}
              outcomeLabel={outcomeLabel}
              onReBacktest={onReBacktest}
              onDeploy={(r) =>
                navigate('/trade/apply', {
                  state: { strategyId: r.strategy_id, strategyVid: r.strategy_vid },
                })
              }
            />
          </Box>
        )}
      </Stack>

      <PromotionRulesFlyout
        metrics={metrics}
        isLoading={promotionMetricsQuery.isLoading}
        isError={promotionMetricsQuery.isError}
        error={promotionMetricsQuery.error}
      />
    </Box>
  );
}

function RecommendedBanner({ row }: { row: PromotionRow | null }) {
  if (!row) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2, borderColor: 'success.main' }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Chip label="Recommended" color="success" />
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          {row.strategy_nm ?? row.strategy_id.slice(0, 8)} · v{row.strategy_vid}
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Metric label="Sharpe" value={row.sharpe_ratio} />
        <Metric label="Calmar" value={row.calmar_ratio} />
        <Metric label="Max DD" value={row.max_drawdown} />
        <Metric label="Total Ret" value={row.total_return} />
      </Stack>
    </Paper>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <Box sx={{ textAlign: 'right', minWidth: 80 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{label}</Typography>
      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{formatMetric(value)}</Typography>
    </Box>
  );
}

function StrategyList({
  groups, selectedId, onSelect, outcomeLabel,
}: {
  groups: [string, PromotionRow[]][];
  selectedId: string | null;
  onSelect: (id: string) => void;
  outcomeLabel: (name: string) => string;
}) {
  return (
    <Stack spacing={1}>
      {groups.map(([strategyId, decisions]) => {
        const nm = decisions[0]?.strategy_nm ?? strategyId.slice(0, 8);
        return (
          <Accordion key={strategyId} defaultExpanded variant="outlined" disableGutters>
            <AccordionSummary expandIcon={<Box component="span" sx={{ fontSize: 18, lineHeight: 1 }}>▾</Box>}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{nm}</Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                {decisions.length} decision{decisions.length === 1 ? '' : 's'}
              </Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ p: 0 }}>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>VID</TableCell>
                      <TableCell>Outcome</TableCell>
                      <TableCell align="right">Sharpe</TableCell>
                      <TableCell align="right">Calmar</TableCell>
                      <TableCell>When</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {decisions.map((d) => (
                      <TableRow
                        key={d.promotion_id}
                        hover
                        selected={d.promotion_id === selectedId}
                        onClick={() => onSelect(d.promotion_id)}
                        sx={{ cursor: 'pointer' }}
                      >
                        <TableCell>
                          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                            <Typography variant="body2">v{d.strategy_vid}</Typography>
                            {d.is_best_ind === 'Y' && (
                              <Chip size="small" label="Best" color="success" variant="outlined"
                                sx={{ height: 18, fontSize: '0.65rem' }} />
                            )}
                          </Stack>
                        </TableCell>
                        <TableCell>
                          <Chip size="small" label={outcomeLabel(d.outcome)}
                            color={OUTCOME_COLOR[d.outcome] ?? 'default'} />
                        </TableCell>
                        <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{formatMetric(d.sharpe_ratio)}</TableCell>
                        <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{formatMetric(d.calmar_ratio)}</TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary">
                            {new Date(d.created_at).toLocaleString()}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Stack>
  );
}

function ComparisonPanel({
  row, rows, metrics, outcomeLabel, onReBacktest, onDeploy,
}: {
  row: PromotionRow | null;
  rows: PromotionRow[];
  metrics: PromotionMetricRow[];
  outcomeLabel: (name: string) => string;
  onReBacktest?: (queueId: string) => void;
  onDeploy: (row: PromotionRow) => void;
}) {
  if (!row) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Select a VID from the list to see gate results and the comparison against the current best.
        </Typography>
      </Paper>
    );
  }

  // The "best" the candidate was compared against — its metrics are carried by
  // the decision row whose VID matches compared_vid within the same strategy.
  const bestRow = row.compared_vid == null
    ? null
    : rows.find((r) => r.strategy_id === row.strategy_id && r.strategy_vid === row.compared_vid) ?? null;

  const softMetrics = metrics
    .filter((m) => m.requirement_type === 'SOFT')
    .sort((a, b) => a.priority - b.priority);

  // First decisive soft metric (priority order) — highlighted as the decider.
  let decisiveKey: string | null = null;
  if (bestRow) {
    for (const m of softMetrics) {
      const cmp = compareMetric(
        readPromotionMetric(row, m.metric_key),
        readPromotionMetric(bestRow, m.metric_key),
        m.direction,
      );
      if (cmp !== 0) { decisiveKey = m.metric_key; break; }
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          {row.strategy_nm ?? row.strategy_id.slice(0, 8)} · v{row.strategy_vid}
        </Typography>
        <Chip size="small" label={outcomeLabel(row.outcome)} color={OUTCOME_COLOR[row.outcome] ?? 'default'} />
        {row.compared_vid != null && (
          <Typography variant="caption" color="text.secondary">vs v{row.compared_vid}</Typography>
        )}
      </Stack>

      <Typography variant="subtitle2" sx={{ mt: 1 }}>Hard gates</Typography>
      {row.gate_results && row.gate_results.length > 0 ? (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Gate</TableCell>
                <TableCell align="right">Value</TableCell>
                <TableCell align="right">Threshold</TableCell>
                <TableCell align="center">Result</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {row.gate_results.map((g) => (
                <TableRow key={g.name}>
                  <TableCell>{g.name}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{formatMetric(g.value)}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{formatMetric(g.threshold)}</TableCell>
                  <TableCell align="center">
                    <Chip size="small" label={g.passed ? 'PASS' : 'FAIL'}
                      color={g.passed ? 'success' : 'error'} variant="outlined" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">No gate snapshot recorded.</Typography>
      )}

      <Divider sx={{ my: 1.5 }} />

      <Typography variant="subtitle2">Soft comparison {bestRow ? `vs v${row.compared_vid}` : '(no baseline)'}</Typography>
      {bestRow ? (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Metric</TableCell>
                <TableCell align="right">This VID</TableCell>
                <TableCell align="right">Best v{row.compared_vid}</TableCell>
                <TableCell align="center">Winner</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {softMetrics.map((m) => {
                const cand = readPromotionMetric(row, m.metric_key);
                const best = readPromotionMetric(bestRow, m.metric_key);
                const cmp = compareMetric(cand, best, m.direction);
                const isDecisive = m.metric_key === decisiveKey;
                return (
                  <TableRow key={m.promotion_metric_id} selected={isDecisive}>
                    <TableCell>
                      {m.display_name}
                      {isDecisive && (
                        <Chip size="small" label="decisive" color="primary" variant="outlined"
                          sx={{ ml: 0.5, height: 18, fontSize: '0.6rem' }} />
                      )}
                    </TableCell>
                    <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{formatMetric(cand)}</TableCell>
                    <TableCell align="right" sx={{ fontFamily: 'monospace' }}>{formatMetric(best)}</TableCell>
                    <TableCell align="center">
                      {cmp === 0 ? '—' : cmp > 0 ? 'This' : 'Best'}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">
          No baseline to compare — first qualifying VID for this strategy.
        </Typography>
      )}

      <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
        {onReBacktest && (
          <Button size="small" variant="outlined" color="secondary"
            onClick={() => onReBacktest(row.queue_id)}>
            Re-backtest
          </Button>
        )}
        <Button size="small" variant="outlined" color="primary" onClick={() => onDeploy(row)}>
          Deploy
        </Button>
      </Stack>
    </Paper>
  );
}

function PromotionRulesFlyout({
  metrics,
  isLoading,
  isError,
  error,
}: {
  metrics: PromotionMetricRow[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}) {
  const [open, setOpen] = useState(false);
  const hoverCapable = useMediaQuery('(hover: hover) and (pointer: fine)');
  const sorted = useMemo(
    () => [...metrics].sort((a, b) => {
      const typeOrder = a.requirement_type === b.requirement_type
        ? 0
        : a.requirement_type === 'HARD' ? -1 : 1;
      return typeOrder !== 0 ? typeOrder : a.priority - b.priority;
    }),
    [metrics],
  );

  const hardCount = sorted.filter((m) => m.requirement_type === 'HARD').length;

  return (
    <Box
      sx={{
        position: 'fixed',
        right: 0,
        top: '50%',
        transform: 'translateY(-50%)',
        zIndex: (theme) => theme.zIndex.drawer + 1,
        display: 'flex',
        flexDirection: 'row-reverse',
        alignItems: 'stretch',
      }}
      onMouseEnter={hoverCapable ? () => setOpen(true) : undefined}
      onMouseLeave={hoverCapable ? () => setOpen(false) : undefined}
    >
      {/* Right-edge tab — always visible */}
      <Box
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label="Promotion rules"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((v) => !v);
          }
          if (e.key === 'Escape') setOpen(false);
        }}
        onClick={hoverCapable ? undefined : () => setOpen((v) => !v)}
        sx={{
          width: 40,
          minHeight: 120,
          bgcolor: open ? 'primary.main' : 'background.paper',
          color: open ? 'primary.contrastText' : 'text.primary',
          border: 1,
          borderRight: 0,
          borderColor: open ? 'primary.main' : 'divider',
          borderRadius: '10px 0 0 10px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 0.5,
          cursor: 'pointer',
          boxShadow: 3,
          py: 2,
          transition: 'background-color 0.15s ease',
          userSelect: 'none',
        }}
      >
        <Typography
          sx={{
            writingMode: 'vertical-rl',
            transform: 'rotate(180deg)',
            fontWeight: 700,
            fontSize: '0.72rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          Rules
        </Typography>
        {sorted.length > 0 && (
          <Typography variant="caption" sx={{ fontSize: '0.65rem', opacity: 0.9 }}>
            {sorted.length}
          </Typography>
        )}
      </Box>

      {/* Flyout — opens on hover / click; closes on mouse leave */}
      <Paper
        elevation={8}
        sx={{
          width: open ? { xs: 'calc(100vw - 48px)', md: 'min(860px, 58vw)' } : 0,
          opacity: open ? 1 : 0,
          overflow: 'hidden',
          transition: 'width 0.22s ease, opacity 0.18s ease',
          borderRadius: '10px 0 0 10px',
          borderRight: 0,
          maxHeight: '88vh',
          display: 'flex',
          flexDirection: 'column',
          pointerEvents: open ? 'auto' : 'none',
        }}
      >
        <Box sx={{ p: 2, pb: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Promotion rules
          </Typography>
          <Typography variant="body2" color="text.secondary">
            HARD gates must all pass ({hardCount}); SOFT metrics break ties in priority order.
          </Typography>
        </Box>

        <Box sx={{ flex: 1, overflow: 'auto', px: 2, pb: 2 }}>
          {isLoading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress size={28} />
            </Box>
          )}
          {isError && (
            <Alert severity="error">
              Failed to load promotion rules: {(error as Error)?.message ?? 'unknown error'}
            </Alert>
          )}
          {!isLoading && !isError && sorted.length === 0 && (
            <Alert severity="warning">
              No rows in REFDATA.PROMOTION_METRIC — refresh refdata or check the database seed.
            </Alert>
          )}
          {!isLoading && !isError && sorted.length > 0 && (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell align="right">Priority</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Display name</TableCell>
                    <TableCell>Metric key</TableCell>
                    <TableCell>Direction</TableCell>
                    <TableCell align="right">Threshold</TableCell>
                    <TableCell>Description</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sorted.map((m) => (
                    <TableRow key={m.promotion_metric_id} hover>
                      <TableCell align="right" sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                        {m.priority}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={m.requirement_type}
                          color={m.requirement_type === 'HARD' ? 'error' : 'primary'}
                          variant="outlined"
                          sx={{ height: 22, fontSize: '0.7rem' }}
                        />
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                        {m.name}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{m.display_name}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                        {m.metric_key}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>
                        {m.direction === 'lower_is_better' ? 'Lower is better' : 'Higher is better'}
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                        {m.threshold != null ? formatMetric(m.threshold) : '—'}
                      </TableCell>
                      <TableCell sx={{ minWidth: 200 }}>
                        <Typography variant="body2" color="text.secondary">
                          {m.description ?? '—'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      </Paper>
    </Box>
  );
}
