import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import PauseCircleIcon from '@mui/icons-material/PauseCircle';
import PlayCircleIcon from '@mui/icons-material/PlayCircle';
import SearchIcon from '@mui/icons-material/Search';
import { useDeferredValue, useMemo, useState } from 'react';
import { useMe } from '../api/auth';
import { useSubscribe, useSubscriptions } from '../api/marketData';
import { intervalLabel, useApps, useTmIntervals } from '../api/refdata';
import AppModeSwitch from '../components/AppModeSwitch';
import BrandMark from '../components/BrandMark';
import UserMenu from '../components/UserMenu';
import BackfillDialog from '../components/market-data/BackfillDialog';
import CreateInstrumentDialog from '../components/market-data/CreateInstrumentDialog';
import SubscriptionDialog from '../components/market-data/SubscriptionDialog';
import { APP_NAME } from '../constants/brand';
import type { BarSubscriptionRow, Coverage } from '../types/marketData';

function formatDay(value: string | null): string {
  return value ? value.slice(0, 10) : '—';
}

const MS_PER_DAY = 86_400_000;

/**
 * How far the capture still is from what was asked for.
 *
 * "Continuous" only means there are no holes *inside* what is stored, so a
 * series one month into a six-year target renders exactly as green as one that
 * is finished. The two columns sat side by side and left the reader to work out
 * the distance between them, while the only colour on the row said success.
 *
 * Measured in days rather than bars on purpose: bars need the interval's
 * period, and fetching that per row to label a table is a cost the backfill
 * dialog already pays once, where it can also say how many passes remain.
 */
function shortfallDays(target: string | null, firstBar: string | null): number {
  if (!target || !firstBar) return 0;
  const gap = Date.parse(firstBar) - Date.parse(target);
  return gap > 0 ? Math.floor(gap / MS_PER_DAY) : 0;
}

/**
 * Whether the capture has reached as far back as it was asked to go.
 *
 * The target defaults to the venue's floor, so reaching it means the venue has
 * nothing older — a series that is finished rather than merely hole-free. A row
 * with no target has nothing to have reached, so it stays "continuous": absent
 * intent must not be read as success.
 */
function reachedTarget(target: string | null, firstBar: string | null): boolean {
  if (!target || !firstBar) return false;
  return Date.parse(firstBar) <= Date.parse(target);
}

function WantedFromCell({ row }: { row: BarSubscriptionRow }) {
  const short = shortfallDays(row.backfill_from_ts, row.coverage.first_bar);
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <Typography variant="body2">{formatDay(row.backfill_from_ts)}</Typography>
      {short > 0 && (
        <Chip
          size="small"
          color="warning"
          variant="outlined"
          label={`${short.toLocaleString()} days short`}
        />
      )}
    </Stack>
  );
}

/**
 * Coverage is the column the page exists for.
 *
 * Being subscribed says a series *will* accrue; only stored bars say whether
 * there is enough to backtest. A gap count above zero is the interesting case —
 * the window is not continuous, so a run over it is not reproducible.
 *
 * Three states, not two. "Continuous" only ever meant there are no holes
 * *inside* what is stored, which a series one month into a six-year target
 * satisfies just as well as a finished one — the complaint §6.1a opens with.
 * A series whose first bar has reached its target is **completed**: nothing
 * more exists to fetch, and the distinction is what stops the reader treating
 * a permanent shortfall as a backfill they forgot to run.
 */
