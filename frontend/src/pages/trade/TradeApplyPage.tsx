import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import PauseCircleIcon from '@mui/icons-material/PauseCircle';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PlayCircleIcon from '@mui/icons-material/PlayCircle';
import ScienceIcon from '@mui/icons-material/Science';
import StopCircleIcon from '@mui/icons-material/StopCircle';
import { useMemo, useState } from 'react';
import { useLocation } from 'react-router';
import { useDeployments, useDryRun, useStopDeployment, useUpdateDeployment } from '../../api/trade';
import { useTradeSession, useTradeSessionFilters } from '../../trade/useTradeSession';
import { ALL_ACCOUNTS } from '../../types/credentials';
import type { DeploymentRow, DryRunReport } from '../../types/trade';
import type { TradeApplyLocationState } from '../../types/strategies';
import AccountSnapshotPanel from '../../components/trade/AccountSnapshotPanel';
import ApplyConfirmDialog from '../../components/trade/ApplyConfirmDialog';
import DeploymentDialog, { type DeploymentSelection } from '../../components/trade/DeploymentDialog';
import DryRunReportDialog from '../../components/trade/DryRunReportDialog';
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
  const {
    accounts,
    tradingMode,
    accountFilter,
    brokerFilter,
    appNameById,
    setAccountFilter,
  } = useTradeSession();
  const { matchesSession, credentialsNotLoaded } = useTradeSessionFilters();

  const dryRun = useDryRun();
  const updateDep = useUpdateDeployment();
  const stopDep = useStopDeployment();

  const [pickerSelection, setPickerSelection] = useState<StrategyPickerSelection | null>(null);
  const [deployOpen, setDeployOpen] = useState(false);
  const [dryRunReport, setDryRunReport] = useState<DryRunReport | null>(null);
  const [applyTarget, setApplyTarget] = useState<DeploymentRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Pre-select from Promotion → Trade navigation (optional location state).
  // Render-phase adjustment keyed on the routed strategy — applies once per
  // navigation without an effect (see React docs: "adjusting state when
  // props change").
  const routeKey =
    routeState?.strategyId && routeState.strategyVid != null
      ? `${routeState.strategyId}|${routeState.strategyVid}`
      : null;
  const [appliedRouteKey, setAppliedRouteKey] = useState<string | null>(null);
  if (routeKey !== null && routeKey !== appliedRouteKey) {
    setAppliedRouteKey(routeKey);
    setPickerSelection({
      strategyId: routeState!.strategyId!,
      strategyVid: routeState!.strategyVid!,
      strategyNm: routeState!.strategyNm ?? null,
    });
  }

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
    () => (deployments ?? [])
      .filter((row) => row.deployment_status !== 'STOPPED')
      .filter(matchesSession),
    [deployments, matchesSession],
  );

  const handleDryRun = async (row: DeploymentRow) => {
    setActionError(null);
    try {
      const report = await dryRun.mutateAsync({
        strategy_id: row.strategy_id,
        strategy_vid: row.strategy_vid,
        api_credential_id: row.api_credential_id,
        app_id: row.app_id,
        internal_cusip: row.internal_cusip,
        qty: row.qty,
        paper: row.is_paper_ind === 'Y',
      });
      setDryRunReport(report);
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Dry-run failed');
    }
  };

  const handleToggleEnabled = async (row: DeploymentRow) => {
    setActionError(null);
    const enabling = row.is_enabled_ind !== 'Y';
    try {
      await updateDep.mutateAsync({
        deploymentId: row.deployment_id,
        enabled: enabling,
      });
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Update failed');
    }
  };

  const handleStopDeployment = async (row: DeploymentRow) => {
    if (!window.confirm('Stop this deployment? It will be disabled and hidden from the list.')) {
      return;
    }
    setActionError(null);
    try {
      await stopDep.mutateAsync(row.deployment_id);
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Stop failed');
    }
  };

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

      <AccountSnapshotPanel
        apiCredentialId={accountFilter === ALL_ACCOUNTS ? null : accountFilter}
        tradingMode={tradingMode}
        accounts={accounts}
        appNameById={appNameById}
        onSelectAccount={setAccountFilter}
      />

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
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8}>
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
                  const enabled = row.is_enabled_ind === 'Y';
                  return (
                    <TableRow key={`${row.deployment_id}-${row.deployment_vid}`}>
                      <TableCell>{exchange}</TableCell>
                      <TableCell>{account}</TableCell>
                      <TableCell>{row.internal_cusip}</TableCell>
                      <TableCell>
                        {row.strategy_id.slice(0, 8)}… v{row.strategy_vid}
                      </TableCell>
                      <TableCell>{row.is_paper_ind === 'Y' ? 'Paper' : 'Live'}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={row.deployment_status}
                          color={enabled ? 'success' : 'default'}
                          variant={enabled ? 'filled' : 'outlined'}
                        />
                      </TableCell>
                      <TableCell align="right">{row.qty}</TableCell>
                      <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>
                        <Tooltip title="Dry run">
                          <IconButton
                            size="small"
                            onClick={() => handleDryRun(row)}
                            disabled={dryRun.isPending}
                          >
                            <ScienceIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title={enabled ? 'Apply signal' : 'Enable first'}>
                          <span>
                            <IconButton
                              size="small"
                              color="primary"
                              disabled={!enabled}
                              onClick={() => setApplyTarget(row)}
                            >
                              <PlayArrowIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title={enabled ? 'Disable (kill switch)' : 'Enable'}>
                          <IconButton
                            size="small"
                            color={enabled ? 'warning' : 'success'}
                            onClick={() => handleToggleEnabled(row)}
                            disabled={updateDep.isPending}
                          >
                            {enabled
                              ? <PauseCircleIcon fontSize="small" />
                              : <PlayCircleIcon fontSize="small" />}
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Stop deployment">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => handleStopDeployment(row)}
                            disabled={stopDep.isPending}
                          >
                            <StopCircleIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>

      {actionError && (
        <Alert severity="error" onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}

      <DeploymentDialog
        open={deployOpen}
        selection={deploySelection}
        onClose={() => setDeployOpen(false)}
        onSuccess={() => setDeployOpen(false)}
      />

      <DryRunReportDialog
        report={dryRunReport}
        onClose={() => setDryRunReport(null)}
      />

      <ApplyConfirmDialog
        deployment={applyTarget}
        onClose={() => setApplyTarget(null)}
      />
    </Stack>
  );
}
