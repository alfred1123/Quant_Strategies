import {
  Alert,
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
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useCreateDeployment } from '../../api/trade';
import { useJob } from '../../api/jobs';
import { useBrokerAccounts } from '../../api/credentials';
import { useApps } from '../../api/refdata';

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
 */
export default function DeploymentDialog({
  open,
  onClose,
  selection,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  selection: DeploymentSelection | null;
  onSuccess?: () => void;
}) {
  const { data: accounts = [] } = useBrokerAccounts();
  const { data: apps = [] } = useApps();
  const create = useCreateDeployment();
  const job = useJob(open ? selection?.queueId : undefined);

  const [credId, setCredId] = useState<number | ''>('');
  const [cusip, setCusip] = useState('');
  const [qty, setQty] = useState('');
  const [mode, setMode] = useState<'paper' | 'live'>('paper');
  const [enabled, setEnabled] = useState(true);
  const [confirmLive, setConfirmLive] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const appNameById = useMemo(() => {
    const m = new Map<number, string>();
    for (const a of apps) m.set(a.app_id, a.display_name);
    return m;
  }, [apps]);

  // Reset every time the dialog opens for a (possibly new) selection.
  useEffect(() => {
    if (!open) return;
    setCredId('');
    setCusip('');
    setQty('');
    setMode('paper');
    setEnabled(true);
    setConfirmLive(false);
    setFormError(null);
    create.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selection?.strategyId, selection?.strategyVid]);

  // Pre-fill the trade product from the strategy's frozen config once loaded.
  const configSymbol = job.data?.config_json?.symbol;
  useEffect(() => {
    if (open && typeof configSymbol === 'string' && configSymbol) {
      setCusip((prev) => prev || configSymbol);
    }
  }, [open, configSymbol]);

  const selectedAccount = useMemo(
    () => accounts.find((a) => a.api_credential_id === credId) ?? null,
    [accounts, credId],
  );

  const isLive = mode === 'live';
  const qtyNum = Number(qty);
  const qtyValid = Number.isFinite(qtyNum) && qtyNum > 0;
  const canApply =
    Boolean(selection) &&
    Boolean(selectedAccount) &&
    qtyValid &&
    cusip.trim().length > 0 &&
    (!isLive || confirmLive) &&
    !create.isPending;

  const strategyLabel = selection
    ? `${selection.strategyNm ?? selection.strategyId.slice(0, 8)} · v${selection.strategyVid}`
    : '';

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
      setFormError('Product (internal cusip) is required.');
      return;
    }
    if (isLive && !confirmLive) {
      setFormError('Confirm live trading to apply a live deployment.');
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
      });
      onSuccess?.();
      onClose();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Failed to apply deployment');
    }
  };

  return (
    <Dialog
      open={open}
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

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Product (internal cusip)"
              size="small"
              value={cusip}
              onChange={(e) => setCusip(e.target.value)}
              helperText={job.isLoading ? 'Loading strategy config…' : 'Trade product to execute'}
              sx={{ flex: 1 }}
            />
            <TextField
              label="Quantity"
              size="small"
              type="number"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              error={qty.length > 0 && !qtyValid}
              helperText={qty.length > 0 && !qtyValid ? 'Must be greater than 0' : 'Order size per signal'}
              slotProps={{ htmlInput: { min: 0, step: 'any' } }}
              sx={{ width: { xs: '100%', sm: 160 } }}
            />
          </Stack>

          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={mode}
              onChange={(_, v) => {
                if (v) {
                  setMode(v);
                  setConfirmLive(false);
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

          {formError && <Alert severity="error">{formError}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={create.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color={isLive ? 'warning' : 'primary'}
          onClick={handleApply}
          disabled={!canApply}
        >
          {create.isPending ? 'Applying…' : `Apply ${isLive ? 'live' : 'paper'}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
