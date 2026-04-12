import {
  Drawer, Box, Typography, TextField, Select, MenuItem,
  FormControl, InputLabel, Button, Divider, IconButton, Stack, CircularProgress,
} from '@mui/material';
import { useIndicators, useSignalTypes, useAssetTypes, useConjunctions } from '../api/refdata';
import { countSteps } from '../utils/grid';
import type { BacktestConfig, FactorConfig, RangeParam } from '../types/backtest';

interface Props {
  open: boolean;
  onClose: () => void;
  config: BacktestConfig;
  onChange: (c: BacktestConfig) => void;
  onRun: () => void;
  isRunning: boolean;
}

export default function ConfigDrawer({ open, onClose, config, onChange, onRun, isRunning }: Props) {
  const { data: indicators = [] } = useIndicators();
  const { data: signalTypes = [] } = useSignalTypes();
  const { data: assetTypes = [] } = useAssetTypes();
  const { data: conjunctions = [] } = useConjunctions();

  const set = (patch: Partial<BacktestConfig>) => onChange({ ...config, ...patch });

  const handleIndicatorChange = (method_name: string) => {
    const ind = indicators.find(i => i.method_name === method_name);
    if (ind) {
      set({
        indicator: method_name,
        windowRange: { min: ind.win_min, max: ind.win_max, step: ind.win_step },
        signalRange: { min: ind.sig_min, max: ind.sig_max, step: ind.sig_step },
      });
    } else {
      set({ indicator: method_name });
    }
  };

  const handleFactorIndicatorChange = (i: number, method_name: string) => {
    const ind = indicators.find(x => x.method_name === method_name);
    const updated = config.factors.map((f, idx) => {
      if (idx !== i) return f;
      return {
        ...f,
        indicator: method_name,
        ...(ind
          ? {
              window_range: { min: ind.win_min, max: ind.win_max, step: ind.win_step } as RangeParam,
              signal_range: { min: ind.sig_min, max: ind.sig_max, step: ind.sig_step } as RangeParam,
            }
          : {}),
      };
    });
    set({ factors: updated });
  };

  const addFactor = () => {
    if (config.factors.length >= 2) return;
    const first = indicators[0];
    const newFactor: FactorConfig = {
      indicator: first?.method_name ?? '',
      strategy: signalTypes[0]?.func_name ?? '',
      data_column: 'price',
      window_range: { min: first?.win_min ?? 5, max: first?.win_max ?? 100, step: first?.win_step ?? 5 },
      signal_range: { min: first?.sig_min ?? 0.25, max: first?.sig_max ?? 2.5, step: first?.sig_step ?? 0.25 },
    };
    set({ factors: [...config.factors, newFactor] });
  };

  const removeFactor = (i: number) => set({ factors: config.factors.filter((_, idx) => idx !== i) });

  const updateFactor = (i: number, patch: Partial<FactorConfig>) => {
    set({ factors: config.factors.map((f, idx) => idx === i ? { ...f, ...patch } : f) });
  };

  const completeFactor = (f: FactorConfig) => Boolean(f.indicator && f.strategy);

  const missingFields: string[] = [];
  if (!config.symbol.trim()) missingFields.push('Symbol');
  if (!config.assetType) missingFields.push('Asset Type');
  config.factors.forEach((f, i) => {
    const label = config.factors.length > 1 ? `Factor ${i + 1} ` : '';
    if (!f.indicator) missingFields.push(`${label}Indicator`);
    if (!f.strategy) missingFields.push(`${label}Strategy`);
  });

  const isRunnable = missingFields.length === 0 && config.factors.length >= 1;

  const totalTrials = config.factors.reduce(
    (acc, f) => acc * countSteps(f.window_range) * countSteps(f.signal_range),
    1,
  );

  return (
    <Drawer
      anchor="top"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { p: 3, maxHeight: '85vh', overflowY: 'auto', position: 'relative' } }}
    >
      {/* Close button — top right corner */}
      <IconButton onClick={onClose} size="small" sx={{ position: 'absolute', top: 12, right: 12 }}>✕</IconButton>

      {/* Header */}
      <Box mb={3}>
        <Typography variant="h6" fontWeight={700}>Configure Backtest</Typography>
        <Typography variant="body2" color="text.secondary" mt={0.5}>Set the backtest parameters and factor grid below, then run the optimization.</Typography>
      </Box>

      {/* Row 1: base params */}
      <Box sx={{ display: 'flex', gap: 1.5, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          label="Symbol" size="small" value={config.symbol} sx={{ width: 130 }}
          onChange={e => set({ symbol: e.target.value })}
        />
        <TextField
          label="Start" size="small" type="date" value={config.start} sx={{ width: 155 }}
          onChange={e => set({ start: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="End" size="small" type="date" value={config.end} sx={{ width: 155 }}
          onChange={e => set({ end: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Asset Type</InputLabel>
          <Select
            value={config.assetType} label="Asset Type"
            onChange={e => {
              const at = assetTypes.find(a => a.display_name === e.target.value);
              set({ assetType: e.target.value, tradingPeriod: at?.trading_period ?? 365 });
            }}
          >
            {assetTypes.map(a => (
              <MenuItem key={a.display_name} value={a.display_name}>{a.display_name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          label="Fee (bps)" size="small" type="number" value={config.feeBps} sx={{ width: 100 }}
          onChange={e => set({ feeBps: Number(e.target.value) })}
        />
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Factor configuration */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {config.factors.map((factor, i) => {
          const factorTrials = countSteps(factor.window_range) * countSteps(factor.signal_range);
          return (
            <>
              {/* Conjunction block — sits between factor 1 and factor 2 */}
              {i === 1 && (
                <Box key="conjunction" sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Divider sx={{ flex: 1 }} />
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Conjunction</InputLabel>
                    <Select value={config.conjunction} label="Conjunction"
                      onChange={e => set({ conjunction: e.target.value })}>
                      {conjunctions.map(c => (
                        <MenuItem key={c.name} value={c.name}>{c.display_name}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Divider sx={{ flex: 1 }} />
                </Box>
              )}

              <Box key={i} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2, bgcolor: 'background.paper' }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="caption" fontWeight={600}>
                    Factor {i + 1}
                    <Typography component="span" variant="caption" color="text.secondary" fontWeight={400}>
                      {' '}— {factorTrials.toLocaleString()} grid pts
                    </Typography>
                  </Typography>
                  {i > 0 && (
                    <IconButton size="small" onClick={() => removeFactor(i)}>×</IconButton>
                  )}
                </Box>
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <FormControl size="small" sx={{ minWidth: 180, flex: 2 }}>
                      <InputLabel>Indicator</InputLabel>
                      <Select value={factor.indicator} label="Indicator"
                        onChange={e => handleFactorIndicatorChange(i, e.target.value)}>
                        {indicators.map(ind => (
                          <MenuItem key={ind.method_name} value={ind.method_name}>{ind.display_name}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl size="small" sx={{ minWidth: 140, flex: 1.5 }}>
                      <InputLabel>Strategy</InputLabel>
                      <Select value={factor.strategy} label="Strategy"
                        onChange={e => updateFactor(i, { strategy: e.target.value })}>
                        {signalTypes.map(s => (
                          <MenuItem key={s.func_name} value={s.func_name}>{s.display_name}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <TextField label="Win Min" size="small" type="number" value={factor.window_range.min} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, min: Number(e.target.value) } })} />
                    <TextField label="Win Max" size="small" type="number" value={factor.window_range.max} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, max: Number(e.target.value) } })} />
                    <TextField label="Win Step" size="small" type="number" value={factor.window_range.step} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, step: Number(e.target.value) } })} />
                    <TextField label="Sig Min" size="small" type="number" value={factor.signal_range.min} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, min: Number(e.target.value) } })} />
                    <TextField label="Sig Max" size="small" type="number" value={factor.signal_range.max} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, max: Number(e.target.value) } })} />
                    <TextField label="Sig Step" size="small" type="number" value={factor.signal_range.step} sx={{ width: 80 }}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, step: Number(e.target.value) } })} />
                  </Stack>
                </Stack>
              </Box>
            </>
          );
        })}
        {config.factors.length < 2 && (
          <Button variant="outlined" size="small" onClick={addFactor} sx={{ alignSelf: 'flex-start' }}>+ Add Factor</Button>
        )}
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Footer: missing fields + trial count + Run */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        {missingFields.length > 0 && (
          <Typography variant="caption" color="error" fontWeight={500}>
            Missing: {missingFields.join(', ')}
          </Typography>
        )}
        {isRunnable && (
          <Typography variant="caption" color="text.secondary">
            ~{totalTrials.toLocaleString()} total grid points
          </Typography>
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Button
          variant="contained"
          size="large"
          onClick={onRun}
          disabled={isRunning || !isRunnable}
          startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          {isRunning ? 'Running…' : 'Run Optimization'}
        </Button>
      </Box>
    </Drawer>
  );
}
