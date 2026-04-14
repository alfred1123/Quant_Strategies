export interface IndicatorRow {
  method_name: string;
  display_name: string;
  win_min: number;
  win_max: number;
  win_step: number;
  sig_min: number | null;
  sig_max: number | null;
  sig_step: number;
  is_bounded_ind: string | null;
}

export interface SignalTypeRow {
  name: string;
  display_name: string;
}

export interface AssetTypeRow {
  display_name: string;
  trading_period: number;
}

export interface ConjunctionRow {
  name: string;
  display_name: string;
}

export interface DataColumnRow {
  column_name: string;
  display_name: string;
}
