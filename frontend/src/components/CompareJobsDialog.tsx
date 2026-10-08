import { useEffect, useState } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  Collapse,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { fetchJob } from '../api/jobs';
import type { JobDetail } from '../types/jobs';

interface CompareJobsDialogProps {
  open: boolean;
  onClose: () => void;
  queueIds: [string, string] | null;
}

interface JobSummary {
  strategyNm: string | null;
  symbol: string | null;
  dateRange: string | null;
  factors: Array<{ name: string; window?: string; signal?: string }>;
  sharpe: number | null;
  calmar: number | null;
  totalReturn: number | null;
  maxDrawdown: number | null;
  configJson: Record<string, unknown> | null;
}

function rangeLabel(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const { min, max, step } = value as Record<string, unknown>;
  if (typeof min !== 'number' || typeof max !== 'number' || typeof step !== 'number') return undefined;
  return `min ${min} max ${max} step ${step}`;
}

// eslint-disable-next-line react-refresh/only-export-components -- the unit test imports this helper
export function extractJobSummary(detail: JobDetail): JobSummary {
  const config = detail.config_json ?? {};
  const result = detail.result ?? {};
  const perf = (result.performance as Record<string, unknown>) ?? {};
  const metrics = (perf.strategy_metrics as Record<string, unknown>) ?? {};

  const factors = Array.isArray(config.factors)
    ? config.factors.map((f: Record<string, unknown>) => ({
        name: String(f.indicator ?? f.name ?? 'Unknown'),
        window: rangeLabel(f.window_range),
        signal: rangeLabel(f.signal_range),
      }))
    : [];

  const startDate = config.start;
  const endDate = config.end;
  const dateRange =
    startDate && endDate ? `${String(startDate)} → ${String(endDate)}` : null;

  const sharpeVal = metrics['Sharpe Ratio'];
  const calmarVal = metrics['Calmar Ratio'];
  const totalReturnVal = metrics['Total Return'];
  const maxDrawdownVal = metrics['Max Drawdown'];

  return {
    strategyNm: detail.strategy_nm,
    symbol: config.symbol ? String(config.symbol) : null,
    dateRange,
    factors,
    sharpe: typeof sharpeVal === 'number' ? sharpeVal : null,
    calmar: typeof calmarVal === 'number' ? calmarVal : null,
    totalReturn: typeof totalReturnVal === 'number' ? totalReturnVal : null,
    maxDrawdown: typeof maxDrawdownVal === 'number' ? maxDrawdownVal : null,
    configJson: detail.config_json,
  };
}

function formatPercent(value: number | null): string {
  if (value === null) return '—';
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value: number | null, decimals = 2): string {
  if (value === null) return '—';
  return value.toFixed(decimals);
}

// eslint-disable-next-line react-refresh/only-export-components -- the unit test imports this helper
export function formatDiff(a: number | null, b: number | null, isPercent = false, lowerIsBetter = false): { text: string; color: string } {
  if (a === null || b === null) return { text: '—', color: 'text.secondary' };
  const diff = a - b;
  if (diff === 0) return { text: '0', color: 'text.secondary' };
  const sign = diff > 0 ? '+' : '';
  const text = isPercent
    ? `${sign}${(diff * 100).toFixed(2)} pp`
    : `${sign}${diff.toFixed(2)}`;
  const color = (lowerIsBetter ? diff < 0 : diff > 0) ? 'success.main' : 'error.main';
  return { text, color };
}

