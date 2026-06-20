import {
  Alert,
  Box,
  Button,
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
import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useDeployments } from '../../api/trade';
import { useTradeSession, useTradeSessionFilters } from '../../trade/TradeSessionContext';
import { ALL_ACCOUNTS } from '../../types/credentials';
import type { TradeApplyLocationState } from '../../types/strategies';
import DeploymentDialog, { type DeploymentSelection } from '../../components/trade/DeploymentDialog';
import StrategyPicker, { type StrategyPickerSelection } from '../../components/trade/StrategyPicker';

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
 * Trade Apply — strategy picker (1.6) + deployments table.
 *
 * Pick a catalog row, then **Deploy** to open the deployment form. Promotion
 * tab can pre-select via react-router location state.
 */
export default function TradeApplyPage() {
  const location = useLocation();
  const routeState = (location.state ?? null) as TradeApplyLocationState | null;

  const { data: deployments, isLoading, isError, error } = useDeployments();
  const { accounts, tradingMode, accountFilter, brokerFilter, appNameById } = useTradeSession();
  const { matchesSession, credentialsNotLoaded } = useTradeSessionFilters();

  const [pickerSelection, setPickerSelection] = useState<StrategyPickerSelection | null>(null);
  const [deployOpen, setDeployOpen] = useState(false);

  // Pre-select from Promotion → Trade navigation (optional location state).
  useEffect(() => {
    if (!routeState?.strategyId || routeState.strategyVid == null) return;
    setPickerSelection({
      strategyId: routeState.strategyId,
      strategyVid: routeState.strategyVid,
      strategyNm: routeState.strategyNm ?? null,
    });
  }, [routeState?.strategyId, routeState?.strategyVid, routeState?.strategyNm]);

  const deploySelection: DeploymentSelection | null = useMemo(() => {
    if (!pickerSelection) return null;
    return {
      strategyId: pickerSelection.strategyId,
      strategyVid: pickerSelection.strategyVid,
      strategyNm: pickerSelection.strategyNm,
      queueId: routeState?.queueId,
    };
  }, [pickerSelection, routeState?.queueId]);

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

      <Paper variant="outlined" sx={{ p: 2 }}>
        <StrategyPicker selected={pickerSelection} onSelect={setPickerSelection} />
        <Stack direction="row" spacing={1.5} sx={{ mt: 2, alignItems: 'center' }}>
          <Button
            variant="contained"
            disabled={!pickerSelection}
            onClick={() => setDeployOpen(true)}
          >
            Deploy selected
          </Button>
          {pickerSelection && (
            <Typography variant="body2" color="text.secondary">
              {pickerSelection.strategyNm ?? pickerSelection.strategyId.slice(0, 8)}
              {' · '}
              v{pickerSelection.strategyVid}
            </Typography>
          )}
        </Stack>
      </Paper>

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
                        No deployments yet. Select a strategy above and click Deploy, or use
                        Promotion → Deploy.
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

      <DeploymentDialog
        open={deployOpen}
        selection={deploySelection}
        onClose={() => setDeployOpen(false)}
        onSuccess={() => setDeployOpen(false)}
      />
    </Stack>
  );
}
