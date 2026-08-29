import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { useCreateDeployment, useDryRun, useScheduleOptions } from '../../api/trade';
import { useJob } from '../../api/jobs';
import { useBrokerAccounts } from '../../api/credentials';
import { useProductXrefs, useProducts } from '../../api/inst';
import { intervalLabel, useApps, useTmIntervals } from '../../api/refdata';
import type { ProductRow } from '../../types/refdata';
import DryRunReportDialog from './DryRunReportDialog';
import type { DryRunReport } from '../../types/trade';

/** Sentinel for the manual option — `SCHEDULE_TM_INTERVAL_ID` is null on the wire. */
const MANUAL_SCHEDULE = 'MANUAL';

/** Strategy + version handed in by the caller (Promotion tab Deploy). */
export interface DeploymentSelection {
  strategyId: string;
  strategyVid: number;
  strategyNm?: string | null;
  /** Completed backtest job — used to pre-fill the trade product. */
  queueId?: string;
}

/**
 * Popup form to apply a promoted strategy to a broker account.
 *
 * Self-contained: fetches accounts / apps directly (no TradeSessionProvider
 * dependency) so it can launch from the Promotion tab. Live deployments
 * require an explicit confirmation — the backend rejects ``paper=false``
 * without ``confirm_live=true``.
 *
 * The content component mounts fresh on every open, so all form state
 * starts from its initial values — no reset effects needed.
 */
export default function DeploymentDialog(props: DeploymentDialogProps) {
  if (!props.open) return null;
  return <DeploymentDialogContent {...props} />;
}

interface DeploymentDialogProps {
  open: boolean;
  onClose: () => void;
  selection: DeploymentSelection | null;
  onSuccess?: () => void;
}

