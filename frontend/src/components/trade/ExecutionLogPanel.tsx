import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  Tab,
  Tabs,
  Tooltip,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useMemo, useState } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef } from '@mui/x-data-grid';
import { useExecutionEvents, useTransactions } from '../../api/trade';
import { useTradeSessionFilters } from '../../trade/useTradeSession';
import type { ExecutionEventRow, TransactionRow } from '../../types/trade';

function formatNum(value: string | null | undefined, digits = 4): string {
  if (value == null || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function sideColor(side: string): 'default' | 'success' | 'error' | 'warning' {
  if (side === 'HOLD') return 'default';
  if (side === 'BUY' || side === 'CLOSE_SHORT') return 'success';
  if (side === 'SELL' || side === 'OPEN_SHORT') return 'error';
  return 'default';
}

const EVENT_COLUMNS: GridColDef<ExecutionEventRow>[] = [
  {
    field: 'transact_at',
    headerName: 'Time',
    flex: 1.2,
    minWidth: 150,
    valueFormatter: (value) => (value ? new Date(String(value)).toLocaleString() : ''),
  },
  {
    field: 'internal_cusip',
    headerName: 'Product',
    flex: 1,
    minWidth: 120,
  },
  {
    field: 'buy_sell_cd',
    headerName: 'Side',
    width: 110,
    renderCell: ({ value }) => (
      <Chip
        size="small"
        label={String(value)}
        color={sideColor(String(value))}
        variant={value === 'HOLD' ? 'outlined' : 'filled'}
      />
    ),
  },
  {
    field: 'quantity',
    headerName: 'Qty',
    width: 90,
    valueFormatter: (value) => formatNum(value as string | null),
  },
  {
    field: 'signal_value',
    headerName: 'Signal',
    width: 90,
    valueFormatter: (value) => formatNum(value as string | null),
  },
  {
    field: 'position_qty',
    headerName: 'Position',
    width: 90,
    valueFormatter: (value) => formatNum(value as string | null),
  },
  {
    field: 'is_success_ind',
    headerName: 'Status',
    width: 90,
    renderCell: ({ value, row }) => {
      if (row.buy_sell_cd === 'HOLD') {
        return <Chip size="small" label="HOLD" variant="outlined" />;
      }
      const ok = value === 'Y';
      return (
        <Chip
          size="small"
          label={ok ? 'OK' : 'Fail'}
          color={ok ? 'success' : 'error'}
          variant="outlined"
        />
      );
    },
  },
  {
    field: 'vendor_order_id',
    headerName: 'Order ID',
    flex: 1,
    minWidth: 100,
    valueFormatter: (value) => {
      const s = value ? String(value) : '';
      if (!s) return '—';
      return s.length > 12 ? `${s.slice(0, 8)}…` : s;
    },
  },
];

const FILL_COLUMNS: GridColDef<TransactionRow>[] = [
  {
    field: 'filled_at',
    headerName: 'Time',
    flex: 1.2,
    minWidth: 150,
    valueFormatter: (value) => (value ? new Date(String(value)).toLocaleString() : ''),
  },
  {
    field: 'internal_cusip',
    headerName: 'Product',
    flex: 1,
    minWidth: 120,
  },
  {
    field: 'buy_sell_cd',
    headerName: 'Side',
    width: 90,
    renderCell: ({ value }) => (
      <Chip size="small" label={String(value)} color={sideColor(String(value))} />
    ),
  },
  {
    field: 'quantity',
    headerName: 'Qty',
    width: 90,
    valueFormatter: (value) => formatNum(value as string | null),
  },
  {
    field: 'price',
    headerName: 'Price',
    width: 100,
    valueFormatter: (value) => formatNum(value as string | null, 2),
  },
  {
    field: 'notional_amt',
    headerName: 'Notional',
    width: 110,
    valueFormatter: (value) => formatNum(value as string | null, 2),
  },
  {
    field: 'fee_amt',
    headerName: 'Fee',
    width: 90,
    valueFormatter: (value) => formatNum(value as string | null, 4),
  },
  {
    field: 'vendor_order_id',
    headerName: 'Order ID',
    flex: 1,
    minWidth: 100,
    valueFormatter: (value) => {
      const s = value ? String(value) : '';
      if (!s) return '—';
      return s.length > 12 ? `${s.slice(0, 8)}…` : s;
    },
  },
];

const GRID_SX = {
  border: 'none',
  '& .MuiDataGrid-columnHeaders': { bgcolor: 'action.hover' },
} as const;

const GRID_PAGE = {
  pageSizeOptions: [10, 25, 50] as const,
  initialState: { pagination: { paginationModel: { pageSize: 10 } } },
};

/** Bottom panel — recent order attempts and confirmed fills (Phase 1.8). */
export default function ExecutionLogPanel() {
  const [tab, setTab] = useState(0);
  const { matchesSession, credentialsNotLoaded } = useTradeSessionFilters();

  const events = useExecutionEvents();
  const fills = useTransactions();

  const filteredEvents = useMemo(
    () => (events.data ?? []).filter(matchesSession),
    [events.data, matchesSession],
  );
  const filteredFills = useMemo(
    () => (fills.data ?? []).filter(matchesSession),
    [fills.data, matchesSession],
  );

  const loading = tab === 0 ? events.isLoading : fills.isLoading;
  const isFetching = tab === 0 ? events.isFetching : fills.isFetching;
  const isError = tab === 0 ? events.isError : fills.isError;
  const error = tab === 0 ? events.error : fills.error;
  const refetch = tab === 0 ? events.refetch : fills.refetch;

  const emptyMessage =
    tab === 0
      ? 'No order attempts yet — apply a deployment or wait for a scheduled tick.'
      : 'No confirmed fills yet — fills appear after a successful order at the broker.';

  const rowCount = tab === 0 ? filteredEvents.length : filteredFills.length;

  return (
    <Box>
      <Stack
        direction="row"
        spacing={1}
        sx={{ mb: 1, alignItems: 'center', justifyContent: 'space-between' }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography variant="subtitle2" color="text.secondary">
            Execution log
          </Typography>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            aria-label="Execution log view"
            sx={{ minHeight: 32, '& .MuiTab-root': { minHeight: 32, py: 0.5, px: 1.5 } }}
          >
            <Tab label={`Attempts (${filteredEvents.length})`} />
            <Tab label={`Fills (${filteredFills.length})`} />
          </Tabs>
        </Stack>
        <Tooltip title="Refresh">
          <span>
            <IconButton
              size="small"
              aria-label="Refresh execution log"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              {isFetching ? <CircularProgress size={18} /> : <RefreshIcon fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      {credentialsNotLoaded && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          Account list still loading — toolbar filters may be incomplete.
        </Typography>
      )}

      {isError && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error instanceof Error ? error.message : 'Failed to load execution log'}
        </Alert>
      )}

      {loading ? (
        <Stack sx={{ py: 3, alignItems: 'center' }}>
          <CircularProgress size={28} />
        </Stack>
      ) : rowCount === 0 ? (
        <Typography variant="body2" color="text.disabled">
          {emptyMessage}
        </Typography>
      ) : tab === 0 ? (
        <DataGrid
          rows={filteredEvents}
          columns={EVENT_COLUMNS}
          getRowId={(row) => row.execution_event_id}
          autoHeight
          density="compact"
          disableRowSelectionOnClick
          hideFooter={filteredEvents.length <= 10}
          pageSizeOptions={[...GRID_PAGE.pageSizeOptions]}
          initialState={GRID_PAGE.initialState}
          sx={GRID_SX}
        />
      ) : (
        <DataGrid
          rows={filteredFills}
          columns={FILL_COLUMNS}
          getRowId={(row) => row.transaction_id}
          autoHeight
          density="compact"
          disableRowSelectionOnClick
          hideFooter={filteredFills.length <= 10}
          pageSizeOptions={[...GRID_PAGE.pageSizeOptions]}
          initialState={GRID_PAGE.initialState}
          sx={GRID_SX}
        />
      )}
    </Box>
  );
}
