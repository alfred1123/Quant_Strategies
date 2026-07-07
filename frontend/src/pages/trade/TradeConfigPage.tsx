import { useState } from 'react';
import {
  Alert,
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
import { useTradeSession } from '../../trade/useTradeSession';
import { useExchangeApps } from '../../api/refdata';
import { useCreateCredential } from '../../api/credentials';

export default function TradeConfigPage() {
  const { accounts, accountsLoading, accountFilter, setAccountFilter } = useTradeSession();
  const { data: exchangeApps = [], isLoading: appsLoading } = useExchangeApps();
  const createCredential = useCreateCredential();

  const [appId, setAppId] = useState<number | ''>('');
  const [label, setLabel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [isPaper, setIsPaper] = useState(true);

  const canSubmit =
    appId !== '' && label.trim().length > 0 && apiKey.trim().length > 0 && apiSecret.trim().length > 0;

  const handleSave = () => {
    if (!canSubmit) return;
    createCredential.mutate(
      {
        app_id: appId as number,
        label: `${label.trim()}${isPaper ? ' (paper)' : ''}`,
        api_key: apiKey.trim(),
        api_secret: apiSecret.trim(),
      },
      {
        onSuccess: () => {
          setAppId('');
          setLabel('');
          setApiKey('');
          setApiSecret('');
          setIsPaper(true);
        },
      },
    );
  };

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

        {createCredential.isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {(createCredential.error as Error)?.message || 'Failed to save account'}
          </Alert>
        )}
        {createCredential.isSuccess && (
          <Alert severity="success" sx={{ mb: 2 }}>
            Account saved successfully.
          </Alert>
        )}

        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', maxWidth: 720 }}>
          <FormControl size="small" sx={{ width: 160 }} disabled={appsLoading}>
            <InputLabel id="add-broker">Exchange</InputLabel>
            <Select
              labelId="add-broker"
              label="Exchange"
              value={appId}
              onChange={e => setAppId(e.target.value as number)}
            >
              {appsLoading && (
                <MenuItem value="" disabled>
                  <CircularProgress size={16} sx={{ mr: 1 }} /> Loading…
                </MenuItem>
              )}
              {exchangeApps.map(app => (
                <MenuItem key={app.app_id} value={app.app_id}>
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
            value={label}
            onChange={e => setLabel(e.target.value)}
            sx={{ width: 160 }}
          />
          <FormControlLabel
            control={<Switch checked={isPaper} onChange={e => setIsPaper(e.target.checked)} />}
            label="Paper / testnet"
          />
        </Stack>
        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', maxWidth: 720, mt: 2 }}>
          <TextField
            size="small"
            label="API key"
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            sx={{ width: 220 }}
          />
          <TextField
            size="small"
            label="API secret"
            type="password"
            value={apiSecret}
            onChange={e => setApiSecret(e.target.value)}
            sx={{ width: 220 }}
          />
        </Stack>
        <Box sx={{ mt: 2 }}>
          <Button
            variant="contained"
            size="small"
            disabled={!canSubmit || createCredential.isPending}
            onClick={handleSave}
          >
            {createCredential.isPending ? 'Saving…' : 'Save account'}
          </Button>
        </Box>
      </Box>
    </Stack>
  );
}
