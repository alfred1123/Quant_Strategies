# Login & Authentication — Design Doc (v1-minimal)

Status: **Draft**
Owner: alfcheun
Related: [decisions #16, #18](../decisions.md), [backtest-queue.md](backtest-queue.md), [trade-api.md](trade-api.md)

---

## 1. Problem

Today the app has **no authentication**. The hardcoded user `alfcheun` is baked into [src/db.py](src/db.py) (`user_id: str = "alfcheun"`) and propagated into every `USER_ID` audit column. The FastAPI backend accepts any caller — anyone with the URL can run backtests, read all `BT.RESULT` rows, and (once the trade API is wired) trigger orders.

Before public hosting (Tier 1 in the deployment ladder), the app must require a login. This doc covers the **smallest possible** design that:

- Stops anonymous access to all `/api/v1/*` endpoints (except health + login).
- Replaces the hardcoded `user_id` with the authenticated user.
- Lays groundwork for true multi-tenancy later, without committing to it now.

**Scoping decision**: users are provisioned **manually by the admin (via Liquibase / `psql`)**. There is no signup endpoint, no admin-user-management UI, no self-service password change, no email infrastructure. This drops a large amount of code, surface area, and risk that is unnecessary for a 1–3-trusted-user system.

---

## 2. Goals

### Functional
1. A user must log in to use the SPA.
2. Backend rejects unauthenticated API calls with `401`.
3. `USER_ID` audit columns reflect the real logged-in user, not `"alfcheun"`.
4. Admin can disable a compromised account or invalidate all sessions without restarting the app.
5. Logout clears credentials client-side and server-side.

### Non-functional
6. Stateless server-side (no in-memory session table) — JWT in HTTP-only cookie.
7. Passwords stored as Argon2id hash. Never plaintext, never reversible.
8. No third-party identity provider.
9. No email service (SES/SMTP). No password reset flow.
10. Works on the existing single-EC2 + single-RDS topology.

---

## 3. Non-Goals (v1)

- **Self-service signup or password change.** Admin handles everything via SQL.
- **Email-based password reset.**
- **Email as login handle.** Username only. (Trivial to swap later — see §15.)
- **Multi-tenancy in queries.** `BT.RESULT` and `INST.PRODUCT` remain globally readable to any logged-in user. `USER_ID` is for audit only — row-level filtering comes in v2.
- **Roles / RBAC.** All logged-in users have the same permissions.
- **OAuth / SSO / MFA.**
- **Per-user API quotas.** Covered later in the queue design.
- **Per-username failed-login lockout.** With manually-provisioned users and per-IP rate limiting at nginx, the surface is small enough not to warrant lockout state in the schema.

---

## 4. Constraints & Observations

- Backend is FastAPI (async, Pydantic v2). Frontend is React 19 + TanStack Query, served separately by Vite in dev and (in prod) by nginx.
- `api/config.py` already has SSM/.env loader — JWT signing key fits there.
- Audit columns (`USER_ID TEXT`) exist on every table per [AGENTS.md](AGENTS.md). Today they receive `"alfcheun"`. We just need to plumb a real value.
- All writes go through SPs (no direct DML). **Login itself reads a user table — `SELECT` is allowed directly per project conventions.** User provisioning runs as Liquibase changesets — that is the documented exception to the no-direct-DML rule.
- HTTPS is mandatory for cookie-based auth. Tier 1 deployment already plans nginx + Let's Encrypt; this doc assumes that's in place.
- **Uvicorn must bind to `127.0.0.1` only** — never `0.0.0.0` — so cleartext credentials never travel outside the box without TLS.
- **All table writes go through stored procedures.** The application DB role is granted `EXECUTE` on procedures and `SELECT` on tables — never `INSERT/UPDATE/DELETE` directly. This removes a class of compromise paths (SQL injection, leaked app credentials, future RBAC errors) and lets schema evolve without re-grant work.

---

## 5. Proposed Architecture

```
┌─────────────┐   POST /api/v1/auth/login     ┌─────────────┐
│  React SPA  │ ───────────────────────────► │  FastAPI    │
│             │ ◄─── Set-Cookie: token=JWT── │             │
│             │                              │  ▲          │
│             │   GET /api/v1/backtest/...   │  │ verify   │
│             │ ───── Cookie: token ──────► │  │ JWT      │
│             │ ◄──── 200 / 401 ──────────── │             │
└─────────────┘                              └──┬──────────┘
                                                │
                                                ▼
                                  ┌──────────────────────────┐
                                  │  CORE_ADMIN.APP_USER     │
                                  │  (id, username, hash)    │
                                  └──────────────────────────┘
```

### 5.1 Trust model

- **Single trust boundary**: nginx terminates TLS, forwards to uvicorn over loopback. No service-to-service auth needed inside the box.
- **Cookie**: `qs_token`, `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api`. Lifetime 7 days; refresh on activity.
- **Why `SameSite=Strict`** (not `Lax`): the app touches a trade API. `Strict` blocks the cookie on *any* cross-site request — including top-level navigations — so a malicious link cannot trigger an authenticated state-changing call. Trade-off: a user clicking an external link to the app (e.g. from email or Slack) lands on `/login` even if they have a valid session, and must navigate forward manually. Acceptable for an internal tool.
- **CSRF**: not required while the SPA is same-origin and `SameSite=Strict` is enforced. The deprecated `X-Requested-With: XMLHttpRequest` heuristic is **not** used — it is a legacy CORS side effect, not a real defense. If the SPA ever moves to a different origin, switch to a double-submit CSRF token.

### 5.2 Why JWT and not server-side sessions

| Concern | JWT in cookie | DB-backed session |
|---|---|---|
| Server state | None | Session table + cleanup job |
| Revocation | Token version bump on user row | `DELETE` row |
| Multi-instance | Stateless, scales trivially | Need shared session store |
| Complexity | Lower for v1 | Higher |

JWT wins for our scale. Immediate revocation comes from the `SESSION_GEN` column (bearer-token generation counter) embedded in the JWT — bumping it via a one-line `UPDATE` invalidates all outstanding tokens for that user.

---

## 6. Data Model

### 6.1 `CORE_ADMIN.APP_USER`

| Column | Type | Notes |
|---|---|---|
| `APP_USER_ID` | `UUID` PK | UUID v7. |
| `USERNAME` | `TEXT NOT NULL UNIQUE` | Login handle. Lowercase enforced at app layer. |
| `PASSWORD_HASH` | `TEXT NOT NULL` | Argon2id, encoded as PHC string. |
| `IS_ACTIVE_IND` | `CHAR(1) NOT NULL` | `Y`/`N`. Disable via `UPDATE`. |
| `SESSION_GEN` | `INT NOT NULL` | Bearer-token generation counter. Bump to invalidate all outstanding JWTs (password change, deactivation, log-out-everywhere). |
| `LAST_LOGIN_AT` | `TIMESTAMPTZ` | Updated on successful login (best-effort). |
| `CREATED_AT` | `TIMESTAMPTZ` | |
| `UPDATED_AT` | `TIMESTAMPTZ` | Genuinely mutable (password change, last-login bump). |

**7 application columns.** No `USER_ID` audit column on this table — `APP_USER` *is* the user identity, so a self-referencing audit FK is circular. Audit of who created/modified a user is captured by `CORE_ADMIN.LOG_PROC_DETAIL` via the SP call. No `EMAIL`, no `ROLE`, no `FAILED_LOGIN_COUNT`, no `LOCKED_UNTIL`. Adding any of these later is a single Liquibase changeset.

### 6.2 Existing tables

No schema changes elsewhere. The hardcoded `"alfcheun"` becomes the actual logged-in `USERNAME` flowing into every existing `USER_ID` audit column.

---

## 7. Stored Procedures

**All writes go through SPs — no direct DML, ever.** This is a deliberate design choice (see §4): the app DB role gets only `EXECUTE` on procedures and `SELECT` on tables. Admin operations call the same SPs from `psql` with `CALL`. No table-level write grants are ever issued.

| SP | Purpose | Called by |
|---|---|---|
| `CORE_ADMIN.SP_GET_APP_USER_BY_USERNAME` | Returns `APP_USER_ID, USERNAME, PASSWORD_HASH, IS_ACTIVE_IND, SESSION_GEN`. | App (login) |
| `CORE_ADMIN.SP_UPD_APP_USER_LAST_LOGIN` | Update `LAST_LOGIN_AT`. Fire-and-forget on every successful login. | App |
| `CORE_ADMIN.SP_INS_APP_USER` | Insert a new user. Inputs: `IN_USERNAME`, `IN_PASSWORD_HASH`, `IN_USER_ID` (creator, for audit log only). Generates `APP_USER_ID` (UUID), defaults `IS_ACTIVE_IND='Y'`, `SESSION_GEN=1`. | Admin |
| `CORE_ADMIN.SP_UPD_APP_USER_PASSWORD` | Set new `PASSWORD_HASH` and bump `SESSION_GEN`. Inputs: `IN_USERNAME`, `IN_PASSWORD_HASH`, `IN_USER_ID`. | Admin |
| `CORE_ADMIN.SP_UPD_APP_USER_ACTIVE` | Set `IS_ACTIVE_IND` and bump `SESSION_GEN`. Inputs: `IN_USERNAME`, `IN_IS_ACTIVE_IND` (`Y`/`N`), `IN_USER_ID`. | Admin |
| `CORE_ADMIN.SP_UPD_APP_USER_BUMP_TOKEN` | Bump `SESSION_GEN` only — force logout-everywhere without changing password (lost laptop). Inputs: `IN_USERNAME`, `IN_USER_ID`. | Admin |

Six procedures total. Naming follows the existing project convention (`SP_GET_*`, `SP_INS_*`, `SP_UPD_*`).

### 7.1 Admin runbook (SP-only operations)

**⚠️ Never paste a plaintext password into an online "Argon2 hash generator" website.** Doing so leaks the password to whoever runs the site. Always hash locally with `scripts/hash_password.py`.

```bash
# Step 1: generate the hash locally (reads from stdin, never echoes the password)
$ python scripts/hash_password.py
Password: ********                       # not echoed
$argon2id$v=19$m=65536,t=3,p=4$...$...   # paste this into the CALL below
```

```sql
-- Create a new user.
CALL CORE_ADMIN.SP_INS_APP_USER(
    IN_USERNAME       => 'newuser',
    IN_PASSWORD_HASH  => '$argon2id$v=19$m=65536,t=3,p=4$...$...',
    IN_USER_ID        => 'alfcheun'
);

-- Change a user's password (also invalidates their sessions).
CALL CORE_ADMIN.SP_UPD_APP_USER_PASSWORD(
    IN_USERNAME       => 'someone',
    IN_PASSWORD_HASH  => '$argon2id$...',
    IN_USER_ID        => 'alfcheun'
);

-- Deactivate / reactivate a user.
CALL CORE_ADMIN.SP_UPD_APP_USER_ACTIVE(
    IN_USERNAME       => 'someone',
    IN_IS_ACTIVE_IND  => 'N',
    IN_USER_ID        => 'alfcheun'
);

-- Force logout-everywhere without changing password.
CALL CORE_ADMIN.SP_UPD_APP_USER_BUMP_TOKEN(
    IN_USERNAME       => 'someone',
    IN_USER_ID        => 'alfcheun'
);
```

The initial admin user is seeded via a Liquibase changeset that calls `SP_INS_APP_USER` (not raw `INSERT`) so the same access path is used everywhere.

### 7.2 Postgres roles vs application users — two identity layers

There are **two completely separate identity layers**. They are intentionally not 1:1.

| Layer | Lives in | Examples | Purpose |
|---|---|---|---|
| **Postgres login user** | `pg_roles` | `quant_app`, `quant_admin` | Authenticates the *process* (FastAPI / `psql`) to Postgres. Holds all `GRANT`s. |
| **Application user** | `CORE_ADMIN.APP_USER` | one row per human | Authenticates the *human* to FastAPI. Drives JWT claims and the `USER_ID` audit column on every table. |

**The FastAPI connection pool always logs in as `quant_app`.** The per-request human identity is carried separately as the `IN_USER_ID` parameter into every SP call. One Postgres handshake per pooled connection; no per-user reconnect cost.

Adding a new human = `CALL CORE_ADMIN.SP_INS_APP_USER(...)`. **No `CREATE ROLE`, no GRANT changes, no app restart, ever.** That dynamism is the reason we route everything through SPs (§4).

### 7.3 Postgres login users

Two login users — one for the app, one for the admin. Grants are issued directly to them. Group roles can be introduced later if a third login user appears (e.g. `quant_worker` for batch jobs).

| User | Type | Created by | Used by |
|---|---|---|---|
| `quant_app`   | LOGIN | **manually** (DBeaver/`psql`) | FastAPI process (password stored only in SSM) |
| `quant_admin` | LOGIN | **pre-existing** — not created here | The human admin via `psql` |

```sql
-- Provisioned manually (DBeaver / psql) so the password never lands in any
-- automation or env var:
CREATE ROLE quant_app LOGIN PASSWORD '<typed-at-the-prompt>';
-- quant_admin already exists; only its grants are managed here.
```

Neither user is `SUPERUSER`, `CREATEROLE`, or `CREATEDB`. The Liquibase deploy itself runs as the cluster master — only that role can issue GRANTs and create extensions. The runtime app **never** uses the master.

> **Why manual provisioning?** Putting the password into a Liquibase property (even one fed from SSM at deploy time) means the secret transits an env var on the deploy host. Provisioning roles by hand keeps the password on exactly two surfaces: the DBA's keystroke and SSM (where the app reads it).

### 7.4 Grants

```sql
-- ===== quant_app (the FastAPI process) =====
-- Strict policy: USAGE on schemas + EXECUTE on app-facing procs.
-- NO direct table access (no SELECT/INSERT/UPDATE/DELETE) and NO
-- ALTER DEFAULT PRIVILEGES entries. Every read AND write goes through a
-- stored procedure.
GRANT USAGE ON SCHEMA CORE_ADMIN, REFDATA, BT, INST, TRADE TO quant_app;

-- EXECUTE on app-facing procs (the two auth SPs + every business SP).
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_GET_APP_USER_BY_USERNAME(TEXT, ...) TO quant_app;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_LAST_LOGIN(UUID, ...)  TO quant_app;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA BT, INST, TRADE, REFDATA TO quant_app;

-- Explicitly NOT granted: the four admin SPs in CORE_ADMIN
-- (SP_INS_APP_USER, SP_UPD_APP_USER_PASSWORD, SP_UPD_APP_USER_ACTIVE,
--  SP_UPD_APP_USER_BUMP_TOKEN). A compromised quant_app process cannot
-- create users or change passwords.

-- ===== quant_admin (the human admin via psql) =====
GRANT USAGE   ON SCHEMA CORE_ADMIN              TO quant_admin;
GRANT SELECT  ON CORE_ADMIN.APP_USER            TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_INS_APP_USER(TEXT, TEXT, TEXT, ...)             TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_PASSWORD(TEXT, TEXT, TEXT, ...)    TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_ACTIVE(TEXT, CHAR, TEXT, ...)      TO quant_admin;
GRANT EXECUTE ON PROCEDURE CORE_ADMIN.SP_UPD_APP_USER_BUMP_TOKEN(TEXT, TEXT, ...)        TO quant_admin;
```

`quant_app` cannot `SELECT`, `INSERT`, `UPDATE`, or `DELETE` any table directly — every read and every write flows through an `SP_*` procedure that runs `SECURITY DEFINER` (or whose owner has the needed privileges). A compromised app process cannot exfiltrate raw rows, create users, or change passwords; it can only invoke the procs we have explicitly defined.

> **Migration impact**: existing code that does direct `SELECT` against tables (e.g. `RefDataCache`, instrument lookups, backtest result reads) must be replaced with `SP_GET_*` procedures before the new grants take effect. Track in [TODO.md](TODO.md).

> **Future**: when a third login user is needed (e.g. `quant_worker`), refactor into NOLOGIN group roles (`quant_app_role`, `quant_admin_role`) and grant them to the login users. Deferred until justified.

### 7.5 Optional: Postgres-side audit context

The `USER_ID` column on every table already records the human (set by the SP from `IN_USER_ID`). If Postgres triggers, RLS, or `pg_stat_activity` ever need to see the human directly, set a session GUC at connection checkout:

```python
# Pool's post-acquire hook
async with pool.connection() as conn:
    await conn.execute("SET LOCAL app.user_id = %s", (user.username,))
```

Then any SP/trigger can read `current_setting('app.user_id', true)`. **Skip for v1** — add only when there's a concrete need. The GRANT model is unchanged either way.

---

## 8. API Design

### 8.1 New endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | none | Body `{username, password}`. On success, sets `qs_token` cookie and returns `{username}`. |
| `POST` | `/api/v1/auth/logout` | required | Clears cookie (`Set-Cookie: qs_token=; Max-Age=0`). |
| `GET`  | `/api/v1/auth/me`     | required | Returns `{username}`. Used by SPA on page load to detect existing session. |

**Three endpoints.** No `/auth/change-password`, no `/admin/users`.

### 8.2 Existing endpoints

Every router under `/api/v1/*` (except `/auth/*` and `/health`) gains a `Depends(require_user)` dependency. The dependency:
1. Reads `qs_token` cookie.
2. Decodes + verifies JWT (signature, `exp`, `iss`).
3. Looks up the user (cached briefly, see §10) — verifies `IS_ACTIVE_IND='Y'` and `SESSION_GEN` matches the JWT claim.
4. Returns a `CurrentUser` dataclass (`username`, `app_user_id`).
5. On any failure → `401 Unauthorized`.

Routers that previously hardcoded `user_id="alfcheun"` switch to:

```python
@router.post("/run")
def run_backtest(cfg: BacktestConfig, user: CurrentUser = Depends(require_user)):
    cache = BacktestCache(conninfo, refdata, user_id=user.username)
    ...
```

The default value `user_id="alfcheun"` in [src/db.py](src/db.py) and [src/data.py](src/data.py) is **removed entirely** (the parameter becomes required). No backward compat per AGENTS.md.

### 8.3 JWT shape

```json
{
  "sub": "01957a...e3b1",        // APP_USER_ID (UUID, opaque — not the username)
  "ver": 1,                       // SESSION_GEN at issue time
  "iat": 1735689600,
  "exp": 1736294400,              // 7 days
  "iss": "quant-strategies"
}
```

Signed with HS256, key from `JWT_SECRET` env var (added to SSM `/quant/prod/JWT_SECRET`, generated with `openssl rand -base64 32`). Rotation = generate a new key, restart — all tokens invalidate.

Username is **not** in the token. The `require_user` dependency resolves `app_user_id → username` from the cached lookup. This means renaming a user later doesn't invalidate their session.

### 8.4 Pydantic input validation

```python
class LoginRequest(BaseModel):
    username: constr(min_length=1, max_length=64, strip_whitespace=True, to_lower=True)
    password: constr(min_length=12, max_length=128)
```

Hard upper bounds prevent a 100 MB POST from triggering Argon2 on giant input — cheap DoS guard.

---

## 9. Frontend Design

### 9.1 Route guard

Top-level `<App>` calls `GET /api/v1/auth/me` once at mount via TanStack Query.
- `401` → redirect to `/login`.
- `200` → render the existing app shell with `currentUser` in React context.

### 9.2 Login page

`/login` — single screen, no app chrome.

```
┌─────────────────────────────────┐
│  Quant Strategies               │
│                                 │
│  Username  [_____________]      │
│  Password  [_____________]      │
│                                 │
│  [   Sign in   ]                │
│                                 │
│  Invalid username or password.  │  ← inline error, no enumeration
└─────────────────────────────────┘
```

- MUI `<Card>` centered, `maxWidth: 400`.
- On submit → `POST /api/v1/auth/login` → on 200, invalidate `auth/me` query, navigate to `/`.
- Error states: 401 → "Invalid username or password" (single message, **never** distinguishes "no such user" vs "wrong password").
- Loading state: button disabled + spinner.
- No "Forgot password?" link — the page shows a static line: *"Forgot password? Contact your administrator."*

### 9.3 Logout

Header gains a user menu (top-right):
- Shows username.
- "Sign out" → `POST /api/v1/auth/logout` → clear local query cache → redirect to `/login`.

(No "Change password…" item — admin handles it.)

### 9.4 Axios interceptor

Global response interceptor: on `401`, evict `auth/me` and redirect to `/login`. Handles tokens that expire mid-session.

---

## 10. Performance & Caching

- JWT verification is local (HMAC) — sub-millisecond. No DB hit per request.
- The `SESSION_GEN + IS_ACTIVE_IND` check would add a DB round-trip per request. Mitigation: in-process LRU cache keyed by `app_user_id` with **5 s TTL**. Worst-case revocation latency: 5 s after the admin runs the `UPDATE`. Acceptable.
- Argon2id verification on login: ~100 ms (intentional). Login is rare; no concern.
- Concurrency cap on `/auth/login` (e.g. semaphore of 4) prevents a burst of logins from OOMing the box on Argon2's 64 MB-per-call memory.

---

## 11. Failure Handling

| Scenario | Behavior |
|---|---|
| Invalid credentials | `401`, generic message. Always run Argon2 verify against a precomputed dummy hash even if the user doesn't exist (timing-attack hardening — see §11.1). |
| User deactivated | Next request → cache miss or refresh → `401`, redirect to `/login`. Worst-case latency 5 s. |
| `JWT_SECRET` rotated | All users logged out on next request. |
| DB unreachable during login | `503`. SPA shows "Service unavailable, retry". |
| DB unreachable during request | The 5 s cache means requests within the window still succeed; afterwards `503`. |
| Brute force on `/auth/login` | **Layered rate limit**: see §11.2. |

### 11.2 Rate limiting (defense in depth)

Rate limiting is layered so that no single layer is a single point of failure (e.g. nginx misconfig in dev, direct uvicorn in tests):

| Layer | Tool | Rule | Why |
|---|---|---|---|
| Outer (network) | nginx `limit_req_zone` | 10 req/min per IP, burst 5, `/api/v1/auth/login` only | Cheap — rejects before reaching Python. Protects against IP-pinned floods. |
| Inner (app) | `slowapi` (FastAPI middleware) | 5 attempts / 15 min per IP on `/auth/login` | Works in dev / tests / direct-uvicorn. Per-route, easy to tune. |

Both fire `429 Too Many Requests`. The SPA shows: *"Too many login attempts. Try again in a few minutes."*

Neither layer locks the **account** (no DB state is mutated) — that requires the `FAILED_LOGIN_COUNT` / `LOCKED_UNTIL` columns deferred to Phase 3. With manually-provisioned users on a private deployment, IP-based throttle is sufficient.

### 11.1 Timing-attack hardening (concrete pattern)

```python
# api/auth/service.py
DUMMY_HASH = PasswordHasher().hash("not-a-real-password-xyz")

def verify_credentials(username: str, password: str) -> AppUser | None:
    user = repo.get_app_user_by_username(username)  # may be None
    hash_to_verify = user.password_hash if user else DUMMY_HASH
    try:
        ph.verify(hash_to_verify, password)
    except VerifyMismatchError:
        return None
    if user is None or user.is_active_ind != "Y":
        return None
    return user
```

Both branches do the same Argon2 work, so `/auth/login` has the same latency profile whether or not the username exists.

---

## 12. Security Checklist

- [x] Passwords hashed with Argon2id (`argon2-cffi`), default `memory_cost=65536, time_cost=3, parallelism=4`.
- [x] Password hashes generated **only** via `scripts/hash_password.py` running locally — never via online tools.
- [x] Cookies `HttpOnly + Secure + SameSite=Strict + Path=/api`.
- [x] HTTPS enforced at nginx (HSTS header).
- [x] Uvicorn binds to `127.0.0.1` only — never accept TLS-stripped traffic.
- [x] JWT signed (HS256) with secret from SSM, never committed.
- [x] `JWT_SECRET` is read at process start via the EC2 instance role from SSM SecureString. Never written to a `.env` file in production.
- [x] `JWT_SECRET` ≥ 32 random bytes (generated with `openssl rand -base64 32`).
- [x] Pydantic `max_length` bounds on `LoginRequest` to cap payload size.
- [x] Generic login error message (no user enumeration).
- [x] Constant-time verify path even when user does not exist (§11.1).
- [x] Layered rate limit on `/auth/login`: nginx + `slowapi` (§11.2).
- [x] Session revocation via `SESSION_GEN` bump (admin SP, see §7.1).
- [x] Logout clears cookie via `Set-Cookie: qs_token=; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Path=/api`.
- [x] No CORS wildcard. `CORS_ORIGINS` is exact list of allowed frontends.
- [x] Disable Swagger UI (`/api/docs`) in prod via `app = FastAPI(docs_url=None, redoc_url=None)` when `APP_ENV=prod`.
- [x] CSP header from nginx (`default-src 'self'`) to mitigate XSS-driven cookie abuse.
- [x] On successful login, call `PasswordHasher.check_needs_rehash()` — if true, recompute hash and call `SP_UPD_APP_USER_PASSWORD`. Cheap forward-compat for parameter bumps.
- [x] App DB login (`quant_app`) has only `USAGE` on schemas + `EXECUTE` on app-facing procs (§7.4). **No `SELECT` or any other table privilege — every read and write goes through an SP.** Admin SPs require `quant_admin`, used only via `psql`. Cluster master is never used by the runtime app.

---

## 13. Migration Plan

1. **Provision login users manually** (one-time, via DBeaver/`psql` as cluster master): `CREATE ROLE quant_app LOGIN PASSWORD '...'`. Verify pre-existing `quant_admin` is present. Passwords are typed at the prompt and immediately mirrored into SSM — they never enter Liquibase or any deploy env var.
2. **Liquibase changeset** `030-core-admin-app-user` creates `CORE_ADMIN.APP_USER` table.
3. **Liquibase changesets** for the 6 SPs (§7) — one changeset per SP, `runOnChange="true"`, `context="proc"`.
4. **Liquibase changeset** `099-core-admin-grants` issues all GRANTs directly to `quant_app` and `quant_admin` (§7.4), `context="grant"`, `runOnChange="true"` so future procs/tables get re-granted on each deploy.
5. **SSM**: change `/quant/prod/QUANTDB_USERNAME` from `postgres` → `quant_app` and rotate `/quant/prod/QUANTDB_PASSWORD` to `quant_app`'s password.
6. **Seed admin user** via a Liquibase changeset that calls `SP_INS_APP_USER` (context `dev` only). Prod runs the `CALL` manually as `quant_admin` after generating a fresh hash with the helper script. **Prod password is never committed.**
7. **Helper script** `scripts/hash_password.py` — reads password from stdin (no echo, via `getpass`), prints Argon2id PHC string. Doc warns against online hash generators.
8. **Add `JWT_SECRET`** to `/quant/prod/JWT_SECRET` (SSM SecureString, 32 random bytes base64). EC2 instance role reads it at process start; not written to `.env` in prod.
9. **Backend**: add `api/auth/` module (login router, JWT helpers, `require_user` dep, repo, service). Add `argon2-cffi`, `pyjwt[cryptography]`, `slowapi` to `requirements.txt`.
10. **Wire `Depends(require_user)`** into existing routers. Replace every `user_id="alfcheun"` with `user.username`. Remove the `="alfcheun"` default in [src/db.py](src/db.py) and [src/data.py](src/data.py) — parameter becomes required.
11. **Frontend**: add `/login` route + `<App>` mount-time `me` check + axios 401 interceptor + user menu.
12. **Tests**: unit tests for JWT encode/decode + Argon2 verify (incl. dummy-hash branch) + each admin SP; integration test for login → protected endpoint → logout flow.
13. **Docs**: update [README.md](README.md) auth section, [docs/architecture/api.md](docs/architecture/api.md) endpoint list, [docs/env-vars.md](docs/env-vars.md) (`JWT_SECRET`), [docs/decisions.md](docs/decisions.md) decision #27, [scripts/README.md](scripts/README.md) for the hash helper.

---

## 14. Phased Plan

### Phase 1 — Auth in place (this doc)
- `APP_USER` table, login/logout/me endpoints, route guard, manually-provisioned users.
- All authenticated users have full access (no row filtering).

### Phase 2 — Multi-user isolation
- Add `USER_ID` filter to BT/INST read queries.
- Per-user `BT.RESULT` lists in the SPA.
- Add `ROLE` column; admin user can see everyone's runs.

### Phase 3 — Self-service & richer auth
- `EMAIL` column + email-as-login-handle.
- `POST /auth/change-password` endpoint + UI modal.
- Admin user-management endpoints (`POST /admin/users`, etc.).
- Per-username failed-login lockout (`FAILED_LOGIN_COUNT`, `LOCKED_UNTIL`).
- `AUTH_EVENT` audit table.
- Eventually: SES + password reset by signed link, OAuth (Google), API keys, MFA (TOTP).

---

## 15. Future-proofing notes

These shape Phase 1 choices to avoid painful rewrites later:

- **JWT `sub` is `APP_USER_ID` (UUID), not `username`.** Renaming a user later does not invalidate their session.
- **Adding `EMAIL` later is a single Liquibase changeset** + `SP_GET_APP_USER_BY_EMAIL` + a frontend label change. The login service abstraction (§11.1) doesn't care which column it queries.
- **Adding `ROLE` later**: single ALTER TABLE + add to JWT claims + update `require_user` to expose it on `CurrentUser`.
- **Adding admin endpoints later**: introduce `SP_INS_APP_USER`, `SP_UPD_APP_USER_PASSWORD` then. Don't pre-build them now — they'd be untested dead code.

---

## 16. Open Questions

1. **Cookie `Path=/api` vs `Path=/`?** `/api` keeps the cookie off static asset requests (smaller header, less log noise). Recommended.
2. **Should `LAST_LOGIN_AT` update be fire-and-forget?** Yes — wrap in `BackgroundTasks` so login latency stays under 150 ms.
3. **Where does the user menu live?** Header right side, next to existing controls.
4. **Confirm uvicorn bind address.** The `appctl` script must launch with `--host 127.0.0.1`. Verify before going live.
5. **CSRF tokens on `/trade/*` writes when those land?** With `SameSite=Strict` already in place, additional CSRF tokens on trade endpoints are belt-and-braces. Decide when designing the trade router.

---

## 17. Recommendation

Build Phase 1 as specified. It's small (~1 backend module, 1 frontend page, 1 table, 2 SPs, 1 helper script) and unblocks **all** public-hosting work in the deployment ladder. Defer Phases 2–3 until there's a real second user or a real need.
