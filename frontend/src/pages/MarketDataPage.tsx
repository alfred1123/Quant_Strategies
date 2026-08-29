import {
  Alert,
  AppBar,
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
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import PauseCircleIcon from '@mui/icons-material/PauseCircle';
import PlayCircleIcon from '@mui/icons-material/PlayCircle';
import { useMemo, useState } from 'react';
import { useMe } from '../api/auth';
import { useSubscribe, useSubscriptions } from '../api/marketData';
import { intervalLabel, useApps, useTmIntervals } from '../api/refdata';
import AppModeSwitch from '../components/AppModeSwitch';
import BrandMark from '../components/BrandMark';
import UserMenu from '../components/UserMenu';
import BackfillDialog from '../components/market-data/BackfillDialog';
import SubscriptionDialog from '../components/market-data/SubscriptionDialog';
import { APP_NAME } from '../constants/brand';
import type { BarSubscriptionRow, Coverage } from '../types/marketData';

function formatDay(value: string | null): string {
  return value ? value.slice(0, 10) : '—';
}

/**
 * Coverage is the column the page exists for.
 *
 * Being subscribed says a series *will* accrue; only stored bars say whether
 * there is enough to backtest. A gap count above zero is the interesting case —
 * the window is not continuous, so a run over it is not reproducible.
 */
function CoverageCell({ coverage }: { coverage: Coverage }) {
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
      ) : (
        <Chip size="small" label="continuous" color="success" variant="outlined" />
      )}
    </Stack>
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
 */
export default function MarketDataPage() {
  const { data: currentUser } = useMe();
  const { data: subscriptions, isLoading, isError, error } = useSubscriptions();
  const { data: intervals = [] } = useTmIntervals();
  const { data: apps = [] } = useApps();
  const toggle = useSubscribe();

  const [createOpen, setCreateOpen] = useState(false);
  const [backfillTarget, setBackfillTarget] = useState<BarSubscriptionRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const intervalNameById = useMemo(
    () => new Map(intervals.map(iv => [iv.tm_interval_id, intervalLabel(iv)])),
    [intervals],
  );
  const appNameById = useMemo(
    () => new Map(apps.map(a => [a.app_id, a.display_name])),
    [apps],
  );

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
            <Button variant="contained" onClick={() => setCreateOpen(true)}>
              Capture a series
            </Button>
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
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Product</TableCell>
                    <TableCell>Interval</TableCell>
                    <TableCell>Venue</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Captured</TableCell>
                    <TableCell>Wanted from</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(subscriptions ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7}>
                        <Typography variant="body2" color="text.secondary">
                          Nothing is being captured beyond what scheduled deployments
                          already need. Capture a series to start accruing history for a
                          product you have not committed to.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                  {(subscriptions ?? []).map(row => {
                    const enabled = row.is_enabled_ind === 'Y';
                    return (
                      <TableRow key={`${row.bar_subscription_id}-${row.bar_subscription_vid}`}>
                        <TableCell>{row.internal_cusip}</TableCell>
                        <TableCell>
                          {intervalNameById.get(row.tm_interval_id) ?? row.tm_interval_id}
                        </TableCell>
                        <TableCell>
                          {appNameById.get(row.source_app_id) ?? `App ${row.source_app_id}`}
                        </TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={enabled ? 'Capturing' : 'Paused'}
                            color={enabled ? 'success' : 'default'}
                            variant={enabled ? 'filled' : 'outlined'}
                          />
                        </TableCell>
                        <TableCell>
                          <CoverageCell coverage={row.coverage} />
                        </TableCell>
                        <TableCell>{formatDay(row.backfill_from_ts)}</TableCell>
                        <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>
                          <Tooltip title="Backfill history">
                            <IconButton
                              size="small"
                              onClick={() => setBackfillTarget(row)}
                            >
                              <DownloadIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title={enabled ? 'Pause capture' : 'Resume capture'}>
                            <IconButton
                              size="small"
                              color={enabled ? 'warning' : 'success'}
                              onClick={() => handleToggleEnabled(row)}
                              disabled={toggle.isPending}
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

      <BackfillDialog row={backfillTarget} onClose={() => setBackfillTarget(null)} />
    </Box>
  );
}
