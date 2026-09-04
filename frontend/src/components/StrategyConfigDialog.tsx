import { useState } from 'react';
import {
  Box,
  Button,
  Chip,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';

interface RangeValue {
  min: number;
  max: number;
  step: number;
}

interface FactorConfig {
  indicator?: string;
  strategy?: string;
  data_column?: string;
  symbol?: string;
  vendor_symbol?: string;
  data_source?: string;
  window_range?: RangeValue;
  signal_range?: RangeValue;
}

interface ConfigJson {
  symbol?: string;
  vendor_symbol?: string;
  vendorSymbol?: string;
  data_source?: string;
  dataSource?: string;
  start?: string;
  end?: string;
  asset_type?: string;
  assetType?: string;
  trading_period?: number;
  tradingPeriod?: number;
  fee_bps?: number;
  feeBps?: number;
  conjunction?: string;
  factors?: FactorConfig[];
  walk_forward?: boolean;
  walkForward?: boolean;
  split_ratio?: number;
  splitRatio?: number;
  refresh_dataset?: boolean;
  refreshDataset?: boolean;
  tm_interval_id?: number | null;
  tmIntervalId?: number | null;
  [key: string]: unknown;
}

interface Props {
  open: boolean;
  onClose: () => void;
  config: Record<string, unknown> | null;
  strategyNm?: string | null;
}

function RangeDisplay({ range }: { range?: RangeValue }) {
  if (!range) return <span>—</span>;
  return (
    <span>
      {range.min} → {range.max}{' '}
      <Typography component="span" color="text.secondary">
        (step {range.step})
      </Typography>
    </span>
  );
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.5 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 120 }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div">
        {value}
      </Typography>
    </Stack>
  );
}

function FactorCard({ factor, index }: { factor: FactorConfig; index: number }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack
        direction="row"
        sx={{ alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 600, flex: 1 }}>
          Factor {index + 1}
        </Typography>
        <Chip
          size="small"
          label={factor.indicator ?? 'Unknown'}
          color="primary"
          variant="outlined"
        />
        <IconButton size="small">
          {expanded ? (
            <ExpandLessIcon fontSize="small" />
          ) : (
            <ExpandMoreIcon fontSize="small" />
          )}
        </IconButton>
      </Stack>
      <Collapse in={expanded}>
        <Box sx={{ mt: 1 }}>
          <FieldRow label="Indicator" value={factor.indicator ?? '—'} />
          <FieldRow label="Strategy" value={factor.strategy ?? '—'} />
          <FieldRow label="Data Column" value={factor.data_column ?? 'price'} />
          <FieldRow
            label="Window Range"
            value={<RangeDisplay range={factor.window_range} />}
          />
          <FieldRow
            label="Signal Range"
            value={<RangeDisplay range={factor.signal_range} />}
          />
          {(factor.symbol || factor.vendor_symbol) && (
            <FieldRow
              label="Symbol Override"
              value={factor.vendor_symbol || factor.symbol || '—'}
            />
          )}
        </Box>
      </Collapse>
    </Paper>
  );
}

export default function StrategyConfigDialog({
  open,
  onClose,
  config,
  strategyNm,
}: Props) {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!config) return null;

  const cfg = config as ConfigJson;
  const factors = cfg.factors ?? [];

  const symbol = cfg.vendor_symbol || cfg.vendorSymbol || cfg.symbol || '—';
  const dataSource = cfg.data_source || cfg.dataSource || '—';
  const assetType = cfg.asset_type || cfg.assetType || '—';
  const feeBps = cfg.fee_bps ?? cfg.feeBps;
  const walkForward = cfg.walk_forward ?? cfg.walkForward;
  const splitRatio = cfg.split_ratio ?? cfg.splitRatio ?? 0.5;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = JSON.stringify(config, null, 2);
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          Strategy Configuration
        </Typography>
        {strategyNm && <Chip size="small" label={strategyNm} variant="outlined" />}
        <IconButton size="small" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2}>
          {/* General Settings */}
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
              General Settings
            </Typography>
            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <FieldRow label="Symbol" value={symbol} />
              <FieldRow label="Data Source" value={dataSource} />
              <FieldRow
                label="Date Range"
                value={
                  cfg.start && cfg.end ? `${cfg.start} → ${cfg.end}` : '—'
                }
              />
              <FieldRow label="Asset Type" value={assetType} />
              <FieldRow
                label="Fee (bps)"
                value={feeBps != null ? feeBps : '—'}
              />
              <FieldRow
                label="Walk-Forward"
                value={
                  walkForward
                    ? `✓ (${Math.round(splitRatio * 100)}% train)`
                    : '✗'
                }
              />
              {(cfg.refresh_dataset || cfg.refreshDataset) && (
                <FieldRow label="Refresh Dataset" value="✓" />
              )}
            </Paper>
          </Box>

          {/* Factors */}
          {factors.length > 0 && (
            <Box>
              <Stack direction="row" sx={{ alignItems: 'center', mb: 1, gap: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  Factors
                </Typography>
                {factors.length > 1 && cfg.conjunction && (
                  <Chip
                    size="small"
                    label={cfg.conjunction}
                    color="warning"
                    variant="outlined"
                  />
                )}
              </Stack>
              <Stack spacing={1.5}>
                {factors.map((factor, i) => (
                  <FactorCard key={i} factor={factor} index={i} />
                ))}
              </Stack>
            </Box>
          )}

          <Divider />

          {/* Raw JSON Toggle */}
          <Box>
            <Stack
              direction="row"
              sx={{ alignItems: 'center', cursor: 'pointer', mb: 1 }}
              onClick={() => setShowRaw(!showRaw)}
            >
              <Typography variant="subtitle2" sx={{ fontWeight: 600, flex: 1 }}>
                Raw JSON
              </Typography>
              <IconButton size="small">
                {showRaw ? (
                  <ExpandLessIcon fontSize="small" />
                ) : (
                  <ExpandMoreIcon fontSize="small" />
                )}
              </IconButton>
            </Stack>
            <Collapse in={showRaw}>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  bgcolor: 'grey.50',
                  maxHeight: 300,
                  overflow: 'auto',
                }}
              >
                <Typography
                  component="pre"
                  variant="caption"
                  sx={{
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    m: 0,
                  }}
                >
                  {JSON.stringify(config, null, 2)}
                </Typography>
              </Paper>
            </Collapse>
          </Box>
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button
          startIcon={<ContentCopyIcon />}
          onClick={handleCopy}
          color={copied ? 'success' : 'inherit'}
        >
          {copied ? 'Copied!' : 'Copy JSON'}
        </Button>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
