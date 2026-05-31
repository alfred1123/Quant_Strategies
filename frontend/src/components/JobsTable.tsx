import { useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Stack, Typography,
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef, GridRenderCellParams } from '@mui/x-data-grid';
import { fetchJob, useCancelJob, useJobs, useReenqueueJob, usePromoteStrategy } from '../api/jobs';
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
const REENQUEUE_STATES: ReadonlySet<JobStatus> = new Set(['FAILED', 'CANCELLED']);

const FILTER_STATES: readonly (JobStatus | 'ALL')[] = [
  'ALL', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED',
] as const;

export interface JobsTableProps {
  /** Optional: invoked when the user clicks "View" on a COMPLETED row. */
  onView?: (queueId: string) => void;
  /** Optional: invoked to open ConfigDrawer pre-filled with a job's config + strategy_id. */
  onCloneEdit?: (strategyId: string, configJson: Record<string, unknown>, strategyNm: string) => void;
}

export default function JobsTable({ onView, onCloneEdit }: JobsTableProps = {}) {
  const jobs = useJobs();
  const cancel = useCancelJob();
  const reenqueue = useReenqueueJob();
  const promote = usePromoteStrategy();
  const [statusFilter, setStatusFilter] = useState<JobStatus | 'ALL'>('ALL');
  const [cloneLoading, setCloneLoading] = useState<string | null>(null);

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
        field: 'strategy_vid',
        headerName: 'VID',
        width: 100,
        renderCell: (p: GridRenderCellParams<JobRow>) => (
          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
            <Typography variant="body2">v{p.row.strategy_vid}</Typography>
            {p.row.is_best_ind === 'Y' && (
              <Chip size="small" label="Best" color="success" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />
            )}
          </Stack>
        ),
      },
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
        width: 340,
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
          if (REENQUEUE_STATES.has(p.row.queue_status)) {
            const pending =
              reenqueue.isPending && reenqueue.variables === p.row.queue_id;
            return (
              <Button
                size="small"
                color="primary"
                variant="outlined"
                disabled={pending}
                onClick={() => reenqueue.mutate(p.row.queue_id)}
              >
                {pending ? '\u2026' : 'Re-run'}
              </Button>
            );
          }
          if (p.row.queue_status === 'COMPLETED') {
            const promPending = promote.isPending
              && promote.variables?.strategyId === p.row.strategy_id;
            const isCloning = cloneLoading === p.row.queue_id;
            return (
              <Stack direction="row" spacing={0.5}>
                {onView && (
                  <Button size="small" color="primary" variant="outlined"
                    onClick={() => onView(p.row.queue_id)}>
                    View
                  </Button>
                )}
                {onCloneEdit && (
                  <Button size="small" color="secondary" variant="outlined"
                    disabled={isCloning}
                    onClick={async () => {
                      setCloneLoading(p.row.queue_id);
                      try {
                        const detail = await fetchJob(p.row.queue_id);
                        if (detail.config_json) {
                          onCloneEdit(
                            p.row.strategy_id,
                            detail.config_json,
                            p.row.strategy_nm ?? '',
                          );
                        }
                      } finally {
                        setCloneLoading(null);
                      }
                    }}>
                    {isCloning ? '\u2026' : 'Clone'}
                  </Button>
                )}
                {p.row.is_best_ind !== 'Y' && (
                  <Button size="small" color="success" variant="outlined"
                    disabled={promPending}
                    onClick={() => promote.mutate({
                      strategyId: p.row.strategy_id,
                      strategyVid: p.row.strategy_vid,
                    })}>
                    {promPending ? '\u2026' : 'Promote'}
                  </Button>
                )}
              </Stack>
            );
          }
          return null;
        },
      },
    ],
    [cancel, reenqueue, promote, onView, onCloneEdit, cloneLoading],
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
      {reenqueue.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => reenqueue.reset()}>
          Re-run failed: {(reenqueue.error as Error)?.message ?? 'unknown error'}
        </Alert>
      )}
      {promote.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => promote.reset()}>
          Promote failed: {(promote.error as Error)?.message ?? 'unknown error'}
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
