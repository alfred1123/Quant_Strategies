import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useApplyDeployment } from '../../api/trade';
import type { ApplyReport, DeploymentRow } from '../../types/trade';
import { MONO_FONT_STACK } from '../../theme';

const SIDE_COLOR: Record<string, 'success' | 'error' | 'default' | 'warning'> = {
  BUY: 'success',
  SELL: 'error',
  HOLD: 'default',
  OPEN_SHORT: 'warning',
  CLOSE_SHORT: 'success',
};

interface Props {
  deployment: DeploymentRow | null;
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

function ResultView({ report }: { report: ApplyReport }) {
  const success = report.order_success === true;
  const hold = report.action === 'HOLD';
  return (
    <Stack spacing={1}>
      <Alert severity={hold ? 'info' : success ? 'success' : 'error'}>
        {report.message}
      </Alert>
      <Row label="Action" value={
        <Chip size="small" label={report.action} color={SIDE_COLOR[report.action] ?? 'default'} />
      } />
      <Row label="Signal" value={report.signal} />
      <Row label="Position qty" value={report.position_qty} />
      <Row label="Vendor symbol" value={report.vendor_symbol} />
      {report.vendor_order_id && <Row label="Order ID" value={report.vendor_order_id} />}
      {report.filled_qty != null && <Row label="Filled qty" value={report.filled_qty} />}
      {report.avg_price != null && <Row label="Avg price" value={report.avg_price} />}
      {report.fee != null && <Row label="Fee" value={report.fee} />}
    </Stack>
  );
}

export default function ApplyConfirmDialog({ deployment, onClose }: Props) {
  if (!deployment) return null;
  return <ApplyConfirmContent deployment={deployment} onClose={onClose} />;
}

function ApplyConfirmContent({ deployment, onClose }: { deployment: DeploymentRow; onClose: () => void }) {
  const apply = useApplyDeployment();
  const [result, setResult] = useState<ApplyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isLive = deployment.is_paper_ind !== 'Y';
  const pending = apply.isPending;

  const handleApply = async () => {
    setError(null);
    try {
      const report = await apply.mutateAsync(deployment.deployment_id);
      setResult(report);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Apply failed');
    }
  };

  return (
    <Dialog open onClose={pending ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        {result ? 'Apply result' : `Apply ${isLive ? 'LIVE' : 'paper'} deployment`}
      </DialogTitle>
      {pending && <LinearProgress />}
      <DialogContent dividers>
        {!result && (
          <Stack spacing={1.5}>
            <Row label="Product" value={deployment.internal_cusip} />
            <Row label="Strategy" value={`${deployment.strategy_id.slice(0, 8)}… v${deployment.strategy_vid}`} />
            <Row label="Mode" value={isLive ? 'Live' : 'Paper'} />
            <Row label="Qty" value={deployment.qty} />
            {isLive && (
              <Alert severity="warning">
                This will place a real order on the exchange.
              </Alert>
            )}
          </Stack>
        )}
        {result && <ResultView report={result} />}
        {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        {!result && (
          <>
            <Button onClick={onClose} disabled={pending}>Cancel</Button>
            <Button
              variant="contained"
              color={isLive ? 'warning' : 'primary'}
              onClick={handleApply}
              disabled={pending}
            >
              {pending ? 'Executing…' : `Apply ${isLive ? 'live' : 'paper'}`}
            </Button>
          </>
        )}
        {result && <Button onClick={onClose}>Close</Button>}
      </DialogActions>
    </Dialog>
  );
}
