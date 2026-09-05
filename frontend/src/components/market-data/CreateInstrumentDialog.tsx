import {
  Alert,
  Autocomplete,
  Box,
  Button,
  createFilterOptions,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useCreateInstrument, useVenueSymbols } from '../../api/inst';
import { useAssetTypes, useExchangeApps } from '../../api/refdata';
import type { VenueSymbol } from '../../types/refdata';

interface CreateInstrumentDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * Add an instrument the platform has never seen.
 *
 * There is no `INSTRUMENT` table: an instrument is `INST.PRODUCT` (its
 * identity, keyed by `INTERNAL_CUSIP`) plus an `INST.PRODUCT_XREF` row per
 * venue (the ticker that venue prints). The form asks for both in one submit
 * because a product with no xref is invisible to every venue-scoped list —
 * created alone it could not be subscribed to, or even found again.
 *
 * The venue therefore belongs to the mapping, not to the identity: one product
 * covers a traded pair across brokers, and `Exchange` on the product is the
 * listing venue of an equity rather than the broker you reach it through.
 *
 * There is no owner field, for the same reason a subscription has none:
 * instruments are shared platform rows, and one row serves everyone.
 */
export default function CreateInstrumentDialog({
  open,
  onClose,
  onSuccess,
}: CreateInstrumentDialogProps) {
  // Remount on open so the form resets without an effect.
  if (!open) return null;
  return <CreateInstrumentDialogContent onClose={onClose} onSuccess={onSuccess} />;
}

/**
 * The rule an internal CUSIP has to follow, where a free-text box gives no hint.
 *
 * Stated as one identifier per *instrument* rather than per broker because the
 * tempting mistake is the other one: `btcusdt.bybit` looks more precise, and
 * produces a second product for a pair the platform already has, whose bars and
 * strategies can never meet the first one's.
 */
function cusipHelp(): string {
  return (
    'Always lowercase, {symbol}.{suffix} — btcusdt.crypto. One row per logical '
    + 'instrument, never one per broker: Bybit and Binance share btcusdt.crypto '
    + 'and differ only in the venue symbol below. btcusdt.bybit is wrong.'
  );
}

/**
 * Why the venue's own ticker is asked for here rather than added later.
 *
 * The field looks optional next to the identity ones, and it is the one that
 * decides whether any of this is reachable: the xref is what venue-scoped
 * lists are built from, so a product submitted without it exists and shows up
 * nowhere.
 */
function vendorSymbolHelp(): string {
  return (
    'The ticker this venue itself prints — BTCUSDT. Required in the same '
    + 'submit: without an xref the product would exist but be invisible to '
    + 'every venue-scoped list.'
  );
}

/**
 * What the ccxt lookup is currently able to offer, in the field's own words.
 *
 * Said out loud because every state here looks identical otherwise — an empty
 * dropdown reads the same whether the venue is unpicked, still downloading, or
 * unreachable, and the third one is the one where the user has to type the
 * symbol themselves rather than wait.
 */
function venueSymbolStatus(
  venuePicked: boolean,
  loading: boolean,
  failed: boolean,
  count: number,
): string {
  if (!venuePicked) return 'Pick a venue and its tickers are offered here.';
  if (loading) return 'Reading this venue’s tickers…';
  if (failed) return 'This venue could not be reached — type the ticker yourself.';
  if (count === 0) return 'This venue publishes no ticker list — type it yourself.';
  return `${count.toLocaleString()} tickers offered; an unlisted one can still be typed.`;
}

/**
 * Cap the rendered list. The venue decides how long it is and Bybit answers
 * with ~1,100 tickers, which MUI would mount in full on the first keystroke.
 */
const filterVenueSymbols = createFilterOptions<VenueSymbol>({
  stringify: opt => `${opt.vendor_symbol} ${opt.base ?? ''} ${opt.quote ?? ''}`,
  limit: 50,
});

function venueSymbolCaption(opt: VenueSymbol): string {
  const pair = opt.base && opt.quote ? `${opt.base}/${opt.quote}` : '';
  const types = opt.market_types.join(', ');
  return [pair, types].filter(Boolean).join(' · ');
}

/**
 * What `EXCHANGE` on the product means, which is not what the word suggests.
 *
 * Read as "which exchange do I trade this on", it invites the broker — the
 * thing that belongs in the xref. It is the listing/clearing venue of an
 * equity, and empty is the correct answer for crypto spot.
 */
function exchangeHelp(): string {
  return (
    'Listing/clearing venue, equities only — NYSE for aapl.nyse. Leave blank '
    + 'for .crypto spot: the broker belongs to the venue symbol, not to the '
    + 'product identity.'
  );
}

