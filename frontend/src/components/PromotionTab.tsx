import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip,
  CircularProgress, Divider, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Typography,
} from '@mui/material';
import { usePromotions } from '../api/promotion';
import { usePromotionMetrics, usePromotionStates } from '../api/refdata';
import { formatMetric } from '../utils/format';
import type { PromotionRow } from '../types/promotion';
import type { PromotionMetricRow } from '../types/refdata';

const OUTCOME_COLOR: Record<string, 'success' | 'default' | 'warning' | 'error'> = {
  PROMOTED: 'success',
  KEPT: 'default',
  DEMOTED: 'warning',
  REJECTED: 'error',
};

// Maps REFDATA.PROMOTION_METRIC.metric_key → the shredded numeric column on PromotionRow.
const METRIC_FIELD: Record<string, keyof PromotionRow> = {
  'Sharpe Ratio': 'sharpe_ratio',
  'Calmar Ratio': 'calmar_ratio',
  'Max Drawdown': 'max_drawdown',
  'Total Return': 'total_return',
  'Annualized Return': 'annualized_return',
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
  const { data: metrics = [] } = usePromotionMetrics();
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
    const best = rows.filter((r) => r.is_best_ind === 'Y' && r.sharpe_ratio != null);
    if (best.length === 0) return null;
    return best.reduce((a, b) => ((b.sharpe_ratio ?? -Infinity) > (a.sharpe_ratio ?? -Infinity) ? b : a));
  }, [rows]);

  const selected = useMemo(
    () => rows.find((r) => r.promotion_id === selectedId) ?? null,
    [rows, selectedId],
  );

  if (promotions.isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
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
          <Stack spacing={3}>
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
            <RulesCard metrics={metrics} />
          </Stack>
        </Box>
      )}
    </Stack>
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

function Metric({ label, value }: { label: string; value: number | null }) {
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
      const field = METRIC_FIELD[m.metric_key];
      if (!field) continue;
      const cmp = compareMetric(row[field] as number | null, bestRow[field] as number | null, m.direction);
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
                const field = METRIC_FIELD[m.metric_key];
                if (!field) return null;
                const cand = row[field] as number | null;
                const best = bestRow[field] as number | null;
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

function RulesCard({ metrics }: { metrics: PromotionMetricRow[] }) {
  const hard = metrics.filter((m) => m.requirement_type === 'HARD').sort((a, b) => a.priority - b.priority);
  const soft = metrics.filter((m) => m.requirement_type === 'SOFT').sort((a, b) => a.priority - b.priority);
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>Promotion rules</Typography>
      <Typography variant="caption" color="text.secondary">
        Hard gates (must all pass), then soft metrics compared in priority order.
      </Typography>

      <Typography variant="caption" sx={{ display: 'block', mt: 1.5, fontWeight: 600 }}>Hard gates</Typography>
      <Stack spacing={0.5} sx={{ mt: 0.5 }}>
        {hard.map((m) => (
          <Stack key={m.promotion_metric_id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip size="small" label="HARD" color="error" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
            <Typography variant="body2">{m.display_name}</Typography>
            <Typography variant="caption" color="text.secondary">
              ({m.direction === 'lower_is_better' ? '≤' : '≥'} {formatMetric(m.threshold)})
            </Typography>
          </Stack>
        ))}
      </Stack>

      <Typography variant="caption" sx={{ display: 'block', mt: 1.5, fontWeight: 600 }}>Soft metrics (priority order)</Typography>
      <Stack spacing={0.5} sx={{ mt: 0.5 }}>
        {soft.map((m, i) => (
          <Stack key={m.promotion_metric_id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip size="small" label={i + 1} variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
            <Typography variant="body2">{m.display_name}</Typography>
            <Typography variant="caption" color="text.secondary">
              ({m.direction === 'lower_is_better' ? 'lower' : 'higher'} is better)
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
