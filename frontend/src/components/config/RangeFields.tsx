import { Stack, TextField } from '@mui/material';
import type { RangeParam } from '../../types/backtest';

interface Props {
  label: 'Win' | 'Sig';
  value: RangeParam;
  onChange: (patch: Partial<RangeParam>) => void;
  /** When true, Min and Max are disabled (used for bounded indicators). */
  disabledMinMax?: boolean;
  fieldWidth?: number;
}

/**
 * Three numeric inputs (Min / Max / Step) for a RangeParam. Reused for
 * both Window range and Signal range inside a factor card. Bounded
 * indicators (e.g. RSI) lock Min / Max so only Step is editable.
 */
export default function RangeFields({
  label, value, onChange, disabledMinMax = false, fieldWidth = 80,
}: Props) {
  const set = (patch: Partial<RangeParam>) => onChange(patch);

  return (
    <Stack direction="row" spacing={1}>
      <TextField
        label={`${label} Min`} size="small" type="number" sx={{ width: fieldWidth }}
        value={value.min}
        disabled={disabledMinMax}
        slotProps={{ inputLabel: { shrink: true } }}
        onChange={e => set({ min: Number(e.target.value) })}
      />
      <TextField
        label={`${label} Max`} size="small" type="number" sx={{ width: fieldWidth }}
        value={value.max}
        disabled={disabledMinMax}
        slotProps={{ inputLabel: { shrink: true } }}
        onChange={e => set({ max: Number(e.target.value) })}
      />
      <TextField
        label={`${label} Step`} size="small" type="number" sx={{ width: fieldWidth }}
        value={value.step}
        slotProps={{ inputLabel: { shrink: true } }}
        onChange={e => set({ step: Number(e.target.value) })}
      />
    </Stack>
  );
}
