import {
  Box, FormControl, IconButton, InputLabel, MenuItem, Select, Stack, Typography,
} from '@mui/material';
import ProductSelector from './ProductSelector';
import RangeFields from './RangeFields';
import type { FactorConfig, RangeParam } from '../../types/backtest';
import type {
  AppRow, DataColumnRow, IndicatorRow, ProductRow, SignalTypeRow,
} from '../../types/refdata';
import { countSteps } from '../../utils/grid';

interface Props {
  index: number;
  total: number;
  factor: FactorConfig;
  onChange: (patch: Partial<FactorConfig>) => void;
  onRemove: () => void;
  indicators: IndicatorRow[];
  signalTypes: SignalTypeRow[];
  dataColumns: DataColumnRow[];
  products: ProductRow[];
  apps: AppRow[];
}

/**
 * Self-contained card for one factor: product override, data column,
 * indicator, strategy, and the two RangeFields blocks. Picking an
 * indicator auto-populates window/signal ranges from REFDATA defaults.
 */
export default function FactorCard({
  index, total, factor, onChange, onRemove,
  indicators, signalTypes, dataColumns, products, apps,
}: Props) {
  const trials = countSteps(factor.window_range) * countSteps(factor.signal_range);
  const ind = indicators.find(x => x.method_name === factor.indicator);
  const isBounded = ind?.is_bounded_ind === 'Y';

  const handleIndicatorChange = (method_name: string) => {
    const next = indicators.find(x => x.method_name === method_name);
    onChange({
      indicator: method_name,
      ...(next
        ? {
            window_range: { min: next.win_min, max: next.win_max, step: next.win_step } as RangeParam,
            signal_range: { min: next.sig_min, max: next.sig_max, step: next.sig_step } as RangeParam,
          }
        : {}),
    });
  };

  return (
    <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2, bgcolor: 'background.paper' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="caption" sx={{ fontWeight: 600 }}>
          Factor {index + 1}
          <Typography component="span" variant="caption" color="text.secondary" sx={{ fontWeight: 400 }}>
            {' '}— {trials.toLocaleString()} grid pts
          </Typography>
        </Typography>
        {total > 1 && (
          <IconButton size="small" onClick={onRemove} title="Remove factor">✕</IconButton>
        )}
      </Box>

      <Stack spacing={1}>
        {/* Shared product selector — same component as the trading row. */}
        <ProductSelector
          value={{
            symbol: factor.symbol,
            vendorSymbol: factor.vendor_symbol,
            dataSource: factor.data_source,
          }}
          onChange={patch => {
            const out: Partial<FactorConfig> = {};
            if ('symbol' in patch) out.symbol = patch.symbol;
            if ('vendorSymbol' in patch) out.vendor_symbol = patch.vendorSymbol;
            if ('dataSource' in patch) out.data_source = patch.dataSource;
            onChange(out);
          }}
          products={products}
          apps={apps}
        />

        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 120, flex: 1 }}>
            <InputLabel>Data Column</InputLabel>
            <Select value={factor.data_column} label="Data Column"
              onChange={e => onChange({ data_column: e.target.value })}>
              {dataColumns.map(dc => (
                <MenuItem key={dc.column_name} value={dc.column_name}>{dc.display_name}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 180, flex: 2 }}>
            <InputLabel>Indicator</InputLabel>
            <Select value={factor.indicator} label="Indicator"
              onChange={e => handleIndicatorChange(e.target.value)}>
              {indicators.map(i => (
                <MenuItem key={i.method_name} value={i.method_name}>{i.display_name}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 140, flex: 1.5 }}>
            <InputLabel>Strategy</InputLabel>
            <Select value={factor.strategy} label="Strategy"
              onChange={e => onChange({ strategy: e.target.value })}>
              {signalTypes.map(s => (
                <MenuItem key={s.name} value={s.name}>{s.display_name}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <RangeFields
            label="Win"
            value={factor.window_range}
            onChange={patch => onChange({ window_range: { ...factor.window_range, ...patch } })}
          />
          <RangeFields
            label="Sig"
            value={factor.signal_range}
            disabledMinMax={isBounded}
            onChange={patch => onChange({ signal_range: { ...factor.signal_range, ...patch } })}
          />
        </Stack>
      </Stack>
    </Box>
  );
}
