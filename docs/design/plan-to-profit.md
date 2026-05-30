# Plan to Profit

!!! info "Status"
    **Planning — derived from product notes.** This document turns informal goals into a phased roadmap. It does not replace detailed design docs; it links to them and records open decisions.

**Source notes:** `../notes/plan_to_profit.md` (workspace sibling)

**North star:** Run the current best backtested strategy live on Bybit (Bollinger-band price signal), prove profitability with daily Sharpe reconciliation, and grow the React SPA into a two-tab product (**Backtest** | **Trade**).

---

## 1. Current Strategy & Confidence

| Item | Detail |
|------|--------|
| **Live candidate** | Bybit execution, Bollinger band on **price** |
| **Backtest Sharpe** | ~1.22 (historical) |
| **Expected live Sharpe** | ~1.08 (haircut vs backtest) |
| **Risk** | Sharpe may degrade over time — must monitor, not assume static edge |
| **Why it matters** | This is the **Phase 0** anchor: keep the strategy running while the profit pipeline is built around it |

**Immediate engineering implication:** Phase 1 deliverables should not block on perfect UI; they should unblock **deploy → execute → log → reconcile**.

---

## 2. Phased Roadmap

Work **one subphase at a time** — finish exit criteria before starting the next. Update the status column as you go (`—` → `in progress` → `done`).

### Progress tracker

