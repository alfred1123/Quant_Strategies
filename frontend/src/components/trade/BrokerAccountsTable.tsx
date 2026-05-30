import { useMemo, useState } from 'react';
import {
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import type { BrokerAccount } from '../../types/credentials';
import { useApps } from '../../api/refdata';
import { useRevokeCredential, useRotateCredential } from '../../api/credentials';

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
  const revokeCredential = useRevokeCredential();
  const rotateCredential = useRotateCredential();

  const [revokeTarget, setRevokeTarget] = useState<BrokerAccount | null>(null);
  const [rotateTarget, setRotateTarget] = useState<BrokerAccount | null>(null);
  const [rotateKey, setRotateKey] = useState('');
  const [rotateSecret, setRotateSecret] = useState('');

  const appNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const a of apps) map.set(a.app_id, a.display_name);
    return map;
  }, [apps]);

  const stopRowClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  const closeRotate = () => {
    setRotateTarget(null);
    setRotateKey('');
    setRotateSecret('');
  };

  const handleRevoke = () => {
    if (!revokeTarget) return;
    revokeCredential.mutate(revokeTarget.api_credential_id, {
      onSuccess: () => setRevokeTarget(null),
    });
  };

  const handleRotate = () => {
    if (!rotateTarget || !rotateKey.trim() || !rotateSecret.trim()) return;
    rotateCredential.mutate(
      {
        api_credential_id: rotateTarget.api_credential_id,
        api_key: rotateKey.trim(),
        api_secret: rotateSecret.trim(),
      },
      { onSuccess: closeRotate },
    );
  };

  return (
    <>
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
                    No broker accounts registered yet. Add one below.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {accounts.map(row => {
              const selected =
                selectedCredentialId !== 'all' &&
                selectedCredentialId === row.api_credential_id;
              const active = row.is_active_ind === 'Y';
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
                      label={active ? 'Active' : 'Inactive'}
                      color={active ? 'success' : 'default'}
                      variant="outlined"
                    />
                  </TableCell>
                  {showActions && (
                    <TableCell align="right" onClick={stopRowClick}>
                      <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                        <Button
                          size="small"
                          disabled={!active}
                          onClick={() => {
                            closeRotate();
                            setRotateTarget(row);
                          }}
                        >
                          Rotate
                        </Button>
                        <Button
                          size="small"
                          color="error"
                          disabled={!active || revokeCredential.isPending}
                          onClick={() => setRevokeTarget(row)}
                        >
                          Revoke
                        </Button>
                      </Stack>
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={revokeTarget !== null} onClose={() => setRevokeTarget(null)}>
        <DialogTitle>Revoke account?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {revokeTarget
              ? `This will deactivate "${revokeTarget.label}" on ${
                  appNameById.get(revokeTarget.app_id) ?? 'exchange'
                }. Deployments using this account will need a new credential.`
              : ''}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevokeTarget(null)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            disabled={revokeCredential.isPending}
            onClick={handleRevoke}
          >
            {revokeCredential.isPending ? 'Revoking…' : 'Revoke'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={rotateTarget !== null} onClose={closeRotate} maxWidth="xs" fullWidth>
        <DialogTitle>Rotate API keys</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {rotateTarget
              ? `Enter new keys for "${rotateTarget.label}". The previous keys will be replaced.`
              : ''}
          </DialogContentText>
          <Stack spacing={2}>
            <TextField
              size="small"
              label="New API key"
              type="password"
              value={rotateKey}
              onChange={e => setRotateKey(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              label="New API secret"
              type="password"
              value={rotateSecret}
              onChange={e => setRotateSecret(e.target.value)}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeRotate}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              !rotateKey.trim() ||
              !rotateSecret.trim() ||
              rotateCredential.isPending
            }
            onClick={handleRotate}
          >
            {rotateCredential.isPending ? 'Saving…' : 'Save keys'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
