import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef } from '@mui/x-data-grid';
import { Button, Chip } from '@mui/material';
import type { Top10Row, OptimizeResponse } from '../types/backtest';

interface Props {
  result: OptimizeResponse;
  selectedIndex: number | null;
  onSelect: (row: Top10Row, index: number) => void;
  isLoadingPerf: boolean;
}

/** Format any cell value defensively — only numbers get toFixed; other types pass through. */
function formatNumeric(value: unknown, digits: number): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '';
}

export default function Top10Table({ result, selectedIndex, onSelect, isLoadingPerf }: Props) {
  const rows = result.top10.map((r, i) => ({ ...r, id: i }));

  // Build param columns dynamically from first row keys (everything except `sharpe`).
  // Don't assume all values are numbers — `formatNumeric` handles non-numeric gracefully.
  const first = (result.top10[0] ?? {}) as Record<string, unknown>;
  const paramCols: GridColDef[] = Object.keys(first)
    .filter(k => k !== 'sharpe')
    .map(k => ({
      field: k,
      headerName: k,
      width: 90,
      type: 'number' as const,
      valueFormatter: (value: unknown) => formatNumeric(value, 2),
    }));

  const columns: GridColDef[] = [
    ...paramCols,
    {
      field: 'sharpe',
      headerName: 'Sharpe',
      width: 100,
      type: 'number',
      valueFormatter: (value: unknown) => formatNumeric(value, 4),
    },
    {
      field: '_action',
      headerName: '',
      width: 155,
      sortable: false,
      renderCell: (params) => {
        const idx = params.row.id as number;
        const isBest = idx === 0;
        const isSelected = idx === selectedIndex;
        return isBest ? (
          <Chip
            label="★ Best"
            color="success"
            size="small"
            onClick={() => !isLoadingPerf && onSelect(result.top10[idx], idx)}
            sx={{ cursor: 'pointer', fontWeight: isSelected ? 700 : 500 }}
          />
        ) : (
          <Button
            size="small"
            variant={isSelected ? 'contained' : 'text'}
            onClick={() => onSelect(result.top10[idx], idx)}
            disabled={isLoadingPerf}
          >
            View Analysis
          </Button>
        );
      },
    },
  ];

  return (
    <DataGrid
      rows={rows}
      columns={columns}
      autoHeight
      hideFooter
      disableColumnMenu
      density="compact"
      sx={{ border: 0 }}
    />
  );
}
