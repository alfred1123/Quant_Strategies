export interface IndicatorRow {
  method_name: string;
  display_name: string;
  win_min: number;
  win_max: number;
  win_step: number;
  sig_min: number;
  sig_max: number;
  sig_step: number;
}

export interface SignalTypeRow {
  func_name: string;
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
