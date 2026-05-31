# User isolation requirements

**Status:** v1 — partial enforcement. Credentials, deployments, and job queue are scoped by owner; strategy **reads** are global; strategy **deploy** ownership is required before Phase 1.7 live apply.

Related: [Login §14 Phase 2](login.md#14-phased-plan), [Plan to Profit §5.5](plan-to-profit.md#55-auth--security-guardrails), [Trade API §2.1](trade-api.md#21-strategy-catalog--phase-16), [Futu Trading §13](futu-trading.md#13-broker-strategy--when-to-scale-futu).

---

## Two identifiers — do not conflate

| Field | Type | Role |
|-------|------|------|
| **`APP_USER_ID`** | `UUID` | **Owner** — who may read/write this row (credentials, deployments) |
| **`USER_ID`** | `TEXT` | **Audit** — who created the row; also used as queue filter in `BT.QUEUE` |

JWT `sub` = `APP_USER_ID`. `require_user` resolves that to `CurrentUser { app_user_id, username }`.

The FastAPI connection pool logs in as Postgres role `quant_app`. The human identity is passed as `IN_APP_USER_ID` / `IN_USER_ID` into stored procedures — not as a separate DB login per user. See [Login §6](login.md#6-database--grants).

### Design debt (normalize before hardening)

| Table / path | What is stored in `USER_ID` today |
|--------------|-------------------------------------|
| `BT.STRATEGY`, `BT.QUEUE` (jobs API) | `str(app_user_id)` — UUID as text |
| `TRADE.DEPLOYMENT` audit column | `username` (TEXT) via `user.username` on create |
| Sync backtest (`/optimize`) | Pool user / cache path — **not** per-human today |

**Phase 1.7 ownership checks** must compare `BT.STRATEGY.USER_ID` against what jobs actually wrote (`str(caller.app_user_id)`), not username.

---

## Requirement matrix

| Domain | Owner column | Enforced today? | Requirement | Phase |
|--------|--------------|-----------------|-------------|-------|
| **Login / session** | `APP_USER_ID` in JWT | **Yes** | One session per human; `SESSION_GEN` revoke | Done |
| **Credentials** | `CORE_ADMIN.API_CREDENTIAL.APP_USER_ID` | **Yes** | SP + API scoped; cross-user id → **404** | 1.1 |
| **Deployments** | `TRADE.DEPLOYMENT.APP_USER_ID` | **Yes** | `SP_GET_DEPLOYMENT(IN_APP_USER_ID)`; credential must match owner | 1.2 |
| **Job queue** | `BT.QUEUE.USER_ID` | **Yes** | List/cancel/SSE scoped; max 20 `QUEUED` per user | Done |
| **Strategy picker (read)** | `BT.STRATEGY.USER_ID` | **No** | Any logged-in user sees all strategies | 1.6 or login Phase 2 |
| **Strategy deploy (write)** | `BT.STRATEGY.USER_ID` vs caller | **No** | Reject deploying another user's strategy | **1.7 — required** |
| **Sync backtest** | — | **No** | No per-user result isolation on `/optimize` | login Phase 2 |
| **`BT.RESULT`** | `USER_ID` audit only | **No** | Globally readable | login Phase 2 |
| **REFDATA / INST** | — | N/A | Shared catalog | By design (v1) |
| **Futu OpenD** | Infra (not per user) | **Partial** | One gateway in v1; **DB** still separates by `APP_USER_ID` | v1 house account |

---

## Enforced today

### Credentials (Phase 1.1)

- Every SP call passes `CurrentUser.app_user_id`.
- Cross-user `api_credential_id` → **404** (never 403 — no existence leak).
- Responses never include `*_CIPHERTEXT`.

Implementation: `quant/api/credentials/`, `CORE_ADMIN.SP_*_API_CREDENTIAL`.

### Deployments (Phase 1.2)

- `SP_GET_DEPLOYMENT` requires `IN_APP_USER_ID`.
- `TradeRepo` rejects credentials and deployments that belong to another user before `CALL TRADE.SP_INS_DEPLOYMENT`.

Implementation: `quant/trade/db_repo.py`, `quant/api/routers/deployments.py`.

### Job queue

- Enqueue / list / cancel / SSE use `str(user.app_user_id)`.
- `SP_GET_QUEUE` filters by `USER_ID` when provided.

Implementation: `quant/api/routers/jobs.py`, `quant/api/services/jobs.py`.

---

## Required before live apply (Phase 1.7)

| Check | Rule |
|-------|------|
| **Strategy ownership** | `BT.STRATEGY.USER_ID` must match caller (`str(app_user_id)` as stored today) |
| **Credential ownership** | Already enforced |
| **Deployment ownership** | Already enforced on get/list |
| **Paper vs live** | `is_paper_ind` enforced **on server** — Trade UI toggle is UX only |
| **Live apply step-up** | Dry-run first + explicit confirm ([Trade API §4.1](trade-api.md#41-confirmation-flow-for-live-trading)) |

Without strategy ownership validation, user A could deploy user B's backtest config to user A's exchange keys — wrong strategy, wrong audit trail, capital at risk.

**Exit criteria (1.7):** deployment create validates strategy ownership; see [plan-to-profit §1.7](plan-to-profit.md#phase-17--live-apply).

---

## Phase 1.6 — strategy picker (read path)

Docs allow a **global** strategy list in early 1.6, but the API should expose `user_id` on each row so the UI can label "mine vs others".

**Recommended:** `BT.SP_GET_STRATEGY` list mode (`IN_STRATEGY_ID` NULL, `IN_USER_ID` required) — same GET convention as `SP_GET_QUEUE`. Optional admin/unfiltered mode when `ROLE` exists (login Phase 2).

See [Trade API §2.1](trade-api.md#21-strategy-catalog--phase-16).

---

## Deferred — login Phase 2 (multi-user isolation)

From [Login §14](login.md#14-phased-plan):

- Add `USER_ID` / owner filter to `BT.STRATEGY`, `BT.RESULT`, and sync backtest read paths.
- Per-user result lists in the SPA.
- Optional `ROLE` column — admin sees all runs.

**Trigger:** a second logged-in user who is **not fully trusted** ([plan-to-profit §5.5](plan-to-profit.md#55-auth--security-guardrails)).

Until then, v1 explicitly allows any authenticated user to browse shared backtest artifacts; mutating paths for credentials, deployments, and jobs are already scoped.

---

## Futu vs Bybit

| Broker | Per-user isolation | Infrastructure |
|--------|-------------------|----------------|
| **Bybit** | `API_CREDENTIAL` per `APP_USER_ID` | Normal SaaS — each user their own REST keys |
| **Futu v1** | **One OpenD / one Futu login** (house account) | Postgres still separates deployments, credentials, and audit by `APP_USER_ID` |

Futu migration does **not** remove DB-level separation — only the **gateway** is shared. See [Futu Trading §13](futu-trading.md#13-broker-strategy--when-to-scale-futu).

Multiple unrelated Futu logins → gateway EC2 + `gateway_id` registry (§12), not ECS. Each credential row still maps to `APP_USER_ID`.

---

## Decision tree

```mermaid
flowchart TD
  A["New feature touches user data?"]
  A --> B{"Mutable / sensitive?"}
  B -->|No — REFDATA| C["Shared — no owner filter"]
  B -->|Yes| D{"Has APP_USER_ID column?"}
  D -->|Yes| E["Filter SP + API by caller APP_USER_ID"]
  D -->|No — BT reads| F{"Deploy or trade?"}
  F -->|Deploy 1.7| G["Require STRATEGY.USER_ID match"]
  F -->|Read-only browse| H["Phase 2 filter or show all + label"]
  E --> I["Cross-user resource id → 404"]
```

---

## Implementation backlog

| Priority | Task | Blocks |
|----------|------|--------|
| **P0** | Deployment create: verify `BT.STRATEGY.USER_ID == str(app_user_id)` | 1.7 live apply |
| **P0** | Deployment create: verify credential + product belong to caller | 1.7 (credential partial) |
| **P1** | `SP_GET_STRATEGY` list mode deployed; wire `GET /api/v1/strategies` | 1.6 privacy / UX |
| **P1** | Normalize BT `USER_ID` — UUID string **or** username consistently | Ownership checks |
| **P2** | Filter `BT.RESULT`, sync backtest cache by owner | login Phase 2 |
| **P2** | `ROLE` + admin bypass | Multi-tenant admin |
| **P3** | Postgres RLS or `SET LOCAL app.user_id` GUC | Defense in depth — see [Login §6.3](login.md#63-optional-session-guc) |

---

## Cross-user response policy

| Situation | HTTP status | Rationale |
|-----------|-------------|-----------|
| Resource id exists but belongs to another user | **404** | Do not leak existence |
| Invalid id format | **400** or **404** | Match existing router patterns |
| Authenticated but not allowed (future RBAC) | **403** | Only when role model exists |

Credentials API established this pattern in Phase 1.1 — reuse for deployments, strategies, and jobs.
