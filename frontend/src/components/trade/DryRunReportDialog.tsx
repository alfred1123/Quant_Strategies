import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material';
import type { DryRunReport } from '../../types/trade';
import { MONO_FONT_STACK } from '../../theme';

const SIDE_COLOR: Record<string, 'success' | 'error' | 'default' | 'warning'> = {
  BUY: 'success',
  SELL: 'error',
  HOLD: 'default',
  OPEN_SHORT: 'warning',
  CLOSE_SHORT: 'success',
};

interface Props {
  report: DryRunReport | null;
  onClose: () => void;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Stack direction="row" sx={{ justifyContent: 'space-between', py: 0.5 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" sx={{ fontFamily: MONO_FONT_STACK }}>{value}</Typography>
    </Stack>
  );
}

/**
 * Name the series the signal came from. The live apply reads the same one, so
 * this is the line that answers "is this preview actually about the order I am
 * going to place?" — a question the report could not previously be asked.
 */
function barSourceLabel(barSource: string): string {
  const venue = barSource.startsWith('price_bar:') ? barSource.slice(10) : null;
  return venue ? `${venue} exchange bars` : 'Market data provider';
}

export default function DryRunReportDialog({ report, onClose }: Props) {
  if (!report) return null;
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Dry-run report</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={0.5}>
          <Row label="Strategy" value={`${report.strategy_nm} · v${report.strategy_vid}`} />
          <Row label="Product" value={report.internal_cusip} />
          <Row label="Vendor symbol" value={report.vendor_symbol} />
          <Row label="Mode" value={report.paper ? 'Paper' : 'Live'} />
          <Row label="Qty" value={report.qty} />
          <Row label="Signal" value={report.signal} />
          <Row
            label="Intended side"
            value={
              <Chip
                size="small"
                label={report.intended_side}
                color={SIDE_COLOR[report.intended_side] ?? 'default'}
              />
            }
          />
          <Row label="Position qty" value={report.position_qty} />
          <Row label="Price source" value={barSourceLabel(report.bar_source)} />
          <Row label="Data as of" value={report.data_as_of} />
          {report.notional != null && (
            <Row
              label="Est. notional"
              value={report.notional.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            />
          )}
        </Stack>
        {report.intended_side === 'HOLD' && (
          <Alert severity="info" sx={{ mt: 2 }}>
            No order would be placed — signal and position already aligned.
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
