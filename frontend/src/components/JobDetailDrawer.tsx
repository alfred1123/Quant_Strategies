import { useState } from 'react';
import {
  Box, Button, Chip, Divider, Drawer, IconButton, Stack, Tab, Tabs,
  Typography, Paper,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import EditIcon from '@mui/icons-material/Edit';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import ReplayIcon from '@mui/icons-material/Replay';
import type { JobRow } from '../types/jobs';
import type { OptimizeRequest, FactorConfig } from '../types/backtest';

interface Props {
  open: boolean;
  job: JobRow | null;
  onClose: () => void;
  onCloneEdit: (config: OptimizeRequest, name: string) => void;
  onCompare: (job: JobRow) => void;
  onRerun: (queueId: string) => void;
}

const DRAWER_WIDTH = 480;

export default function JobDetailDrawer({
  open,
  job,
  onClose,
  onCloneEdit,
  onCompare,
  onRerun,
}: Props) {
  const [tab, setTab] = useState(0);
  const [copySuccess, setCopySuccess] = useState(false);

  const config = job?.config_json as OptimizeRequest | null;

  const handleCopyJson = async () => {
    if (!config) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleCloneEdit = () => {
    if (!config || !job) return;
    const newName = `${job.strategy_nm || 'Strategy'} (copy)`;
    onCloneEdit(config, newName);
  };

  const isTerminal = job?.queue_status === 'COMPLETED' || 
                     job?.queue_status === 'FAILED' || 
                     job?.queue_status === 'CANCELLED';

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: DRAWER_WIDTH, p: 0 } }}
    >
      {job && (
        <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {/* Header */}
          <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
            <Stack direction="row" alignItems="flex-start" justifyContent="space-between">
              <Box sx={{ flex: 1, mr: 1 }}>
                <Typography variant="h6" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                  {job.strategy_nm || 'Job Details'}
                </Typography>
                <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', gap: 0.5 }}>
                  <Chip
                    size="small"
                    label={job.queue_status}
                    color={
                      job.queue_status === 'COMPLETED' ? 'success' :
                      job.queue_status === 'FAILED' ? 'error' :
                      job.queue_status === 'RUNNING' ? 'primary' :
                      'default'
                    }
                  />
                  <Chip size="small" label={`Priority: ${job.priority}`} variant="outlined" />
                </Stack>
              </Box>
              <IconButton onClick={onClose} size="small">
                <CloseIcon />
              </IconButton>
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Submitted: {new Date(job.transact_from_ts).toLocaleString()}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              ID: {job.queue_id}
            </Typography>
          </Box>

          {/* Tabs */}
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }}>
            <Tab label="Strategy" />
            <Tab label="Raw JSON" />
          </Tabs>

          {/* Tab Content */}
          <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
            {tab === 0 && config && (
              <StrategyTab config={config} />
            )}
            {tab === 0 && !config && (
              <Typography color="text.secondary">No config available for this job.</Typography>
            )}
            {tab === 1 && (
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  bgcolor: 'grey.900',
                  color: 'grey.100',
                  fontFamily: 'monospace',
                  fontSize: 12,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  maxHeight: 400,
                  overflow: 'auto',
                }}
              >
                {config ? JSON.stringify(config, null, 2) : 'No config available'}
              </Paper>
            )}

            {/* Error text if failed */}
            {job.error_text && (
              <Paper variant="outlined" sx={{ mt: 2, p: 1.5, bgcolor: 'error.50' }}>
                <Typography variant="subtitle2" color="error" sx={{ fontWeight: 600, mb: 0.5 }}>
                  Error
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
                >
                  {job.error_text}
                </Typography>
              </Paper>
            )}
          </Box>

          {/* Footer Actions */}
          <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={copySuccess ? null : <ContentCopyIcon />}
                onClick={handleCopyJson}
                color={copySuccess ? 'success' : 'primary'}
                disabled={!config}
              >
                {copySuccess ? 'Copied!' : 'Copy JSON'}
              </Button>
              <Button
                size="small"
                variant="contained"
                startIcon={<EditIcon />}
                onClick={handleCloneEdit}
                disabled={!config}
              >
                Clone & Edit
              </Button>
              <Button
                size="small"
                variant="outlined"
                startIcon={<CompareArrowsIcon />}
                onClick={() => onCompare(job)}
              >
                Compare
              </Button>
              {isTerminal && (
                <Button
                  size="small"
                  variant="outlined"
                  color="secondary"
                  startIcon={<ReplayIcon />}
                  onClick={() => onRerun(job.queue_id)}
                >
                  Re-run
                </Button>
              )}
            </Stack>
          </Box>
        </Box>
      )}
    </Drawer>
  );
}

function StrategyTab({ config }: { config: OptimizeRequest }) {
  const factors = config.factors || [];
  
  return (
    <Stack spacing={2}>
      {/* Basic Info */}
      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Trading Product</Typography>
        <Stack spacing={0.5}>
          <InfoRow label="Symbol" value={config.symbol} />
          {config.data_source && <InfoRow label="Data Source" value={config.data_source} />}
          <InfoRow label="Date Range" value={`${config.start} → ${config.end}`} />
          <InfoRow label="Trading Period" value={`${config.trading_period} days`} />
          <InfoRow label="Fee" value={`${config.fee_bps} bps`} />
          {config.refresh_dataset && <Chip size="small" label="Refresh Dataset" color="info" sx={{ mt: 0.5 }} />}
        </Stack>
      </Paper>

      {/* Factors */}
      {factors.map((factor: FactorConfig, i: number) => (
        <Paper key={i} variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
            Factor {i + 1}
          </Typography>
          <Stack spacing={0.5}>
            <InfoRow label="Indicator" value={factor.indicator} />
            <InfoRow label="Strategy" value={factor.strategy} />
            <InfoRow label="Data Column" value={factor.data_column} />
            <InfoRow 
              label="Window Range" 
              value={`${factor.window_range.min} - ${factor.window_range.max} (step: ${factor.window_range.step})`} 
            />
            <InfoRow 
              label="Signal Range" 
              value={`${factor.signal_range.min} - ${factor.signal_range.max} (step: ${factor.signal_range.step})`} 
            />
            {factor.symbol && <InfoRow label="Factor Symbol" value={factor.symbol} />}
          </Stack>
        </Paper>
      ))}

      {/* Conjunction */}
      {factors.length > 1 && config.conjunction && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <InfoRow label="Conjunction" value={config.conjunction} />
        </Paper>
      )}

      {/* Walk-Forward */}
      {config.walk_forward && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>Walk-Forward</Typography>
          <InfoRow label="Split Ratio" value={`${((config.split_ratio || 0.5) * 100).toFixed(0)}% train`} />
        </Paper>
      )}
    </Stack>
  );
}

function InfoRow({ label, value }: { label: string; value: string | number }) {
  return (
    <Box sx={{ display: 'flex', gap: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 100 }}>
        {label}:
      </Typography>
      <Typography variant="caption" sx={{ fontWeight: 500 }}>
        {value}
      </Typography>
    </Box>
  );
}