| Subphase | Title | Status |
|----------|-------|--------|
| [0.1](#phase-01--strategy-health) | Strategy health | done |
| [0.2](#phase-02--host-capacity) | Host capacity | done |
| [0.3](#phase-03--deploy-topology-decision) | Deploy topology decision | done |
| [1.1](#phase-11--user-secrets) | User secrets | done |
| [1.2](#phase-12--trade-schema--apply-api) | Trade schema + apply API | done |
| [1.3](#phase-13--bybit-adapter-dry-run) | Bybit adapter (dry run) | — |
| [1.4](#phase-14--trade-ui-shell) | Trade UI shell | done |
| [1.5](#phase-15--exchange-config-ui) | Exchange config UI | done |
| [1.6](#phase-16--strategy-picker) | Strategy picker | — |
| [1.7](#phase-17--live-apply) | Live apply | — |
| [1.8](#phase-18--execution-log) | Execution log | — |
| [2.1](#phase-21--reconcile-data-model) | Reconcile data model | — |
| [2.2](#phase-22--daily-sharpe-job) | Daily Sharpe job | — |
| [2.3](#phase-23--reconcile-ui) | Reconcile UI | — |
| [2.4](#phase-24--telegram-error-alerts) | Telegram error alerts | — |
| [2.5](#phase-25--silent-failure-detection) | Silent failure detection | — |
| [3.1](#phase-31--top-nav--trade-tab) | Top nav + Trade tab | — |
| [3.2](#phase-32--strategy-ranking-backend) | Strategy ranking backend | — |
| [3.3](#phase-33--best-strategy-banner) | Best strategy banner | — |
| [3.4](#phase-34--backtest-side-nav) | Backtest side nav | — |
| [3.5](#phase-35--compact-queue-table) | Compact queue table | — |
| [3.6](#phase-36--job--strategy-detail-drawer) | Job / strategy detail drawer | — |
| [3.7](#phase-37--separate-trade-host-optional) | Separate TRADE host (optional) | — |

```mermaid
flowchart TB
  subgraph P0[Phase 0]
    P01[0.1 Health]
    P02[0.2 Capacity]
    P03[0.3 Topology]
    P01 --> P02 --> P03
  end
  subgraph P1[Phase 1]
    P11[1.1 Secrets]
    P12[1.2 Schema/API]
    P13[1.3 Dry run]
    P14[1.4 UI shell]
    P15[1.5 Config UI]
    P16[1.6 Picker]
    P17[1.7 Live]
    P18[1.8 Log]
    P11 --> P12 --> P13
    P14 --> P15
    P12 --> P16 --> P17 --> P18
    P13 --> P17
    P15 --> P17
  end
  subgraph P2[Phase 2]
    P21[2.1 DB]
    P22[2.2 Job]
    P23[2.3 UI]
    P24[2.4 Telegram]
    P25[2.5 Heartbeat]
    P21 --> P22 --> P23
    P24 --> P25
  end
  subgraph P3[Phase 3]
    P31[3.1 Nav]
    P32[3.2 Rank]
    P33[3.3 Banner]
    P34[3.4 Side nav]
    P35[3.5 Queue]
    P36[3.6 Drawer]
    P37[3.7 ECR]
    P31 --> P34
    P32 --> P33
    P35 --> P36
  end
  P0 --> P1 --> P2 --> P3
```

---

### Phase 0 — Operational baseline

**Phase goal:** Confirm the live edge still exists and the host plan won’t break when TRADE containers/jobs land.

#### Phase 0.1 — Strategy health

| | |
|---|---|
| **Depends on** | — |
| **Blocks** | 1.6, 1.7 (confidence in strategy id) |

**Scope:** Research sign-off only — **not** production trade tracking. Use existing backtest tooling (`python -m quant.cli --walk-forward`); do **not** build rolling-Sharpe scripts against historical bars for go/no-go.

**Tasks**

- [x] Run walk-forward on the live candidate (e.g. `btcusdt.crypto`, Bollinger / momentum) via CLI or queued optimize + WF.
- [x] Record OOS Sharpe, overfitting ratio, and chosen `window` / `signal` in a ticket or [decisions log](../decisions.md).
- [x] Agree go / no-go / watch for promoting that `strategy_id` into the Trade picker.

**Exit criteria:** Written note with walk-forward OOS metrics; live candidate `strategy_id` confirmed for Phase 1.6 / 1.7.

**Result (2026-05-20):** **WATCH** — `bollinger_momentum_60_1.75` on `btcusdt.crypto`. Full Sharpe 1.19; OOS (30%) 0.42; WF OOS negative. Dry-run/paper OK; defer live apply. See [phase-0.1-signoff.md](../archive/phase-0/phase-0.1-signoff.md) and decision #33.

---

#### Phase 0.2 — Host capacity

| | |
|---|---|
| **Depends on** | — (can run parallel with 0.1) |
| **Blocks** | 1.7, 3.7 |

**Tasks**

- [x] Capture current EC2 CPU/mem with API + worker + Redis (and any manual Bybit process).
- [x] Estimate headroom for +1 Docker service (trade worker or reconcile cron).
- [x] List which processes must move off the box first if headroom is tight.

**Exit criteria:** One-page capacity snapshot with “safe to add container Y/N” and rough CPU/mem budget.

**Result (2026-05-20):** t4g.small (2 GiB) — **NO** for +1 trade worker without upgrade; **YES** for daily reconcile cron. **Upgraded to t4g.medium** per decision #34. See [phase-0.2-capacity.md](../archive/phase-0/phase-0.2-capacity.md); live metrics: `bash aws/scripts/capacity_snapshot.sh` on EC2.

---

#### Phase 0.3 — Deploy topology decision

| | |
|---|---|
| **Depends on** | 0.2 |
| **Blocks** | 3.7 (execution only) |

**Tasks**

- [x] Decide timing: TRADE on same EC2 vs separate host vs ECR image.
- [x] Decide whether daily Sharpe job shares host with trade executor.
- [x] Log decision in [Decisions log](../decisions.md) (see [open decision #4](#8-open-decisions)).

**Exit criteria:** Recorded decision — no need to implement ECR yet unless chosen “now.”

**Result (2026-05-20):** **Same EC2** for Phase 1 TRADE + Phase 2 reconcile after **t4g.medium** upgrade. **ECR pull deploy adopted now** (before Phase 1 app work). Separate TRADE host only if needed in Phase 3.7. See [phase-0.3-topology.md](../archive/phase-0/phase-0.3-topology.md) and decision #35.

---

### Phase 1 — Fastest profit pipeline

**Phase goal:** Closed loop — configure credentials → pick backtested strategy → dry-run → live apply → see executions in UI.  
**Out of scope until Phase 3:** strategy JSON popup, full optimization browser, enlarged queue, best-strategy banner.

#### Phase 1.1 — User secrets

| | |
|---|---|
| **Depends on** | Auth (`CORE_ADMIN.APP_USER`) |
| **Blocks** | 1.3, 1.5, 1.7 |

**Scope:** Per-user **exchange API keys** in `CORE_ADMIN` only. No `TRADE.CONNECTION` table — runtime sessions to Bybit are ephemeral; the audit trail you care about is **`TRADE.EXECUTION_EVENT` / `TRADE.TRANSACTION`** (Phase 1.8), not “which connection was opened.”

**Tasks**

- [x] DDL: `CORE_ADMIN.API_CREDENTIAL` (soft-versioned; see below).
- [x] REFDATA: seed `bybit` row in `REFDATA.APP` (broker identified by `APP_ID`, not free-text exchange).
- [x] SPs: insert (new account / rotate keys) / get / revoke — **no raw DML** from Python.
- [x] App-layer Fernet encryption before `SP_INS_*`; key from SSM `EXCHANGE_SECRETS_KEY`.
- [x] API: `/api/v1/credentials` — masked read, write, rotate, revoke (never log or return full secrets).
- [x] Security review: multi-user prod does not store per-user exchange keys in `.env`.
- [x] Security: prod boot **fail-fast** without `EXCHANGE_SECRETS_KEY` (mirror `JWT_SECRET` — never reuse it).
- [x] Security: API response schemas exclude ciphertext columns; unit test GET never returns `*_CIPHERTEXT`.
- [x] Security: rate-limit `POST`/`PUT` `/api/v1/credentials` (same pattern as login — see [login.md §11.2](login.md#112-rate-limiting-defense-in-depth)).

**Data model — `CORE_ADMIN.API_CREDENTIAL`**

| Column | Notes |
|--------|--------|
| `API_CREDENTIAL_ID` | `INTEGER` — **not** `IDENTITY`; assigned in SP (`COALESCE(MAX(...), 0) + 1`) on **new account** |
| `API_CREDENTIAL_VID` | Soft-version; bump on **key rotation** only |
| `APP_USER_ID` | Owner (`UUID`, JWT `sub`) |
| `APP_ID` | `REFDATA.APP` — e.g. Bybit broker row |
| `LABEL` | User label (“Main”, “Subaccount”) |
| `API_KEY_CIPHERTEXT` / `API_SECRET_CIPHERTEXT` | Fernet blobs (encrypt in app before SP) |
| `IS_ACTIVE_IND` | `Y`/`N` — revoke |
| `IS_CURRENT_IND` | `Y`/`N` — current version |
| `CREATED_AT` | `TIMESTAMPTZ` — per row; **no `UPDATED_AT`** |

PK: `(API_CREDENTIAL_ID, API_CREDENTIAL_VID)`. No unique on `(APP_USER_ID, APP_ID)` — **multiple accounts per exchange** via distinct `API_CREDENTIAL_ID` values (1, 2, 3, …).

**Stored procedures**

| Procedure | Behaviour |
|-----------|-----------|
| `SP_INS_API_CREDENTIAL` | **New account** (`IN_API_CREDENTIAL_ID` NULL): assign next `API_CREDENTIAL_ID`, `VID=1`. **Rotate** (id set): demote current row, `VID := MAX(VID)+1`, insert. |
| `SP_GET_API_CREDENTIAL` | By `APP_USER_ID`; optional id; default `IS_CURRENT_IND='Y'` + `IS_ACTIVE_IND='Y'`. |
| `SP_UPD_API_CREDENTIAL_REVOKE` | Soft-version revoke: new row, `IS_ACTIVE_IND='N'`, cleared ciphertext. |

Optional `CORE_INS_LOG_PROC` on credential SPs only (security-sensitive writes).

**API (1.1 — no UI)**

| Method | Path |
|--------|------|
| `GET` | `/api/v1/credentials` |
| `GET` | `/api/v1/credentials/{api_credential_id}` |
| `POST` | `/api/v1/credentials` — body: `app_id`, `label`, `api_key`, `api_secret` |
| `PUT` | `/api/v1/credentials/{api_credential_id}` — rotate keys |
| `DELETE` | `/api/v1/credentials/{api_credential_id}` — revoke |

Responses: `api_key_masked`, `app_id`, `label`, `api_credential_id` — never full secrets.

**Application layer — reuse from auth**

Reuse login/JWT **plumbing**, not login **crypto**. Full table: [Login design §6.4](login.md#64-reuse-from-login--jwt-credential-api--phase-11).

| Reuse | Do not reuse |
|-------|----------------|
| `require_user`, `DbGateway` / `AuthRepo` pattern, SSM config, never log secrets, ownership scoping | JWT, Argon2, `SESSION_GEN`, decrypted-key cache |

Implement Fernet in `quant/shared/secrets_crypto.py`; `ApiCredentialRepo` calls `CORE_ADMIN.SP_*` only; router behind `require_user`.

**Explicitly out of scope for 1.1**

- `TRADE.CONNECTION` table or connection audit/history
- `CONFIG_JSON` or trade-default columns (add on `TRADE.DEPLOYMENT` or credential when needed)
- Bybit validation (1.3), Config UI (1.5)

**Exit criteria:** Test user saves Bybit keys (`app_id` from REFDATA) via API; GET returns masked credential; rotate bumps `API_CREDENTIAL_VID`; revoke sets inactive; second account on same exchange gets a new `API_CREDENTIAL_ID`. **Security:** prod refuses to start without `EXCHANGE_SECRETS_KEY`; GET/POST responses never include `*_CIPHERTEXT`; cross-user credential id returns **404** (not 403); `POST`/`PUT` credentials are rate-limited.

---

#### Phase 1.2 — Trade schema + apply API

| | |
|---|---|
| **Depends on** | — |
| **Blocks** | 1.3, 1.6, 1.7, 1.8, 2.1 |

**Tasks**

- [x] DDL: `TRADE.DEPLOYMENT`, `TRADE.EXECUTION_EVENT`, `TRADE.TRANSACTION` (per [Trade API](trade-api.md)). **No `TRADE.INTENT`** — signal computed in worker; see decision #38.
- [x] `TRADE.DEPLOYMENT` includes **`API_CREDENTIAL_ID INTEGER`** (points at current credential row via GET with `IS_CURRENT_IND='Y'`) — not a separate connection entity.
- [x] SP: create deployment linked to `BT.STRATEGY` id + `API_CREDENTIAL_ID`.
- [x] API: `POST` apply / `GET` deployment status (skeleton OK without exchange call).

**Exit criteria:** Deployment row persists with `strategy_id` and `api_credential_id`; status endpoint returns stored state.

---

#### Phase 1.3 — Bybit adapter (dry run)

| | |
|---|---|
| **Depends on** | 1.1, 1.2 |
| **Blocks** | 1.7 |

**Tasks**

- [ ] Implement `BybitAdapter` (or extend `quant/trade/`) with dry-run path.
- [ ] Validate credentials, `INST.PRODUCT_XREF` symbol mapping, sizing — no live orders.
- [ ] Return structured dry-run report (signals, intended side, errors).

**Exit criteria:** Dry-run API succeeds for test user against Bybit testnet or read-only validation path.

---

#### Phase 1.4 — Trade UI shell

| | |
|---|---|
| **Depends on** | React router |
| **Blocks** | 1.5, 1.6, 1.8, 3.1 |

**Tasks**

- [x] Add **Trade** route (`/trade/config`, `/trade/apply`) with layout: sidebar + main + bottom execution-log placeholder.
- [x] Sidebar nav entries: **Config** | **Trade**.
- [x] Auth-gate same as Backtest (`RequireAuth`).
- [x] **Toolbar** (compact, not full-width): **Exchange** filter · **Account** filter · **Paper / Live** toggle — shared via `TradeSessionContext`.
- [x] **Deployments table** on Trade page with Exchange + Account columns; rows filtered by toolbar selection.
- [x] Wire `GET /api/v1/trade/deployments` via `useDeployments()` (TanStack Query).

**Exit criteria:** Logged-in user navigates to Trade layout; sidebar switches Config ↔ Trade; toolbar filters deployments; execution-log panel is a placeholder.

**Result (2026-05-20):** `TradeLayout`, `TradeNavBar`, `TradeSessionContext`, `TradeConfigPage`, `TradeApplyPage` in `frontend/src/`. See [Frontend § Trade](../architecture/frontend.md#trade-ui-phase-14).

---

#### Phase 1.5 — Exchange config UI

| | |
|---|---|
| **Depends on** | 1.1, 1.4 |
| **Blocks** | 1.7 |

**Tasks**

- [x] **Accounts table** on Config page: Exchange · Account · Mode (Paper/Live) · masked API key · Status — click row to set toolbar account filter (`BrokerAccountsTable`).
- [x] **Multi-broker / multi-account** UX: toolbar **Exchange** + **Account** dropdowns filter deployments and highlight table rows (not one broker / one account).
- [x] Compact **Add account** form (Exchange, label, paper toggle, API key/secret).
- [x] **Paper / Live** mode toggle in toolbar (filters deployments by `is_paper_ind`; apply buttons reflect mode).
- [x] Wire **REFDATA.APP** broker dropdown (`app_id`) on add form.
- [x] Wire `GET` / `POST` / `PUT` / `DELETE` → `/api/v1/credentials`.
- [x] Enable save, rotate, revoke actions in table.
- [ ] Trade defaults (size, Telegram chat id) deferred until columns exist on `TRADE.DEPLOYMENT` or credential.

**Exit criteria:** User saves Bybit credential in UI and reload sees masked keys in the accounts table; can register **multiple accounts per broker** and filter Trade/deployments via toolbar.

**Result (2026-05-28):** `TradeConfigPage` + `BrokerAccountsTable` wired to `/api/v1/credentials`; REFDATA exchange dropdown; rotate/revoke dialogs. See [Frontend § Trade](../architecture/frontend.md#trade-ui-phase-14).

---

#### Phase 1.6 — Strategy picker

| | |
|---|---|
| **Depends on** | 1.2, 1.4, 0.1 (recommended) |
| **Blocks** | 1.7 |

**Scope:** Pick an **existing** `BT.STRATEGY` row for deployment — not build a new backtest config. Do **not** reuse Backtest `ConfigDrawer` / `FactorCard` (those edit REFDATA signal types for optimize requests). See [Trade API §2.1](trade-api.md#21-strategy-catalog--phase-16).

**Tasks**

- [ ] DDL: `BT.SP_LIST_STRATEGY` (or equivalent) — list current strategies (`IS_CURRENT_IND='Y'`) with optional latest-result stats; reads only.
- [ ] API module: `quant/api/strategies/` — `GET /api/v1/strategies` (id, vid, name, minimal stats); behind `require_user`. Full CRUD deferred — create/update stays on backtest queue path (`BT.SP_INS_STRATEGY` via jobs).
- [ ] Frontend: `frontend/src/api/strategies.ts` + `StrategyPicker` on Trade Apply — selectable list/table; no JSON drill-down.
- [ ] Selecting row sets active `{ strategy_id, strategy_vid }` for apply / deployment payload.
- [ ] **1.7 prep:** list response includes `user_id`; deployment create validates strategy ownership (see [§5.5](#55-auth--security-guardrails)).

**Architecture (decided)**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Backend** | New `quant/api/strategies/` reading `BT.STRATEGY` | Cross-cutting catalog; matches [trade-api.md §2.1](trade-api.md#21-strategy-catalog--phase-16). Not `quant/strategy/` (execution math) or `quant/trade/` (deployments only). |
| **Frontend** | New `StrategyPicker` + `useStrategies()` | Trade-specific UX. Extract to `components/strategy/` only when Backtest also needs the same picker (e.g. “Deploy this”). |
| **Do not** | Reuse Backtest config UI or move `quant/strategy/` to shared | Wrong domain — signal-type builder ≠ persisted strategy catalog. |

**Exit criteria:** User picks a strategy by name/id in UI; selection passed to apply payload as `strategy_id` + `strategy_vid`.

**Known gap (v1):** `BT.STRATEGY` rows are globally readable to any logged-in user today; ownership enforcement lands in **1.7** deployment create. See [login.md](login.md) and [§5.5](#55-auth--security-guardrails).

---

#### Phase 1.7 — Live apply

| | |
|---|---|
| **Depends on** | 1.2, 1.3, 1.5, 1.6 |
| **Blocks** | 1.8, 2.x |

**Tasks**

- [ ] UI: Dry-run button → show report; Apply button → confirm live.
- [ ] Backend: apply uses BT strategy config + deployment record + Bybit live path.
- [ ] Error responses surfaced in UI (Telegram deferred to 2.4).
- [ ] Security: server enforces `is_paper_ind` — UI Paper/Live toggle is **not** an auth boundary (see [§5.5](#55-auth--security-guardrails)).
- [ ] Security: live apply requires prior dry-run + explicit confirm payload; reject `is_paper_ind='N'` without both.
- [ ] Security: deployment create validates strategy **ownership** (`BT.STRATEGY` user matches `CurrentUser`).
- [ ] Security: `PATCH` deployment kill switch (`is_enabled_ind`) before first live apply (see [Trade API §4](trade-api.md#4-risk--safety)).

**Exit criteria:** **M1 — Pipeline** met: one real (or testnet) live apply completes end-to-end for Bollinger strategy. **Security:** backend rejects live apply without dry-run + confirm; paper/live cannot be bypassed via raw API; caller cannot deploy another user's strategy; deployment can be disabled via PATCH without DB access.

---

#### Phase 1.8 — Execution log

| | |
|---|---|
| **Depends on** | 1.2, 1.7, 1.4 |
| **Blocks** | 2.2 (live PnL inputs) |

**Tasks**

- [ ] SP: append execution rows to `TRADE.EXECUTION_EVENT` on submit/error; fills to `TRADE.TRANSACTION`.
- [ ] API: paginated transaction history per deployment.
- [ ] UI: bottom-right panel lists recent executions with refresh.

**Exit criteria:** After 1.7 apply, user sees at least one row in transaction history without DB access.

---

### Phase 2 — Prove profitability

**Phase goal:** Trust but verify — daily Sharpe vs backtest, loud failures, quiet success. Reconcile frequency can drop after stabilization.

#### Phase 2.1 — Reconcile data model

| | |
|---|---|
| **Depends on** | 1.2, 1.8 |
| **Blocks** | 2.2, 2.3 |

**Tasks**

- [ ] Design table(s) for daily deployment snapshots (live Sharpe, cumulative return, vs backtest expectation).
- [ ] Avoid full scan of `TRADE.EXECUTION_EVENT` / `BT.RESULT` each run — aggregate on write or nightly rollup.
- [ ] SP: insert daily snapshot; SP/GET: series for chart.

**Exit criteria:** Schema + procedures merged; manual insert of one test snapshot succeeds.

---

#### Phase 2.2 — Daily Sharpe job

| | |
|---|---|
| **Depends on** | 2.1, 1.8 |
| **Blocks** | 2.3 |

**Tasks**

- [ ] Scheduled job (cron / worker) runs once per day per active deployment.
- [ ] Computes live metrics vs stored backtest benchmark for same strategy.
- [ ] Idempotent per `(deployment_id, trade_date)`.

**Exit criteria:** Job runs manually twice; second run updates or no-ops without duplicate bad rows.

---

#### Phase 2.3 — Reconcile UI

| | |
|---|---|
| **Depends on** | 2.2, 1.4 |
| **Blocks** | — |

**Tasks**

- [ ] Trade page top-right: chart or summary of Sharpe / drift vs backtest.
- [ ] Show last reconcile timestamp and stale warning if &gt; 36h old.
- [ ] *(Nice-to-have)* Calendar-year live Sharpe table (Year | Sharpe | return) from reconcile snapshots — production tracking only, not backtest.

**Exit criteria:** User opens Trade and sees at least 7 days of reconcile data (or explicit “insufficient data”).

---

#### Phase 2.4 — Telegram error alerts

| | |
|---|---|
| **Depends on** | 1.7 |
| **Blocks** | 2.5 (optional coupling) |

**Tasks**

- [ ] User preference: Telegram chat id (Config or profile).
- [ ] Notify on apply failure, adapter errors, kill-switch trips — not on success heartbeats.
- [ ] Rate-limit duplicate alerts.

**Exit criteria:** Forced test error delivers one Telegram message; healthy apply sends none.

---

#### Phase 2.5 — Silent failure detection

| | |
|---|---|
| **Depends on** | 1.7, 2.4 (recommended) |
| **Blocks** | — |

**Tasks**

- [ ] Heartbeat or last-seen timestamp on deployment / worker.
- [ ] Alert if no heartbeat in N hours while deployment status = RUNNING.
- [ ] Document runbook: EC2 down, exchange disconnect, stuck process (see [open decision #5](#8-open-decisions)).

**Exit criteria:** **M2 — Proof** met: simulated missed heartbeat triggers Telegram; 24h healthy run triggers none.

---

### Phase 3 — Full product UX

**Phase goal:** Research and operations in one app — ranked strategies, structured backtest nav, rich queue UX. Can overlap Phase 2 subphases once M1 is done.

#### Phase 3.1 — Top nav + Trade tab

| | |
|---|---|
| **Depends on** | 1.4 |
| **Blocks** | 3.4 |

**Tasks**

- [ ] Top navigation: **Backtest** | **Trade** tabs.
- [ ] Route each tab to its own layout shell with side nav slot.

**Exit criteria:** Tab switch preserves auth; URLs deep-link (`/backtest`, `/trade`).

---

#### Phase 3.2 — Strategy ranking backend

| | |
|---|---|
| **Depends on** | [§3 Prerequisites](#3-prerequisites-data-model--ranking) |
| **Blocks** | 3.3 |

**Tasks**

- [ ] Add/queryable strategy summary columns (Sharpe, overfitting ratio, etc.).
- [ ] Background job writes rank cache (not computed on every page load).
- [ ] Define ranking formula and tie-break rules.

**Exit criteria:** `GET` rank endpoint returns ordered list from cache with `cached_at` timestamp.

---

#### Phase 3.3 — Best strategy banner

| | |
|---|---|
| **Depends on** | 3.2, 3.1 |
| **Blocks** | — |

**Tasks**

- [ ] Backtest page top-right: show #1 ranked strategy (name + key metrics).
- [ ] Link to strategy detail when 3.6 exists; stub until then.

**Exit criteria:** Banner matches rank API #1; updates after cache refresh job.

---

#### Phase 3.4 — Backtest side nav

| | |
|---|---|
| **Depends on** | 3.1, [side nav decision](#8-open-decisions) |
| **Blocks** | — |

**Tasks**

- [ ] Implement chosen taxonomy (recommended: **B — Object**: Strategies · Jobs · Leaderboard · Settings).
- [ ] Move **Configure** entry off center of monolithic backtest page into nav or sub-route.

**Exit criteria:** All backtest flows reachable via side nav without scrolling past unrelated sections.

---

#### Phase 3.5 — Compact queue table

| | |
|---|---|
| **Depends on** | Existing jobs API |
| **Blocks** | 3.6 |

**Tasks**

- [ ] Bottom-right (or Jobs section): compact table — `STRATEGY_NM`, status, View / Cancel / Re-enqueue.
- [ ] **Enlarge** opens full-width modal or route with same data + more columns.
- [ ] QUEUED jobs: status only, no partial optimization preview.

**Exit criteria:** User can cancel and re-enqueue from compact table; enlarge shows full queue view.

---

#### Phase 3.6 — Job / strategy detail drawer

| | |
|---|---|
| **Depends on** | 3.5, [Jobs Table Detail UX](jobs-table-detail-ux.md) |
| **Blocks** | — |

**Tasks**

- [ ] View action opens drawer: left = strategy JSON summary, right = optimization summary (not full equity curve unless stored).
- [ ] Deep-link `?job=<queue_id>`.
- [ ] Trade tab can link here for optional drill-down (nice-to-have).

**Exit criteria:** Shared drawer works from queue and from strategy banner link; `?job=` loads correct row.

---

#### Phase 3.7 — Separate TRADE host (optional)

| | |
|---|---|
| **Depends on** | 0.3, 1.7 stable |
| **Blocks** | — |

**Scope:** ECR for app/nginx is **already live** (decision #35). This subphase is only about a **second EC2** if metrics warrant isolation.

**Tasks**

- [ ] If metrics warrant: second EC2 pulling same ECR `quant-app` image with trade-only `command:`.
- [ ] If same host: document why and set revisit trigger (CPU &gt; X%).

**Exit criteria:** **M3 — Product** met when 3.1–3.6 done; 3.7 done only if topology decision requires it.

Align with [Backtest Queue](backtest-queue.md), [Infrastructure CI/CD](../architecture/infrastructure.md#cicd--github-actions).

---

## 3. Prerequisites (data model & ranking)

Before the “best strategy” banner and one-liner strategy rows work at DB scale:

| Prerequisite | Purpose |
|--------------|---------|
| **Strategy summary columns** | Expose Sharpe, overfitting ratio, etc. as queryable columns (not only inside JSON blobs) for list views and ranking |
| **Ranking job** | Background process computes leaderboard; **cache** before UI reads |
| **Result retention policy** | Decide what optimization artifacts are stored vs recomputed (equity curve, full grid, etc.) |

**Retention principle (from notes):**

- Persist **immediately** when user **applies strategy to trade**.
- Other heavy artifacts: store only if needed for UX/cost tradeoff; otherwise require rerun.
- While job is **QUEUED**: show queue status only — no partial optimization UI.

---

## 4. Frontend shell

Wireframes, zone maps, and rollout-by-subphase: **[§4.0 UI visualization](#40-ui-visualization)**.

### 4.0 UI visualization

Layouts below use a **12-column grid** mental model. Subphase tags show when each region first ships.

#### App shell (Phase 3.1 — top nav)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Quant Strategies          [ Backtest ]  [ Trade ]              user ▾  ⎋   │  ← 3.1
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                         (active tab content — see below)                     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Route | Tab | Notes |
|-------|-----|--------|
| `/backtest` | Backtest | Default after login today; gains side nav in 3.4 |
| `/trade` | Trade | Shell in **1.4**; full layout by **1.8** |

---

#### Phase 1 MVP — Trade tab only (subphases 1.4 – 1.8)

Routes: `/backtest` (default) and `/trade/config` | `/trade/apply`. App mode switch in header (Backtest \| Trade); full top nav tabs ship in **3.1**.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Quant Strategies     [ Backtest ] [ Trade* ]                    user ▾     │
├──────────┬───────────────────────────────────────────────────────────────────┤
│ SIDE     │  Filter: [Exchange ▾] [Account ▾]  [ Paper | Live ]     (1.4)   │  ← compact toolbar
│ 1.4      ├───────────────────────────────────────────────────────────────────┤
│          │                                                                   │
│ ● Config │   (Config = accounts table + add form  OR  Trade = picker/apply)  │
│ ○ Trade  │                                                                   │
│          │   Trade page — DEPLOYMENTS TABLE (filtered by toolbar):           │
│          │   ┌─────────┬─────────┬─────────┬──────────┬──────┬────────┬───┐ │
│          │   │Exchange │ Account │ Product │ Strategy │ Mode │ Status │Qty│ │
│          │   ├─────────┼─────────┼─────────┼──────────┼──────┼────────┼───┤ │
│          │   │ Bybit   │ Main    │ btc…    │ boll…    │Paper │ ACTIVE │…  │ │
│          │   └─────────┴─────────┴─────────┴──────────┴──────┴────────┴───┘ │
│          │   [ Dry run ]  [ Apply paper/live ]  (1.7)                        │
│          ├───────────────────────────────────────────────────────────────────┤
│          │  EXECUTION LOG (1.8) — bottom panel                             │
│          │  ┌────────┬──────────┬────────┬─────────┐                        │
│          │  │ Time   │ Side     │ Qty    │ Status  │                        │
│          │  └────────┴──────────┴────────┴─────────┘                        │
└──────────┴───────────────────────────────────────────────────────────────────┘

Config page (sidebar ● Config) — multi-broker account registry (1.5):
┌──────────────────────────────────────────────────────────────────────────────┐
│ Exchange accounts                                                            │
├──────────┬─────────┬──────┬────────────┬────────┬─────────┐                  │
│ Exchange │ Account │ Mode │ API key    │ Status │ Actions │  ← click row     │
├──────────┼─────────┼──────┼────────────┼────────┼─────────┤    sets toolbar│
│ Bybit    │ Main    │ Paper│ ****1234   │ Active │ Revoke  │    account filter│
│ Bybit    │ Sub     │ Live │ ****5678   │ Active │ Revoke  │                  │
│ Futu     │ HK      │ Live │ ****9012   │ Active │ Revoke  │                  │
└──────────┴─────────┴──────┴────────────┴────────┴─────────┘                  │
│ Add account (compact row, ~160px fields — not full width):                   │
│ [Exchange ▾] [Label] [Paper toggle]  [API key] [API secret]  [Save]          │
│ → POST /api/v1/credentials when 1.1 + 1.5 wiring complete                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Filter model:** Toolbar **Account** dropdown is a **filter** over the consolidated deployments (and accounts) table — “All exchanges” / “All accounts” show everything; narrowing Exchange then Account scopes Trade and Config row highlight. **Paper / Live** toggles which `is_paper_ind` rows appear.

---

#### Phase 3 target — Backtest tab (3.1 – 3.6)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Quant Strategies          [ Backtest*]  [ Trade ]              user ▾       │
├──────────┬───────────────────────────────────────────────────────────────────┤
│ SIDE     │                    BEST STRATEGY (3.3)                            │
│ 3.4      │         ★ bollinger_momentum_20_1.0 · Sharpe 1.22 · [details]   │
│          ├─────────────────────────────────────────────┬─────────────────────┤
│ Strategies│  MAIN — Configure / Run / Charts           │ QUEUE compact (3.5)│
│ Jobs     │  (today’s backtest UI; Configure in nav)   │ ┌──────┬────┬─────┐ │
│ Leaderboard│                                            │ │ Name │ St │ Act │ │
│ Settings │                                              │ ├──────┼────┼─────┤ │
│          │                                              │ │ bol… │ RUN│ ⋮   │ │
│          │                                              │ └──────┴────┴─────┘ │
│          │                                              │      [ Enlarge ]   │
└──────────┴─────────────────────────────────────────────┴─────────────────────┘
          │◄──────────── ~8 cols main ────────────────►│◄── ~4 cols queue ──►│
```

**Side nav (recommended B — Object):**

```mermaid
flowchart LR
  subgraph backtestSide["Backtest sidebar 3.4"]
    S[Strategies]
    J[Jobs]
    L[Leaderboard]
    SET[Settings]
  end
  S --> configure[Configure / edit]
  S --> run[Run / enqueue]
  J --> queueFocus[Scroll to queue panel]
  L --> banner[Feeds top-right banner 3.3]
```

| Side item | Main area shows |
|-----------|-----------------|
| **Strategies** | Factor cards, configure, run / enqueue |
| **Jobs** | Highlights queue panel; same compact table |
| **Leaderboard** | Ranked table (source for banner #1) |
| **Settings** | Backtest defaults (not exchange secrets) |

---

#### Phase 3 target — Trade tab (1.x layout + 2.3 reconcile)

Same compact toolbar as Phase 1 MVP; reconcile chart added top-right of main area.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Quant Strategies          [ Backtest ]  [ Trade*]              user ▾       │
├──────────┬───────────────────────────────────────────────────────────────────┤
│ SIDE     │  Filter: [Exchange ▾] [Account ▾] [Paper|Live]  RECONCILE (2.3)  │
│          │                                     ┌─────────────────────────┐   │
│ ● Config │                                     │ chart: live vs BT exp   │   │
│ ○ Trade  │                                     │ last run: today 06:00   │   │
│          ├────────────────────────────────────────┴─────────────────────────┤
│          │  STRATEGY PICKER + deployments table + [ Dry run ] [ Apply ]      │
│          ├───────────────────────────────────────────────────────────────────┤
│          │  EXECUTION LOG (transaction table — full width bottom)             │
└──────────┴───────────────────────────────────────────────────────────────────┘
```

---

#### Overlays (Phase 3.5 – 3.6)

**Enlarged queue** — triggered by `[ Enlarge ]` on Backtest (modal or `/backtest/jobs`):

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Jobs (full)                                                    [ ✕ Close ] │
├──────────────┬───────────┬──────────┬──────────┬────────────────────────────┤
│ STRATEGY_NM  │ Status    │ Queued   │ Updated  │ Actions                    │
├──────────────┼───────────┼──────────┼──────────┼────────────────────────────┤
│ bollinger_…  │ RUNNING   │ 10:00    │ 10:05    │ View · Cancel · Re-enqueue │
│ rsi_rev_…    │ QUEUED    │ 10:06    │ —        │ View · Cancel              │
└──────────────┴───────────┴──────────┴──────────┴────────────────────────────┘
```

**Job / strategy detail drawer** (3.6) — `View` or `?job=<id>`:

```
                                    ┌──────────────────────────────────────────┐
                                    │  Job detail                        [ ✕ ] │
                                    ├────────────────────┬─────────────────────┤
                                    │ STRATEGY (left)    │ RESULTS (right)     │
                                    │ · name, ticker     │ · best Sharpe       │
                                    │ · substrategies    │ · params grid sum.  │
                                    │ · JSON (collapsed) │ · (no equity curve  │
                                    │                    │   unless stored)    │
                                    │                    │                     │
                                    │ QUEUED: banner only│ "Queued — no preview"│
                                    └────────────────────┴─────────────────────┘
```

Slides in from the right; Backtest page dims behind. Trade tab may deep-link here later (optional).

---

#### UI rollout by subphase

| Subphase | UI change |
|----------|-----------|
| **1.4** | Trade routes + sidebar + compact filter toolbar (Exchange / Account / Paper·Live) + deployments table + execution-log placeholder |
| **1.5** | Config accounts table + compact add form; wire `/api/v1/credentials` |
| **1.6** | Strategy picker in Trade main |
| **1.7** | Dry-run report + Apply buttons |
| **1.8** | Bottom execution log table |
| **2.3** | Trade top-right reconcile chart |
| **2.4** | Telegram chat id on Config page |
| **3.1** | Top nav Backtest \| Trade |
| **3.3** | Backtest top-right best-strategy banner |
| **3.4** | Backtest left sidebar (4 items) |
| **3.5** | Backtest bottom-right compact queue + Enlarge |
| **3.6** | Detail drawer + `?job=` |

```mermaid
flowchart TB
  subgraph p1["Phase 1 UI"]
    T1[Trade shell 1.4]
    T2[Config 1.5]
    T3[Picker + Apply 1.6-1.7]
    T4[Exec log 1.8]
    T1 --> T2 --> T3 --> T4
  end
  subgraph p2["Phase 2 UI"]
    R[Reconcile chart 2.3]
    TG[Telegram field 2.4]
  end
  subgraph p3["Phase 3 UI"]
    NAV[Top tabs 3.1]
    BT[Backtest layout 3.3-3.5]
    DR[Drawer 3.6]
    NAV --> BT --> DR
  end
  p1 --> p2
  p1 --> p3
  T4 --> R
```

---

#### Zone map (full product)

| Zone | Backtest tab | Trade tab |
|------|--------------|-----------|
| Top bar | App title · **Backtest** \| **Trade** · user menu | Same |
| Left column | Side nav: Strategies, Jobs, Leaderboard, Settings | Side nav: **Config**, **Trade** |
| Below header | — | Compact toolbar: **Exchange** filter · **Account** filter · **Paper / Live** toggle |
| Top-right of main | Best strategy banner | Live Sharpe / reconcile chart (Phase 2) |
| Main center | Configure, run, charts | Config: **accounts table** + add form · Trade: picker, deployments table, dry-run, apply |
| Bottom / right | Compact queue (+ Enlarge) | Execution log (full width bottom) |
| Overlay | Enlarged jobs · detail drawer | Optional link to drawer |

---

### 4.1 Backtest tab

| Zone | Content |
|------|---------|
| **Top right** | Best strategy ever (from cached rank) |
| **Main** | Existing backtest configure/run flows — move **Configure** entry out of monolithic page center if possible |
| **Bottom right** | Queue table (subset of columns) + **Enlarge** button |

**Queue columns (minimum):**

| Column | Notes |
|--------|--------|
| `STRATEGY_NM` | Human-readable name |
| Status | `QUEUED` / `RUNNING` / terminal states |
| Actions | View, Cancel, Re-enqueue |

**Later:** View opens drawer/popup — left: strategy details, right: optimization summary. Deep-link `?job=` per [Jobs Table Detail UX](jobs-table-detail-ux.md).

**Backtest side nav (proposed categories — pick one structure):**

| Option | Sections |
|--------|----------|
| **A — Workflow** | Configure → Run / Queue → Results → History |
| **B — Object** | Strategies → Jobs → Leaderboard → Settings |
| **C — Role** | Research (configure + run) · Operations (queue) · Review (ranked results) |

Recommendation: start with **B** — matches mental model (strategy artifact vs job vs leaderboard).

### 4.2 Trade tab

| Zone | Content |
|------|---------|
| **Side nav** | **Config** (register broker accounts) · **Trade** (apply strategy) |
| **Toolbar** | **Exchange** dropdown (~160px) · **Account** dropdown (~200px) · **Paper / Live** toggle — filters deployments and highlights Config table rows |
| **Config main** | **Accounts table** (Exchange · Account · Mode · masked key · Status) + compact **Add account** form |
| **Trade main** | Strategy picker (1.6) · deployments table (Exchange · Account · …) · Dry-run / Apply buttons |
| **Top right** | Live Sharpe / reconcile series (Phase 2) |
| **Bottom** | Execution / transaction history (Phase 1.8) |

**Multi-broker model:**

- Many rows in `CORE_ADMIN.API_CREDENTIAL` — distinct `API_CREDENTIAL_ID` per saved key pair; same user may have multiple accounts on the same `APP_ID` (exchange).
- Toolbar **Account** filter scopes the deployments table (and Config row selection); “All accounts” shows every deployment matching Exchange + Paper/Live filters.
- **Paper / Live** toggle filters by `is_paper_ind` on credentials and deployments — not a separate “connection” entity.

**Flow:**

1. User registers accounts on **Config** (table); selects filter via toolbar or by clicking a table row.
2. On **Trade**, pick strategy (1.6) and optional **dry run** before live apply.
3. Apply uses BT strategy + `TRADE.DEPLOYMENT` (holds `API_CREDENTIAL_ID`); **audit = `TRADE.EXECUTION_EVENT` + `TRADE.TRANSACTION`**, not connection history ([Decisions log](../decisions.md) #36).
4. Errors → Telegram; refer strategy detail via Backtest/leaderboard when drill-down exists.

**Bybit:** Reference implementation in `backup/deco/`; active experimentation in `quant/trade/`. Adapter pattern: `BybitAdapter` in [Trade API](trade-api.md).

**Futu:** Prototype in `quant/trade/futu_trader.py`; target architecture in [Futu Trading — OOP Implementation](futu-trading.md) (`FutuAdapter`, `FutuTradeGateway`, `AdapterRegistry`).

---

## 5. Cross-cutting concerns

### 5.1 User secrets (exchange API keys)

| Requirement | Direction |
|-------------|-----------|
| Per-user credentials | `CORE_ADMIN.API_CREDENTIAL`; not in `.env` for multi-user prod |
| Broker identity | `APP_ID` → `REFDATA.APP` (seed `bybit`, etc.) — not free-text `EXCHANGE` |
| Multiple accounts | Distinct `API_CREDENTIAL_ID` (SP-assigned integer) per saved key pair; same user + same `APP_ID` allowed |
| Versioning | Soft-version (`API_CREDENTIAL_VID` + `IS_CURRENT_IND`); rotate keys = new VID; **no `UPDATED_AT`**; **no table IDENTITY** |
| Encryption | Fernet in app before SP; `EXCHANGE_SECRETS_KEY` in SSM |
| Writes | `CALL CORE_ADMIN.SP_*` only — no raw DML |
| Audit | Credential SPs may use `CORE_INS_LOG_PROC`; **no connection entity or connection audit** — trade audit = `TRADE.EXECUTION_EVENT` / `TRANSACTION` |
| UI | Trade → Config sidebar (1.5); API `/api/v1/credentials` (1.1) |
| App patterns | Reuse `require_user`, `DbGateway`, secret bootstrap — **not** JWT/Argon2 ([login.md §6.4](login.md#64-reuse-from-login--jwt-credential-api--phase-11)) |

Align with [Login design](login.md) (`CORE_ADMIN.APP_USER`) and [Database](../architecture/database.md). See decision #36.

### 5.2 API URL layout

| Area | Prefix | Phase |
|------|--------|-------|
| Auth | `/api/v1/auth/*` | done |
| Backtest (sync) | `/api/v1/backtest/*` | done |
| Backtest queue | `/api/v1/backtest/jobs/*` | done |
| REFDATA / INST | `/api/v1/refdata/*`, `/api/v1/inst/*` | done (shared) |
| Credentials | `/api/v1/credentials/*` | 1.1 (API) · 1.5 (UI) |
| Trade deployments | `/api/v1/trade/deployments/*` | **done** (1.2) |
| Trade dry-run / log | `/api/v1/trade/*` (future) | 1.3+ |

No backward-compat aliases — update all call sites when paths change (decision #37).

### 5.3 Error handling & observability

| Signal | Channel |
|--------|---------|
| Trade / deployment errors | Telegram (user-supplied chat id) |
| Healthy steady state | No Telegram noise |
| Process / host health | Heartbeat or external monitor — TBD |

### 5.4 Dry run

Required before first live apply per deployment:

- Validate credentials, symbol mapping (`INST.PRODUCT_XREF`), position sizing, and signal path without placing orders (or exchange paper mode if available).

### 5.5 Auth & security guardrails

Cross-cutting rules from the [login](login.md) / trade security review (2026-05-28). Phase-specific exit criteria in [§1.1](#phase-11--user-secrets) and [§1.7](#phase-17--live-apply).

#### Reuse login plumbing — not login crypto

| Reuse | Do not reuse |
|-------|----------------|
| `require_user`, `DbGateway` / repo + `CALL SP_*`, SSM secret bootstrap, never log secrets, ownership scoping (`APP_USER_ID`), Pydantic input strip, **404** for cross-user resource ids | JWT/Argon2/`SESSION_GEN`, decrypted-key cache, timing-attack dummy verify |

Full table: [login.md §6.4](login.md#64-reuse-from-login--jwt-credential-api--phase-11).

#### Authorization model (v1)

Full matrix, phased backlog, and Futu/Bybit split: **[User isolation requirements](user-isolation.md)**.

| Topic | v1 behaviour | When to revisit |
|-------|--------------|-----------------|
| RBAC | **None** — any logged-in user can save credentials, create deployments, and (1.7) live apply | Second user who is not fully trusted |
| Strategy visibility | `BT.STRATEGY` / results are **globally readable** to any logged-in user (`USER_ID` audit-only today) | login.md Phase 2 multi-user isolation |
| Strategy deploy | Must validate strategy **ownership** before 1.7 — `_strategy_exists` alone is insufficient |
| Paper vs live | **`is_paper_ind` on server** — client toolbar filter is UX only |

#### Secrets at rest and in transit

| Risk | Mitigation |
|------|------------|
| `SP_GET_API_CREDENTIAL` returns ciphertext | Service layer strips before JSON; response schema has no `*_CIPHERTEXT` fields; unit test |
| Missing Fernet bootstrap | `EXCHANGE_SECRETS_KEY` from SSM; prod **fail-fast** at boot (mirror `_resolve_jwt_secret`); **never** reuse `JWT_SECRET` |
| Worker decrypt path | Decrypt only at adapter boundary; short-lived; never log; no parallel env-key path once 1.1 is live |
| Legacy `.env` exchange keys | Multi-user prod uses `CORE_ADMIN.API_CREDENTIAL` only — not shared `.env` keys (house account exception must be explicit) |
| Futu unlock password | Not covered by key+secret model — decide before Futu live: extra column, credential type, or infra-only unlock |

#### API hardening

| Control | Where |
|---------|--------|
| Rate limit credential writes | `POST`/`PUT` `/api/v1/credentials` — at least login-tier limits |
| CSRF | `SameSite=Strict` + HTTPS same-origin SPA is sufficient for v1; cross-origin frontend needs CSRF tokens ([login.md §16 Q5](login.md#16-open-questions)) |
| Kill switch | `PATCH` deployment `is_enabled_ind` — required before 1.7 ([Trade API §4](trade-api.md#4-risk--safety)) |
| Live apply step-up | Align with [Trade API §4.1](trade-api.md#41-confirmation-flow-for-live-trading): dry-run first, explicit confirm; Futu may need trade-unlock password |

#### Frontend reuse (login page)

| Reuse | Do not reuse |
|-------|----------------|
| `RequireAuth`, `useMe()`, controlled form + error display, `type="password"` for key/secret fields | Persisting API keys in `localStorage`; mixing credential calls into `/auth/login` module |

---

## 6. Infrastructure & ops

| Topic | Notes |
|-------|--------|
| **EC2 + Docker** | Measure CPU/mem before adding trade container alongside API + worker + Redis |
| **ECR step 1** | **Done** — `quant-ecr` stack, repos `quant-app` / `quant-nginx`, EC2 ECR read, CI IAM |
| **ECR pipeline** | **Done** — compose + CI push/pull + selective deploy; see [infrastructure.md](../architecture/infrastructure.md#cicd--github-actions) |
| **Existing stack** | See [Infrastructure](../architecture/infrastructure.md), [Dev vs Prod](../architecture/dev-vs-prod.md) |

---

## 7. Work breakdown (maps to subphases)

| Subphase | Work item (summary) |
|----------|---------------------|
| **0.1** | Walk-forward sign-off on live candidate (`quant.cli --walk-forward`) |
| **0.2** | EC2 + Docker capacity snapshot |
| **0.3** | ECR / separate-host decision → decisions log |
| **1.1** | `CORE_ADMIN.API_CREDENTIAL` + SPs + `/api/v1/credentials` (Fernet, `APP_ID`, soft-version) |
| **1.2** | `TRADE.DEPLOYMENT` / `EXECUTION_EVENT` / `TRANSACTION` + apply endpoint (no `INTENT`) |
| **1.3** | Bybit adapter dry-run |
| **1.4** | Trade tab shell + sidebar routes + multi-broker filter toolbar |
| **1.5** | Exchange config UI — accounts table + credentials API wiring |
| **1.6** | Strategy picker — `GET /api/v1/strategies` + `StrategyPicker` (reads `BT.STRATEGY`; not Backtest config UI) |
| **1.7** | Live apply (dry-run → apply) |
| **1.8** | Execution log UI + `TRADE.EXECUTION_EVENT` writes |
| **2.1** | Reconcile snapshot schema + SP |
| **2.2** | Daily Sharpe reconcile job |
| **2.3** | Reconcile chart (Trade top-right) |
| **2.4** | Telegram error notifier + user chat id |
| **2.5** | Heartbeat / silent-failure alerts |
| **3.1** | Top nav Backtest \| Trade |
| **3.2** | Strategy summary columns + rank cache job |
| **3.3** | Best strategy banner |
| **3.4** | Backtest side nav + configure placement |
| **3.5** | Compact queue table + enlarge |
| **3.6** | Job / strategy detail drawer + `?job=` |
| **3.7** | Trade worker ECR / separate host (if 0.3 requires) |

Detailed tasks and exit criteria for each row are in [§2 Phased Roadmap](#2-phased-roadmap).

---

## 8. Open decisions

| # | Question | Options / notes |
|---|----------|-----------------|
| 1 | **Backtest side nav taxonomy** | See §4.1 options A/B/C |
| 2 | **What to store per optimization** | Full equity curve vs summary stats only |
| 3 | **Sharpe reconcile storage** | Daily snapshot table vs rolling window materialized view |
| 4 | **ECR cutover for TRADE** | **Resolved (0.3):** **ECR now** — see [infrastructure.md § CI/CD](../architecture/infrastructure.md#cicd--github-actions). |
| 5 | **Silent failure policy** | Heartbeat table, external uptime, exchange position reconcile |
| 6 | **Exchange limit detection** | Post-MVP per exchange |

Record resolutions in [Decisions log](../decisions.md) when agreed.

---

## 9. Out of scope (ideas captured, not roadmap)

Notes mentioned alternative profit paths (e.g. horse racing, Poisson/Bernoulli models with small *n*). These are **not** part of this codebase roadmap unless explicitly promoted later.

---

## 10. Related documentation

| Doc | Relevance |
|-----|-----------|
| [Trade API](trade-api.md) | Strategy JSON, deployment, adapters, risk checks |
| [Futu Trading (OOP)](futu-trading.md) | Futu adapter class design, OpenD, implementation phases |
| [Backtest Queue](backtest-queue.md) | Queue states, worker, jobs API |
| [Jobs Table Detail UX](jobs-table-detail-ux.md) | Drawer / `?job=` deep links |
| [Database](../architecture/database.md) | `BT.*`, planned `TRADE.*` |
| [Frontend](../architecture/frontend.md) | React SPA structure |
| [Paper Trading guide](../guides/trading.md) | Existing Futu utility (pattern reference) |
| [Deploy Build Pipeline](../archive/deploy-build-pipeline.md) | ECR history — **live ops:** [infrastructure.md](../architecture/infrastructure.md#cicd--github-actions) |

---

## 11. Success criteria

| Milestone | Subphases | Definition of done |
|-----------|-----------|-------------------|
| **M1 — Pipeline** | 1.1 – 1.8 (after 0.x) | User configures Bybit credentials, selects a backtested strategy, dry-runs, applies live, sees transactions in UI |
| **M2 — Proof** | 2.1 – 2.5 | Daily Sharpe reconcile visible; Telegram on failure; no silent 24h outage without alert |
| **M3 — Product** | 3.1 – 3.6 (+ 3.7 if needed) | Backtest + Trade tabs with side nav, ranked best strategy, compact queue with enlarge/detail |

When **M1** is reached (subphase **1.7** + **1.8**), the project has a **closed loop** from research → execution → audit — the minimum bar for “plan to profit.”
