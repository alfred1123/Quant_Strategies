# Design Doc: Alternative Data Sources

**Status:** Partially implemented (Glassnode + NasdaqDataLink classes exist in `src/data.py`; FMP/MarineTraffic/Aviationstack are still proposals).
**Date:** 2026-04-15
**Scope:** `src/data.py`, `api/`, REFDATA

---

## 1. Overview

Extend the backtest pipeline with **non-market-price** data sources — physical
and operational metrics that serve as leading/alternative indicators for equity
and crypto strategies. Each provider will be integrated as a new class in
`src/data.py` following the existing duck-typed interface
(`get_historical_price()` → DataFrame `['t', 'v']`).

```
┌──────────────────────────────────────────────────────────────────┐
│                        Backtest Pipeline                        │
│                                                                 │
│  Glassnode (on-chain) ──┐                                       │
│  FMP ──┤                                                        │
│  Nasdaq Data Link ──┤                                           │
│  MarineTraffic ──┼──► data.py ──► strat.py ──► perf.py         │
│  Aviationstack ──┤                                              │
│  (future: sat/foot traffic) ──┘                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Selection Criteria

| # | Criterion | Required |
|---|-----------|----------|
| C1 | **Non-market-price data** — physical or operational metrics (vessel movements, flight counts, treasury rates, industrial production) | Yes |
| C2 | **Industry-specific indicators** — tied to Maritime, Aviation, Macro, Industrial sectors | Yes |
| C3 | **10+ year historical depth** — at least a decade of archive for long-term trend analysis | Yes |
| C4 | **Daily time interval** — end-of-day resolution for consistent tracking | Yes |
| C5 | **Operational detail** — granular enough to track physical activity (e.g. ship counts at a specific harbor) | Preferred |
| C6 | **Affordable for solo/small-team** — under ~$100/mo for research-grade access | Preferred |

---

## 3. Provider Evaluation

### 3.1 Deferred — Glassnode On-Chain Metrics

| Attribute | Detail |
|-----------|--------|
| **Data type** | Crypto on-chain — SOPR, MVRV, active addresses, exchange net flows, NVT ratio, hash rate, supply in profit |
| **Historical depth** | 10+ years (BTC data since 2009 genesis block) |
| **Resolution** | Daily (`24h`) |
| **API limits** | Tier-dependent; free tier covers ~20 core metrics |
| **Cost** | Free (very limited) / $29/mo (Advanced) / **$799/mo (Professional — required for most useful metrics)** |
| **Key endpoints** | `/v1/metrics/indicators/sopr`, `/v1/metrics/market/mvrv`, `/v1/metrics/addresses/active_count`, `/v1/metrics/transactions/transfers_volume_to_exchanges_sum`, `/v1/metrics/mining/hash_rate_mean` |
| **Criteria met** | C1 ✓ C2 ✓ C3 ✓ C4 ✓ C6 ✗ (Professional tier is $799/mo) |

**Why deferred:** While the `Glassnode` class already exists in `data.py`, the
free tier is extremely limited — most actionable on-chain metrics (SOPR, MVRV,
exchange flows) require the Professional tier at **$799/mo**, which fails C6
(affordable for solo/small-team). The Advanced tier ($29/mo) unlocks some
metrics but with restricted resolution and history. Revisit when the platform
generates revenue or when Glassnode offers more affordable research-grade access.

**Integration sketch** (extend existing class):

```python
# Add to existing Glassnode class in data.py

@lru_cache(maxsize=32)
def get_onchain_metric(self, metric_path, symbol, start_date, end_date, resolution='24h'):
    """Fetch any on-chain metric from Glassnode.

    Args:
        metric_path: API metric path (e.g. 'indicators/sopr',
                     'market/mvrv', 'addresses/active_count').
        symbol: Crypto asset (e.g. 'BTC').
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        resolution: Data interval. Defaults to '24h'.

    Returns:
        DataFrame with columns ['t', 'v'].
    """
    since = int(time.mktime(time.strptime(start_date, "%Y-%m-%d")))
    until = int(time.mktime(time.strptime(end_date, "%Y-%m-%d")))
    res = requests.get(
        f"https://api.glassnode.com/v1/metrics/{metric_path}",
        params={"a": symbol, "s": since, "u": until, "i": resolution},
        headers={"X-Api-Key": self.__api_key},
        timeout=30,
    )
    res.raise_for_status()
    df = pd.read_json(res.text, convert_dates=['t'])
    logger.info("Glassnode %s: fetched %d rows for %s", metric_path, len(df), symbol)
    return df
