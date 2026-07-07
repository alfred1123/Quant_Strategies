import { useMemo } from 'react';
import Plot from '../lib/Plot';
import type { Top10Row } from '../types/backtest';
import { buildHeatmapMatrix } from '../utils/heatmap';

interface Props {
  grid: Top10Row[];
  mode?: 'single' | 'multi';
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
