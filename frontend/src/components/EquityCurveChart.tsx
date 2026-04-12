import Plot from '../lib/Plot';
import type { EquityPoint } from '../types/backtest';

interface Props {
  curve: EquityPoint[];
  splitDate?: string;
}

export default function EquityCurveChart({ curve, splitDate }: Props) {
  if (!curve || !curve.length) return null;

  if (!Plot) return <p style={{ color: '#ef5350' }}>Plotly failed to load.</p>;

  const dates = curve.map(p => p.datetime);

  const splitLine = splitDate
    ? [{
        type: 'line' as const,
        x0: splitDate, x1: splitDate,
        y0: 0, y1: 1, yref: 'paper' as const,
        line: { color: '#ffa726', width: 2, dash: 'dash' as const },
      }]
    : [];

  return (
    <>
      <Plot
        data={[
          {
            x: dates,
            y: curve.map(p => +(p.cumu * 100).toFixed(2)),
            name: 'Strategy',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#4d8ef0', width: 2 },
          },
          {
            x: dates,
            y: curve.map(p => +(p.buy_hold_cumu * 100).toFixed(2)),
            name: 'Buy & Hold',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#7a8aa8', dash: 'dash', width: 1.5 },
          },
        ]}
        layout={{
          title: { text: 'Cumulative Return (%)', font: { color: '#c8d0e0' } },
          paper_bgcolor: '#131929',
          plot_bgcolor: '#0d0f1a',
          font: { color: '#c8d0e0' },
          xaxis: { gridcolor: '#1e2d45', tickfont: { color: '#c8d0e0' } },
          yaxis: { gridcolor: '#1e2d45', tickfont: { color: '#c8d0e0' } },
          height: 320,
          margin: { t: 50, r: 30, b: 40, l: 60 },
          legend: { orientation: 'h', y: -0.2, font: { color: '#c8d0e0' } },
          hovermode: 'x unified',
          shapes: splitLine,
          ...(splitDate ? {
            annotations: [{
              x: splitDate, y: 1, yref: 'paper' as const,
              text: 'Train | Test', showarrow: false,
              font: { color: '#ffa726', size: 11 },
              yanchor: 'bottom' as const,
            }],
          } : {}),
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: '100%' }}
      />
      <Plot
        data={[
          {
            x: dates,
            y: curve.map(p => +(p.dd * 100).toFixed(2)),
            name: 'Strategy DD',
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            line: { color: '#ef5350', width: 1.5 },
            fillcolor: 'rgba(239,83,80,0.15)',
          },
          {
            x: dates,
            y: curve.map(p => +(p.buy_hold_dd * 100).toFixed(2)),
            name: 'B&H DD',
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            line: { color: '#ffa726', dash: 'dash', width: 1 },
            fillcolor: 'rgba(255,167,38,0.08)',
          },
        ]}
        layout={{
          title: { text: 'Drawdown (%)', font: { color: '#c8d0e0' } },
          paper_bgcolor: '#131929',
          plot_bgcolor: '#0d0f1a',
          font: { color: '#c8d0e0' },
          xaxis: { gridcolor: '#1e2d45', tickfont: { color: '#c8d0e0' } },
          yaxis: { gridcolor: '#1e2d45', tickfont: { color: '#c8d0e0' } },
          height: 250,
          margin: { t: 50, r: 30, b: 40, l: 60 },
          legend: { orientation: 'h', y: -0.25, font: { color: '#c8d0e0' } },
          hovermode: 'x unified',
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: '100%' }}
      />
    </>
  );
}
