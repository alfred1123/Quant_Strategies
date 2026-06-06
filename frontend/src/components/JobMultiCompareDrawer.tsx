import {
  Box, Chip, Drawer, IconButton, Paper, Stack, Typography,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import type { JobRow } from '../types/jobs';
import type { OptimizeRequest, FactorConfig } from '../types/backtest';

interface Props {
  open: boolean;
  jobs: JobRow[];
  onClose: () => void;
}

const DRAWER_WIDTH = 900;

export default function JobMultiCompareDrawer({ open, jobs, onClose }: Props) {
  if (jobs.length < 2) {
    return (
      <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: DRAWER_WIDTH, p: 2 } }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">Compare Jobs</Typography>
          <IconButton onClick={onClose}><CloseIcon /></IconButton>
        </Stack>
        <Typography color="text.secondary">
          Select at least 2 jobs to compare.
        </Typography>
      </Drawer>
    );
  }

  const configs = jobs.map(j => j.config_json as OptimizeRequest | null);
  
  // Find the best sharpe among all jobs
  const bestSharpeValue = Math.max(...jobs.map(j => j.best_sharpe ?? -Infinity));

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: DRAWER_WIDTH, p: 0 } }}>
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Compare {jobs.length} Jobs
            </Typography>
            <IconButton onClick={onClose}><CloseIcon /></IconButton>
          </Stack>
        </Box>

        {/* Content */}
        <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
          {/* Performance Summary */}
          <Paper 
            variant="outlined" 
            sx={{ p: 2, mb: 3, bgcolor: 'grey.900', color: 'grey.100', borderRadius: 2 }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: 'grey.400' }}>
              Performance Summary
            </Typography>
            <Stack direction="row" spacing={3} justifyContent="center">
              {jobs.map((job, i) => (
                <SharpeCard 
                  key={job.queue_id}
                  index={i + 1}
                  job={job}
                  isWinner={job.best_sharpe === bestSharpeValue && bestSharpeValue > -Infinity}
                />
              ))}
            </Stack>
          </Paper>

          {/* Comparison Table */}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600, minWidth: 150 }}>Parameter</TableCell>
                  {jobs.map((job, i) => (
                    <TableCell key={job.queue_id} sx={{ fontWeight: 600, minWidth: 150 }}>
                      <Stack spacing={0.5}>
                        <Typography variant="caption" sx={{ fontWeight: 600 }}>
                          Job {i + 1}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" noWrap title={job.strategy_nm || ''}>
                          {job.strategy_nm?.slice(0, 20) || 'Unnamed'}
                        </Typography>
                      </Stack>
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {/* Results */}
                <SectionRow label="Results" colSpan={jobs.length + 1} />
                <CompareTableRow 
                  label="Best Sharpe" 
                  values={jobs.map(j => j.best_sharpe?.toFixed(4))}
                  highlightMax
                />
                <CompareTableRow 
                  label="Total Trials" 
                  values={jobs.map(j => j.total_trials?.toString())}
                />
                <CompareTableRow 
                  label="Status" 
                  values={jobs.map(j => j.queue_status)}
                />

                {/* Basic Settings */}
                <SectionRow label="Basic Settings" colSpan={jobs.length + 1} />
                <CompareTableRow 
                  label="Symbol" 
                  values={configs.map(c => c?.symbol)}
                />
                <CompareTableRow 
                  label="Data Source" 
                  values={configs.map(c => c?.data_source)}
                />
                <CompareTableRow 
                  label="Date Range" 
                  values={configs.map(c => c ? `${c.start} → ${c.end}` : undefined)}
                />
                <CompareTableRow 
                  label="Trading Period" 
                  values={configs.map(c => c?.trading_period ? `${c.trading_period} days` : undefined)}
                />
                <CompareTableRow 
                  label="Fee (bps)" 
                  values={configs.map(c => c?.fee_bps?.toString())}
                />

                {/* Factors */}
                {renderFactorRows(configs)}

                {/* Walk-Forward */}
                {configs.some(c => c?.walk_forward) && (
                  <>
                    <SectionRow label="Walk-Forward" colSpan={jobs.length + 1} />
                    <CompareTableRow 
                      label="Enabled" 
                      values={configs.map(c => c?.walk_forward ? 'Yes' : 'No')}
                    />
                    <CompareTableRow 
                      label="Split Ratio" 
                      values={configs.map(c => c?.split_ratio ? `${(c.split_ratio * 100).toFixed(0)}%` : undefined)}
                    />
                  </>
                )}

                {/* Job Info */}
                <SectionRow label="Job Info" colSpan={jobs.length + 1} />
                <CompareTableRow 
                  label="Submitted" 
                  values={jobs.map(j => new Date(j.transact_from_ts).toLocaleString())}
                />
                <CompareTableRow 
                  label="Priority" 
                  values={jobs.map(j => j.priority.toString())}
                />
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      </Box>
    </Drawer>
  );
}

function SharpeCard({ index, job, isWinner }: { index: number; job: JobRow; isWinner: boolean }) {
  const sharpe = job.best_sharpe;
  const displaySharpe = sharpe !== null ? sharpe.toFixed(4) : '—';
  const isGood = sharpe !== null && sharpe >= 1.5;
  const isOk = sharpe !== null && sharpe >= 1.0 && sharpe < 1.5;

  return (
    <Box sx={{ textAlign: 'center', minWidth: 100 }}>
      <Typography variant="caption" sx={{ color: 'grey.500', display: 'block', mb: 0.5 }}>
        Job {index}
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
        {isWinner && <TrendingUpIcon sx={{ color: 'success.main', fontSize: 20 }} />}
        <Typography 
          variant="h5" 
          sx={{ 
            fontWeight: 700,
            color: sharpe === null ? 'grey.500' : isGood ? 'success.light' : isOk ? 'warning.light' : 'error.light',
          }}
        >
          {displaySharpe}
        </Typography>
      </Box>
      <Typography variant="caption" sx={{ color: 'grey.500' }}>
        Best Sharpe
      </Typography>
      {job.total_trials !== null && (
        <Typography variant="caption" sx={{ color: 'grey.600', display: 'block' }}>
          ({job.total_trials} trials)
        </Typography>
      )}
    </Box>
  );
}

function SectionRow({ label, colSpan }: { label: string; colSpan: number }) {
  return (
    <TableRow>
      <TableCell 
        colSpan={colSpan} 
        sx={{ bgcolor: 'grey.100', fontWeight: 600, py: 1 }}
      >
        {label}
      </TableCell>
    </TableRow>
  );
}

function CompareTableRow({ 
  label, 
  values, 
  highlightMax = false 
}: { 
  label: string; 
  values: (string | undefined)[]; 
  highlightMax?: boolean;
}) {
  const allSame = values.every(v => v === values[0]);
  
  // Find max value for highlighting (only for numeric strings)
  let maxIndex = -1;
  if (highlightMax) {
    let maxVal = -Infinity;
    values.forEach((v, i) => {
      const num = parseFloat(v || '');
      if (!isNaN(num) && num > maxVal) {
        maxVal = num;
        maxIndex = i;
      }
    });
  }

  return (
    <TableRow>
      <TableCell sx={{ color: 'text.secondary', fontSize: 12 }}>{label}</TableCell>
      {values.map((value, i) => {
        const isDifferent = !allSame;
        const isMax = highlightMax && i === maxIndex;
        return (
          <TableCell 
            key={i}
            sx={{
              fontWeight: isDifferent ? 600 : 400,
              bgcolor: isMax ? 'success.50' : isDifferent ? 'warning.50' : 'transparent',
              color: isMax ? 'success.main' : isDifferent ? 'text.primary' : 'text.secondary',
            }}
          >
            {value || '—'}
          </TableCell>
        );
      })}
    </TableRow>
  );
}

function renderFactorRows(configs: (OptimizeRequest | null)[]): React.ReactNode {
  const maxFactors = Math.max(...configs.map(c => c?.factors?.length || 0));
  if (maxFactors === 0) return null;

  const rows: React.ReactNode[] = [];

  for (let i = 0; i < maxFactors; i++) {
    rows.push(
      <SectionRow key={`factor-header-${i}`} label={`Factor ${i + 1}`} colSpan={configs.length + 1} />
    );
    rows.push(
      <CompareTableRow 
        key={`factor-${i}-indicator`}
        label="Indicator" 
        values={configs.map(c => c?.factors?.[i]?.indicator)}
      />
    );
    rows.push(
      <CompareTableRow 
        key={`factor-${i}-strategy`}
        label="Strategy" 
        values={configs.map(c => c?.factors?.[i]?.strategy)}
      />
    );
    rows.push(
      <CompareTableRow 
        key={`factor-${i}-column`}
        label="Data Column" 
        values={configs.map(c => c?.factors?.[i]?.data_column)}
      />
    );
    rows.push(
      <CompareTableRow 
        key={`factor-${i}-window`}
        label="Window Range" 
        values={configs.map(c => {
          const f = c?.factors?.[i];
          return f ? `${f.window_range.min}-${f.window_range.max} (${f.window_range.step})` : undefined;
        })}
      />
    );
    rows.push(
      <CompareTableRow 
        key={`factor-${i}-signal`}
        label="Signal Range" 
        values={configs.map(c => {
          const f = c?.factors?.[i];
          return f ? `${f.signal_range.min}-${f.signal_range.max} (${f.signal_range.step})` : undefined;
        })}
      />
    );
  }

  // Conjunction if multiple factors
  if (maxFactors > 1) {
    rows.push(
      <CompareTableRow 
        key="conjunction"
        label="Conjunction" 
        values={configs.map(c => c?.conjunction)}
      />
    );
  }

  return <>{rows}</>;
}
