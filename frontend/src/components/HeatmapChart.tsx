import Plot from '../lib/Plot';
import type { Top10Row } from '../types/backtest';

interface Props {
  grid: Top10Row[];
  mode?: 'single' | 'multi';
}

export default function HeatmapChart({ grid, mode = 'single' }: Props) {
  if (!grid || !grid.length || mode !== 'single') return null;

  if (!Plot) return <p style={{ color: '#ef5350' }}>Plotly failed to load.</p>;

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
