import { MenuItem, Select, Stack, Typography } from '@mui/material';
import { useMemo } from 'react';
import { intervalLabel, useTmIntervals } from '../../api/refdata';
import { useUpdateDeployment } from '../../api/trade';
import type { DeploymentRow } from '../../types/trade';

interface ScheduleCellProps {
  row: DeploymentRow;
  onError: (message: string) => void;
}

/**
 * Schedule cadence for one deployment, editable in place.
 *
 * Manual is a real option rather than an absence: picking it sends an explicit
 * null, which the backend distinguishes from an omitted field and reads as
 * "back to manual apply only".
 *
 * A cadence is also what puts the product's price data on the platform's
 * hourly warm — `SP_GET_SCHEDULED_INSTRUMENTS` returns exactly the enabled,
 * non-manual deployments — so there is no separate control for that.
 */
export default function ScheduleCell({ row, onError }: ScheduleCellProps) {
  const { data: intervals = [] } = useTmIntervals();
  const update = useUpdateDeployment();

  const sorted = useMemo(
    () => [...intervals].sort((a, b) => a.tm_interval_id - b.tm_interval_id),
    [intervals],
  );

  const currentId = row.schedule_tm_interval_id ?? null;
  const current = sorted.find((iv) => iv.tm_interval_id === currentId) ?? null;
  const isLive = row.is_paper_ind === 'N';

  // Until REFDATA arrives there is nothing valid to select, and rendering a
  // value with no matching option would blank the cell.
  if (sorted.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {currentId == null ? 'Manual' : `#${currentId}`}
      </Typography>
    );
  }

  const handleChange = async (raw: string) => {
    const next = raw === '' ? null : Number(raw);
    if (next === currentId) return;
    if (next !== null && isLive) {
      const label = sorted.find((iv) => iv.tm_interval_id === next);
      const cadence = label ? intervalLabel(label).toLowerCase() : 'this schedule';
      const ok = window.confirm(
        `Trade ${row.internal_cusip} automatically on the ${cadence} schedule?\n\n` +
          'This is a LIVE deployment — real orders will be placed without anyone pressing Apply.',
      );
      if (!ok) return;
    }
    try {
      await update.mutateAsync({
        deploymentId: row.deployment_id,
        schedule_tm_interval_id: next,
      });
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : 'Failed to change schedule');
    }
  };

  return (
    <Stack spacing={0.25}>
      <Select
        variant="standard"
        displayEmpty
        value={currentId == null ? '' : String(currentId)}
        onChange={(e) => handleChange(e.target.value)}
        disabled={update.isPending}
        inputProps={{ 'aria-label': `Schedule for ${row.internal_cusip}` }}
        sx={{ fontSize: '0.875rem', minWidth: 96 }}
      >
        <MenuItem value="">Manual</MenuItem>
        {sorted.map((iv) => (
          <MenuItem key={iv.tm_interval_id} value={String(iv.tm_interval_id)}>
            {intervalLabel(iv)}
          </MenuItem>
        ))}
      </Select>
      {current && row.next_due_at && (
        <Typography variant="caption" color="text.secondary" noWrap>
          Next {new Date(row.next_due_at).toLocaleString()}
        </Typography>
      )}
    </Stack>
  );
}
