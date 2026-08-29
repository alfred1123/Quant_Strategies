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
import { useEffect, useMemo, useState } from 'react';
import { useSubscribe, useVenueDepth } from '../../api/marketData';
import { useProducts } from '../../api/inst';
import { intervalLabel, useExchangeApps, useTmIntervals } from '../../api/refdata';
import type { VenueDepth } from '../../types/marketData';

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

/**
 * What the venue said, in the space where a hint about a typed date used to go.
 *
 * Names the number of bars as well as the date because the date alone hides
 * the cost: the same six years is a couple of thousand daily bars and millions
 * of minute ones, and only one of those can be filled.
 */
function venueDepthHelp(
  loading: boolean,
  depth: VenueDepth | undefined,
  earliest: string,
): string {
  if (loading) return 'Asking the venue how far back it goes…';
  if (!depth) return 'Pick a product, interval and venue to see how far back it goes.';
  // Unknown, not empty: the venue may simply not publish a listing time, and
  // claiming it holds nothing would be a stronger statement than we can make.
  if (!earliest) return 'This venue did not say how far back it goes — pick a date.';
  const bars = depth.bars_available;
  if (bars === null) return `This venue serves bars from ${earliest}.`;
  const fits = bars <= depth.max_backfill_bars;
  return (
    `This venue serves bars from ${earliest} — ${bars.toLocaleString()} of them. `
    + (fits
      ? 'One backfill covers all of it.'
      : `More than one backfill can take (${depth.max_backfill_bars.toLocaleString()}), `
        + 'so filling it all will take several passes.')
  );
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

  // Only once all three are chosen is there a series to ask the venue about.
  const depthQuery = useVenueDepth({
    internal_cusip: internalCusip || undefined,
    tm_interval_id: intervalId ? Number(intervalId) : undefined,
    source_app_id: sourceAppId ? Number(sourceAppId) : undefined,
  });
  const depth = depthQuery.data;
  const venueEarliest = depth?.earliest ? depth.earliest.slice(0, 10) : '';

  // Adopt the venue's floor as the target the moment it is known, so the
  // default is "everything this exchange has" rather than a date invented by
  // whoever opened the dialog. Their own edit wins — hence `touched`.
  const [touched, setTouched] = useState(false);
  useEffect(() => {
    if (!touched && venueEarliest) setBackfillFrom(venueEarliest);
  }, [touched, venueEarliest]);

  // A target the exchange cannot reach is not a gap that backfill will close
  // later; it is history that does not exist. Say so while it can still be
  // changed, rather than leaving the row short against it forever.
  const unreachable = Boolean(
    venueEarliest && backfillFrom && backfillFrom < venueEarliest,
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
            onChange={e => {
              setTouched(true);
              setBackfillFrom(e.target.value);
            }}
            slotProps={{
              inputLabel: { shrink: true },
              htmlInput: venueEarliest ? { min: venueEarliest } : undefined,
            }}
            helperText={venueDepthHelp(depthQuery.isFetching, depth, venueEarliest)}
            error={unreachable}
            fullWidth
          />

          {unreachable && (
            <Alert severity="warning">
              This venue's earliest bar is {venueEarliest}, so nothing before it
              can ever be captured — the row would show a shortfall no backfill
              could close. Use {venueEarliest} to take everything the exchange has.
            </Alert>
          )}

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