function CreateInstrumentDialogContent({
  onClose,
  onSuccess,
}: Omit<CreateInstrumentDialogProps, 'open'>) {
  const { data: exchanges = [] } = useExchangeApps();
  const { data: assetTypes = [] } = useAssetTypes();
  const create = useCreateInstrument();

  const [appId, setAppId] = useState('');
  const venueSymbols = useVenueSymbols(appId ? Number(appId) : null);
  const symbolOptions = venueSymbols.data ?? [];
  const [vendorSymbol, setVendorSymbol] = useState('');
  const [internalCusip, setInternalCusip] = useState('');
  const [displayNm, setDisplayNm] = useState('');
  const [assetTypeId, setAssetTypeId] = useState('');
  const [ccy, setCcy] = useState('');
  const [exchange, setExchange] = useState('');
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // The cusip is an identifier, so what is stored is the normalised form
  // rather than what was typed — a stray capital or space makes a second
  // product for an instrument the platform already has.
  const cusip = internalCusip.trim().toLowerCase();

  const canSubmit =
    cusip !== ''
    && displayNm.trim() !== ''
    && assetTypeId !== ''
    && appId !== ''
    && vendorSymbol.trim() !== '';

  const handleSubmit = async () => {
    setFormError(null);
    try {
      await create.mutateAsync({
        internal_cusip: cusip,
        display_nm: displayNm.trim(),
        asset_type_id: Number(assetTypeId),
        exchange: exchange.trim() || null,
        ccy: ccy.trim() || null,
        description: description.trim() || null,
        app_id: Number(appId),
        vendor_symbol: vendorSymbol.trim(),
      });
      onSuccess();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Could not create the instrument');
    }
  };

  return (
    <Dialog
      open
      onClose={create.isPending ? undefined : onClose}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>Add an instrument</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {/*
            Venue first, as in the capture dialog: it is the one field that
            says which mapping is being made, and the vendor symbol under it
            only means anything once the exchange printing it is known.
          */}
          <TextField
            select
            label="Venue"
            value={appId}
            onChange={e => setAppId(e.target.value)}
            helperText="The first venue to list this instrument — more can be mapped later."
            fullWidth
          >
            {exchanges.map(a => (
              <MenuItem key={a.app_id} value={String(a.app_id)}>
                {a.display_name}
              </MenuItem>
            ))}
          </TextField>

          {/*
            `freeSolo`, unlike the capture dialog's product picker. There the
            list is the platform's own and a value outside it cannot work; here
            the list is the exchange's, and a pair listed this morning is
            genuinely absent from a table ccxt cached minutes ago. Suggesting is
            the whole job — refusing would make the venue's staleness the
            user's problem.

            `autoSelect` is what makes a suggestion worth having: typing
            ETHUSD and tabbing away commits ETHUSDT rather than leaving a
            symbol that resolves to nothing.
          */}
          <Autocomplete<VenueSymbol, false, false, true>
            freeSolo
            autoHighlight
            autoSelect
            options={symbolOptions}
            filterOptions={filterVenueSymbols}
            inputValue={vendorSymbol}
            onInputChange={(_, val) => setVendorSymbol(val)}
            getOptionLabel={opt =>
              typeof opt === 'string' ? opt : opt.vendor_symbol}
            loading={venueSymbols.isFetching}
            slotProps={{ listbox: { sx: { maxHeight: 320 } } }}
            renderInput={params => (
              <TextField
                {...params}
                label="Venue symbol"
                helperText={`${vendorSymbolHelp()} ${venueSymbolStatus(
                  appId !== '',
                  venueSymbols.isFetching,
                  venueSymbols.isError,
                  symbolOptions.length,
                )}`}
                // Chrome offers saved values from other forms over the ticker
                // list otherwise, and honours `off` only intermittently.
                slotProps={{
                  ...params.slotProps,
                  htmlInput: {
                    ...params.slotProps?.htmlInput,
                    autoComplete: 'new-password',
                  },
                }}
              />
            )}
            renderOption={(props, opt) => (
              <li {...props} key={opt.vendor_symbol}>
                <Box>
                  <Typography variant="body2">{opt.vendor_symbol}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {venueSymbolCaption(opt)}
                  </Typography>
                </Box>
              </li>
            )}
            fullWidth
          />

          <TextField
            label="Internal CUSIP"
            value={internalCusip}
            onChange={e => setInternalCusip(e.target.value)}
            helperText={cusipHelp()}
            fullWidth
          />

          <TextField
            label="Display name"
            value={displayNm}
            onChange={e => setDisplayNm(e.target.value)}
            helperText="What a person reads on a list — Bitcoin / USDT."
            fullWidth
          />

          <TextField
            select
            label="Asset type"
            value={assetTypeId}
            onChange={e => setAssetTypeId(e.target.value)}
            fullWidth
          >
            {assetTypes.map(t => (
              <MenuItem key={t.asset_type_id} value={String(t.asset_type_id)}>
                {t.display_name}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Currency"
            value={ccy}
            onChange={e => setCcy(e.target.value)}
            helperText="The quote currency you trade — USDT for BTC/USDT."
            fullWidth
          />

          <TextField
            label="Exchange"
            value={exchange}
            onChange={e => setExchange(e.target.value)}
            helperText={exchangeHelp()}
            fullWidth
          />

          <TextField
            label="Description"
            value={description}
            onChange={e => setDescription(e.target.value)}
            multiline
            minRows={2}
            fullWidth
          />

          <Typography variant="caption" color="text.secondary">
            An instrument is a shared platform row: it is visible to everyone,
            and anyone can subscribe to or trade it. The product and its venue
            symbol are created in one step because a product with no venue
            mapping is invisible to every venue-scoped list.
          </Typography>

          {formError && <Alert severity="error">{formError}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={create.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!canSubmit || create.isPending}
        >
          Add instrument
        </Button>
      </DialogActions>
    </Dialog>
  );
}
