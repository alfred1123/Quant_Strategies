import { useState } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import BrokerAccountsTable from '../../components/trade/BrokerAccountsTable';
import { useTradeSession } from '../../trade/TradeSessionContext';
import { useExchangeApps } from '../../api/refdata';

/** Phase 1.4 / 1.5 — multi-broker account registry + compact add form. */
export default function TradeConfigPage() {
  const { accounts, accountsLoading, accountFilter, setAccountFilter } = useTradeSession();
  const { data: exchangeApps = [], isLoading: appsLoading } = useExchangeApps();
  const [selectedExchange, setSelectedExchange] = useState<string>('');

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h5" component="h1" gutterBottom>
          Exchange accounts
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Register multiple accounts per broker. The top bar filters Trade and deployments by
          exchange, account, and paper/live mode.
        </Typography>
      </Box>

      <BrokerAccountsTable
        accounts={accounts}
        loading={accountsLoading}
        selectedCredentialId={accountFilter}
        onSelectAccount={id => setAccountFilter(id)}
        showActions
      />

      <Box>
        <Typography variant="subtitle1" gutterBottom>
          Add account
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Saves to <code>/api/v1/credentials</code> (Phase 1.5).
        </Typography>

        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', maxWidth: 720 }}>
          <FormControl size="small" sx={{ width: 160 }} disabled={appsLoading}>
            <InputLabel id="add-broker">Exchange</InputLabel>
            <Select
              labelId="add-broker"
              label="Exchange"
              value={selectedExchange}
              onChange={e => setSelectedExchange(e.target.value)}
            >
              {appsLoading && (
                <MenuItem value="" disabled>
                  <CircularProgress size={16} sx={{ mr: 1 }} /> Loading…
                </MenuItem>
              )}
              {exchangeApps.map(app => (
                <MenuItem key={app.app_id} value={app.name}>
                  {app.display_name}
                </MenuItem>
              ))}
              {!appsLoading && exchangeApps.length === 0 && (
                <MenuItem value="" disabled>No exchanges configured</MenuItem>
              )}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Account label"
            placeholder="Main"
            disabled
            sx={{ width: 160 }}
          />
          <FormControlLabel
            control={<Switch disabled defaultChecked />}
            label="Paper / testnet"
          />
        </Stack>
        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', maxWidth: 720, mt: 2 }}>
          <TextField
            size="small"
            label="API key"
            type="password"
            placeholder="••••••••"
            disabled
            sx={{ width: 220 }}
          />
          <TextField
            size="small"
            label="API secret"
            type="password"
            placeholder="••••••••"
            disabled
            sx={{ width: 220 }}
          />
        </Stack>
        <Box sx={{ mt: 2 }}>
          <Button variant="contained" size="small" disabled>
            Save account
          </Button>
        </Box>
      </Box>
    </Stack>
  );
}
