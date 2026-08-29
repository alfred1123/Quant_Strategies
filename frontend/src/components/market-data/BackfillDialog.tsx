import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useBackfill, useVenueDepth } from '../../api/marketData';
import type {
  BackfillReport,
  BarSubscriptionRow,
  VenueDepth,
} from '../../types/marketData';

interface BackfillDialogProps {
  row: BarSubscriptionRow | null;
  onClose: () => void;
}

function isoDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : '';
}

/**
 * Whether the venue holds more than one pass can store.
 *
 * Warned about before the click rather than after the refusal, so the cost of
 * a minute-scale series is visible while it is still a choice.
 */
function tooLarge(depth: VenueDepth | undefined, start: string): boolean {
  if (!depth?.bars_available || !depth.earliest || !start) return false;
  return start <= isoDate(depth.earliest)
    && depth.bars_available > depth.max_backfill_bars;
}

/**
 * Fill history for one series, back to wherever the venue's records start.
 *
 * There is no "to" field. The end was always implied — the last closed bar,
 * since a forming bar cannot be stored and nothing beyond it exists — so
 * asking for it only invented a decision. The start is likewise defaulted
 * rather than asked: the venue knows its own earliest bar, so "everything
 * available" is the offer, and narrowing it is the deliberate act.
 *
 * Deliberately manual and deliberately blocking. A long range is many
 * paginated exchange calls, and the alternative — a background filler — would
 * need progress tracking that nothing here keeps. So the user waits and is
 * told exactly what arrived, including what the venue would not serve.
 */
export default function BackfillDialog({ row, onClose }: BackfillDialogProps) {
  if (!row) return null;
  return <BackfillDialogContent key={row.bar_subscription_id} row={row} onClose={onClose} />;
}

function BackfillDialogContent({
  row,
  onClose,
}: {
  row: BarSubscriptionRow;
  onClose: () => void;
}) {
  const fill = useBackfill();
  const depthQuery = useVenueDepth({
    internal_cusip: row.internal_cusip,
    tm_interval_id: row.tm_interval_id,
    source_app_id: row.source_app_id,
  });
  const depth = depthQuery.data;
  const venueEarliest = isoDate(depth?.earliest);

  // Reach for everything the venue holds. The subscription's own target is
  // only a floor when the user set one deeper than the venue can serve, which
  // the subscribe dialog now prevents but older rows may still carry.
  const [override, setOverride] = useState<string | null>(null);
  const start = override
    ?? (venueEarliest || isoDate(row.backfill_from_ts ?? row.coverage.first_bar));

  const [report, setReport] = useState<BackfillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setReport(null);
    try {
      setReport(
        await fill.mutateAsync({
          internal_cusip: row.internal_cusip,
          tm_interval_id: row.tm_interval_id,
          source_app_id: row.source_app_id,
          start: new Date(start).toISOString(),
          // Always the last closed bar. There is nothing later to fetch.
          end: null,
        }),
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Backfill failed');
    }
  };

  return (
    <Dialog open onClose={fill.isPending ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Backfill {row.internal_cusip}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            type="date"
            label="From"
            value={start}
            onChange={e => setOverride(e.target.value)}
            slotProps={{
              inputLabel: { shrink: true },
              htmlInput: venueEarliest ? { min: venueEarliest } : undefined,
            }}
            helperText={
              depthQuery.isFetching
                ? 'Asking the venue how far back it goes…'
                : venueEarliest
                  ? `Runs to the most recent closed bar. ${venueEarliest} is as far `
                    + 'back as this venue goes.'
                  : 'Runs to the most recent closed bar.'
            }
            fullWidth
          />

          {tooLarge(depth, start) && (
            <Alert severity="info">
              This venue holds {depth?.bars_available?.toLocaleString()} bars at this
              interval — more than the {depth?.max_backfill_bars.toLocaleString()} one
              pass can store, because backfill holds the connection open while it
              writes. Fill a nearer date first and repeat; each pass keeps what it
              stored.
            </Alert>
          )}

          <Typography variant="caption" color="text.secondary">
            How far back this reaches is the exchange's decision, not ours. A range
            that predates the listing, or goes past what the venue retains, comes
            back partly unfilled rather than failing.
          </Typography>

          {error && <Alert severity="error">{error}</Alert>}

          {report && (
            <Alert severity={report.is_continuous ? 'success' : 'warning'}>
              {report.inserted} bar(s) stored of {report.missing} missing across{' '}
              {report.expected} boundaries.{' '}
              {report.is_continuous
                ? 'The range is now continuous.'
                : `${report.unfilled.length} boundary(s) could not be filled from this
                   venue — the range has holes and a backtest over it would not be
                   reproducible.`}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={fill.isPending}>
          Close
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!start || fill.isPending}
        >
          {fill.isPending ? 'Filling…' : 'Backfill'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
