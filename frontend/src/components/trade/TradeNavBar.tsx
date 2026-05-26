import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useTradeSession } from '../../trade/TradeSessionContext';
import { ALL_ACCOUNTS, ALL_BROKERS } from '../../types/credentials';

const compactSelect = { minWidth: 0, width: 160 };

/** Top bar: exchange + account filters and paper/live mode (Phase 1.4 / 1.5). */
export default function TradeNavBar() {
  const {
    brokerFilter,
    accountFilter,
    tradingMode,
    brokerOptions,
    accountOptions,
    accountsLoading,
    setBrokerFilter,
    setAccountFilter,
    setTradingMode,
  } = useTradeSession();

  return (
    <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
      <Typography variant="body2" color="text.secondary" sx={{ mr: 0.5 }}>
        Filter:
      </Typography>

      <FormControl size="small" sx={compactSelect} disabled={accountsLoading}>
        <InputLabel id="trade-broker-filter">Exchange</InputLabel>
        <Select
          labelId="trade-broker-filter"
          label="Exchange"
          value={brokerFilter}
          onChange={e => setBrokerFilter(e.target.value)}
        >
          <MenuItem value={ALL_BROKERS}>All exchanges</MenuItem>
          {brokerOptions.map(o => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
          {brokerOptions.length === 0 && (
            <MenuItem value={ALL_BROKERS} disabled>
              (register in Config)
            </MenuItem>
          )}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ ...compactSelect, width: 200 }} disabled={accountsLoading}>
        <InputLabel id="trade-account-filter">Account</InputLabel>
        <Select
          labelId="trade-account-filter"
          label="Account"
          value={accountFilter === ALL_ACCOUNTS ? ALL_ACCOUNTS : accountFilter}
          onChange={e => {
            const v = e.target.value;
            setAccountFilter(v === ALL_ACCOUNTS ? ALL_ACCOUNTS : Number(v));
          }}
        >
          <MenuItem value={ALL_ACCOUNTS}>All accounts</MenuItem>
          {accountOptions.map(o => (
            <MenuItem key={o.value} value={o.value}>
              {o.broker_name} · {o.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <ToggleButtonGroup
        size="small"
        exclusive
        value={tradingMode}
        onChange={(_, v: 'paper' | 'live' | null) => {
          if (v) setTradingMode(v);
        }}
        aria-label="Trading mode"
      >
        <ToggleButton value="paper" aria-label="Paper trading">
          Paper
        </ToggleButton>
        <ToggleButton value="live" aria-label="Live trading">
          Live
        </ToggleButton>
      </ToggleButtonGroup>
    </Stack>
  );
}
