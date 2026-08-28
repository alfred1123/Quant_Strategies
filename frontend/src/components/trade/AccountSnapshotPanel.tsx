import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useAccountSnapshot } from '../../api/trade';
import type { BrokerAccount, TradingMode } from '../../types/credentials';
import type { PositionRow } from '../../types/trade';

interface AccountSnapshotPanelProps {
  /** Credential to read, or null when the toolbar is on "all accounts". */
  apiCredentialId: number | null;
  tradingMode: TradingMode;
  accounts: BrokerAccount[];
  appNameById: Map<number, string>;
  /** Called when the user picks an account from the fallback selector. */
  onSelectAccount?: (id: number) => void;
}

/** Fixed decimals would show 0.00 for a 0.003 BTC position. */
function num(value: number | null, maxDigits = 8): string {
  if (value === null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: maxDigits });
}

function money(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function sideLabel(row: PositionRow): { label: string; color: 'success' | 'error' } {
  const short = row.qty < 0 || row.side === 'short';
  return { label: short ? 'Short' : 'Long', color: short ? 'error' : 'success' };
}

/**
 * Live broker account state — cash and open positions, read from the exchange.
 *
 * Shows what the account *actually* holds rather than what our tables believe,
 * so a position opened by hand or left behind by a stopped deployment is
 * visible. Read-only: this panel places no orders.
 */
export default function AccountSnapshotPanel({
  apiCredentialId,
  tradingMode,
  accounts,
  appNameById,
  onSelectAccount,
}: AccountSnapshotPanelProps) {
  const paper = tradingMode === 'paper';
  const { data, isLoading, isError, error, isFetching, refetch } = useAccountSnapshot(
    apiCredentialId,
    paper,
  );

  const account = accounts.find(a => a.api_credential_id === apiCredentialId);
  const exchange = account
    ? appNameById.get(account.app_id) ?? `App ${account.app_id}`
    : null;

  return (
    <Box>
      <Stack
        direction="row"
        spacing={1}
        sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography variant="subtitle2">Account</Typography>
          <Chip
            size="small"
            label={paper ? 'Paper' : 'Live'}
            color={paper ? 'default' : 'warning'}
            variant="outlined"
          />
          {account && (
            <Typography variant="caption" color="text.secondary">
              {exchange} · {account.label}
            </Typography>
          )}
        </Stack>
        {apiCredentialId !== null && (
          <Tooltip title="Refresh from exchange">
            <span>
              <IconButton size="small" onClick={() => refetch()} disabled={isFetching}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Stack>

      {apiCredentialId === null && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Typography variant="body2" color="text.secondary">
              Pick one account to read its live balances and positions — a snapshot is a
              call to a single exchange account.
            </Typography>
            {accounts.length > 0 && onSelectAccount && (
              <TextField
                select
                size="small"
                label="Account"
                value=""
                onChange={e => onSelectAccount(Number(e.target.value))}
                sx={{ maxWidth: 320 }}
              >
                {accounts.map(a => (
                  <MenuItem key={a.api_credential_id} value={a.api_credential_id}>
                    {appNameById.get(a.app_id) ?? `App ${a.app_id}`} · {a.label}
                  </MenuItem>
                ))}
              </TextField>
            )}
          </Stack>
        </Paper>
      )}

      {apiCredentialId !== null && isLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
          <CircularProgress size={28} />
        </Box>
      )}

      {apiCredentialId !== null && isError && (
        <Alert severity="error" action={<IconButton size="small" onClick={() => refetch()}><RefreshIcon fontSize="small" /></IconButton>}>
          {error instanceof Error ? error.message : 'Could not read the account'}
        </Alert>
      )}

      {data && (
        <Stack spacing={2}>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Currency</TableCell>
                  <TableCell align="right">Available</TableCell>
                  <TableCell align="right">In use</TableCell>
                  <TableCell align="right">Total</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.balances.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" color="text.secondary">
                        No cash on this account.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {data.balances.map(b => (
                  <TableRow key={b.code}>
                    <TableCell>{b.code}</TableCell>
                    <TableCell align="right">{money(b.free)}</TableCell>
                    <TableCell align="right">{money(b.used)}</TableCell>
                    <TableCell align="right">{money(b.total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Side</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Entry</TableCell>
                  <TableCell align="right">Mark</TableCell>
                  <TableCell align="right">Unrealised P&amp;L</TableCell>
                  <TableCell align="right">Leverage</TableCell>
                  <TableCell align="right">Liquidation</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.positions.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography variant="body2" color="text.secondary">
                        Flat — no open positions on this account.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {data.positions.map(p => {
                  const side = sideLabel(p);
                  const pnl = p.unrealized_pnl;
                  return (
                    <TableRow key={p.symbol}>
                      <TableCell>{p.symbol}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={side.label}
                          color={side.color}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell align="right">{num(Math.abs(p.qty))}</TableCell>
                      <TableCell align="right">{money(p.entry_price)}</TableCell>
                      <TableCell align="right">{money(p.mark_price)}</TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          color:
                            pnl === null || pnl === 0
                              ? 'text.primary'
                              : pnl > 0
                                ? 'success.main'
                                : 'error.main',
                        }}
                      >
                        {money(pnl)}
                      </TableCell>
                      <TableCell align="right">
                        {p.leverage === null ? '—' : `${num(p.leverage, 2)}×`}
                      </TableCell>
                      <TableCell align="right">{money(p.liquidation_price)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="caption" color="text.secondary">
            Read live from the exchange, including positions not opened by a deployment.
            Not auto-refreshed — every read is a rate-limited API call.
          </Typography>
        </Stack>
      )}
    </Box>
  );
}
