import { useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, IconButton, Stack, Tooltip, Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef, GridRenderCellParams } from '@mui/x-data-grid';
import { useCancelJob, useDeleteJob, useJobs, useReenqueueJob } from '../api/jobs';
import type { JobRow, JobStatus } from '../types/jobs';
import type { OptimizeRequest } from '../types/backtest';
import JobDetailDrawer from './JobDetailDrawer';
import JobCompareDrawer from './JobCompareDrawer';
import JobMultiCompareDrawer from './JobMultiCompareDrawer';

const MAX_COMPARE_JOBS = 4;

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
const DELETABLE_STATES: ReadonlySet<JobStatus> = new Set(['COMPLETED', 'FAILED', 'CANCELLED']);

const FILTER_STATES: readonly (JobStatus | 'ALL')[] = [
  'ALL', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED',
] as const;

export interface JobsTableProps {
  /** Optional: invoked when the user clicks "View" on a COMPLETED row. */
  onView?: (queueId: string) => void;
  /** Optional: invoked when the user clicks "Clone & Edit" to pre-fill the config drawer. */
  onCloneEdit?: (config: OptimizeRequest, name: string) => void;
}

export default function JobsTable({ onView, onCloneEdit }: JobsTableProps = {}) {
  const jobs = useJobs();
  const cancel = useCancelJob();
  const reenqueue = useReenqueueJob();
  const deleteJob = useDeleteJob();
  const [statusFilter, setStatusFilter] = useState<JobStatus | 'ALL'>('ALL');
  
  // Detail drawer state
  const [detailJob, setDetailJob] = useState<JobRow | null>(null);
  
  // Compare state - supports up to MAX_COMPARE_JOBS
  const [compareMode, setCompareMode] = useState(false);
  const [compareJobs, setCompareJobs] = useState<JobRow[]>([]);
  const [showMultiCompare, setShowMultiCompare] = useState(false);
  
  // Legacy 2-job compare state (for backwards compatibility)
  const [compareJobA, setCompareJobA] = useState<JobRow | null>(null);
  const [compareJobB, setCompareJobB] = useState<JobRow | null>(null);

  const handleRowClick = (job: JobRow) => {
    if (compareMode) {
      // In compare mode, add job to selection
      const alreadySelected = compareJobs.some(j => j.queue_id === job.queue_id);
      if (alreadySelected) {
        // Deselect if already selected
        setCompareJobs(compareJobs.filter(j => j.queue_id !== job.queue_id));
      } else if (compareJobs.length < MAX_COMPARE_JOBS) {
        setCompareJobs([...compareJobs, job]);
      }
    } else {
      // Normal mode: open detail drawer
      setDetailJob(job);
    }
  };

  const handleStartCompare = (job: JobRow) => {
    setDetailJob(null);
    setCompareJobs([job]);
    setCompareMode(true);
  };

  const handleAddToCompare = (job: JobRow) => {
    if (compareJobs.length < MAX_COMPARE_JOBS && !compareJobs.some(j => j.queue_id === job.queue_id)) {
      setCompareJobs([...compareJobs, job]);
    }
  };

  const handleOpenMultiCompare = () => {
    if (compareJobs.length >= 2) {
      setShowMultiCompare(true);
      setCompareMode(false);
    }
  };

  const handleCloseCompare = () => {
    setCompareJobs([]);
    setCompareMode(false);
    setShowMultiCompare(false);
    // Legacy cleanup
    setCompareJobA(null);
    setCompareJobB(null);
  };

  const handleLegacyStartCompare = (job: JobRow) => {
    setDetailJob(null);
    setCompareJobA(job);
    setCompareJobB(null);
    setCompareMode(true);
    setCompareJobs([job]);
  };

  const handleCloneEdit = (config: OptimizeRequest, name: string) => {
    setDetailJob(null);
    onCloneEdit?.(config, name);
  };

  const handleRerun = (queueId: string) => {
    setDetailJob(null);
    reenqueue.mutate(queueId);
  };

  const rows = useMemo(() => {
    const all = jobs.data ?? [];
    if (statusFilter === 'ALL') return all;
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
      {
        field: 'strategy_nm',
        headerName: 'Strategy',
        flex: 1,
        minWidth: 160,
        renderCell: (p: GridRenderCellParams<JobRow, string | null>) => {
          const isSelected = compareMode && p.row && compareJobs.some(j => j.queue_id === p.row?.queue_id);
          const selectionIndex = p.row ? compareJobs.findIndex(j => j.queue_id === p.row?.queue_id) : -1;
          const canSelect = compareMode && !isSelected && compareJobs.length < MAX_COMPARE_JOBS;
          return (
            <Stack direction="row" spacing={0.5} alignItems="center">
              {isSelected && (
                <Chip 
                  size="small" 
                  label={selectionIndex + 1} 
                  color="warning" 
                  sx={{ minWidth: 24, height: 20, '& .MuiChip-label': { px: 0.5 } }}
                />
              )}
              <Typography
                variant="body2"
                sx={{
                  cursor: 'pointer',
                  textDecoration: 'underline dotted',
                  '&:hover': { color: 'primary.main' },
                  ...(canSelect && {
                    bgcolor: 'warning.50',
                    px: 0.5,
                    borderRadius: 0.5,
                  }),
                  ...(isSelected && {
                    bgcolor: 'warning.100',
                    px: 0.5,
                    borderRadius: 0.5,
                    fontWeight: 600,
                  }),
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (p.row) handleRowClick(p.row);
                }}
              >
                {p.value || '—'}
              </Typography>
            </Stack>
          );
        },
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
        width: 260,
        sortable: false,
        filterable: false,
        renderCell: (p: GridRenderCellParams<JobRow>) => {
          if (!p.row) return null;
          const deletePending =
            deleteJob.isPending && deleteJob.variables === p.row.queue_id;
          const canDelete = DELETABLE_STATES.has(p.row.queue_status);

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
              <Stack direction="row" spacing={1} alignItems="center">
                <Button
                  size="small"
                  color="primary"
                  variant="outlined"
                  disabled={pending}
                  onClick={() => reenqueue.mutate(p.row.queue_id)}
                >
                  {pending ? '\u2026' : 'Re-run'}
                </Button>
                <Tooltip title="Delete job">
                  <IconButton
                    size="small"
                    color="error"
                    disabled={deletePending}
                    onClick={() => deleteJob.mutate(p.row.queue_id)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            );
          }
          if (p.row.queue_status === 'COMPLETED') {
            return (
              <Stack direction="row" spacing={1} alignItems="center">
                {onView && (
                  <Button
                    size="small"
                    color="primary"
                    variant="outlined"
                    onClick={() => onView(p.row.queue_id)}
                  >
                    View
                  </Button>
                )}
                <Tooltip title="Delete job">
                  <IconButton
                    size="small"
                    color="error"
                    disabled={deletePending}
                    onClick={() => deleteJob.mutate(p.row.queue_id)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            );
          }
          return canDelete ? (
            <Tooltip title="Delete job">
              <IconButton
                size="small"
                color="error"
                disabled={deletePending}
                onClick={() => deleteJob.mutate(p.row.queue_id)}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : null;
        },
      },
    ],
    [cancel, reenqueue, deleteJob, onView, compareMode, compareJobs],
  );

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          My Jobs
        </Typography>
        {jobs.isFetching && <CircularProgress size={16} />}
        <Box sx={{ flexGrow: 1 }} />
        {compareMode && (
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              icon={<CompareArrowsIcon />}
              label={`Compare mode: ${compareJobs.length}/${MAX_COMPARE_JOBS} selected`}
              color="warning"
              onDelete={handleCloseCompare}
            />
            {compareJobs.map((job, i) => (
              <Chip
                key={job.queue_id}
                label={`${i + 1}. ${job.strategy_nm?.slice(0, 15) || 'Job'}...`}
                size="small"
                variant="outlined"
                onDelete={() => setCompareJobs(compareJobs.filter(j => j.queue_id !== job.queue_id))}
              />
            ))}
            {compareJobs.length >= 2 && (
              <Button
                size="small"
                variant="contained"
                color="primary"
                onClick={handleOpenMultiCompare}
              >
                Compare Now
              </Button>
            )}
          </Stack>
        )}
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
      {deleteJob.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => deleteJob.reset()}>
          Delete failed: {(deleteJob.error as Error)?.message ?? 'unknown error'}
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

      {/* Job Detail Drawer */}
      <JobDetailDrawer
        open={!!detailJob}
        job={detailJob}
        onClose={() => setDetailJob(null)}
        onCloneEdit={handleCloneEdit}
        onCompare={handleStartCompare}
        onRerun={handleRerun}
      />

      {/* Multi-Job Compare Drawer (table view) */}
      <JobMultiCompareDrawer
        open={showMultiCompare}
        jobs={compareJobs}
        onClose={handleCloseCompare}
      />
    </Box>
  );
}
