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

| Task | Event | Endpoint |
|------|-------|----------|
| `trade_apply` | `{"task": "trade_apply", "deployment_id": "<uuid>"}` | `POST /api/v1/trade/deployments/{id}/apply` |
| `price_bar_sync` (planned) | `{"task": "price_bar_sync", "payload": {...}}` | `POST /api/v1/market-data/price-bars/sync` — add to `_TASK_PATHS` once the endpoint exists |

An optional `payload` object becomes the POST body (defaults to `{}`).

## Env (set by CloudFormation)

| Variable | Source |
|----------|--------|
| `API_BASE_URL` | CFN parameter `ApiBaseUrl` (prod default `https://algodaemon.com`) |
| `TRADE_SERVICE_TOKEN_SSM_PATH` | Path of the SecureString, e.g. `/quant/prod/TRADE_SERVICE_TOKEN`. The handler fetches + decrypts it at cold start — CloudFormation cannot inject `ssm-secure` into Lambda env vars, and this keeps the secret out of plaintext function config. |
| `HTTP_TIMEOUT_S` | `110` (under the 120s Lambda timeout; live apply can retry orders for ~60s+) |

## Scheduler retry policy — important

The apply endpoint places **orders**. When the app creates schedules via
boto3, it must set `RetryPolicy.MaximumRetryAttempts = 0` — EventBridge
Scheduler's default (185 retries over 24h) would hammer a failing apply.
Order-level retries already live in the API (`OrderRetryExecutor`).

## Prerequisite

```bash
bash aws/scripts/init-ssm-params.sh   # creates TRADE_SERVICE_TOKEN if missing
bash aws/deploy.sh scheduler
```

**Note:** The API must accept this service token (Phase 1.9 app work). Until then,
manual invoke of the Lambda will reach nginx/API but return **401**.
