import { useMemo } from 'react';
import Plot from '../lib/Plot';
import type { Top10Row } from '../types/backtest';
import { isSingleFactorRow } from '../utils/top10';

interface Props {
  grid: Top10Row[];
  mode?: 'single' | 'multi';
}

/** Pure helper — extracted for unit testing without Plotly. */
export function buildHeatmapMatrix(grid: Top10Row[]): {
  windows: number[];
  signals: number[];
  z: (number | null)[][];
} {
  const singleRows = grid.filter(isSingleFactorRow);

  const windowsSet = new Set<number>();
  const signalsSet = new Set<number>();
  const sharpeByKey = new Map<string, number>();

  for (const row of singleRows) {
    windowsSet.add(row.window);
    signalsSet.add(row.signal);
    sharpeByKey.set(`${row.window}|${row.signal}`, row.sharpe);
  }

  const windows = [...windowsSet].sort((a, b) => a - b);
  const signals = [...signalsSet].sort((a, b) => a - b);
  const z = signals.map(sig =>
    windows.map(win => sharpeByKey.get(`${win}|${sig}`) ?? null),
  );

  return { windows, signals, z };
}

export default function HeatmapChart({ grid, mode = 'single' }: Props) {
  const matrix = useMemo(() => buildHeatmapMatrix(grid), [grid]);

  if (!grid || !grid.length || mode !== 'single') return null;
  if (!Plot) return <p style={{ color: '#ef5350' }}>Plotly failed to load.</p>;
  if (matrix.windows.length === 0 || matrix.signals.length === 0) return null;

  return (
    <Plot
      data={[
        {
          type: 'heatmap',
          x: matrix.windows,
          y: matrix.signals,
          z: matrix.z as unknown as number[][],
          colorscale: 'RdYlGn',
          zsmooth: 'best',
          colorbar: { title: { text: 'Sharpe' } },
        },
      ]}
      layout={{
        title: { text: 'Sharpe Ratio — Parameter Grid', font: { color: '#c8d0e0' } },
        paper_bgcolor: '#131929',
        plot_bgcolor: '#0d0f1a',
        font: { color: '#c8d0e0' },
        xaxis: { title: { text: 'Window' }, gridcolor: '#1e2d45', tickfont: { color: '#c8d0e0' } },
        yaxis: { title: { text: 'Signal' }, gridcolor: '#1e2d45', tickfont: { color: '#c8d0e0' } },
        height: 360,
        margin: { t: 50, r: 80, b: 50, l: 60 },
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: '100%' }}
    />
  );
}