function DifferenceColumn({ a, b }: { a: JobSummary; b: JobSummary }) {
  const sharpeDiff = formatDiff(a.sharpe, b.sharpe);
  const calmarDiff = formatDiff(a.calmar, b.calmar);
  const returnDiff = formatDiff(a.totalReturn, b.totalReturn, true);
  const ddDiff = formatDiff(a.maxDrawdown, b.maxDrawdown, true, true);

  return (
    <Box sx={{ minWidth: 100, textAlign: 'center' }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
        A compare to B
      </Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        &nbsp;
      </Typography>

      <Divider sx={{ my: 1.5 }} />

      <Typography variant="caption" color="text.secondary">
        &nbsp;
      </Typography>
      <Typography variant="body2" gutterBottom>
        &nbsp;
      </Typography>

      <Typography variant="caption" color="text.secondary">
        &nbsp;
      </Typography>
      <Typography variant="body2" gutterBottom>
        &nbsp;
      </Typography>

      <Typography variant="caption" color="text.secondary">
        &nbsp;
      </Typography>
      <Typography variant="body2" gutterBottom>
        &nbsp;
      </Typography>

      <Divider sx={{ my: 1.5 }} />

      <Typography variant="subtitle2" gutterBottom>
        Diff
      </Typography>

      <Grid container spacing={1}>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Sharpe
          </Typography>
          <Typography variant="body2" sx={{ color: sharpeDiff.color }}>{sharpeDiff.text}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Calmar
          </Typography>
          <Typography variant="body2" sx={{ color: calmarDiff.color }}>{calmarDiff.text}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Return
          </Typography>
          <Typography variant="body2" sx={{ color: returnDiff.color }}>{returnDiff.text}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Drawdown
          </Typography>
          <Typography variant="body2" sx={{ color: ddDiff.color }}>{ddDiff.text}</Typography>
        </Grid>
      </Grid>
    </Box>
  );
}

function JobColumn({ summary, label }: { summary: JobSummary; label: string }) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
        {label}
      </Typography>
      <Typography variant="body2" color="text.secondary" noWrap title={summary.strategyNm ?? undefined}>
        {summary.strategyNm ?? '—'}
      </Typography>

      <Divider sx={{ my: 1.5 }} />

      <Typography variant="caption" color="text.secondary">
        Symbol
      </Typography>
      <Typography variant="body2" gutterBottom>
        {summary.symbol ?? '—'}
      </Typography>

      <Typography variant="caption" color="text.secondary">
        Date Range
      </Typography>
      <Typography variant="body2" gutterBottom>
        {summary.dateRange ?? '—'}
      </Typography>

      <Typography variant="caption" color="text.secondary">
        Factors
      </Typography>
      {summary.factors.length > 0 ? (
        <Stack spacing={0.5} sx={{ mb: 1 }}>
          {summary.factors.map((f, i) => (
            <Typography key={i} variant="body2">
              {f.name}
              {f.window !== undefined && ` (win: ${f.window})`}
              {f.signal !== undefined && ` (sig: ${f.signal})`}
            </Typography>
          ))}
        </Stack>
      ) : (
        <Typography variant="body2" gutterBottom>
          —
        </Typography>
      )}

      <Divider sx={{ my: 1.5 }} />

      <Typography variant="subtitle2" gutterBottom>
        Results
      </Typography>

      <Grid container spacing={1}>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Sharpe
          </Typography>
          <Typography variant="body2">{formatNumber(summary.sharpe)}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Calmar
          </Typography>
          <Typography variant="body2">{formatNumber(summary.calmar)}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Total Return
          </Typography>
          <Typography variant="body2">{formatPercent(summary.totalReturn)}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="caption" color="text.secondary">
            Max Drawdown
          </Typography>
          <Typography variant="body2">{formatPercent(summary.maxDrawdown)}</Typography>
        </Grid>
      </Grid>

      <Divider sx={{ my: 1.5 }} />

      <Button
        size="small"
        onClick={() => setShowRaw(!showRaw)}
        endIcon={showRaw ? <ExpandLessIcon /> : <ExpandMoreIcon />}
      >
        Raw JSON
      </Button>
      <Collapse in={showRaw}>
        <Paper
          variant="outlined"
          sx={{
            p: 1.5,
            mt: 1,
            bgcolor: '#000',
            color: '#fff',
            maxHeight: 200,
            overflow: 'auto',
          }}
        >
          <Typography
            component="pre"
            variant="caption"
            sx={{
              fontFamily: 'monospace',
              color: '#fff',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              m: 0,
            }}
          >
            {JSON.stringify(summary.configJson, null, 2)}
          </Typography>
        </Paper>
      </Collapse>
    </Box>
  );
}

function CompareJobsBody({ queueIds }: { queueIds: [string, string] }) {
  const [error, setError] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<[JobSummary, JobSummary] | null>(null);
  const loading = summaries === null && error === null;

  useEffect(() => {
    let cancelled = false;

    Promise.all([fetchJob(queueIds[0]), fetchJob(queueIds[1])])
      .then(([job1, job2]) => {
        if (cancelled) return;
        setSummaries([extractJobSummary(job1), extractJobSummary(job2)]);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load jobs');
      });

    return () => {
      cancelled = true;
    };
  }, [queueIds]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Typography color="error" sx={{ py: 2 }}>
        {error}
      </Typography>
    );
  }

  if (!summaries) return null;

  return (
    <Stack direction="row" spacing={3} divider={<Divider orientation="vertical" flexItem />}>
      <JobColumn summary={summaries[0]} label="Job A" />
      <DifferenceColumn a={summaries[0]} b={summaries[1]} />
      <JobColumn summary={summaries[1]} label="Job B" />
    </Stack>
  );
}

export default function CompareJobsDialog({ open, onClose, queueIds }: CompareJobsDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center' }}>
        Compare Jobs
        <IconButton onClick={onClose} sx={{ ml: 'auto' }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {open && queueIds && (
          <CompareJobsBody key={`${queueIds[0]}:${queueIds[1]}`} queueIds={queueIds} />
        )}
      </DialogContent>
    </Dialog>
  );
}
