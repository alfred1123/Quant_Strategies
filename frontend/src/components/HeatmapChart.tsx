import Plot from 'react-plotly.js';
import type { Top10Row } from '../types/backtest';

interface Props {
  grid: Top10Row[];
  mode?: 'single' | 'multi';
}

export default function HeatmapChart({ grid, mode = 'single' }: Props) {
  if (!grid.length || mode !== 'single') return null;

  const windows = [...new Set(grid.map(r => r.window as number))].sort((a, b) => a - b);
  const signals = [...new Set(grid.map(r => r.signal as number))].sort((a, b) => a - b);

  const z = signals.map(sig =>
    windows.map(win => {
      const row = grid.find(r => r.window === win && r.signal === sig);
      return (row?.sharpe ?? null) as number | null;
    })
  );

  return (
    <Plot
      data={[
        {
          type: 'heatmap',
          x: windows,
          y: signals,
          z: z as unknown as number[][],
          colorscale: 'RdYlGn',
          zsmooth: 'best',
          colorbar: { title: { text: 'Sharpe' } },
        },
      ]}
      layout={{
        title: { text: 'Sharpe Ratio — Parameter Grid' },
        xaxis: { title: { text: 'Window' } },
        yaxis: { title: { text: 'Signal' } },
        height: 360,
        margin: { t: 50, r: 80, b: 50, l: 60 },
      }}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: '100%' }}
    />
  );
}