function CoverageCell({ coverage, target }: { coverage: Coverage; target: string | null }) {
  if (coverage.error) {
    return (
      <Tooltip title={coverage.error}>
        <Chip size="small" label="unavailable" color="warning" variant="outlined" />
      </Tooltip>
    );
  }
  if (!coverage.first_bar) {
    return (
      <Typography variant="body2" color="text.secondary">
        nothing captured yet
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <Typography variant="body2">
        {formatDay(coverage.first_bar)} → {formatDay(coverage.last_bar)}
      </Typography>
      {coverage.gaps ? (
        <Chip size="small" label={`${coverage.gaps} gaps`} color="warning" />
      ) : reachedTarget(target, coverage.first_bar) ? (
        <Tooltip title="Back to the venue's first bar — there is nothing older to fetch">
          <Chip size="small" label="completed" color="success" />
        </Tooltip>
      ) : (
        <Tooltip title="No holes in what is stored, but it has not reached the capture target yet">
          <Chip size="small" label="continuous" color="success" variant="outlined" />
        </Tooltip>
      )}
    </Stack>
  );
}

/**
 * The ticker the venue prints, beside the identifier we store it under.
 *
 * An internal CUSIP cannot be checked against anything — you cannot look up
 * `btcusdt.crypto` on an exchange. The vendor symbol is what a venue's own UI
 * shows, which is what makes "am I capturing the right thing" answerable.
 */
function ProductCell({ row }: { row: BarSubscriptionRow }) {
  return (
    <Stack spacing={0.25}>
      <Typography variant="body2">{row.internal_cusip}</Typography>
      {row.vendor_symbol ? (
        <Typography variant="caption" color="text.secondary">
          {row.vendor_symbol}
        </Typography>
      ) : (
        <Tooltip title="No INST.PRODUCT_XREF row maps this product to that venue, so capture cannot run.">
          <Typography variant="caption" color="warning.main">
            not listed on this venue
          </Typography>
        </Tooltip>
      )}
    </Stack>
  );
}

interface TableProps {
  label: string;
  rows: BarSubscriptionRow[];
  intervalNameById: Map<number, string>;
  appNameById: Map<number, string>;
  emptyMessage: string;
  busy: boolean;
  onBackfill: (row: BarSubscriptionRow) => void;
  onToggle: (row: BarSubscriptionRow) => void;
}

function SubscriptionTable({
  label,
  rows,
  intervalNameById,
  appNameById,
  emptyMessage,
  busy,
  onBackfill,
  onToggle,
}: TableProps) {
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small" aria-label={label}>
        <TableHead>
          <TableRow>
            <TableCell>Product</TableCell>
            <TableCell>Interval</TableCell>
            <TableCell>Venue</TableCell>
            <TableCell>Captured</TableCell>
            <TableCell>Wanted from</TableCell>
            <TableCell align="center">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={6}>
                <Typography variant="body2" color="text.secondary">
                  {emptyMessage}
                </Typography>
              </TableCell>
            </TableRow>
          )}
          {rows.map(row => {
            const enabled = row.is_enabled_ind === 'Y';
            return (
              <TableRow key={`${row.bar_subscription_id}-${row.bar_subscription_vid}`}>
                <TableCell>
                  <ProductCell row={row} />
                </TableCell>
                <TableCell>
                  {intervalNameById.get(row.tm_interval_id) ?? row.tm_interval_id}
                </TableCell>
                <TableCell>
                  {appNameById.get(row.source_app_id) ?? `App ${row.source_app_id}`}
                </TableCell>
                <TableCell>
                  <CoverageCell coverage={row.coverage} target={row.backfill_from_ts} />
                </TableCell>
                <TableCell><WantedFromCell row={row} /></TableCell>
                <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>
                  <Tooltip title="Backfill history">
                    <IconButton size="small" onClick={() => onBackfill(row)}>
                      <DownloadIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={enabled ? 'Pause capture' : 'Resume capture'}>
                    <IconButton
                      size="small"
                      color={enabled ? 'warning' : 'success'}
                      onClick={() => onToggle(row)}
                      disabled={busy}
                    >
                      {enabled
                        ? <PauseCircleIcon fontSize="small" />
                        : <PlayCircleIcon fontSize="small" />}
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

/** Match on either identifier — nobody remembers which one they know. */
function matches(row: BarSubscriptionRow, needle: string): boolean {
  if (!needle) return true;
  const q = needle.trim().toLowerCase();
  return (
    row.internal_cusip.toLowerCase().includes(q)
    || (row.vendor_symbol?.toLowerCase().includes(q) ?? false)
  );
}

/**
 * Market data — capture price bars for products nobody is trading yet.
 *
 * The platform could only collect bars for instruments a strategy was already
 * deployed against, which made the first thing you want to do impossible:
 * gather history for a product while deciding whether to trade it. This page is
 * the other way in. Subscriptions are shared, so the table is the platform's,
 * not the signed-in user's.
 *
 * Paused series are listed **separately** rather than mixed in with a status
 * chip. The two answer different questions — "what is accruing right now" is
 * the operational one and must not be diluted by rows that are deliberately
 * dormant — and a status column asks the reader to filter by eye every time.
 */
export default function MarketDataPage() {
  const { data: currentUser } = useMe();
  const { data: subscriptions, isLoading, isError, error } = useSubscriptions();
  const { data: intervals = [] } = useTmIntervals();
  const { data: apps = [] } = useApps();
  const toggle = useSubscribe();

  const [createOpen, setCreateOpen] = useState(false);
  const [createInstrumentOpen, setCreateInstrumentOpen] = useState(false);
  const [backfillTarget, setBackfillTarget] = useState<BarSubscriptionRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  // Typing must not stall on re-filtering a long list.
  const needle = useDeferredValue(search);

  const intervalNameById = useMemo(
    () => new Map(intervals.map(iv => [iv.tm_interval_id, intervalLabel(iv)])),
    [intervals],
  );
  const appNameById = useMemo(
    () => new Map(apps.map(a => [a.app_id, a.display_name])),
    [apps],
  );

  const { capturing, paused, hidden } = useMemo(() => {
    const all = subscriptions ?? [];
    const shown = all.filter(row => matches(row, needle));
    return {
      capturing: shown.filter(row => row.is_enabled_ind === 'Y'),
      paused: shown.filter(row => row.is_enabled_ind === 'N'),
      hidden: all.length - shown.length,
    };
  }, [subscriptions, needle]);

  const handleToggleEnabled = async (row: BarSubscriptionRow) => {
    const enabled = row.is_enabled_ind === 'Y';
    if (
      enabled &&
      !window.confirm(
        'Pause this capture? Bars are shared, so the series stops accruing for '
          + 'everyone, and the history missed while paused cannot be recovered '
          + 'beyond what the venue still retains.',
      )
    ) {
      return;
    }
    setActionError(null);
    try {
      await toggle.mutateAsync({
        bar_subscription_id: row.bar_subscription_id,
        internal_cusip: row.internal_cusip,
        tm_interval_id: row.tm_interval_id,
        source_app_id: row.source_app_id,
        is_enabled_ind: enabled ? 'N' : 'Y',
        backfill_from_ts: row.backfill_from_ts,
      });
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Update failed');
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="static"
        elevation={0}
        sx={{
          bgcolor: 'background.paper',
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Toolbar sx={{ gap: 2 }}>
          <BrandMark />
          <Typography variant="h6" color="text.primary" sx={{ fontWeight: 700, mr: 1 }}>
            {APP_NAME}
          </Typography>
          <AppModeSwitch mode="market-data" />
          <Box sx={{ flexGrow: 1 }} />
          {currentUser && <UserMenu user={currentUser} />}
        </Toolbar>
      </AppBar>

      <Box sx={{ p: 3 }}>
        <Stack spacing={3}>
          <Stack
            direction="row"
            sx={{ justifyContent: 'space-between', alignItems: 'center' }}
          >
            <Box>
              <Typography variant="h5" component="h1">
                Market data
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Capture exchange bars for a product before deciding to trade it — so a
                strategy can be fitted on the series it will actually trade.
              </Typography>
            </Box>
            {/*
              Capturing stays the page's primary action — adding an instrument
              is what you do first only on the rare visit where the product
              does not exist yet, so it sits beside it at lower emphasis.
            */}
            <Stack direction="row" spacing={1}>
              <Button variant="outlined" onClick={() => setCreateInstrumentOpen(true)}>
                Add an instrument
              </Button>
              <Button variant="contained" onClick={() => setCreateOpen(true)}>
                Capture a series
              </Button>
            </Stack>
          </Stack>

          {isLoading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress size={28} />
            </Box>
          )}
          {isError && (
            <Alert severity="error">
              {error instanceof Error ? error.message : 'Failed to load subscriptions'}
            </Alert>
          )}

          {!isLoading && !isError && (
            <>
              <TextField
                size="small"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by product or venue symbol — btcusdt, BTCUSDT…"
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon fontSize="small" />
                      </InputAdornment>
                    ),
                  },
                }}
                sx={{ maxWidth: 420 }}
              />

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Capturing ({capturing.length})
                </Typography>
                <SubscriptionTable
                  label="Capturing series"
                  rows={capturing}
                  intervalNameById={intervalNameById}
                  appNameById={appNameById}
                  busy={toggle.isPending}
                  onBackfill={setBackfillTarget}
                  onToggle={handleToggleEnabled}
                  emptyMessage={
                    needle
                      ? 'No capturing series matches that search.'
                      : 'Nothing is being captured beyond what scheduled deployments '
                        + 'already need. Capture a series to start accruing history for '
                        + 'a product you have not committed to.'
                  }
                />
              </Box>

              {paused.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                    Paused ({paused.length})
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
                    Not accruing. Bars missed while paused are only recoverable as far
                    back as the venue still retains them — resume, then backfill.
                  </Typography>
                  <SubscriptionTable
                    label="Paused series"
                    rows={paused}
                    intervalNameById={intervalNameById}
                    appNameById={appNameById}
                    busy={toggle.isPending}
                    onBackfill={setBackfillTarget}
                    onToggle={handleToggleEnabled}
                    emptyMessage="No paused series matches that search."
                  />
                </Box>
              )}

              {hidden > 0 && (
                <Typography variant="caption" color="text.secondary">
                  {hidden} series hidden by the search.
                </Typography>
              )}
            </>
          )}

          {actionError && (
            <Alert severity="error" onClose={() => setActionError(null)}>
              {actionError}
            </Alert>
          )}
        </Stack>
      </Box>

      <SubscriptionDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={() => setCreateOpen(false)}
      />

      <CreateInstrumentDialog
        open={createInstrumentOpen}
        onClose={() => setCreateInstrumentOpen(false)}
        onSuccess={() => setCreateInstrumentOpen(false)}
      />

      <BackfillDialog row={backfillTarget} onClose={() => setBackfillTarget(null)} />
    </Box>
  );
}
