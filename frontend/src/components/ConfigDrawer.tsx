import {
  Drawer, Box, Typography, TextField, Select, MenuItem,
  FormControl, InputLabel, Button, RadioGroup, FormControlLabel,
  Radio, Divider, IconButton, Stack, CircularProgress,
} from '@mui/material';
import { useIndicators, useSignalTypes, useAssetTypes, useConjunctions } from '../api/refdata';
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

  return (
    <Drawer
      anchor="left"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 400, p: 3, overflowX: 'hidden' } }}
    >
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
        <Typography variant="h6" fontWeight={700}>Configure Backtest</Typography>
        <IconButton onClick={onClose} size="small">✕</IconButton>
      </Box>

      <Stack spacing={2.5}>
        {/* Symbol */}
        <TextField
          label="Symbol" size="small" value={config.symbol} fullWidth
          onChange={e => set({ symbol: e.target.value })}
        />

        {/* Dates */}
        <Stack direction="row" spacing={1}>
          <TextField
            label="Start" size="small" type="date" value={config.start} fullWidth
            onChange={e => set({ start: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="End" size="small" type="date" value={config.end} fullWidth
            onChange={e => set({ end: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        </Stack>

        {/* Asset type + Fee */}
        <Stack direction="row" spacing={1}>
          <FormControl size="small" fullWidth>
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
            label="Fee (bps)" size="small" type="number" value={config.feeBps}
            onChange={e => set({ feeBps: Number(e.target.value) })}
            sx={{ width: 110 }}
          />
        </Stack>

        <Divider />

        {/* Mode */}
        <RadioGroup
          row value={config.mode}
          onChange={e => set({ mode: e.target.value as 'single' | 'multi' })}
        >
          <FormControlLabel value="single" control={<Radio size="small" />} label="Single Factor" />
          <FormControlLabel value="multi" control={<Radio size="small" />} label="Multi Factor" />
        </RadioGroup>

        {config.mode === 'single' ? (
          <>
            <FormControl size="small" fullWidth>
              <InputLabel>Indicator</InputLabel>
              <Select
                value={config.indicator} label="Indicator"
                onChange={e => handleIndicatorChange(e.target.value)}
              >
                {indicators.map(i => (
                  <MenuItem key={i.method_name} value={i.method_name}>{i.display_name}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" fullWidth>
              <InputLabel>Strategy</InputLabel>
              <Select
                value={config.strategy} label="Strategy"
                onChange={e => set({ strategy: e.target.value })}
              >
                {signalTypes.map(s => (
                  <MenuItem key={s.func_name} value={s.func_name}>{s.display_name}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <Typography variant="caption" color="text.secondary">Window Range</Typography>
            <Stack direction="row" spacing={1}>
              <TextField label="Min" size="small" type="number" value={config.windowRange.min}
                onChange={e => set({ windowRange: { ...config.windowRange, min: Number(e.target.value) } })} />
              <TextField label="Max" size="small" type="number" value={config.windowRange.max}
                onChange={e => set({ windowRange: { ...config.windowRange, max: Number(e.target.value) } })} />
              <TextField label="Step" size="small" type="number" value={config.windowRange.step}
                onChange={e => set({ windowRange: { ...config.windowRange, step: Number(e.target.value) } })} />
            </Stack>

            <Typography variant="caption" color="text.secondary">Signal Range</Typography>
            <Stack direction="row" spacing={1}>
              <TextField label="Min" size="small" type="number" value={config.signalRange.min}
                onChange={e => set({ signalRange: { ...config.signalRange, min: Number(e.target.value) } })} />
              <TextField label="Max" size="small" type="number" value={config.signalRange.max}
                onChange={e => set({ signalRange: { ...config.signalRange, max: Number(e.target.value) } })} />
              <TextField label="Step" size="small" type="number" value={config.signalRange.step}
                onChange={e => set({ signalRange: { ...config.signalRange, step: Number(e.target.value) } })} />
            </Stack>
          </>
        ) : (
          <>
            <FormControl size="small" fullWidth>
              <InputLabel>Conjunction</InputLabel>
              <Select
                value={config.conjunction} label="Conjunction"
                onChange={e => set({ conjunction: e.target.value })}
              >
                {conjunctions.map(c => (
                  <MenuItem key={c.name} value={c.name}>{c.display_name}</MenuItem>
                ))}
              </Select>
            </FormControl>

            {config.factors.map((factor, i) => (
              <Box key={i} sx={{ border: '1px solid #e0e0e0', borderRadius: 1, p: 1.5 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="caption" fontWeight={600}>Factor {i + 1}</Typography>
                  <IconButton size="small" onClick={() => removeFactor(i)}>×</IconButton>
                </Box>
                <Stack spacing={1.5}>
                  <FormControl size="small" fullWidth>
                    <InputLabel>Indicator</InputLabel>
                    <Select
                      value={factor.indicator} label="Indicator"
                      onChange={e => handleFactorIndicatorChange(i, e.target.value)}
                    >
                      {indicators.map(ind => (
                        <MenuItem key={ind.method_name} value={ind.method_name}>{ind.display_name}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl size="small" fullWidth>
                    <InputLabel>Strategy</InputLabel>
                    <Select
                      value={factor.strategy} label="Strategy"
                      onChange={e => updateFactor(i, { strategy: e.target.value })}
                    >
                      {signalTypes.map(s => (
                        <MenuItem key={s.func_name} value={s.func_name}>{s.display_name}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Stack direction="row" spacing={1}>
                    <TextField label="Win Min" size="small" type="number" value={factor.window_range.min}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, min: Number(e.target.value) } })} />
                    <TextField label="Win Max" size="small" type="number" value={factor.window_range.max}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, max: Number(e.target.value) } })} />
                    <TextField label="Step" size="small" type="number" value={factor.window_range.step}
                      onChange={e => updateFactor(i, { window_range: { ...factor.window_range, step: Number(e.target.value) } })} />
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    <TextField label="Sig Min" size="small" type="number" value={factor.signal_range.min}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, min: Number(e.target.value) } })} />
                    <TextField label="Sig Max" size="small" type="number" value={factor.signal_range.max}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, max: Number(e.target.value) } })} />
                    <TextField label="Step" size="small" type="number" value={factor.signal_range.step}
                      onChange={e => updateFactor(i, { signal_range: { ...factor.signal_range, step: Number(e.target.value) } })} />
                  </Stack>
                </Stack>
              </Box>
            ))}

            <Button variant="outlined" size="small" onClick={addFactor}>+ Add Factor</Button>
          </>
        )}

        <Divider />

        <Button
          variant="contained"
          size="large"
          onClick={onRun}
          disabled={isRunning}
          startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          {isRunning ? 'Running…' : 'Run Optimization'}
        </Button>
      </Stack>
    </Drawer>
  );
}
