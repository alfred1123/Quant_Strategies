import { Card, CardContent, Typography } from '@mui/material';
import type { PerformanceResponse } from '../types/backtest';

const PERCENT_KEYS = new Set(['Total Return', 'Annualized Return', 'Max Drawdown']);

function fmt(key: string, v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return '—';
  if (PERCENT_KEYS.has(key)) return `${(v * 100).toFixed(1)}%`;
  return v.toFixed(3);
}

interface CardProps {
  title: string;
  metrics: Record<string, number>;
  highlight?: boolean;
}

function MetricCard({ title, metrics, highlight }: CardProps) {
  return (
    <Card variant="outlined" sx={{ flex: 1, borderColor: highlight ? 'primary.main' : undefined }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Typography
          variant="subtitle2"
          color={highlight ? 'primary' : 'text.secondary'}
          gutterBottom
        >
          {title}
        </Typography>
        {Object.entries(metrics).map(([k, v]) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
            <Typography variant="body2" color="text.secondary">{k}</Typography>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>{fmt(k, v)}</Typography>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function MetricsCards({ result }: { result: PerformanceResponse }) {
  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <MetricCard title="Strategy" metrics={result.strategy_metrics} highlight />
      <MetricCard title="Buy & Hold" metrics={result.buy_hold_metrics} />
    </div>
  );
}
