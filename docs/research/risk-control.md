# Risk control for the three crypto sleeves

**Doc type:** strategy research  
**Status:** DRAFT — decisions pending Alfred. Same-close blend figures are platform-confirmed. Delay-1 results, the 2018–21 stress test, the bootstrap, and the alarms are offline. Nothing on this page can run on AlgoDaemon yet.

Risk Guardian, 2026-09-29 HKT. This is a draft for Alfred. It covers fixed weights, drawdown tiers, a kill switch with re-entry, and return concentration for the three sleeves: **ETH A2**, **BNB 100/0.5**, and **BTC 60/2.25**. It does not authorise a trade, a deployment, or a code change.

The inputs are the researcher's platform daily P&L (algodaemon.com, round 7) and Scout's [persistence validation study](strategy-persistence-validation.md). Weights and thresholds are calibrated on in-sample Bybit data only. The 2018–21 Binance splice is a stress test. How the bots divide this work is in the [research workflow](workflow.md#risk-control-risk-guardian).

!!! warning "DRAFT — decisions pending Alfred"
    Three choices are open:

    1. **Weights.** Middle **0.37 / 0.25 / 0.38** (ETH / BNB / BTC), or BTC-trim **0.45 / 0.25 / 0.30**.
    2. **Drawdown tiers.** Levels **14% / 18% / 23.5%**, and whether the top tier cuts to a quarter of size or goes flat.
    3. **Kill switch.** Sign-off on the trigger (CUSUM, threshold h = 27.5) and the re-entry rule (reset the CUSUM at the cut, wait 30 days, step back up one level at a time).

    The platform cannot size a position or combine sleeves. That work is the [fractional sizing and stateful exits](../design/2026-09-26-fractional-sizing-stateful-exits.md) proposal ([PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63)). Until it ships, every blend, tier, and kill switch here is paper only. Sleeves could be run as separate sub-accounts and rebalanced by hand; that has not been set up.

!!! note "What is platform-confirmed"
    **Same-close blends are platform-confirmed.** Round 7 showed each sleeve's daily P&L identical to the platform's own series. The researcher then rebuilt equal weight, inverse-vol, Middle, and BTC-trim from that platform daily P&L. The rebuild matched the offline expected values to three decimals. Those figures are in [Platform reconciliation](#platform-reconciliation).

    **Delay-1 rows are an engine copy.** The copy's same-close sleeve P&L matches the platform exactly. The delay-1 rows were not run on algodaemon.com.

    **Offline only.** The 2018–21 Binance splice, every bootstrap quantile, and every alarm and kill-switch simulation. The scripts live outside this repository.

## Setup

| Item | Value |
|---|---|
| Sleeves | **ETH A2**: hold ETH when `FILTER(BTC BB z(65) > 2.25, ETH BB z(100) > −1.0)`. **BNB**: hold BNB when `BTC BB z(100) > 0.5`. **BTC**: hold BTC when `BTC BB z(60) > 2.25` |
| Data | Bybit spot daily. Fee 10 bps per side. `trading_period` 365. Platform runs from 2021-07-01 to 2026-09-25 |
| Fills | **Same-close** (delay 0) fills at the signal close. That is the platform convention. **Delay 1** fills at the next close |
| Blend | Daily fixed-weight sum of sleeve P&L. Rebalanced every day, with no extra rebalancing cost. Gross exposure at most 1.0 (spot, no leverage). Sleeve fees are already inside each sleeve's P&L |
| Calibration sample | In-sample Bybit only, 2021-10-09 to 2024-06-30. Out-of-sample and the 2018–21 splice are checks, not fitting samples |
| Sharpe | mean / sample standard deviation (ddof = 1) × √365. Max drawdown from compounded daily P&L. CAGR = (Π(1+r))^(365/n) − 1 |

| Label | Range (UTC daily, inclusive) | Data | Where the figures come from |
|---|---|---|---|
| FULL | 2021-10-09 → 2026-09-25 (1,813 days) | Bybit | Same-close blends: platform daily P&L, rebuilt. Delay 1 starts 2021-10-10 (1,812 days) and is an engine copy |
| IS / TRAIN | 2021-10-09 → 2024-06-30 (996 days) | Bybit | Same as FULL. This is the only sample used to set weights and thresholds |
| OOS | 2024-07-01 → 2026-09-25 (817 days) | Bybit | Same as FULL |
| LATE | 2024-11-19 → 2026-09-25 | Bybit | Same as FULL |
| PRE | 2018-03-01 → 2021-06-30 (1,218 days) | Binance splice | Offline stress test. Outside the Bybit-only rule. It cannot be reconciled with the platform |

FULL here starts on 2021-10-09, after the 100-bar warm-up of ETH and BNB. Platform full-period runs start on 2021-07-01, and each sleeve's P&L begins after its own warm-up: ETH and BNB on 2021-10-09, BTC on 2021-08-30. Both bases are in the reconciliation section.

Some engine tables below (the bootstrap tail, the ensemble, the tiers, the kill switch, and concentration) include 2021-10-09 in their delay-1 window, one day more than the 1,812-day series. On that extra day, equal-weight delay-1 FULL Sharpe is 1.85, against 1.837 on the 1,812-day series. The weighting tables use the 1,812-day series.

**Time in market** (platform positions, round 7; days held long, from 2021-10-09): BNB 42.1% FULL / 41.0% OOS, ETH 7.7% / 6.5%, BTC 7.0% / 6.2% (6.9% from its own 2021-08-30 start). An earlier 0.44 / 0.09 pair counted fee-only exit days.

## Recommended spec

| Item | Proposal | Alfred |
|---|---|---|
| Weights | **Middle: ETH 0.37 / BNB 0.25 / BTC 0.38**, fixed, daily rebalance. BTC-trim 0.45 / 0.25 / 0.30 is the alternative | Pick Middle or BTC-trim |
| Vol target | **None.** A training-period vol target with a 1.0 gross cap did not restore out-of-sample return and lowered Sharpe | — |
| Family ensemble | **Not in this draft.** It is worse on every platform-reproducible window. Revisit once fractional sizing exists | — |
| Drawdown tiers | Measured on the full-size **shadow** blend, from its peak since go-live. **T1 14% = review** (no size change). **T2 18% = 0.5×.** **T3 23.5% = 0.25×.** Calibrated on in-sample Bybit same-close only. A rerun with a different seed gave 17.5% / 23% (bootstrap noise of about 0.5 percentage points). The same levels apply at delay 1 | Levels, and 0.25× versus flat at T3 |
| Kill switch | **CUSUM on shadow-blend daily P&L** (Scout's method in [live monitoring](strategy-persistence-validation.md#7-live-monitoring-optional-rule-tested-historically)). In-sample mean μ0 = 0.000767 and standard deviation 0.008518 per day. k = μ0/2. **h = 27.5**, set for a 5% per year false-alarm rate. Action: **0.5× and a review.** It runs together with the tiers | Sign off the trigger |
| Re-entry | At least **30 days** at the reduced size. **The CUSUM restarts at 0 at each cut.** Step up one level at a time: 0.25× → 0.5× once shadow drawdown is back under T2; 0.5× → 1× once CUSUM ≤ h/2 and shadow drawdown is back under T1 | Sign off the re-entry rule |
| When size is set | At close t, from data up to t, and filled the same way as the positions (same close, or the next close). Resize fees of 10 bps per side are in every test | — |
| What an alarm means | **Review and cut size.** Flat is used only if Alfred sets T3 to flat. Scout's study reached the same conclusion: an alarm is not a switch-off | Confirm, if T3 is left at a quarter |

### Record of the recommended rule

Tiers plus CUSUM, re-entry variant B, on the Middle blend. PRE rows are the offline stress test.

| Window | Delay | Cuts | False alarms (forward 365-day shadow return > 0) | Days below 1× | CAGR, no rule → rule | MDD, no rule → rule | Sharpe, no rule → rule |
|---|---|---|---|---|---|---|---|
| IS | 0 | 1 (CUSUM 2023-08-14) | 1 (forward +77.7%, partial window) | 30 | 0.306 → 0.307 | 0.119 → 0.117 | 1.72 → 1.73 |
| OOS | 0 | 0 | 0 | 0 | 0.222 → 0.222 | 0.095 → 0.095 | 1.54 → 1.54 |
| PRE, offline stress | 0 | 3 (2019-02-24 CUSUM, 2019-11-05 CUSUM, 2020-04-30 DD ≥ T2) | 3 | 217 | 0.468 → 0.428 | 0.229 → 0.223 | 1.49 → 1.42 |
| IS | 1 | 0 | 0 | 0 | 0.413 → 0.413 | 0.074 → 0.074 | 2.19 → 2.19 |
| OOS | 1 | 0 | 0 | 0 | 0.212 → 0.212 | 0.076 → 0.076 | 1.50 → 1.50 |
| PRE, offline stress | 1 | 4 (2019-07-16 T2, 2020-03-08 T2, 2020-05-10 T3, 2021-02-23 T2) | 3 | 415 | 0.507 → 0.447 | 0.263 → 0.256 | 1.52 → 1.45 |

*Delay 0 on IS and OOS uses platform-identical sleeve P&L. The rule itself, the resize fees, and every PRE row are offline. Delay 1 is the engine copy.*

The chance of any cut within one year when the in-sample edge is intact (in-sample bootstrap, 1,000 paths of 365 days) is **4.6%** at same-close and 0.1% at delay 1. The same-close levels are loose for the smoother delay-1 series. That rate is an offline bootstrap.

The rule never fired on platform-reproducible out-of-sample data. On the offline stress test every cut was a false alarm, and it cost about 4–6 percentage points of CAGR for at most 0.7 percentage points less max drawdown. It is insurance with a cost and no demonstrated benefit on our data. That is why an alarm means review and cut, and why flat is not the default.

## Weights

### How Middle and BTC-trim are built

BNB is fixed at 0.25. The remaining 0.75 is split between ETH and BTC in inverse proportion to their in-sample daily P&L standard deviation (2021-10-09 to 2024-06-30, same-close): 0.75 × 0.4875 = 0.366 for ETH and 0.384 for BTC, rounded to **0.37 / 0.38**. The rounded weights are used as-is at both delays.

Middle blend P&L on day t is `0.37 * r_ETH(t) + 0.25 * r_BNB(t) + 0.38 * r_BTC(t)`.

BTC-trim uses the same sum with weights **0.45 / 0.25 / 0.30**. It is an alternative for Alfred, not the default. On platform-reproducible data it ties Middle. Its extra case is BTC's weak 2018–21 record (offline stress only) and BTC's weak LATE Sharpe of 0.646.

### Results on Bybit

Same-close rows are platform-confirmed: the researcher's rebuild from algodaemon.com daily P&L matched these figures to three decimals. Delay-1 rows are the engine copy (1,812 days from 2021-10-10). They were not platform runs.

**Same-close (platform-confirmed)**

| Weighting (ETH/BNB/BTC) | FULL SR / MDD / CAGR | IS SR | OOS SR / MDD / CAGR | LATE SR / CAGR |
|---|---|---|---|---|
| Equal weight 1/3 | 1.593 / 0.122 / 0.284 | 1.660 | 1.511 / 0.110 / 0.235 | 1.452 / 0.213 |
| Inverse-vol 0.40/0.17/0.43 | 1.645 / 0.117 / 0.250 | 1.737 | 1.526 / 0.092 / 0.208 | 1.346 / 0.163 |
| **Middle 0.37/0.25/0.38** | 1.641 / 0.119 / 0.267 | 1.720 | **1.541 / 0.095 / 0.222** | 1.426 / 0.188 |
| BTC-trim 0.45/0.25/0.30 | 1.637 / 0.130 / 0.271 | 1.713 | 1.540 / 0.097 / 0.230 | 1.430 / 0.198 |

**Delay 1 (engine copy)**

| Weighting (ETH/BNB/BTC) | FULL SR / MDD / CAGR | IS SR | OOS SR / MDD / CAGR | LATE SR / CAGR |
|---|---|---|---|---|
| Equal weight 1/3 | 1.837 / 0.123 / 0.337 | 2.097 | 1.469 / 0.087 / 0.224 | 1.680 / 0.245 |
| Inverse-vol 0.40/0.17/0.43 | 1.897 / 0.090 / 0.296 | 2.193 | 1.483 / 0.071 / 0.199 | 1.642 / 0.197 |
| **Middle 0.37/0.25/0.38** | 1.893 / 0.105 / 0.316 | 2.172 | **1.499 / 0.076 / 0.212** | 1.694 / 0.221 |
| BTC-trim 0.45/0.25/0.30 | 1.897 / 0.109 / 0.323 | 2.177 | 1.508 / 0.078 / 0.222 | 1.726 / 0.238 |

UW-BTC (0.55 / 0.25 / 0.20) is a fifth case from the offline weighting study, computed on the same sleeve P&L. It was not in the researcher's four-blend rebuild. Same-close FULL / OOS / LATE Sharpe 1.621 / 1.526 / 1.426, FULL MDD 0.145, OOS CAGR 0.239. Delay 1: FULL / OOS Sharpe 1.889 / 1.507, OOS MDD 0.080, OOS CAGR 0.233. It is there so the grid around Middle is visible.

The inverse-vol weights, and Middle's ETH/BTC split, are fitted on in-sample volatilities, so their in-sample Sharpe is mildly flattered. Judge weights on OOS and LATE. PRE is a stress check only. ETH and BTC in-sample vols are nearly equal (0.164 vs 0.156 annualised), so Middle's split is close to 50/50 and the fit matters little.

Sleeves, same-close, platform FULL / OOS / LATE Sharpe: ETH A2 1.324 / 1.241 / 1.002; BNB 1.094 / 1.037 / 1.215; BTC 1.267 from 2021-10-09 (1.211 from its own 2021-08-30 start) / 1.068 / **0.646**.

### Risk contribution, the bootstrap tail, and the offline stress test

Offline. Risk shares are computed from sleeve P&L (same-close sleeve P&L is the platform series). The bootstrap is a joint stationary block bootstrap of the blend's daily P&L over one year, 4,000 paths. PRE is the Binance splice. None of this block is a platform result.

| Weighting | Risk share IS (E/B/T) | Risk share OOS | 1y MDD p95/p99, FULL, block 10 | block 20 | same, IS, block 10 | block 20 | PRE SR / MDD / CAGR (same-close) | PRE (delay 1) |
|---|---|---|---|---|---|---|---|---|
| Equal weight | 0.20 / **0.62** / 0.18 | 0.28 / 0.56 / 0.17 | 0.159 / 0.199 | 0.157 / 0.197 | 0.164 / 0.203 | 0.156 / 0.194 | 1.57 / 0.246 / 0.586 | 1.57 / 0.287 / 0.618 |
| Inverse-vol | 0.36 / 0.28 / 0.36 | 0.46 / 0.22 / 0.31 | 0.122 / 0.157 | 0.118 / 0.148 | 0.122 / 0.154 | 0.117 / 0.147 | 1.35 / 0.214 / 0.357 | 1.40 / 0.239 / 0.401 |
| **Middle** | 0.28 / 0.45 / 0.27 | 0.37 / 0.39 / 0.24 | 0.138 / 0.178 | 0.134 / 0.169 | 0.138 / 0.176 | 0.134 / 0.163 | 1.49 / 0.229 / 0.468 | 1.52 / 0.263 / 0.507 |
| BTC-trim | 0.35 / 0.45 / 0.20 | 0.46 / 0.37 / 0.17 | 0.141 / 0.178 | 0.138 / 0.173 | 0.143 / 0.184 | 0.136 / 0.168 | 1.53 / 0.220 / 0.496 | 1.56 / 0.256 / 0.531 |
| UW-BTC | 0.44 / 0.44 / 0.12 | 0.56 / 0.34 / 0.10 | 0.144 / 0.180 | 0.143 / 0.180 | 0.146 / 0.185 | 0.145 / 0.178 | 1.56 / 0.208 / 0.531 | 1.59 / 0.247 / 0.561 |

Delay-1 one-year MDD p95 / p99, FULL sample, block 10: equal weight 0.127 / 0.159, inverse-vol 0.095 / 0.120, Middle 0.107 / 0.137, BTC-trim 0.110 / 0.137.

PRE risk share, same-close: equal weight gives BNB 72% of the risk. Middle is 0.27 / 0.57 / 0.16.

**Why Middle, on platform-reproducible evidence.**

- All five weightings sit within 0.03 of each other on out-of-sample Sharpe (1.51–1.54 same-close, 1.47–1.51 delay 1). The out-of-sample Sharpe standard error is about 0.6 (the width of Scout's intervals), so Sharpe cannot choose the weights. The choice is a risk budget.
- Middle ties for the best out-of-sample Sharpe at both delays.
- Against equal weight, it cuts BNB's in-sample risk share from 62% to 45%, out-of-sample max drawdown from 0.110 to 0.095, and the bootstrap one-year p95 max drawdown from 0.159 to 0.138. The cost is 1.3 percentage points of out-of-sample CAGR (0.222 against 0.235).
- Against inverse-vol, it keeps more return (out-of-sample CAGR 0.222 against 0.208, LATE Sharpe 1.426 against 1.346). It does not hand about 64–77% of the risk to the ETH+BTC pair. Those two correlate 0.61, and ETH is long on 93% of BTC's active days.
- The offline stress test points the same way (PRE Sharpe 1.49 against inverse-vol 1.35). It was not needed for the choice.

**BTC-trim is the alternative.**

- On Bybit it ties Middle: out-of-sample Sharpe 1.540 against 1.541, out-of-sample CAGR 0.8 percentage points higher, LATE Sharpe 0.004 higher. FULL max drawdown is worse (0.130 against 0.119), and so is the in-sample bootstrap one-year p95 (0.143 against 0.138).
- Its case rests on BTC's unseen 2018–21 Sharpe of 0.14 (offline stress only), BTC's LATE Sharpe of 0.646, and the BTC CUSUM alarm in the out-of-sample window. The last two are Bybit, and they are a sub-window of OOS.
- It is the one to pick if Alfred wants to act on Scout's "size BTC down" reading of the [validation study](strategy-persistence-validation.md).

Sensitivity grid (BNB 0.20 / 0.25 / 0.30 × BTC from 0.38 down to 0.15): out-of-sample Sharpe stays between 1.50 and 1.54 across the whole grid at same-close. Each extra 0.05 of BNB weight adds roughly 0.1 to BNB's risk share and about 1 percentage point to the bootstrap one-year p95.

### Volatility target

Offline. Scale k = (equal-weight in-sample blend vol) / (candidate in-sample blend vol): 1.19 inverse-vol, 1.10 Middle, 1.10 BTC-trim, 1.08 UW-BTC. Gross cap 1.0. The cap binds on 5.4% of out-of-sample days, the days when ETH and BTC are both long.

| Book | OOS SR / MDD / CAGR |
|---|---|
| Middle, same-close, no vol target | 1.54 / 0.095 / 0.222 |
| Middle + vol target, same-close | 1.50 / 0.102 / 0.222 |
| Inverse-vol, same-close, no vol target | 1.53 / 0.092 / 0.208 |
| Inverse-vol + vol target, same-close | 1.47 / 0.104 / 0.206 |

Middle with the vol target has FULL CAGR 0.274 against 0.267 without it. Delay 1 shows the same pattern: the target adds exposure on single-sleeve days, and the cap clips the joint ETH+BTC breakout days that carry the return (see [Concentration](#concentration)). Out-of-sample return is not restored, and Sharpe falls. **No vol target.**

## Family-ensemble sizing

Offline. This is Scout's ensemble: the average position over the grid (ETH 5,040 cells, BNB and BTC 315 each), fractional from 0 to 1. The platform cannot express it. See [Proposal A](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-a-fractional-weights) and [Proposal B](../design/2026-09-26-fractional-sizing-stateful-exits.md#proposal-b-an-average-then-a-volatility-weight). PRE is the offline stress test.

| Blend (Middle weights) | Delay | FULL SR / MDD | OOS SR / MDD / CAGR | LATE SR | PRE SR / MDD / CAGR |
|---|---|---|---|---|---|
| Finalists | 0 | 1.64 / 0.119 | 1.54 / 0.095 / 0.222 | 1.43 | 1.49 / 0.229 / 0.468 |
| All three ensembles | 0 | 1.01 / 0.247 | 0.94 / 0.153 / 0.155 | 0.81 | 1.89 / 0.259 / 0.807 |
| Finalists ETH/BNB + BTC ensemble | 0 | 1.34 / 0.200 | 1.31 / 0.122 / 0.222 | 1.14 | 1.83 / 0.230 / 0.753 |
| Finalists | 1 | 1.90 / 0.105 | 1.50 / 0.076 / 0.212 | 1.69 | 1.52 / 0.263 / 0.507 |
| All three ensembles | 1 | 0.96 / 0.283 | 0.71 / 0.174 / 0.111 | 0.70 | 1.97 / 0.262 / 0.870 |
| Finalists ETH/BNB + BTC ensemble | 1 | 1.47 / 0.171 | 1.24 / 0.126 / 0.205 | 1.31 | 1.84 / 0.256 / 0.773 |

Re-weighting by the ensembles' own in-sample vols (0.43 / 0.25 / 0.32) gives out-of-sample Sharpe 0.95 at same-close. Scaling to the finalist blend's in-sample vol (k = 0.81) gives 0.94. The ensembles hold far more often (in-sample average exposure ETH 0.19, BNB 0.36, BTC 0.36) and are more correlated with each other, so the blend loses its diversification.

The ensemble wins on the offline stress test, as Scout found per sleeve, and it is worse on every Bybit window. Under the Bybit-decides rule it does not improve the blend. Part of the gap is hindsight: the finalists were chosen on 2021–26. Revisit after PR #63, with walk-forward rather than this comparison.

## Blend drawdown tiers

Offline. Calibrated on in-sample Bybit only (2021-10-09 to 2024-06-30): joint stationary block bootstrap, 4,000 paths, the max over block lengths 10 and 20, rounded up to 0.5 percentage points. Drawdown is the full-size shadow blend's drawdown from its peak since go-live. T2 cuts to 0.5×. T3 cuts to 0.25×, or to flat if Alfred chooses that. Hysteresis: 0.25× steps back to 0.5× once drawdown is under T2, and 0.5× steps back to 1× once drawdown is under T1.

| Blend | Calibrated on | 1y MDD p95 (block 10 / 20) | 1y p99 | 3y p99 | Tiers T1 / T2 / T3 |
|---|---|---|---|---|---|
| **Middle** | IS same-close | 0.139 / 0.134 | 0.173 / 0.164 | 0.226 / 0.222 | **14.0% / 17.5% / 23.0%** (rerun: **14 / 18 / 23.5**) |
| Middle | IS delay 1 | 0.100 / 0.091 | 0.124 / 0.112 | 0.147 / 0.132 | 10.5 / 12.5 / 15.0 |
| Equal weight | IS same-close | 0.165 / 0.155 | 0.209 / 0.193 | 0.268 / 0.256 | 16.5 / 21.0 / 27.0 |
| BTC-trim | IS same-close | 0.146 / 0.139 | 0.180 / 0.171 | 0.233 / 0.235 | 15.0 / 18.0 / 23.5 |

The proposed levels are the rerun, **14 / 18 / 23.5**. The fire record below uses the first draw, 14 / 17.5 / 23, which is the same rule within the 0.5 percentage-point bootstrap noise.

| Window | Delay | Shadow MDD | Days at or above T1 (review) | T2 fires | T3 fires | CAGR, no rule → rule | MDD, no rule → rule |
|---|---|---|---|---|---|---|---|
| IS | 0 / 1 | 0.119 / 0.074 | 0 | 0 | 0 | unchanged | unchanged |
| OOS | 0 / 1 | 0.095 / 0.076 | 0 | 0 | 0 | unchanged (0.222 / 0.212) | unchanged |
| PRE stress | 0 | 0.229 | 441 of 1,218 (20 crossings) | 3 (2019-07-16, 2019-08-21, 2020-03-07) | 0 | 0.468 → 0.428 | 0.229 → **0.242** (worse: whipsaw) |
| PRE stress | 1 | 0.263 | 450 (15 crossings) | 4 | 1 (2020-05-10) | 0.507 → 0.467 (flat variant 0.457) | 0.263 → 0.244 (flat 0.251) |
| PRE stress, delay-1-calibrated tiers | 1 | 0.263 | 554 | 6 | 7 | 0.507 → 0.409 (flat 0.390) | 0.263 → 0.200 (flat 0.206) |

The tiers never fire on Bybit in-sample or out-of-sample, so they cost nothing on platform-reproducible data. On the offline stress test they cost about 4 percentage points of CAGR at the same-close levels, and they cut max drawdown by at most about 2 percentage points (at same-close the drawdown rose, because of whipsaw).

Calibrate on same-close. The delay-1 in-sample series is unusually smooth (in-sample Sharpe 2.19 against 1.72), so its tiers are tight and fire much more often.

At T3, flat cost slightly more on the stress test (delay-1 CAGR 0.457 against 0.467), so the proposal is **0.25×**. Alfred can still choose flat.

An earlier draft used 16 / 20 / 24, set on the full sample for equal weight. That draft is superseded. Equal weight recalibrated on the in-sample window only gives 16.5 / 21 / 27. Middle gives 14 / 18 / 23.5.

## Blend-level kill switch

Offline. Three versions were tried. The recommended one is version 2 with re-entry B, already summarised in the [record](#record-of-the-recommended-rule).

**Version 1 is rejected.** It is Scout's rule applied to the blend: the CUSUM, plus a pointwise 95% / 99% band on max-drawdown-to-date (block length 10). The chance of any cut within one year when the in-sample edge is intact is **0.33** at same-close and **0.30** at delay 1. A pointwise band is crossed somewhere far more often than 5%. At same-close, out-of-sample had 0 cuts, and the stress test had 4 cuts (3 false), with CAGR 0.468 → 0.365. With delay-1 calibration, out-of-sample had 1 cut (CUSUM 2026-06-24, false; CAGR 0.212 → 0.187; block length 20 adds a 2024-11-04 cut and CAGR falls to 0.131), and the stress test had 9 cuts (8 false), CAGR 0.507 → 0.217.

**Version 2** is the CUSUM (5% per year) plus the fixed tiers from the previous section. The chance of a cut within one year is **0.046** at same-close. Re-entry, same-close calibration:

| Re-entry | IS, same-close: cuts, CAGR | OOS, same-close | PRE, same-close: cuts / false, days below 1×, CAGR, MDD | PRE, delay 1 |
|---|---|---|---|---|
| A, sticky: CUSUM not reset, 30-day minimum | 1, 0.306 → 0.272 | 0 cuts | 2 / 2, 499 days, 0.468 → 0.369, 0.229 → 0.202 | 3 / 2, 567 days, 0.507 → 0.430, 0.263 → 0.211 |
| **B: CUSUM reset at the cut, 30-day minimum** | 1, 0.306 → 0.307 | 0 cuts | 3 / 3, 217 days, 0.468 → 0.428, 0.229 → 0.223 | 4 / 3, 415 days, 0.507 → 0.447, 0.263 → 0.256 |
| C: reset, 90-day minimum | 1, 0.306 → 0.269 | 0 cuts | 3 / 3, 277 days, 0.468 → 0.367, 0.229 → 0.223 | 4 / 3, 538 days, 0.507 → 0.420, 0.263 → 0.244 |

B is the cheapest on in-sample Bybit, which is the window that decides. The stress test agrees. Against B, variant A costs a further 6 percentage points of stress-test CAGR at same-close (0.369 against 0.428) for about 2 percentage points less max drawdown (0.202 against 0.223).

**Per-sleeve alarms against the blend alarm.** Version 2, re-entry A on both, each sleeve calibrated on its own in-sample window: ETH tiers 17 / 21.5 / 29.5% and h 29.6; BNB 39 / 46.5 / 59.5% and h 29.1; BTC 12 / 15.5 / 21% and h 23.8.

| Window | Delay | Blend alarm: cuts / false, CAGR | Per-sleeve alarms: cuts / false, CAGR, MDD |
|---|---|---|---|
| IS | 0 | 1 / 1, 0.272 | 2 / 2 (ETH 2023-07-02, BNB 2023-06-24), 0.262, 0.113 |
| OOS | 0 | 0, 0.222 | 1 / 1 (BTC CUSUM 2026-01-29, forward +8.6%), 0.214, 0.090 |
| PRE stress | 0 | 2 / 2, 0.369 | 7 / 5, 0.366, 0.210 |
| OOS | 1 | 0, 0.212 | 1 / 1 (BTC CUSUM 2026-04-19), 0.206 |
| PRE stress | 1 | 3 / 2, 0.430 | 8 / 4, 0.456, 0.227 |

Per-sleeve alarms fire two to four times as often. They cost about the same as the blend alarm on the same-close stress test, and less at delay 1. Scout's BTC out-of-sample CUSUM is 2026-04-18. This calibration (in-sample from 2021-10-09, a different seed, h 23.8 against Scout's 25.6) fires on 2026-01-29 at same-close and 2026-04-19 at delay 1, so the date is sensitive to the calibration. **The blend alarm drives size. Per-sleeve alarms drive review only, especially BTC. They do not cut automatically.**

## Concentration

Offline arithmetic. The top N days are set to zero P&L. Per-sleeve inputs are the platform series. Buy-and-hold is context.

| Series (same-close) | Period | Total return | ex top 5 | ex top 10 | ex top 20 | Top 10 share of log return |
|---|---|---|---|---|---|---|
| **Middle blend** | FULL | 2.243 (CAGR 0.267) | 1.315 (0.184) | 0.804 (0.126) | 0.228 (0.042) | 50% |
| **Middle blend** | OOS | 0.566 (0.222) | 0.183 (0.078) | **0.001 (0.000)** | −0.177 | **100%** |
| Middle blend | PRE stress | 2.604 (0.468) | 1.093 | 0.510 | −0.092 | 68% |
| Equal weight | OOS | 0.603 | 0.218 | 0.020 | −0.180 | 96% |
| ETH | OOS | 0.578 | 0.061 | −0.179 | −0.352 | 143% |
| BNB | OOS | 0.824 | 0.213 | −0.091 | −0.431 | 116% |
| BTC | OOS | 0.320 | −0.032 | −0.149 | −0.234 | 158% |
| Buy-and-hold BTC / ETH / BNB | OOS | 0.340 / −0.217 / 0.334 | −0.191 / −0.633 / −0.229 | −0.429 / −0.794 / −0.472 | — | — |

Delay-1 Middle: OOS total return 0.538, and 0.007 once the top 10 days are removed. FULL 2.954, and 1.194 once the top 10 are removed.

The blend's out-of-sample return sits in about 10 days (1.2% of 817). Crypto trend exposure looks like this. Buy-and-hold is more concentrated still.

The top out-of-sample days are mostly joint breakouts (2024-11-09, 2024-11-11, 2024-11-21, 2025-05-09, 2025-05-10, 2026-08-20, 2026-08-21), with ETH and BNB, and usually BTC, long together. One of the top 10 (2024-12-03) is a single-sleeve BNB day. Diversifying across sleeves does not spread the upside tail.

Three consequences follow. A missed signal or an outage on a breakout day is the main operational risk. A size cut that happens to cover one of those days is expensive, which is why the stress-test cuts cost so much. The blend's Sharpe is fragile to a handful of days, which matches the wide intervals in Scout's study.

## Platform reconciliation

### Same-close blends, platform-confirmed

Round 7 on algodaemon.com matched each sleeve's daily P&L to the platform's own series, and confirmed sleeve FULL / IS / OOS / LATE Sharpe, sleeve correlations, and time in market.

The researcher then rebuilt the four blends from that platform daily P&L, on the common window 2021-10-09 to 2026-09-25 (1,813 days). The rebuild matched the offline expected values to three decimals. These are the platform-confirmed figures:

| Weighting (ETH/BNB/BTC) | FULL SR | FULL MDD | FULL CAGR | IS SR | OOS SR | OOS MDD | OOS CAGR | LATE SR |
|---|---|---|---|---|---|---|---|---|
| Middle 0.37/0.25/0.38 | 1.641 | 0.119 | 0.267 | 1.720 | 1.541 | 0.095 | 0.222 | 1.426 |
| BTC-trim 0.45/0.25/0.30 | 1.637 | 0.130 | 0.271 | 1.713 | 1.540 | 0.097 | 0.230 | 1.430 |
| Equal weight 1/3 | 1.593 | 0.122 | 0.284 | 1.660 | 1.511 | 0.110 | 0.235 | 1.452 |
| Inverse-vol 0.40/0.17/0.43 | 1.645 | 0.117 | 0.250 | 1.737 | 1.526 | 0.092 | 0.208 | 1.346 |

### Delay 1, engine copy

These rows come from an engine copy whose same-close sleeve P&L matches the platform exactly. They are not algodaemon.com runs. The window is 2021-10-10 to 2026-09-25 (1,812 days).

| Weighting (ETH/BNB/BTC) | FULL SR | FULL MDD | FULL CAGR | IS SR | OOS SR | OOS MDD | OOS CAGR | LATE SR |
|---|---|---|---|---|---|---|---|---|
| Middle 0.37/0.25/0.38 | 1.893 | 0.105 | 0.316 | 2.172 | 1.499 | 0.076 | 0.212 | 1.694 |
| BTC-trim 0.45/0.25/0.30 | 1.897 | 0.109 | 0.323 | 2.177 | 1.508 | 0.078 | 0.222 | 1.726 |
| Equal weight 1/3 | 1.837 | 0.123 | 0.337 | 2.097 | 1.469 | 0.087 | 0.224 | 1.680 |
| Inverse-vol 0.40/0.17/0.43 | 1.897 | 0.090 | 0.296 | 2.193 | 1.483 | 0.071 | 0.199 | 1.642 |

### FULL Sharpe on the platform's own start

For comparison with platform runs that start on 2021-07-01. The common-basis same-close column repeats the confirmed table above. The platform-start basis (2021-07-02 to 2026-09-25, 1,912 days, each sleeve's warm-up days counted as cash) is an offline reconstruction on the same series. Every delay-1 cell is the engine copy.

| Series | Platform start, warm-up as cash, same-close / delay 1 | Common basis from 2021-10-09 (delay 1 from 2021-10-10), same-close / delay 1 |
|---|---|---|
| ETH A2 | 1.324 (from 2021-10-09) / 1.574 (from 2021-10-10) | 1.324 / 1.574 |
| BNB 100/0.5 | 1.094 / 1.255 | 1.094 / 1.255 |
| BTC 60/2.25 | 1.211 (from 2021-08-30) / 1.445 (from 2021-08-31) | 1.267 / 1.458 |
| Equal weight 1/3 | 1.540 / 1.795 | 1.593 / 1.837 |
| Inverse-vol 0.40/0.17/0.43 | 1.585 / 1.857 | 1.645 / 1.897 |
| **Middle 0.37/0.25/0.38** | 1.584 / 1.851 | 1.641 / 1.893 |
| BTC-trim 0.45/0.25/0.30 | 1.583 / 1.853 | 1.637 / 1.897 |

Same-close sleeve FULL Sharpes in the first column (ETH 1.324, BNB 1.094, BTC 1.211) are the platform figures from round 7. BTC's 1.267 is the same sleeve from the common 2021-10-09 start.

### Offline only

These cannot be reconciled with algodaemon.com:

- The 2018–21 Binance splice. Every PRE figure on this page.
- Bootstrap quantiles, and the drawdown-tier and CUSUM levels that are read off them. The resampling uses platform-identical in-sample P&L. The resampling itself is offline.
- Alarm and kill-switch simulations, including resize fees and the re-entry paths.
- The volatility-target and family-ensemble results. Fractional sizing does not exist on the platform ([PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63)).
- The concentration tables for the blends. The per-sleeve inputs are the platform series. The top-day arithmetic is offline.
- Risk shares. They are computed offline from the sleeve P&L.

## Caveats

- **The platform cannot size or blend.** The sleeve combiner and fractional sizing are [PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63), and they are still a proposal. Every blend, tier, and kill switch here is paper until that ships, or until the sleeves run as separate sub-accounts that are rebalanced by hand. Daily rebalancing at zero extra cost is an assumption.
- **The out-of-sample window is 817 days.** Scout's out-of-sample Sharpe interval is about ±1.2 per sleeve. A weight gap of 0.03 Sharpe is noise. Out-of-sample max drawdowns of 0.08–0.11 are one draw from a distribution whose one-year 95th percentile is 0.13–0.16.
- **The bootstrap reshuffles one regime.** Stationary block bootstrap, mean block 10 or 20 days, of in-sample 2021-10 to 2024-06 only. It cannot produce a regime that never happened in that window. Middle's PRE drawdowns (0.229 same-close, 0.263 delay 1) exceed the in-sample one-year 99th percentile (0.173) and sit next to the three-year 99th percentile (0.226). A rerun moves the tiers by about 0.5 percentage points.
- **The finalists were chosen with 2021–26 in view.** Every fixed-finalist figure on that span is optimistic. PRE is the only unseen stretch, and it is a different venue.
- **A false alarm here means the next 365 days of shadow return were positive.** Some of those windows are cut short at the end of the sample. On a sparse sleeve the CUSUM mostly measures time since the last win (Scout, [live monitoring](strategy-persistence-validation.md#7-live-monitoring-optional-rule-tested-historically)). At blend level this is milder, because BNB is long on 42% of days.
- **Engine delay-1 tables that include 2021-10-09** are one day longer than the 1,812-day delay-1 series in the reconciliation tables.
