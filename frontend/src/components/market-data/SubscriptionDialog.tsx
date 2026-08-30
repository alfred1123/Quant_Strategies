import {
  Alert,
  Autocomplete,
  Box,
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
import { useSubscribe, useVenueDepth } from '../../api/marketData';
import { useAppProducts } from '../../api/inst';
import { intervalLabel, useExchangeApps, useTmIntervals } from '../../api/refdata';
import type { VenueDepth } from '../../types/marketData';
import type { ListedProduct } from '../../types/refdata';

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

/**
 * Why the product box is empty, when it is.
 *
 * Naming the count matters: a venue listing eight products is a different
 * thing to search than one listing eight hundred, and "no options" after
 * typing reads as a broken search unless the size was visible beforehand.
 */
function productHelp(
  venue: string,
  loading: boolean,
  count: number,
): string {
  if (!venue) return 'Pick a venue first — it decides which products exist here.';
  if (loading) return 'Loading what this venue lists…';
  if (count === 0) {
    return 'This venue lists nothing yet. Add an INST.PRODUCT_XREF row for it.';
  }
  return `${count.toLocaleString()} products listed on this venue.`;
}

function SubscriptionDialogContent({
  onClose,
  onSuccess,
}: Omit<SubscriptionDialogProps, 'open'>) {
  const { data: intervals = [] } = useTmIntervals();
  const { data: exchanges = [] } = useExchangeApps();
  const create = useSubscribe();

  const [internalCusip, setInternalCusip] = useState('');
  const [intervalId, setIntervalId] = useState('');
  const [sourceAppId, setSourceAppId] = useState('');

  // Scoped to the venue, so the options are things this exchange can actually
  // serve rather than every instrument the platform knows.
  const productsQuery = useAppProducts(sourceAppId ? Number(sourceAppId) : null);
  const products = useMemo(() => productsQuery.data ?? [], [productsQuery.data]);
  /** `null` until the user picks a date; the venue's floor stands in. */
  const [chosenTarget, setChosenTarget] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const sortedIntervals = useMemo(
    () => [...intervals].sort((a, b) => a.tm_interval_id - b.tm_interval_id),
    [intervals],
  );

  // Autocomplete holds the option, not the id the form submits.
  const selectedProduct = useMemo(
    () => products.find(p => p.internal_cusip === internalCusip) ?? null,
    [products, internalCusip],
  );

  // Only once all three are chosen is there a series to ask the venue about.
  const depthQuery = useVenueDepth({
    internal_cusip: internalCusip || undefined,
    tm_interval_id: intervalId ? Number(intervalId) : undefined,
    source_app_id: sourceAppId ? Number(sourceAppId) : undefined,
  });
  const depth = depthQuery.data;
  const venueEarliest = depth?.earliest ? depth.earliest.slice(0, 10) : '';

  // Adopt the venue's floor as the target, so the default is "everything this
  // exchange has" rather than a date invented by whoever opened the dialog.
  // Derived rather than copied into state by an effect: `null` means the user
  // has not chosen, so the answer tracks the venue as the series changes, and
  // anything they type — including clearing it — wins from then on.
  const backfillFrom = chosenTarget ?? venueEarliest;

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
          {/*
            Venue comes first because it is what makes the product question
            answerable. Asked the other way round, the list is every instrument
            the platform knows — mostly things the chosen exchange has never
            listed, which is not a set anyone can usefully scroll or search.
          */}
          <TextField
            select
            label="Venue"
            value={sourceAppId}
            onChange={e => {
              setSourceAppId(e.target.value);
              // A product listed here may not be listed there.
              setInternalCusip('');
            }}
            helperText="Bars are a fact from one exchange — this picks which order book you capture."
            fullWidth
          >
            {exchanges.map(a => (
              <MenuItem key={a.app_id} value={String(a.app_id)}>
                {a.display_name}
              </MenuItem>
            ))}
          </TextField>

          {/*
            A search box over what this venue lists, not a dropdown over
            everything. Not `freeSolo`, unlike the backtest config's selector —
            a subscription must name a product the venue carries, since capture
            resolves it through `INST.PRODUCT_XREF` to reach the venue at all.

            The label carries name, CUSIP and vendor symbol, so MUI's default
            filter matches any of the three without a custom `filterOptions`.
          */}
          <Autocomplete<ListedProduct>
            options={products}
            value={selectedProduct}
            onChange={(_, val) => setInternalCusip(val?.internal_cusip ?? '')}
            getOptionLabel={opt =>
              `${opt.display_nm} (${opt.internal_cusip}) ${opt.vendor_symbol}`}
            isOptionEqualToValue={(opt, val) =>
              opt.internal_cusip === val.internal_cusip}
            disabled={!sourceAppId}
            loading={productsQuery.isFetching}
            slotProps={{ listbox: { sx: { maxHeight: 320 } } }}
            renderInput={params => (
              <TextField
                {...params}
                label="Product"
                placeholder="Search by name, CUSIP or venue symbol…"
                helperText={productHelp(
                  sourceAppId,
                  productsQuery.isFetching,
                  products.length,
                )}
              />
            )}
            renderOption={(props, opt) => (
              <li {...props} key={opt.internal_cusip}>
                <Box>
                  <Typography variant="body2">{opt.display_nm}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {opt.internal_cusip} · {opt.vendor_symbol}
                  </Typography>
                </Box>
              </li>
            )}
            fullWidth
          />

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
            type="date"
            label="History wanted from"
            value={backfillFrom}
            onChange={e => setChosenTarget(e.target.value)}
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
