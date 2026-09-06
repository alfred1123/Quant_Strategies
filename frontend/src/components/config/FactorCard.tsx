import {
  Box, FormControl, IconButton, InputLabel, MenuItem, Select, Stack, Typography,
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import ProductSelector from './ProductSelector';
import RangeFields from './RangeFields';
import type { FactorConfig, RangeParam } from '../../types/backtest';
import type {
  AppRow, DataColumnRow, IndicatorRow, ProductRow, SignalTypeRow,
} from '../../types/refdata';
import { countSteps } from '../../utils/grid';
import { scaleWindowRange } from '../../utils/interval';

interface Props {
  index: number;
  total: number;
  conjunction?: string;
  factor: FactorConfig;
  onChange: (patch: Partial<FactorConfig>) => void;
  onRemove: () => void;
  indicators: IndicatorRow[];
  signalTypes: SignalTypeRow[];
  dataColumns: DataColumnRow[];
  products: ProductRow[];
  apps: AppRow[];
  /**
   * Bars this cadence produces in a day. REFDATA WIN_* are daily-bar
   * counts; the grid is scaled so lookback stays in calendar days.
   */
  barsPerDay?: number;
  /** Traded venue. A leftover provider override is dropped when the
   *  factor product is picked and this venue is an exchange — otherwise
   *  ETH on a Bybit run stays pinned to Yahoo and is left out of coverage. */
  tradeDataSource?: string;
}

/**
 * Self-contained card for one factor: product override, data column,
 * indicator, strategy, and the two RangeFields blocks. Picking an
 * indicator auto-populates window/signal ranges from REFDATA defaults,
 * with the window grid scaled by bars-per-day so lookback stays in
 * calendar days (hourly Win Max is 100 × 24, not 100 bars).
 */
function factorRoleLabel(index: number, total: number, conjunction: string): string {
  if (conjunction === 'FILTER' && total > 1) {
    return index === 0 ? 'Gate (on/off)' : 'Signal (direction)';
  }
  return `Factor ${index + 1}`;
}

/** One factor card. Under FILTER, index 0 is the gate and index 1 the signal. */
export default function FactorCard({
  index, total, conjunction = 'AND', factor, onChange, onRemove,
  indicators, signalTypes, dataColumns, products, apps,
  barsPerDay = 1,
  tradeDataSource,
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
            window_range: scaleWindowRange(
              { min: next.win_min, max: next.win_max, step: next.win_step } as RangeParam,
              1,
              barsPerDay,
            ),
            signal_range: { min: next.sig_min, max: next.sig_max, step: next.sig_step } as RangeParam,
          }
        : {}),
    });
  };

  return (
    <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2, bgcolor: 'background.paper' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="caption" sx={{ fontWeight: 600 }}>
          {factorRoleLabel(index, total, conjunction)}
          <Typography component="span" variant="caption" color="text.secondary" sx={{ fontWeight: 400 }}>
            {' '}— {trials.toLocaleString()} grid pts
          </Typography>
        </Typography>
        {total > 1 && (
          <IconButton size="small" onClick={onRemove} title="Remove factor" aria-label="Remove factor">
            <CloseRoundedIcon fontSize="small" />
          </IconButton>
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
            // Picking a product while the factor still carries a provider
            // override (DEFAULT used to pin yahoo) would keep ETH off the
            // Bybit coverage set. Drop that leftover so the factor inherits
            // the traded exchange; a deliberate Yahoo/^VIX factor is set
            // afterwards by changing Data Source.
            if ('symbol' in patch && tradeDataSource) {
              const tradeApp = apps.find(a => a.name === tradeDataSource);
              const factorApp = apps.find(a => a.name === (out.data_source ?? factor.data_source));
              if (tradeApp?.is_exchange_ind === 'Y' && factorApp?.is_exchange_ind !== 'Y') {
                out.data_source = tradeDataSource;
              }
            }
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
