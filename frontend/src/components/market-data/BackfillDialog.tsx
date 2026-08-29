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
import { useBackfill } from '../../api/marketData';
import type { BackfillReport, BarSubscriptionRow } from '../../types/marketData';

interface BackfillDialogProps {
  row: BarSubscriptionRow | null;
  onClose: () => void;
}

function isoDate(value: string | null): string {
  return value ? value.slice(0, 10) : '';
}

/**
 * Fill history for one series over an explicit range.
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
  // Default to the depth the subscription already asked for, falling back to
  // the oldest bar held: the common case is extending backward from there.
  const [start, setStart] = useState(
    isoDate(row.backfill_from_ts ?? row.coverage.first_bar),
  );
  const [end, setEnd] = useState('');
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
          end: end ? new Date(end).toISOString() : null,
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
            onChange={e => setStart(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            fullWidth
          />
          <TextField
            type="date"
            label="To"
            value={end}
            onChange={e => setEnd(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            helperText="Leave blank for the most recent closed bar."
            fullWidth
          />

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
