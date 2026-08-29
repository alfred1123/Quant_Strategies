import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { useSubscribe } from '../../api/marketData';
import { useProducts } from '../../api/inst';
import { intervalLabel, useExchangeApps, useTmIntervals } from '../../api/refdata';

interface SubscriptionDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * Start capturing one bar series.
 *
 * Product, cadence and venue are the whole form, because they are the whole
 * identity of a series: the `MARKET_DATA.PRICE_BAR` key minus the timestamp.
 * The venue is a first-class choice rather than a detail — the same instrument
 * on two exchanges is two different series, and a strategy fitted on one does
 * not reproduce on the other.
 *
 * There is no owner field because a subscription has no owner: bars are shared
 * facts and one row serves the platform.
 */
export default function SubscriptionDialog({
  open,
  onClose,
  onSuccess,
}: SubscriptionDialogProps) {
  // Remount on open so the form resets without an effect.
  if (!open) return null;
  return <SubscriptionDialogContent onClose={onClose} onSuccess={onSuccess} />;
}

function SubscriptionDialogContent({
  onClose,
  onSuccess,
}: Omit<SubscriptionDialogProps, 'open'>) {
  const { data: products = [] } = useProducts();
  const { data: intervals = [] } = useTmIntervals();
  const { data: exchanges = [] } = useExchangeApps();
  const create = useSubscribe();

  const [internalCusip, setInternalCusip] = useState('');
  const [intervalId, setIntervalId] = useState('');
  const [sourceAppId, setSourceAppId] = useState('');
  const [backfillFrom, setBackfillFrom] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const sortedIntervals = useMemo(
    () => [...intervals].sort((a, b) => a.tm_interval_id - b.tm_interval_id),
    [intervals],
  );

  const canSubmit = internalCusip !== '' && intervalId !== '' && sourceAppId !== '';

  const handleSubmit = async () => {
    setFormError(null);
    try {
      await create.mutateAsync({
        internal_cusip: internalCusip,
        tm_interval_id: Number(intervalId),
        source_app_id: Number(sourceAppId),
        backfill_from_ts: backfillFrom ? new Date(backfillFrom).toISOString() : null,
      });
      onSuccess();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Could not subscribe');
    }
  };

  return (
    <Dialog
      open
      onClose={create.isPending ? undefined : onClose}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>Capture a price series</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            select
            label="Product"
            value={internalCusip}
            onChange={e => setInternalCusip(e.target.value)}
            fullWidth
          >
            {products.map(p => (
              <MenuItem key={p.internal_cusip} value={p.internal_cusip}>
                {p.display_nm} ({p.internal_cusip})
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Bar interval"
            value={intervalId}
            onChange={e => setIntervalId(e.target.value)}
            fullWidth
          >
            {sortedIntervals.map(iv => (
              <MenuItem key={iv.tm_interval_id} value={String(iv.tm_interval_id)}>
                {intervalLabel(iv)}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Venue"
            value={sourceAppId}
            onChange={e => setSourceAppId(e.target.value)}
            helperText="Bars are a fact from one exchange — this picks which order book you capture."
            fullWidth
          >
            {exchanges.map(a => (
              <MenuItem key={a.app_id} value={String(a.app_id)}>
                {a.display_name}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            type="date"
            label="History wanted from"
            value={backfillFrom}
            onChange={e => setBackfillFrom(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            helperText="Optional target. Nothing fills automatically — use Backfill on the row."
            fullWidth
          />

          <Typography variant="caption" color="text.secondary">
            Subscribing starts the series from now. It does not create history that
            was never captured — use Backfill to reach as far back as the venue
            will serve. Captured bars are shared: this subscription is visible to
            everyone, and anyone can pause it.
          </Typography>

          {formError && <Alert severity="error">{formError}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={create.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!canSubmit || create.isPending}
        >
          Subscribe
        </Button>
      </DialogActions>
    </Dialog>
  );
}
