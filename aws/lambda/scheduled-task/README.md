# scheduled-task Lambda

Generic bridge from **EventBridge Scheduler** to the FastAPI app. One Lambda
serves every scheduled task; the event names the task, all business logic
stays in FastAPI.

```
POST {API_BASE_URL}{task path}
Authorization: Bearer {TRADE_SERVICE_TOKEN}
```

## Source of truth

- Handler: [`handler.py`](handler.py) (stdlib + bundled boto3 — no layers)
- Infra: [`../../cfn/04-scheduler.yml`](../../cfn/04-scheduler.yml)
- Deploy: `bash aws/deploy.sh scheduler` packages this directory and runs
  `aws lambda update-function-code`

## Event payload

The event carries **both** the task name and the path to post to:

```json
{"task": "trade_apply_tick", "path": "/api/v1/scheduler/tick"}
```

Both come from `config/scheduler/<task>.yml`, which `scripts/sync_schedules.py`
reads when it creates or updates the schedule. This handler holds no
task-to-path table, so adding or repointing a job is a YAML change with no
Lambda redeploy. Current jobs:

| Task | Endpoint | Config |
|------|----------|--------|
| `trade_apply_tick` | `POST /api/v1/scheduler/tick` | `config/scheduler/trade_apply_tick.yml` |
| `price_bar_sync` | `POST /api/v1/market-data/price-bars/sync` | `config/scheduler/price_bar_sync.yml` |
| `log_proc_summary` | `POST /api/v1/admin/log-proc-summary/summarize` | `config/scheduler/log_proc_summary.yml` |

An optional `payload` object becomes the POST body (defaults to `{}`).

No path takes substitution fields, and deliberately so: each route acts on
everything currently due, which is what lets one schedule serve every
deployment. There is no per-deployment `trade_apply` job — that route requires a
human, since it trades on the caller's own account, so a schedule pointing at it
could only return 401. `trade_apply_tick` applies each due deployment as the
owner the database resolves for it.

Because the path comes from the event, the handler validates it: it must be an
absolute path, never a URL. Every request leaves here with the service token
attached, so an event must not be able to choose the host it is sent to.

## Env (set by CloudFormation)

| Variable | Source |
|----------|--------|
| `API_BASE_URL` | CFN parameter `ApiBaseUrl` (prod default `https://algodaemon.com`) |
| `TRADE_SERVICE_TOKEN_SSM_PATH` | Path of the SecureString, e.g. `/quant/prod/TRADE_SERVICE_TOKEN`. The handler fetches + decrypts it at cold start — CloudFormation cannot inject `ssm-secure` into Lambda env vars, and this keeps the secret out of plaintext function config. |
| `HTTP_TIMEOUT_S` | `110` (under the 120s Lambda timeout; live apply can retry orders for ~60s+) |

## Scheduler retry policy — important

The tick places **orders**. `scripts/sync_schedules.py` sets
`RetryPolicy.MaximumRetryAttempts = 0` on every schedule it creates —
EventBridge Scheduler's default (185 retries over 24h) would hammer a failing
apply. Order-level retries live in the API (`OrderRetryExecutor`), and the tick's
own attempt budget retries a deployment on the next wakeup rather than seconds
later.

## Prerequisite

```bash
bash aws/scripts/init-ssm-params.sh   # creates TRADE_SERVICE_TOKEN if missing
bash aws/deploy.sh scheduler
```

**Note:** The API must accept this service token (Phase 1.9 app work). Until then,
manual invoke of the Lambda will reach nginx/API but return **401**.
