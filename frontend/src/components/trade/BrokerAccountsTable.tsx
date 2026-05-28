import {
  Chip,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { BrokerAccount } from '../../types/credentials';
import { useApps } from '../../api/refdata';
import { useMemo } from 'react';

interface BrokerAccountsTableProps {
  accounts: BrokerAccount[];
  loading?: boolean;
  /** Highlight row matching layout account filter */
  selectedCredentialId?: number | 'all';
  onSelectAccount?: (id: number) => void;
  showActions?: boolean;
}

export default function BrokerAccountsTable({
  accounts,
  loading = false,
  selectedCredentialId,
  onSelectAccount,
  showActions = false,
}: BrokerAccountsTableProps) {
  const { data: apps = [] } = useApps();

  const appNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const a of apps) map.set(a.app_id, a.display_name);
    return map;
  }, [apps]);

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Exchange</TableCell>
            <TableCell>Account</TableCell>
            <TableCell>API key</TableCell>
            <TableCell>Status</TableCell>
            {showActions && <TableCell align="right">Actions</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {!loading && accounts.length === 0 && (
            <TableRow>
              <TableCell colSpan={showActions ? 5 : 4}>
                <Typography variant="body2" color="text.secondary">
                  No broker accounts registered yet. Add one below (Phase 1.5).
                </Typography>
              </TableCell>
            </TableRow>
          )}
          {accounts.map(row => {
            const selected =
              selectedCredentialId !== 'all' &&
              selectedCredentialId === row.api_credential_id;
            return (
              <TableRow
                key={row.api_credential_id}
                hover={!!onSelectAccount}
                selected={selected}
                onClick={
                  onSelectAccount
                    ? () => onSelectAccount(row.api_credential_id)
                    : undefined
                }
                sx={onSelectAccount ? { cursor: 'pointer' } : undefined}
              >
                <TableCell>{appNameById.get(row.app_id) ?? `App ${row.app_id}`}</TableCell>
                <TableCell>{row.label}</TableCell>
                <TableCell>{row.api_key_masked}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={row.is_active_ind === 'Y' ? 'Active' : 'Inactive'}
                    color={row.is_active_ind === 'Y' ? 'success' : 'default'}
                    variant="outlined"
                  />
                </TableCell>
                {showActions && (
                  <TableCell align="right">
                    <Typography variant="caption" color="text.disabled">
                      Revoke (1.5)
                    </Typography>
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
