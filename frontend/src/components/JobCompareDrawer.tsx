import {
  Box, Chip, Drawer, IconButton, Paper, Stack, Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import type { JobRow } from '../types/jobs';
import type { OptimizeRequest, FactorConfig } from '../types/backtest';

interface Props {
  open: boolean;
  jobA: JobRow | null;
  jobB: JobRow | null;
  onClose: () => void;
}

const DRAWER_WIDTH = 800;

export default function JobCompareDrawer({ open, jobA, jobB, onClose }: Props) {
  const configA = jobA?.config_json as OptimizeRequest | null;
  const configB = jobB?.config_json as OptimizeRequest | null;

  if (!jobA || !jobB) {
    return (
      <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: DRAWER_WIDTH, p: 2 } }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">Compare Jobs</Typography>
          <IconButton onClick={onClose}><CloseIcon /></IconButton>
        </Stack>
        <Typography color="text.secondary">
          Select two jobs to compare. Click "Compare" on a job, then select another job to compare with.
        </Typography>
      </Drawer>
    );
  }

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: DRAWER_WIDTH, p: 0 } }}>
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6" sx={{ fontWeight: 600 }}>Compare Jobs</Typography>
            <IconButton onClick={onClose}><CloseIcon /></IconButton>
          </Stack>
        </Box>

        {/* Comparison Content */}
        <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
          {/* Performance Summary - Best Sharpe */}
          <Paper 
            variant="outlined" 
            sx={{ 
              p: 2, mb: 2, 
              bgcolor: 'grey.900', 
              color: 'grey.100',
              borderRadius: 2,
            }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, color: 'grey.400' }}>
              Performance Summary
            </Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: 2, alignItems: 'center' }}>
              <SharpeDisplay 
                label="Job A" 
                sharpe={jobA.best_sharpe} 
                trials={jobA.total_trials}
                isWinner={jobA.best_sharpe !== null && jobB.best_sharpe !== null && jobA.best_sharpe > jobB.best_sharpe}
              />
              <Box sx={{ textAlign: 'center' }}>
                <CompareArrowsIcon sx={{ color: 'grey.500' }} />
              </Box>
              <SharpeDisplay 
                label="Job B" 
                sharpe={jobB.best_sharpe} 
                trials={jobB.total_trials}
                isWinner={jobA.best_sharpe !== null && jobB.best_sharpe !== null && jobB.best_sharpe > jobA.best_sharpe}
              />
            </Box>
          </Paper>

          {/* Job Headers */}
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: 1, mb: 2 }}>
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'primary.50' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Job A</Typography>
              <Typography variant="caption" noWrap title={jobA.strategy_nm || ''}>
                {jobA.strategy_nm || 'Unnamed'}
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Chip size="small" label={jobA.queue_status} color={getStatusColor(jobA.queue_status)} />
              </Box>
            </Paper>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CompareArrowsIcon color="disabled" />
            </Box>
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'secondary.50' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Job B</Typography>
              <Typography variant="caption" noWrap title={jobB.strategy_nm || ''}>
                {jobB.strategy_nm || 'Unnamed'}
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Chip size="small" label={jobB.queue_status} color={getStatusColor(jobB.queue_status)} />
              </Box>
            </Paper>
          </Box>

          {/* Comparison Rows */}
          <Stack spacing={1}>
            <CompareSection title="Basic Settings">
              <CompareRow 
                label="Symbol" 
                valueA={configA?.symbol} 
                valueB={configB?.symbol} 
              />
              <CompareRow 
                label="Data Source" 
                valueA={configA?.data_source} 
                valueB={configB?.data_source} 
              />
              <CompareRow 
                label="Date Range" 
                valueA={configA ? `${configA.start} → ${configA.end}` : undefined}
                valueB={configB ? `${configB.start} → ${configB.end}` : undefined}
              />
              <CompareRow 
                label="Trading Period" 
                valueA={configA?.trading_period ? `${configA.trading_period} days` : undefined}
                valueB={configB?.trading_period ? `${configB.trading_period} days` : undefined}
              />
              <CompareRow 
                label="Fee (bps)" 
                valueA={configA?.fee_bps?.toString()}
                valueB={configB?.fee_bps?.toString()}
              />
              <CompareRow 
                label="Refresh Dataset" 
                valueA={configA?.refresh_dataset ? 'Yes' : 'No'}
                valueB={configB?.refresh_dataset ? 'Yes' : 'No'}
              />
            </CompareSection>

            {/* Compare Factors */}
            <CompareSection title="Factors">
              {compareFactors(configA?.factors || [], configB?.factors || [])}
            </CompareSection>

            {/* Conjunction */}
            {((configA?.factors?.length || 0) > 1 || (configB?.factors?.length || 0) > 1) && (
              <CompareSection title="Multi-Factor">
                <CompareRow 
                  label="Conjunction" 
                  valueA={configA?.conjunction}
                  valueB={configB?.conjunction}
                />
              </CompareSection>
            )}

            {/* Walk-Forward */}
            {(configA?.walk_forward || configB?.walk_forward) && (
              <CompareSection title="Walk-Forward">
                <CompareRow 
                  label="Enabled" 
                  valueA={configA?.walk_forward ? 'Yes' : 'No'}
                  valueB={configB?.walk_forward ? 'Yes' : 'No'}
                />
                <CompareRow 
                  label="Split Ratio" 
                  valueA={configA?.split_ratio ? `${(configA.split_ratio * 100).toFixed(0)}%` : undefined}
                  valueB={configB?.split_ratio ? `${(configB.split_ratio * 100).toFixed(0)}%` : undefined}
                />
              </CompareSection>
            )}

            {/* Results Summary */}
            {(jobA.queue_status === 'COMPLETED' || jobB.queue_status === 'COMPLETED') && (
              <CompareSection title="Results">
                <CompareRow 
                  label="Best Sharpe" 
                  valueA={jobA.best_sharpe?.toFixed(4)}
                  valueB={jobB.best_sharpe?.toFixed(4)}
                />
                <CompareRow 
                  label="Total Trials" 
                  valueA={jobA.total_trials?.toString()}
                  valueB={jobB.total_trials?.toString()}
                />
                <CompareRow 
                  label="Status" 
                  valueA={jobA.queue_status}
                  valueB={jobB.queue_status}
                />
              </CompareSection>
            )}

            {/* Grid Search Ranges */}
            <CompareSection title="Grid Search Ranges">
              {compareGridRanges(configA?.factors || [], configB?.factors || [])}
            </CompareSection>

            {/* Job Metadata */}
            <CompareSection title="Job Info">
              <CompareRow 
                label="Submitted" 
                valueA={new Date(jobA.transact_from_ts).toLocaleString()}
                valueB={new Date(jobB.transact_from_ts).toLocaleString()}
              />
              <CompareRow 
                label="Priority" 
                valueA={jobA.priority.toString()}
                valueB={jobB.priority.toString()}
              />
              <CompareRow 
                label="Queue ID" 
                valueA={jobA.queue_id.substring(0, 8) + '...'}
                valueB={jobB.queue_id.substring(0, 8) + '...'}
              />
            </CompareSection>
          </Stack>
        </Box>
      </Box>
    </Drawer>
  );
}

function CompareSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>{title}</Typography>
      <Stack spacing={0.5}>{children}</Stack>
    </Paper>
  );
}

function CompareRow({ label, valueA, valueB }: { label: string; valueA?: string; valueB?: string }) {
  const isDifferent = valueA !== valueB;
  
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '120px 1fr 40px 1fr', gap: 1, alignItems: 'center' }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography 
        variant="caption" 
        sx={{ 
          fontWeight: isDifferent ? 600 : 400,
          color: isDifferent ? 'primary.main' : 'text.primary',
          bgcolor: isDifferent ? 'primary.50' : 'transparent',
          px: isDifferent ? 0.5 : 0,
          borderRadius: 0.5,
        }}
      >
        {valueA || '—'}
      </Typography>
      <Box sx={{ textAlign: 'center' }}>
        {isDifferent && <Typography variant="caption" color="warning.main">≠</Typography>}
      </Box>
      <Typography 
        variant="caption" 
        sx={{ 
          fontWeight: isDifferent ? 600 : 400,
          color: isDifferent ? 'secondary.main' : 'text.primary',
          bgcolor: isDifferent ? 'secondary.50' : 'transparent',
          px: isDifferent ? 0.5 : 0,
          borderRadius: 0.5,
        }}
      >
        {valueB || '—'}
      </Typography>
    </Box>
  );
}