```

**Backtest use cases:**
- SOPR < 1 as capitulation / buy signal
- MVRV Z-Score for cycle top/bottom detection
- Exchange net flow spike as sell pressure indicator
- Active address growth as network health / trend confirmation
- Hash rate drop as miner stress signal

---

### 3.2 Priority 1 — FMP (Financial Modeling Prep)

| Attribute | Detail |
|-----------|--------|
| **Data type** | Macro/Corporate — Treasury rates, economic indicators, financial ratios, sector performance |
| **Historical depth** | 30+ years |
| **Resolution** | Daily |
| **API limits** | 750 calls/min (Premium) |
| **Cost** | $49/mo (Premium) |
| **Key endpoints** | `/api/v3/treasury`, `/api/v3/economic`, `/api/v3/ratios/{symbol}`, `/api/v3/sector-performance` |
| **Criteria met** | C1 ✓ C2 ✓ C3 ✓ C4 ✓ C6 ✓ |

**Why P1:** Best cost-to-depth ratio. 30+ years of macro data at $49/mo. Treasury
rates and economic indicators are immediately usable as features in
multi-factor strategies. Clean REST API with JSON responses — fastest to
integrate.

**Integration sketch:**

```python
class FMP:
    """Retrieve macro/economic data from Financial Modeling Prep."""

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv("FMP_API_KEY")
        if not self.__api_key:
            raise ValueError("FMP_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date):
        # GET https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}
        ...
        return pd.DataFrame({"t": dates, "v": values})

    @lru_cache(maxsize=32)
    def get_treasury_rate(self, start_date, end_date):
        # GET /api/v3/treasury?from={start}&to={end}
        ...
        return pd.DataFrame({"t": dates, "v": rates})

    @lru_cache(maxsize=32)
    def get_economic_indicator(self, indicator, start_date, end_date):
        # GET /api/v4/economic?name={indicator}&from={start}&to={end}
        ...
        return pd.DataFrame({"t": dates, "v": values})
```

**Backtest use cases:**
- Treasury yield as regime filter (risk-on vs risk-off)
- Sector performance as rotation signal
- Financial ratios as value factor overlay

---

### 3.3 Priority 2 — Nasdaq Data Link (formerly Quandl)

| Attribute | Detail |
|-----------|--------|
| **Data type** | Industrial production, commodities, macro series |
| **Historical depth** | 30–50+ years (dataset-dependent) |
| **Resolution** | Daily (most series) |
| **API limits** | Varies by dataset; 50 calls/day on free tier |
| **Cost** | Free (limited) to $50–100+/mo for premium datasets |
| **Key datasets** | `FRED/INDPRO` (Industrial Production), `CHRIS/CME_CL1` (Crude Oil), `FRED/DFF` (Fed Funds Rate) |
| **Criteria met** | C1 ✓ C2 ✓ C3 ✓ C4 ✓ C6 ✓ |

**Why P2:** Unmatched historical depth (50+ years for many FRED series). Free
tier covers several core macro indicators. The `nasdaqdatalink` Python package
provides a clean pandas interface — minimal HTTP plumbing needed.

**Integration sketch:**

```python
class NasdaqDataLink:
    """Retrieve economic/industrial data from Nasdaq Data Link (Quandl)."""

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv("NASDAQ_DATA_LINK_API_KEY")
        if not self.__api_key:
            raise ValueError("NASDAQ_DATA_LINK_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_historical_price(self, dataset, start_date, end_date):
        # nasdaqdatalink.get(dataset, start_date=..., end_date=...)
        ...
        return pd.DataFrame({"t": dates, "v": values})
```

**Backtest use cases:**
- Industrial production as economic cycle indicator
- Crude oil price as inflation/energy sector proxy
- Fed Funds Rate as monetary policy regime signal

#### Targeted Nasdaq Data Link Datasets — Industrial & Alternative Metrics

All fetched via `NasdaqDataLink.get_table_data()` or `NasdaqDataLink.get_historical_price()` (APP_ID = 4).

| Category | Metric Name | Description | API Table Code | Column / Path |
|----------|-------------|-------------|---------------|---------------|
| Machinery Activity | Machine Movement | 7-day rolling sum of physical machine moves | `NDAQ/GIALST` | `move_rollsum` |
| Machinery Activity | Equipment Runtime | Cumulative hours of machine movement (7-day roll) | `NDAQ/GIALST` | `runtime_rollsum` |
| Machinery Activity | Active Machine Count | Unique count of active machines recorded daily | `NDAQ/GIALST` | `count_rollsum` |
| Machinery Activity | Equipment Type | Category of machinery (e.g. Construction, Mining) | `NDAQ/GIALST` | `equip_type` |
| Supply Chain | Accounts Receivable | Daily B2B payment behavior and credit patterns | `NDAQ/CSP` | — |
| Supply Chain | Revenue Dependency | % of revenue tied to specific industrial partners | `NDAQ/CSP` | — |
| ESG & Risk | Risk Incident Alerts | Daily environmental or labor strike notifications | `REPRISK/TR` | — |
| ESG & Risk | Carbon Estimates | Daily/periodic modeled GHG emission outputs | `NDAQ/ESG` | — |
| Thematic | Industrial Exposure | Daily score (0–1) of exposure to "Metal Supply" | `NDAQ/GFT` | — |
| Corporate | Daily List | Daily tracking of listings, delistings, and name changes | `NDAQ/NDL` | — |

---

### 3.4 Priority 3 — MarineTraffic

| Attribute | Detail |
|-----------|--------|
| **Data type** | Maritime — port calls, vessel tracks, ship counts per harbor |
| **Historical depth** | 15+ years (archived since 2009) |
| **Resolution** | Daily (aggregated from event-level) |
| **API limits** | Varies by contract; credit-based system |
| **Cost** | ~£10–£100+/mo depending on data scope |
| **Key endpoints** | `EV01` (Vessel Historical Track), `EV03` (Port Calls), `VI06` (Voyage Info) |
| **Criteria met** | C1 ✓ C2 ✓ C3 ✓ C4 ✓ C5 ✓ |

**Why P3:** Only provider that satisfies C5 (operational detail — ship counts at
a specific harbor). 15+ year history is solid. However, credit-based pricing is
opaque and per-vessel queries may be expensive at scale. Requires more complex
aggregation logic (port-call events → daily ship counts).

**Integration sketch:**

```python
class MarineTraffic:
    """Retrieve port call and vessel data from MarineTraffic API."""

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv("MARINETRAFFIC_API_KEY")
        if not self.__api_key:
            raise ValueError("MARINETRAFFIC_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_port_calls(self, port_id, start_date, end_date):
        # GET /exportportcalls/v:6/{api_key}/portid:{port_id}/...
        # Aggregate events → daily ship count
        ...
        return pd.DataFrame({"t": dates, "v": daily_ship_counts})

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date):
        # Wrapper: symbol = port_id, v = daily ship count
        return self.get_port_calls(symbol, start_date, end_date)
```

**Backtest use cases:**
- Harbor ship count as trade-volume proxy (e.g. Shanghai, Rotterdam)
- Container vessel frequency as supply-chain leading indicator
- Tanker traffic at oil terminals as crude demand signal

---

### 3.5 Priority 4 — Aviationstack

| Attribute | Detail |
|-----------|--------|
| **Data type** | Aviation — daily flight counts, airport traffic |
| **Historical depth** | Typically <10 years (standard plans) |
| **Resolution** | Daily |
| **API limits** | 10,000+ calls/mo (paid) |
| **Cost** | $49.99+/mo |
| **Key endpoints** | `/v1/flights` (historical), `/v1/airports` |
| **Criteria met** | C1 ✓ C2 ✓ C3 ✗ C4 ✓ C6 ✓ |

**Why P4:** Fails C3 (10+ year history) on standard plans. Useful for aviation
sector analysis but the shallow archive limits long-term backtesting. Similar
cost to FMP but far less historical depth.

**Integration sketch:**

```python
class Aviationstack:
    """Retrieve daily flight data from Aviationstack."""

    def __init__(self) -> None:
        load_dotenv()
        self.__api_key = os.getenv("AVIATIONSTACK_API_KEY")
        if not self.__api_key:
            raise ValueError("AVIATIONSTACK_API_KEY must be set in .env")

    @lru_cache(maxsize=32)
    def get_historical_price(self, airport_iata, start_date, end_date):
        # Paginate /v1/flights?dep_iata={airport}&flight_date={date}
        # Aggregate → daily flight count
        ...
        return pd.DataFrame({"t": dates, "v": daily_flight_counts})
```

---

### 3.6 Deferred — Satellite & Foot Traffic

| Provider | Data Type | Why Deferred |
|----------|-----------|-------------|
| **Planet Labs** | Satellite imagery (ship/truck counts) | Enterprise pricing, complex CV pipeline needed |
| **Unacast** | Retail foot traffic | $1,000+/mo, mobile signal data has privacy concerns |
| **Vizion API** | Container tracking | Custom pricing, narrow logistics scope |
| **SkyFi** | On-demand satellite | Pay-per-image, not suited for daily time series |
| **GrowthFactor** | Retail foot traffic | $400–5,000/mo, US-focused |
| **OAG** | Institutional aviation stats | Institutional pricing, overlaps Aviationstack |

These providers are either too expensive for solo research or require
non-trivial processing pipelines (computer vision for satellite imagery).
Revisit when the platform generates revenue or when a specific strategy demands
this data.

---

## 4. Priority Ranking & Rationale

| Rank | Provider | Cost | History | Effort | Score |
|------|----------|------|---------|--------|-------|
| **P1** | FMP | $49/mo | 30+ yr | Low — clean REST JSON | ★★★★★ |
| **P2** | Nasdaq Data Link | $0–50/mo | 50+ yr | Low — Python SDK | ★★★★☆ |
| **P3** | MarineTraffic | £10–100/mo | 15+ yr | Medium — event aggregation | ★★★☆☆ |
| **P4** | Aviationstack | $50/mo | <10 yr | Medium — pagination + aggregation | ★★☆☆☆ |
| **—** | Glassnode (on-chain) | $29–799/mo | 10+ yr | Minimal — extend existing class | Deferred (cost) |
| **—** | Satellite/Foot Traffic | $400–5K/mo | Varies | High — CV/enterprise | Deferred |

**Recommended order:** FMP → Nasdaq Data Link → MarineTraffic → Aviationstack.

**Rationale:** FMP offers the best cost-to-depth ratio ($49/mo for 30+ years of
macro data) and requires minimal integration effort (clean REST JSON). Nasdaq
Data Link follows with unmatched historical depth and a free tier. MarineTraffic
unlocks the unique harbor-tracking use case but needs event-to-daily aggregation.
Aviationstack is lowest priority due to shallow history. Glassnode on-chain
metrics are deferred until the Professional tier ($799/mo) becomes justifiable.

---

## 5. Integration Pattern

All new sources follow the existing `data.py` duck-typed interface:

```python
class <Source>:
    def __init__(self) -> None:
        # Load API key from .env, raise ValueError if missing

    @lru_cache(maxsize=32)
    def get_historical_price(self, symbol, start_date, end_date) -> pd.DataFrame:
        # Returns DataFrame with columns ['t', 'v']
        # t = YYYY-MM-DD date strings
        # v = float metric values
```

### Pipeline wiring

1. **REFDATA registration:** Add a row to `REFDATA.APP` (the canonical app/data-source table — not a separate `DATA_SOURCE` table). The `App` row drives the `Data Source` dropdown in the SPA (`useApps()` hook).
2. **`main.py` dispatch:** Add source to the data-fetch dispatch logic. (CLI currently hard-wires `YahooFinance`; see [CLI Backtest](../guides/cli-backtest.md).)
3. **API access:** Pulls already happen indirectly through `BacktestCache.get_or_fetch_payload()`. A direct `GET /api/v1/data/{source}/{symbol}` endpoint is **not** exposed today.
4. **env var:** `<SOURCE>_API_KEY` in `.env` and SSM Parameter Store (`/quant/{env}/<SOURCE>_API_KEY`).

### Rate limiting

| Source | Limit | Strategy |
|--------|-------|----------|
| FMP | 750/min | Simple `time.sleep(0.08)` between calls |
| Nasdaq Data Link | 50/day (free) | Cache aggressively; batch date ranges |
| MarineTraffic | Credit-based | Pre-aggregate port calls; minimize API hits |
| Aviationstack | 10K/mo | One call per airport-day; local cache |

---

## 6. REFDATA Changes

Add a new row to **`REFDATA.APP`** (single source-of-truth for data-source dropdowns) per provider — wrapped in a Liquibase changeset:

```sql
-- FMP
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, USER_ID, UPDATED_AT)
VALUES ('fmp', 'Financial Modeling Prep', 'alfcheun', now());

-- Nasdaq Data Link
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, USER_ID, UPDATED_AT)
VALUES ('nasdaq_data_link', 'Nasdaq Data Link', 'alfcheun', now());
```

The frontend's `useApps()` hook will pick them up automatically after `POST /api/v1/refdata/refresh`.

---

## 7. Open Questions

| # | Question | Impact |
|---|----------|--------|
| Q1 | Should alternative data metrics use the same `['t', 'v']` interface or extend to multi-column? | Interface design — affects all downstream modules |
| Q2 | Store fetched alternative data in PostgreSQL for caching, or rely on `@lru_cache` only? | Cost control — reduces API calls on repeated backtests |
| Q3 | How to handle mixed frequencies (some series skip weekends/holidays)? | Data alignment with market price series |
| Q4 | Should MarineTraffic aggregation (events → daily counts) happen at fetch time or in `strat.py`? | Separation of concerns |

---

## 8. Next Steps

1. **Sign up for FMP API key** — verify endpoint responses against docs.
2. **Implement `FMP` class** in `data.py` with treasury rate + economic indicator methods.
3. **Add FMP unit tests** with mocked API responses.
4. **Build macro overlay strategy** — e.g. BTC + Treasury yield regime filter.
5. **Repeat for Nasdaq Data Link** (P2) once FMP is validated.
6. **Glassnode on-chain** — revisit when Professional tier cost is justifiable.
