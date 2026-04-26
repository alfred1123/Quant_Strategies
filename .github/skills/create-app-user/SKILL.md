---
name: create-app-user
description: 'Create or manage a CORE_ADMIN.APP_USER row (login account for the FastAPI app). Use when seeding the first admin user, adding a new human teammate, resetting a password, deactivating a user, or forcing a logout-everywhere. Covers hashing the password locally with scripts/hash_password.py and calling the right SP as quant_admin.'
---

# Create / Manage App User Skill

## When to Use

- Seeding the first admin user after a fresh DB deploy
- Adding a new human user to the system
- Resetting a forgotten password
- Deactivating (or re-activating) a user
- Forcing logout-everywhere (lost laptop) without changing the password

## Prerequisites

1. SSM port-forward task running (`localhost:5433` reachable).
2. `.env` exports `LIQUIBASE_COMMAND_USERNAME=quant_admin` and `LIQUIBASE_COMMAND_PASSWORD=<admin-pw>`.
3. Schema deployed: `CORE_ADMIN.APP_USER` table + 6 SPs (`SP_GET_APP_USER_BY_USERNAME`, `SP_INS_APP_USER`, `SP_UPD_APP_USER_PASSWORD`, `SP_UPD_APP_USER_ACTIVE`, `SP_UPD_APP_USER_BUMP_TOKEN`, `SP_UPD_APP_USER_LAST_LOGIN`).
4. `argon2-cffi` installed (`pip install -r requirements.txt`).

## The Two-Step Pattern

Hashing and DB-writing are kept separate **on purpose**:

| Step | Tool | Why separated |
|---|---|---|
| 1. Hash password | `scripts/hash_password.py` (offline, no DB) | Pure function. No network. Hash never touches a third-party site. |
| 2. Seed/update row | `psql ... -c "CALL CORE_ADMIN.SP_INS_APP_USER(...)"` | Privileged DB write. Explicit. Auditable via `LOG_PROC_DETAIL`. |

**Never** combine them into one script that knows DB credentials AND reads passwords — that script would be a juicier target than either piece alone.

## 1. Hash the Password

```bash
$ python scripts/hash_password.py
Password: ••••••••••••       # ≥ 12 chars, not echoed
Confirm:  ••••••••••••       # asked twice to catch typos
$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
```

- Reads via `getpass` — no shell-history leak, no `ps aux` leak.
- Prompts go to **stderr**; the hash goes to **stdout** (single line, no labels).
- Exit codes: `0` ok · `1` mismatch · `2` too short (<12) · `3` cancelled.
- Pipe-friendly:

```bash
HASH=$(python scripts/hash_password.py)
```

## 2. Call the Right Stored Procedure

Always run as `quant_admin` (set in `.env`).

### 2a. Create a new user

```bash
HASH=$(python scripts/hash_password.py)

source .env
psql "host=localhost port=5433 dbname=quantdb \
      user=$LIQUIBASE_COMMAND_USERNAME \
      password=$LIQUIBASE_COMMAND_PASSWORD" \
  -c "CALL CORE_ADMIN.SP_INS_APP_USER('newuser', '$HASH', 'alfcheun', NULL, NULL, NULL, NULL);"
unset HASH
```

Argument order: `IN_USERNAME, IN_PASSWORD_HASH, IN_USER_ID, OUT_APP_USER_ID, OUT_SQLSTATE, OUT_SQLMSG, OUT_SQLERRMC`. **OUT params must be passed as `NULL` placeholders by position** — psql's `CALL` does not accept `=>` named syntax for OUT arguments. The procedure prints the OUT values as a result row.

Defaults set by the SP: `IS_ACTIVE_IND='Y'`, `SESSION_GEN=1`, `APP_USER_ID = gen_random_uuid()`, `CREATED_AT = NOW()`.

### 2b. Reset a password

