import {
  Alert,
  Box,
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
  accounts: { api_credential_id: number; app_id: number; label: string }[],
  appNameById: Map<number, string>,
): { exchange: string; account: string } {
  const acct = accounts.find(a => a.api_credential_id === apiCredentialId);
  if (acct) {
    return { exchange: appNameById.get(acct.app_id) ?? `App ${acct.app_id}`, account: acct.label };
  }
  return { exchange: appNameById.get(appId) ?? `App ${appId}`, account: `#${apiCredentialId}` };
}

/**
 * Trade deployments list, filtered by the session toolbar.
 *
 * Strategies are applied via the Deploy popup on the Promotion tab
 * (``DeploymentDialog``); this page shows the resulting deployments.
 */
export default function TradeApplyPage() {
  const { data: deployments, isLoading, isError, error } = useDeployments();
  const { accounts, tradingMode, accountFilter, brokerFilter, appNameById } = useTradeSession();
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

      <Alert severity="info">
        Apply a strategy from the <strong>Promotion</strong> tab — click <strong>Deploy</strong>{' '}
        on a strategy to open the deployment form. New deployments appear below.
      </Alert>

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
            No broker accounts loaded — exchange filter may hide valid deployments. Register
            accounts in Config first.
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
                        No deployments match the current filter. Register accounts in Config,
                        then Deploy a strategy from the Promotion tab.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {filtered.map(row => {
                  const { exchange, account } = accountLabel(
                    row.api_credential_id,
                    row.app_id,
                    accounts,
                    appNameById,
                  );
                  return (
                    <TableRow key={`${row.deployment_id}-${row.deployment_vid}`}>
                      <TableCell>{exchange}</TableCell>
                      <TableCell>{account}</TableCell>
                      <TableCell>{row.internal_cusip}</TableCell>
                      <TableCell>
                        {row.strategy_id.slice(0, 8)}… v{row.strategy_vid}
                      </TableCell>
                      <TableCell>{row.is_paper_ind === 'Y' ? 'Paper' : 'Live'}</TableCell>
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
