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
import { useBackfill, useBackfillPlan, useVenueDepth } from '../../api/marketData';
import type {
  BackfillPlan,
  BackfillReport,
  BarSubscriptionRow,
} from '../../types/marketData';

interface BackfillDialogProps {
  row: BarSubscriptionRow | null;
  onClose: () => void;
}

function isoDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : '';
}

/** What one click will do, in the units the user is looking at. */
function passSummary(plan: BackfillPlan): string {
  if (!plan.start || !plan.end) {
    return 'Nothing older to fetch — this series already reaches the target.';
  }
  const window = `${isoDate(plan.start)} to ${isoDate(plan.end)}`;
  const bars = `${plan.bars.toLocaleString()} bar(s)`;
  return plan.passes_remaining > 1
    ? `This pass fetches ${window} — ${bars}. `
      + `${plan.passes_remaining} passes to reach ${isoDate(plan.target)}.`
    : `This pass fetches ${window} — ${bars}, reaching ${isoDate(plan.target)}.`;
}

/**
 * Fill history for one series, one pass at a time.
 *
 * There is still no "to" field, because the *target* is the decision and the
 * window is arithmetic. What changed is which window a pass covers. Every fill
 * used to run to the last closed bar, which made deep intraday history
 * unreachable: an hourly series already holding a year has no start that both
 * reaches further back and stays under the ceiling, since the nearer the start
 * the more of the span is bars already stored. So the advice to "fill a nearer
 * date first and repeat" could not work, however many times it was followed.
 *
 * Each pass now ends where coverage begins, spanning only what is absent, and
 * the next resumes from the ground the last one gained. The user sets how far
 * back they want once and clicks until it arrives, with the remaining count
 * visible so the commitment is known before the first one.
 *
 * Deliberately manual and deliberately blocking. Chunking on the caller's
 * behalf would be the background filler this design declined, needing progress
 * tracking nothing here keeps — so a pass is a click, and each one reports
 * exactly what arrived, including what the venue would not serve.
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
  const series = {
    internal_cusip: row.internal_cusip,
    tm_interval_id: row.tm_interval_id,
    source_app_id: row.source_app_id,
  };
  const depthQuery = useVenueDepth(series);
  const venueEarliest = isoDate(depthQuery.data?.earliest);

  // Reach for everything the venue holds. The subscription's own target is
  // only a floor when the user set one deeper than the venue can serve, which
  // the subscribe dialog now prevents but older rows may still carry.
  const [override, setOverride] = useState<string | null>(null);
  const target = override
    ?? (venueEarliest || isoDate(row.backfill_from_ts ?? row.coverage.first_bar));

  const planQuery = useBackfillPlan(series, target || null);
  const plan = planQuery.data;
  const nothingLeft = plan != null && plan.start === null;

  const [report, setReport] = useState<BackfillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!plan?.start) return;
    setError(null);
    setReport(null);
    try {
      setReport(
        await fill.mutateAsync({
          internal_cusip: row.internal_cusip,
          tm_interval_id: row.tm_interval_id,
          source_app_id: row.source_app_id,
          start: plan.start,
          // Bounded, unlike the old fill-to-now: this pass covers only the
          // stretch below what is already stored.
          end: plan.end,
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
            label="History wanted from"
            value={target}
            onChange={e => setOverride(e.target.value)}
            slotProps={{
              inputLabel: { shrink: true },
              htmlInput: venueEarliest ? { min: venueEarliest } : undefined,
            }}
            helperText={
              depthQuery.isFetching
                ? 'Asking the venue how far back it goes…'
                : venueEarliest
                  ? `${venueEarliest} is as far back as this venue goes.`
                  : 'The venue did not say how far back it goes.'
            }
            fullWidth
          />

          {/*
            Three states, not two. An unanswered plan and a failed one both
            leave `plan` undefined, and collapsing them renders a dead dialog:
            "working out what is left to fetch" forever, next to a disabled
            button, with the actual cause — an expired session, a backend
            without the route — never shown. Waiting has to be distinguishable
            from broken, and broken has to be retryable.
          */}
          {planQuery.isError ? (
            <Alert
              severity="error"
              action={
                <Button size="small" onClick={() => void planQuery.refetch()}>
                  Retry
                </Button>
              }
            >
              Could not work out what is left to fetch:{' '}
              {planQuery.error instanceof Error
                ? planQuery.error.message
                : 'the request failed'}
            </Alert>
          ) : plan ? (
            <Alert severity={nothingLeft ? 'success' : 'info'}>
              {passSummary(plan)}
            </Alert>
          ) : (
            <Alert severity="info">Working out what is left to fetch…</Alert>
          )}

          {plan && plan.passes_remaining > 1 && (
            <Typography variant="caption" color="text.secondary">
              A fill holds the connection open while it writes, so one pass is
              capped. Click Backfill again after each one — the next pass picks up
              where this leaves off, and nothing already stored is refetched.
            </Typography>
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
          disabled={!plan?.start || fill.isPending}
        >
          {fill.isPending ? 'Filling…' : 'Backfill'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