```bash
HASH=$(python scripts/hash_password.py)

psql ... -c "CALL CORE_ADMIN.SP_UPD_APP_USER_PASSWORD('alice', '$HASH', 'alfcheun', NULL, NULL, NULL);"
unset HASH
```

Side effect: `SESSION_GEN` is bumped — every existing JWT for `alice` becomes invalid on the next protected request.

### 2c. Deactivate / re-activate a user

```bash
psql ... -c "CALL CORE_ADMIN.SP_UPD_APP_USER_ACTIVE('alice', 'N', 'alfcheun', NULL, NULL, NULL);"
# Pass 'Y' instead of 'N' to re-activate.
```

Side effect: `SESSION_GEN` is bumped.

### 2d. Force logout-everywhere (lost laptop, no password change)

```bash
psql ... -c "CALL CORE_ADMIN.SP_UPD_APP_USER_BUMP_TOKEN('alice', 'alfcheun', NULL, NULL, NULL);"
```

Only `SESSION_GEN` and `UPDATED_AT` change. Password and active flag untouched. Alice can log back in with her existing password.

## 3. Verify

```bash
psql "host=localhost port=5433 dbname=quantdb \
      user=$LIQUIBASE_COMMAND_USERNAME \
      password=$LIQUIBASE_COMMAND_PASSWORD" \
  -c "SELECT username, is_active_ind, session_gen, last_login_at, created_at, updated_at
        FROM core_admin.app_user
       ORDER BY created_at;"
```

For audit trail of *who did what when*:

```sql
SELECT proc_nm, start_ts, user_id, other_text, sql_state
  FROM core_admin.log_proc_detail
 WHERE proc_nm LIKE 'SP_%APP_USER%'
 ORDER BY start_ts DESC
 LIMIT 20;
```

## Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `ERROR: password must be at least 12 characters` (script exits 2) | Pydantic + script enforce 12-char minimum | Use a longer password |
| `ERROR: duplicate key value violates unique constraint "ux_app_user_username"` | Username already exists | Use `SP_UPD_APP_USER_PASSWORD` instead, or pick a different username |
| `permission denied for procedure sp_ins_app_user` | Connected as `quant_app` not `quant_admin` | Re-source `.env` and confirm `LIQUIBASE_COMMAND_USERNAME=quant_admin` |
| `procedure ... does not exist ... You might need to add explicit type casts` | Forgot the `NULL` placeholders for the 4 OUT parameters — the proc has 7 positional args, not 3 | Add the trailing `, NULL, NULL, NULL, NULL` for `SP_INS_APP_USER` (or 3 NULLs for the others) |
| User can still log in after deactivation | JWT cache TTL not yet expired (≤ 5 s) | Wait 5 seconds, then retry |
| Password hash leaks into shell history | Used `--password=...` flag pattern | Always pipe via `HASH=$(python scripts/hash_password.py)` |
| `psql: FATAL: SSL connection has been closed unexpectedly` | SSM tunnel went stale | Restart the `SSM Port Forward` VS Code task |

## Anti-Patterns

- ❌ Pasting plaintext passwords into online "Argon2 hash generator" sites.
- ❌ Writing a one-shot script that takes the password as a CLI arg.
- ❌ Direct `INSERT INTO core_admin.app_user ...` — bypasses the audit log and is forbidden by `AGENTS.md` ("No Direct DML").
- ❌ Storing the plaintext password anywhere — even temporarily in a shell variable. Only the hash should ever be assigned to `$HASH`.
- ❌ Running these procs as `quant_app` — they are intentionally not granted to the runtime role.

## Related

- Design rationale: [docs/design/login.md](../../../docs/design/login.md) §7.1 (Admin runbook), §7.4 (Why no `SELECT` on `quant_app`).
- DDL conventions: [.github/skills/db-ddl/SKILL.md](../db-ddl/SKILL.md) — `_GEN` suffix for `SESSION_GEN`.
- Liquibase deployment: [.github/skills/liquibase/SKILL.md](../liquibase/SKILL.md).
