import { useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Stack, Typography,
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef, GridRenderCellParams } from '@mui/x-data-grid';
import { useCancelJob, useJobs } from '../api/jobs';
import type { JobRow, JobStatus } from '../types/jobs';

const STATUS_COLOR: Record<
  JobStatus,
  'default' | 'primary' | 'success' | 'error' | 'warning'
> = {
  QUEUED: 'default',
  RUNNING: 'primary',
  COMPLETED: 'success',
  FAILED: 'error',
  CANCEL_REQUESTED: 'warning',
  CANCELLED: 'warning',
};

const ACTIVE_STATES: ReadonlySet<JobStatus> = new Set(['QUEUED', 'RUNNING']);

const FILTER_STATES: readonly (JobStatus | 'ALL')[] = [
  'ALL', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED',
] as const;

export interface JobsTableProps {
  /** Optional: invoked when the user clicks "View" on a COMPLETED row. */
  onView?: (queueId: string) => void;
}

export default function JobsTable({ onView }: JobsTableProps = {}) {
  const jobs = useJobs();
  const cancel = useCancelJob();
  const [statusFilter, setStatusFilter] = useState<JobStatus | 'ALL'>('ALL');

  const rows = useMemo(() => {
    const all = jobs.data ?? [];
    if (statusFilter === 'ALL') return all;
    // CANCELLED chip groups CANCEL_REQUESTED + CANCELLED \u2014 they're the same to a user.
    if (statusFilter === 'CANCELLED') {
      return all.filter(
        (r) => r.queue_status === 'CANCELLED' || r.queue_status === 'CANCEL_REQUESTED',
      );
    }
    return all.filter((r) => r.queue_status === statusFilter);
  }, [jobs.data, statusFilter]);

  const columns: GridColDef<JobRow>[] = useMemo(
    () => [
      {
        field: 'queue_id',
        headerName: 'Queue ID',
        width: 290,
        renderCell: (p: GridRenderCellParams<JobRow, string>) => (
          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
            {p.value}
          </Typography>
        ),
      },
      { field: 'strategy_nm', headerName: 'Strategy', flex: 1, minWidth: 160 },
      {
        field: 'queue_status',
        headerName: 'Status',
        width: 160,
        renderCell: (p: GridRenderCellParams<JobRow, JobStatus>) =>
          p.value ? (
            <Chip size="small" label={p.value} color={STATUS_COLOR[p.value]} />
          ) : null,
      },
      { field: 'priority', headerName: 'Priority', width: 100, type: 'number' },
      {
        field: 'transact_from_ts',
        headerName: 'Submitted',
        width: 200,
        valueFormatter: (value: string) =>
          value ? new Date(value).toLocaleString() : '',
      },
      {
        field: 'error_text',
        headerName: 'Error',
        flex: 1,
        minWidth: 200,
        renderCell: (p: GridRenderCellParams<JobRow, string | null>) =>
          p.value ? (
            <Typography
              variant="caption"
              color="error"
              sx={{
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                display: 'block',
              }}
              title={p.value}
            >
              {p.value}
            </Typography>
          ) : null,
      },
      {
        field: 'actions',
        headerName: '',
        width: 140,
        sortable: false,
        filterable: false,
        renderCell: (p: GridRenderCellParams<JobRow>) => {
          if (!p.row) return null;
          if (ACTIVE_STATES.has(p.row.queue_status)) {
            const pending =
              cancel.isPending && cancel.variables === p.row.queue_id;
            return (
              <Button
                size="small"
                color="warning"
                variant="outlined"
                disabled={pending}
                onClick={() => cancel.mutate(p.row.queue_id)}
              >
                {pending ? '\u2026' : 'Cancel'}
              </Button>
            );
          }
          if (p.row.queue_status === 'COMPLETED' && onView) {
            return (
              <Button
                size="small"
                color="primary"
                variant="outlined"
                onClick={() => onView(p.row.queue_id)}
              >
                View
              </Button>
            );
          }
          return null;
        },
      },
    ],
    [cancel, onView],
  );

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          My Jobs
        </Typography>
        {jobs.isFetching && <CircularProgress size={16} />}
        <Box sx={{ flexGrow: 1 }} />
        <Typography variant="caption" color="text.secondary">
          Auto-refreshes every 3 seconds
        </Typography>
      </Stack>

      {jobs.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load jobs: {(jobs.error as Error)?.message ?? 'unknown error'}
        </Alert>
      )}
      {cancel.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => cancel.reset()}>
          Cancel failed: {(cancel.error as Error)?.message ?? 'unknown error'}
        </Alert>
      )}

      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap' }}>
        {FILTER_STATES.map((s) => (
          <Chip
            key={s}
            label={s}
            size="small"
            color={statusFilter === s ? 'primary' : 'default'}
            variant={statusFilter === s ? 'filled' : 'outlined'}
            onClick={() => setStatusFilter(s)}
          />
        ))}
      </Stack>

      <Box sx={{ height: 560 }}>
        <DataGrid
          rows={rows}
          columns={columns}
          getRowId={(r) => r.queue_id}
          loading={jobs.isLoading}
          disableRowSelectionOnClick
          density="compact"
          initialState={{
            sorting: { sortModel: [{ field: 'transact_from_ts', sort: 'desc' }] },
            pagination: { paginationModel: { pageSize: 25 } },
          }}
          pageSizeOptions={[10, 25, 50]}
        />
      </Box>
    </Box>
  );
}