function DeploymentDialogContent({
  onClose,
  selection,
  onSuccess,
}: DeploymentDialogProps) {
  const { data: accounts = [] } = useBrokerAccounts();
  const { data: apps = [] } = useApps();
  const { data: intervals = [] } = useTmIntervals();
  const { data: scheduleOptions } = useScheduleOptions();
  const { data: products = [] } = useProducts();
  const create = useCreateDeployment();
  const dryRun = useDryRun();
  const job = useJob(selection?.queueId);

  const [credId, setCredId] = useState<number | ''>('');
  const [selectedProduct, setSelectedProduct] = useState<ProductRow | null>(null);
  const [cusipOverride, setCusipOverride] = useState<string | null>(null);
  const [qty, setQty] = useState('');
  const [mode, setMode] = useState<'paper' | 'live'>('paper');
  const [enabled, setEnabled] = useState(true);
  const [confirmLive, setConfirmLive] = useState(false);
  // Manual is a real selection rather than an empty one, so the closed Select
  // reads "Manual only" instead of blank. Deploying is not the same as opting
  // into automated trading, so a cadence is always an explicit choice.
  const [scheduleValue, setScheduleValue] = useState<string>(MANUAL_SCHEDULE);
  const [confirmSchedule, setConfirmSchedule] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [previewReport, setPreviewReport] = useState<DryRunReport | null>(null);

  const configSymbol = job.data?.config_json?.symbol;
  const cusip = cusipOverride ?? selectedProduct?.internal_cusip
    ?? (typeof configSymbol === 'string' ? configSymbol : '');

  const appNameById = useMemo(() => {
    const m = new Map<number, string>();
    for (const a of apps) m.set(a.app_id, a.display_name);
    return m;
  }, [apps]);

  const selectedAccount = useMemo(
    () => accounts.find((a) => a.api_credential_id === credId) ?? null,
    [accounts, credId],
  );

  const sortedIntervals = useMemo(
    () => [...intervals].sort((a, b) => a.tm_interval_id - b.tm_interval_id),
    [intervals],
  );

  // The schedule sets the bars the live signal is computed from, so a cadence
  // the strategy was not fitted on would trade on statistics no backtest
  // produced. The API refuses those; offering them greyed out says why,
  // where hiding them would just look like a missing feature.
  const schedulableIds = scheduleOptions?.tm_interval_ids;
  const isSchedulable = (id: number) => !schedulableIds || schedulableIds.includes(id);
  const hasUnfittedCadence = sortedIntervals.some(
    (iv) => !isSchedulable(iv.tm_interval_id),
  );

  const { data: xrefs = [] } = useProductXrefs(selectedProduct?.product_id ?? null);
  const vendorSymbol = useMemo(() => {
    if (!selectedAccount) return '';
    return xrefs.find((x) => x.app_id === selectedAccount.app_id)?.vendor_symbol ?? '';
  }, [selectedAccount, xrefs]);

  const isLive = mode === 'live';
  const isScheduled = scheduleValue !== MANUAL_SCHEDULE;
  const needsScheduleConfirm = isLive && isScheduled;
  const qtyNum = Number(qty);
  const qtyValid = Number.isFinite(qtyNum) && qtyNum > 0;
  const canPreview = Boolean(selection) && Boolean(selectedAccount) && qtyValid && cusip.trim().length > 0;
  const canApply =
    canPreview &&
    (!isLive || confirmLive) &&
    (!needsScheduleConfirm || confirmSchedule) &&
    !create.isPending;

  const strategyLabel = selection
    ? `${selection.strategyNm ?? selection.strategyId.slice(0, 8)} · v${selection.strategyVid}`
    : '';

  const handlePreview = async () => {
    setFormError(null);
    if (!selection || !selectedAccount) return;
    try {
      const report = await dryRun.mutateAsync({
        strategy_id: selection.strategyId,
        strategy_vid: selection.strategyVid,
        api_credential_id: selectedAccount.api_credential_id,
        app_id: selectedAccount.app_id,
        internal_cusip: cusip.trim(),
        qty,
        paper: !isLive,
      });
      setPreviewReport(report);
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Dry-run preview failed');
    }
  };

  const handleApply = async () => {
    setFormError(null);
    if (!selection) return;
    if (!selectedAccount) {
      setFormError('Select an account.');
      return;
    }
    if (!qtyValid) {
      setFormError('Quantity must be greater than 0.');
      return;
    }
    if (!cusip.trim()) {
      setFormError('Product is required.');
      return;
    }
    if (isLive && !confirmLive) {
      setFormError('Confirm live trading to apply a live deployment.');
      return;
    }
    if (needsScheduleConfirm && !confirmSchedule) {
      setFormError('Confirm automatic live trading, or set the schedule to manual.');
      return;
    }
    try {
      await create.mutateAsync({
        strategy_id: selection.strategyId,
        strategy_vid: selection.strategyVid,
        api_credential_id: selectedAccount.api_credential_id,
        app_id: selectedAccount.app_id,
        internal_cusip: cusip.trim(),
        qty,
        paper: !isLive,
        confirm_live: isLive && confirmLive,
        enabled,
        deployment_status: 'CREATED',
        schedule_tm_interval_id: isScheduled ? Number(scheduleValue) : null,
      });
      onSuccess?.();
      onClose();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Failed to apply deployment');
    }
  };

  const notionalHint = previewReport?.notional != null
    ? `Est. notional ≈ ${previewReport.notional.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
    : canPreview
      ? 'Use Preview dry-run to see estimated notional'
      : 'Order size per signal';

  return (
    <>
      <Dialog
        open
        onClose={create.isPending ? undefined : onClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Deploy strategy</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="body2" color="text.secondary">
                Strategy
              </Typography>
              <Chip size="small" color="primary" variant="outlined" label={strategyLabel} />
            </Stack>

            <FormControl size="small" fullWidth>
              <InputLabel id="deploy-account-label">Account</InputLabel>
              <Select
                labelId="deploy-account-label"
                label="Account"
                value={credId === '' ? '' : String(credId)}
                onChange={(e) =>
                  setCredId(e.target.value === '' ? '' : Number(e.target.value))
                }
              >
                {accounts.length === 0 && (
                  <MenuItem value="" disabled>
                    No accounts — register in Config first
                  </MenuItem>
                )}
                {accounts.map((a) => (
                  <MenuItem key={a.api_credential_id} value={String(a.api_credential_id)}>
                    {(appNameById.get(a.app_id) ?? `App ${a.app_id}`)} — {a.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Autocomplete<ProductRow, false, false, true>
              size="small"
              freeSolo
              options={products}
              value={selectedProduct}
              inputValue={
                selectedProduct
                  ? `${selectedProduct.display_nm} (${selectedProduct.internal_cusip})`
                  : cusipOverride ?? cusip
              }
              getOptionLabel={(opt) =>
                typeof opt === 'string' ? opt : `${opt.display_nm} (${opt.internal_cusip})`
              }
              isOptionEqualToValue={(opt, val) => {
                if (typeof opt === 'string' || typeof val === 'string') return opt === val;
                return opt.internal_cusip === val.internal_cusip;
              }}
              onChange={(_, val) => {
                setCusipOverride(null);
                if (!val) {
                  setSelectedProduct(null);
                } else if (typeof val === 'string') {
                  setSelectedProduct(null);
                  setCusipOverride(val);
                } else {
                  setSelectedProduct(val);
                }
              }}
              onInputChange={(_, val, reason) => {
                if (reason === 'input') {
                  setSelectedProduct(null);
                  setCusipOverride(val);
                }
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Product"
                  helperText={
                    job.isLoading
                      ? 'Loading strategy config…'
                      : vendorSymbol
                        ? `Vendor symbol: ${vendorSymbol}`
                        : selectedAccount && selectedProduct
                          ? 'No xref for this exchange — check INST.PRODUCT_XREF'
                          : 'Pick from catalog or type internal cusip'
                  }
                />
              )}
              renderOption={(props, opt) => (
                <li {...props} key={opt.internal_cusip}>
                  <Box>
                    <Typography variant="body2">{opt.display_nm}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {opt.internal_cusip}
                    </Typography>
                  </Box>
                </li>
              )}
            />

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Quantity"
                size="small"
                type="number"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                error={qty.length > 0 && !qtyValid}
                helperText={notionalHint}
                slotProps={{ htmlInput: { min: 0, step: 'any' } }}
                sx={{ width: { xs: '100%', sm: '100%' } }}
              />
            </Stack>

            <FormControl size="small" fullWidth>
              <InputLabel id="deploy-schedule-label">Schedule</InputLabel>
              <Select
                labelId="deploy-schedule-label"
                label="Schedule"
                value={scheduleValue}
                onChange={(e) => {
                  setScheduleValue(e.target.value);
                  setConfirmSchedule(false);
                }}
              >
                <MenuItem value={MANUAL_SCHEDULE}>Manual only</MenuItem>
                {sortedIntervals.map((iv) => (
                  <MenuItem
                    key={iv.tm_interval_id}
                    value={String(iv.tm_interval_id)}
                    disabled={!isSchedulable(iv.tm_interval_id)}
                  >
                    {intervalLabel(iv)}
                  </MenuItem>
                ))}
              </Select>
              <FormHelperText>
                {isScheduled
                  ? 'Applies automatically on each closed bar, and keeps this product’s price data up to date.'
                  : 'Apply button only — no automatic trading, and no scheduled price data.'}
                {hasUnfittedCadence &&
                  ' Cadences the strategy was not fitted on are disabled — the schedule decides which bars the signal is computed from.'}
              </FormHelperText>
            </FormControl>

            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <ToggleButtonGroup
                size="small"
                exclusive
                value={mode}
                onChange={(_, v) => {
                  if (v) {
                    setMode(v);
                    setConfirmLive(false);
                    setConfirmSchedule(false);
                  }
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
              <Box sx={{ flexGrow: 1 }} />
              <FormControlLabel
                control={<Checkbox checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />}
                label="Enable immediately"
              />
            </Stack>

            {isLive && (
              <>
                <Alert severity="warning">
                  Live mode places real orders on the selected account. Switch to Paper to test first.
                </Alert>
                <FormControlLabel
                  control={
                    <Checkbox
                      color="warning"
                      checked={confirmLive}
                      onChange={(e) => setConfirmLive(e.target.checked)}
                    />
                  }
                  label="I confirm this is a LIVE deployment"
                />
              </>
            )}

            {needsScheduleConfirm && (
              <>
                <Alert severity="warning">
                  This deployment will trade real money unattended, without anyone
                  pressing Apply. Set the schedule to manual to decide each trade
                  yourself.
                </Alert>
                <FormControlLabel
                  control={
                    <Checkbox
                      color="warning"
                      checked={confirmSchedule}
                      onChange={(e) => setConfirmSchedule(e.target.checked)}
                    />
                  }
                  label="I confirm automatic live trading on this schedule"
                />
              </>
            )}

            {formError && <Alert severity="error">{formError}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button
            variant="outlined"
            onClick={handlePreview}
            disabled={!canPreview || dryRun.isPending}
          >
            {dryRun.isPending ? 'Previewing…' : 'Preview dry-run'}
          </Button>
          <Button
            variant="contained"
            color={isLive ? 'warning' : 'primary'}
            onClick={handleApply}
            disabled={!canApply}
          >
            {create.isPending ? 'Deploying…' : `Deploy ${isLive ? 'live' : 'paper'}`}
          </Button>
        </DialogActions>
      </Dialog>

      <DryRunReportDialog report={previewReport} onClose={() => setPreviewReport(null)} />
    </>
  );
}
