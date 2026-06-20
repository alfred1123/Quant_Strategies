import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef, GridRenderCellParams, GridRowParams } from '@mui/x-data-grid';
import { useMemo, useState } from 'react';
import { useStrategies } from '../../api/strategies';
import { formatMetric } from '../../utils/format';
import type { StrategyListRow, StrategyListVersions } from '../../types/strategies';

export interface StrategyPickerSelection {
  strategyId: string;
  strategyVid: number;
  strategyNm: string | null;
}

export interface StrategyPickerProps {
  selected: StrategyPickerSelection | null;
  onSelect: (row: StrategyPickerSelection | null) => void;
}

export default function StrategyPicker({ selected, onSelect }: StrategyPickerProps) {
  const [versions, setVersions] = useState<StrategyListVersions>('best');
  const strategies = useStrategies(versions);

  const rows = strategies.data ?? [];

  const columns: GridColDef<StrategyListRow>[] = useMemo(
    () => [
      {
        field: 'strategy_nm',
        headerName: 'Strategy',
        flex: 1,
        minWidth: 200,
        valueFormatter: (value: string | null) => value ?? '—',
      },
      {
        field: 'strategy_vid',
        headerName: 'VID',
        width: 90,
        renderCell: (p: GridRenderCellParams<StrategyListRow>) => (
          <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
            <Typography variant="body2">v{p.row.strategy_vid}</Typography>
            {p.row.is_best_ind === 'Y' && (
              <Chip size="small" label="Best" color="success" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />
            )}
          </Stack>
        ),
      },
      {
        field: 'sharpe_ratio',
        headerName: 'Sharpe',
        width: 100,
        valueFormatter: (value: number | null) =>
          value == null ? '—' : formatMetric(value),
      },
      {
        field: 'created_at',
        headerName: 'Created',
        width: 180,
        valueFormatter: (value: string) =>
          value ? new Date(value).toLocaleString() : '',
      },
    ],
    [],
  );

  const handleRowClick = (params: GridRowParams<StrategyListRow>) => {
    const row = params.row;
    const next: StrategyPickerSelection = {
      strategyId: row.strategy_id,
      strategyVid: row.strategy_vid,
      strategyNm: row.strategy_nm,
    };
    const same =
      selected?.strategyId === next.strategyId
      && selected?.strategyVid === next.strategyVid;
    onSelect(same ? null : next);
  };

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 1.5 }}>
        <Typography variant="subtitle2">Your strategies</Typography>
        {strategies.isFetching && <CircularProgress size={16} />}
        <Box sx={{ flexGrow: 1 }} />
        <ToggleButtonGroup
          size="small"
          exclusive
          value={versions}
          onChange={(_, v: StrategyListVersions | null) => {
            if (v) setVersions(v);
          }}
          aria-label="Strategy version filter"
        >
          <ToggleButton value="best">Best only</ToggleButton>
          <ToggleButton value="all">All versions</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {strategies.isError && (
        <Alert severity="error" sx={{ mb: 1 }}>
          Failed to load strategies: {(strategies.error as Error)?.message ?? 'unknown error'}
        </Alert>
      )}

      {!strategies.isLoading && !strategies.isError && rows.length === 0 && (
        <Alert severity="info" sx={{ mb: 1 }}>
          {versions === 'best'
            ? 'No promoted best VID yet — switch to All versions to pick any owned backtest version.'
            : 'No strategies yet — run a backtest to create one.'}
        </Alert>
      )}

      <Box sx={{ height: 320 }}>
        <DataGrid
          rows={rows}
          columns={columns}
          getRowId={(r) => `${r.strategy_id}-${r.strategy_vid}`}
          loading={strategies.isLoading}
          onRowClick={handleRowClick}
          getRowClassName={(params) => {
            if (
              selected
              && params.row.strategy_id === selected.strategyId
              && params.row.strategy_vid === selected.strategyVid
            ) {
              return 'selected-strategy';
            }
            return '';
          }}
          sx={{
            '& .MuiDataGrid-row.selected-strategy': {
              bgcolor: 'action.selected',
            },
          }}
          disableRowSelectionOnClick
          density="compact"
          pageSizeOptions={[10, 25, 50]}
          initialState={{
            pagination: { paginationModel: { pageSize: 10 } },
            sorting: { sortModel: [{ field: 'created_at', sort: 'desc' }] },
          }}
        />
      </Box>
    </Box>
  );
}
