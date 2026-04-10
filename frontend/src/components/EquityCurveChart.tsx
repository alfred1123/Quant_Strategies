import Plot from 'react-plotly.js';
import type { EquityPoint } from '../types/backtest';

export default function EquityCurveChart({ curve }: { curve: EquityPoint[] }) {
  if (!curve.length) return null;

  const dates = curve.map(p => p.datetime);

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
            line: { color: '#1976d2', width: 2 },
          },
          {
            x: dates,
            y: curve.map(p => +(p.buy_hold_cumu * 100).toFixed(2)),
            name: 'Buy & Hold',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#9e9e9e', dash: 'dash', width: 1.5 },
          },
        ]}
        layout={{
          title: { text: 'Cumulative Return (%)' },
          height: 320,
          margin: { t: 50, r: 30, b: 40, l: 60 },
          legend: { orientation: 'h', y: -0.2 },
          hovermode: 'x unified',
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
            line: { color: '#d32f2f', width: 1.5 },
            fillcolor: 'rgba(211,47,47,0.15)',
          },
          {
            x: dates,
            y: curve.map(p => +(p.buy_hold_dd * 100).toFixed(2)),
            name: 'B&H DD',
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            line: { color: '#ff9800', dash: 'dash', width: 1 },
            fillcolor: 'rgba(255,152,0,0.08)',
          },
        ]}
        layout={{
          title: { text: 'Drawdown (%)' },
          height: 250,
          margin: { t: 50, r: 30, b: 40, l: 60 },
          legend: { orientation: 'h', y: -0.25 },
          hovermode: 'x unified',
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: '100%' }}
      />
    </>
  );
}
