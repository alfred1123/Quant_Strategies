import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useMemo } from 'react';
import { useDeployments } from '../../api/trade';
import { useTradeSession, useTradeSessionFilters } from '../../trade/TradeSessionContext';
import { ALL_ACCOUNTS } from '../../types/credentials';

function accountLabel(
  apiCredentialId: number,
  appId: number,
  accounts: { api_credential_id: number; broker_name: string; label: string; app_id: number }[],
): { exchange: string; account: string } {
  const acct = accounts.find(a => a.api_credential_id === apiCredentialId);
  if (acct) {
    return { exchange: acct.broker_name, account: acct.label };
  }
  return { exchange: `app ${appId}`, account: `#${apiCredentialId}` };
}

/** Phase 1.4 shell + 1.2 deployments filtered by exchange / account / paper-live. */
export default function TradeApplyPage() {
  const { data: deployments, isLoading, isError, error } = useDeployments();
  const { accounts, tradingMode, accountFilter, brokerFilter } = useTradeSession();
  const { matchesSession, credentialsNotLoaded } = useTradeSessionFilters();

  const filtered = useMemo(
    () => (deployments ?? []).filter(matchesSession),
    [deployments, matchesSession],
  );

  const filterHint =
    accountFilter !== ALL_ACCOUNTS || brokerFilter !== 'all'
      ? 'Filtered by toolbar — change Exchange / Account / Paper|Live above.'
      : `Showing ${tradingMode} deployments — toggle Paper / Live in the toolbar.`;

  return (
    <Stack spacing={3}>
      <Typography variant="h5" component="h1">
        Trade
      </Typography>

      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Strategy picker (Phase 1.6)
        </Typography>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="body2" color="text.disabled">
            ○ bollinger_momentum_20_1.0
          </Typography>
          <Typography variant="body2" color="text.disabled">
            ○ rsi_reversion_14_30
          </Typography>
        </Paper>
      </Box>

      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
        <Button variant="outlined" size="small" disabled>
          Dry run
        </Button>
        <Button variant="contained" size="small" disabled>
          Apply {tradingMode === 'paper' ? 'paper' : 'live'}
        </Button>
        <Chip
          size="small"
          label={tradingMode === 'paper' ? 'Paper mode' : 'Live mode'}
          color={tradingMode === 'live' ? 'warning' : 'default'}
          variant="outlined"
        />
      </Stack>

      <Box>
        <Stack
          direction="row"
          sx={{ justifyContent: 'space-between', alignItems: 'baseline', mb: 1 }}
        >
          <Typography variant="subtitle2">Deployments</Typography>
          <Typography variant="caption" color="text.secondary">
            {filterHint}
          </Typography>
        </Stack>
        {credentialsNotLoaded && brokerFilter !== 'all' && (
          <Alert severity="warning" sx={{ mb: 1 }}>
            No broker accounts loaded — exchange filter may hide valid deployments.
            Register accounts in Config first.
          </Alert>
        )}
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
            <CircularProgress size={28} />
          </Box>
        )}
        {isError && (
          <Alert severity="error">
            {error instanceof Error ? error.message : 'Failed to load deployments'}
          </Alert>
        )}
        {!isLoading && !isError && (
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Exchange</TableCell>
                  <TableCell>Account</TableCell>
                  <TableCell>Product</TableCell>
                  <TableCell>Strategy</TableCell>
                  <TableCell>Mode</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Qty</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Typography variant="body2" color="text.secondary">
                        No deployments match the current filter. Register accounts in Config
                        (Phase 1.5) or apply a strategy (Phase 1.7).
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {filtered.map(row => {
                  const { exchange, account } = accountLabel(
                    row.api_credential_id,
                    row.app_id,
                    accounts,
                  );
                  return (
                    <TableRow key={`${row.deployment_id}-${row.deployment_vid}`}>
                      <TableCell>{exchange}</TableCell>
                      <TableCell>{account}</TableCell>
                      <TableCell>{row.internal_cusip}</TableCell>
                      <TableCell>
                        {row.strategy_id.slice(0, 8)}… v{row.strategy_vid}
                      </TableCell>
                      <TableCell>
                        {row.is_paper_ind === 'Y' ? 'Paper' : 'Live'}
                      </TableCell>
                      <TableCell>{row.deployment_status}</TableCell>
                      <TableCell align="right">{row.qty}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>
    </Stack>
  );
}
