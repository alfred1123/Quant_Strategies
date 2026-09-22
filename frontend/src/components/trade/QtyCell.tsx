import { TextField } from '@mui/material';
import { useRef, useState } from 'react';
import { useUpdateDeployment } from '../../api/trade';
import type { DeploymentRow } from '../../types/trade';

interface QtyCellProps {
  row: DeploymentRow;
  onError: (message: string) => void;
}

/**
 * Position size for one deployment, editable in place.
 *
 * Commit on blur or Enter; Escape reverts. The backend refuses qty ≤ 0 and
 * anything under the venue's lot size, so the cell checks both before
 * PATCHing — a rejected size is worth saying without a round-trip, and
 * `min_qty` is on the row for exactly that. A live row asks once more because
 * the next apply — scheduled or manual — will use the new size.
 */
export default function QtyCell({ row, onError }: QtyCellProps) {
  const update = useUpdateDeployment();
  const skipBlur = useRef(false);
  const [draft, setDraft] = useState(row.qty);
  const [sourceQty, setSourceQty] = useState(row.qty);
  if (row.qty !== sourceQty) {
    setSourceQty(row.qty);
    setDraft(row.qty);
  }

  const commit = async (raw: string) => {
    const trimmed = raw.trim();
    const num = Number(trimmed);
    if (!Number.isFinite(num) || num <= 0) {
      setDraft(row.qty);
      onError('Quantity must be greater than 0');
      return;
    }
    if (row.min_qty != null && num < row.min_qty) {
      setDraft(row.qty);
      onError(
        `${row.internal_cusip} trades in lots of at least ${row.min_qty} — ` +
          'the exchange would reject this order.',
      );
      return;
    }
    if (num === Number(row.qty)) {
      setDraft(row.qty);
      return;
    }
    if (row.is_paper_ind === 'N') {
      const ok = window.confirm(
        `Change live quantity for ${row.internal_cusip} from ${row.qty} to ${trimmed}?\n\n` +
          'This is a LIVE deployment — the next apply will use the new size.',
      );
      if (!ok) {
        setDraft(row.qty);
        return;
      }
    }
    try {
      await update.mutateAsync({
        deploymentId: row.deployment_id,
        qty: trimmed,
      });
    } catch (e: unknown) {
      setDraft(row.qty);
      onError(e instanceof Error ? e.message : 'Failed to change quantity');
    }
  };

  return (
    <TextField
      variant="standard"
      size="small"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={(e) => {
        if (skipBlur.current) {
          skipBlur.current = false;
          return;
        }
        void commit(e.target.value);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          setDraft(row.qty);
          skipBlur.current = true;
          (e.target as HTMLInputElement).blur();
        }
      }}
      disabled={update.isPending}
      slotProps={{
        htmlInput: {
          'aria-label': `Quantity for ${row.internal_cusip}`,
          inputMode: 'decimal',
          title: row.min_qty != null ? `Venue minimum ${row.min_qty}` : undefined,
        },
      }}
      sx={{
        width: 88,
        '& input': { textAlign: 'right', fontSize: '0.875rem' },
      }}
    />
  );
}