function compareFactors(factorsA: FactorConfig[], factorsB: FactorConfig[]): React.ReactNode {
  const maxLen = Math.max(factorsA.length, factorsB.length);
  if (maxLen === 0) {
    return <Typography variant="caption" color="text.secondary">No factors configured</Typography>;
  }

  const rows: React.ReactNode[] = [];
  
  for (let i = 0; i < maxLen; i++) {
    const fA = factorsA[i];
    const fB = factorsB[i];
    
    rows.push(
      <Box key={i} sx={{ mt: i > 0 ? 1 : 0 }}>
        <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.5 }}>
          Factor {i + 1}
        </Typography>
        <CompareRow label="Indicator" valueA={fA?.indicator} valueB={fB?.indicator} />
        <CompareRow label="Strategy" valueA={fA?.strategy} valueB={fB?.strategy} />
        <CompareRow label="Data Column" valueA={fA?.data_column} valueB={fB?.data_column} />
        <CompareRow 
          label="Window" 
          valueA={fA ? `${fA.window_range.min}-${fA.window_range.max} (${fA.window_range.step})` : undefined}
          valueB={fB ? `${fB.window_range.min}-${fB.window_range.max} (${fB.window_range.step})` : undefined}
        />
        <CompareRow 
          label="Signal" 
          valueA={fA ? `${fA.signal_range.min}-${fA.signal_range.max} (${fA.signal_range.step})` : undefined}
          valueB={fB ? `${fB.signal_range.min}-${fB.signal_range.max} (${fB.signal_range.step})` : undefined}
        />
      </Box>
    );
  }
  
  return <>{rows}</>;
}

function compareGridRanges(factorsA: FactorConfig[], factorsB: FactorConfig[]): React.ReactNode {
  const maxLen = Math.max(factorsA.length, factorsB.length);
  if (maxLen === 0) {
    return <Typography variant="caption" color="text.secondary">No factors configured</Typography>;
  }

  const rows: React.ReactNode[] = [];
  
  for (let i = 0; i < maxLen; i++) {
    const fA = factorsA[i];
    const fB = factorsB[i];
    
    // Calculate grid sizes
    const gridSizeA = fA ? calculateGridSize(fA.window_range, fA.signal_range) : 0;
    const gridSizeB = fB ? calculateGridSize(fB.window_range, fB.signal_range) : 0;
    
    rows.push(
      <Box key={i} sx={{ mt: i > 0 ? 1.5 : 0 }}>
        <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.5 }}>
          Factor {i + 1}: {fA?.indicator || fB?.indicator || 'Unknown'}
        </Typography>
        <CompareRow 
          label="Window Min" 
          valueA={fA?.window_range.min.toString()}
          valueB={fB?.window_range.min.toString()}
        />
        <CompareRow 
          label="Window Max" 
          valueA={fA?.window_range.max.toString()}
          valueB={fB?.window_range.max.toString()}
        />
        <CompareRow 
          label="Window Step" 
          valueA={fA?.window_range.step.toString()}
          valueB={fB?.window_range.step.toString()}
        />
        <CompareRow 
          label="Signal Min" 
          valueA={fA?.signal_range.min.toString()}
          valueB={fB?.signal_range.min.toString()}
        />
        <CompareRow 
          label="Signal Max" 
          valueA={fA?.signal_range.max.toString()}
          valueB={fB?.signal_range.max.toString()}
        />
        <CompareRow 
          label="Signal Step" 
          valueA={fA?.signal_range.step.toString()}
          valueB={fB?.signal_range.step.toString()}
        />
        <CompareRow 
          label="Grid Size" 
          valueA={gridSizeA > 0 ? `${gridSizeA} combos` : undefined}
          valueB={gridSizeB > 0 ? `${gridSizeB} combos` : undefined}
        />
      </Box>
    );
  }
  
  return <>{rows}</>;
}

function calculateGridSize(
  windowRange: { min: number; max: number; step: number },
  signalRange: { min: number; max: number; step: number }
): number {
  const windowCount = Math.floor((windowRange.max - windowRange.min) / windowRange.step) + 1;
  const signalCount = Math.floor((signalRange.max - signalRange.min) / signalRange.step) + 1;
  return windowCount * signalCount;
}

function getStatusColor(status: string): 'success' | 'error' | 'primary' | 'warning' | 'default' {
  switch (status) {
    case 'COMPLETED': return 'success';
    case 'FAILED': return 'error';
    case 'RUNNING': return 'primary';
    case 'CANCELLED':
    case 'CANCEL_REQUESTED': return 'warning';
    default: return 'default';
  }
}

function SharpeDisplay({ 
  label, 
  sharpe, 
  trials, 
  isWinner 
}: { 
  label: string; 
  sharpe: number | null; 
  trials: number | null;
  isWinner: boolean;
}) {
  const displaySharpe = sharpe !== null ? sharpe.toFixed(4) : '—';
  const isGood = sharpe !== null && sharpe >= 1.5;
  const isOk = sharpe !== null && sharpe >= 1.0 && sharpe < 1.5;
  
  return (
    <Box sx={{ textAlign: 'center' }}>
      <Typography variant="caption" sx={{ color: 'grey.500', display: 'block', mb: 0.5 }}>
        {label}
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
      {trials !== null && (
        <Typography variant="caption" sx={{ color: 'grey.600', display: 'block' }}>
          ({trials} trials)
        </Typography>
      )}
    </Box>
  );
}
