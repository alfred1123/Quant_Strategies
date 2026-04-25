# Environment Variables

Copy the template and fill in any keys you need:

```bash
cp .env.example .env
```

| Variable | Required? | Description |
|---|---|---|
| `ALPHAVANTAGE_API_KEY` | Optional | Free key from [alphavantage.co](https://www.alphavantage.co/support/#api-key). Limited to 25 req/day. |
| `GLASSNODE_API_KEY` | Optional | On-chain crypto metrics. Only if you use the Glassnode data source. |
| `FUTU_HOST` / `FUTU_PORT` | Optional | Only if using Futu OpenD gateway for HK/US equities. |
| `QUANTDB_HOST` | Optional | PostgreSQL host (default: `localhost`). |
| `QUANTDB_PORT` | Optional | PostgreSQL port (default: `5433`). |
| `QUANTDB_USERNAME` | Optional | Database user for quantdb. |
| `QUANTDB_PASSWORD` | Optional | Database password. |
| `QUANTDB_CONNINFO` | Optional | Full libpq connection string. **Overrides** the four `QUANTDB_*` vars above. Must include `sslmode=require`. Use only when you need non-standard libpq options (e.g. `connect_timeout`, `application_name`). Leave unset for normal dev/prod — the four split vars are preferred. |

!!! note
    **Yahoo Finance requires no API key** — it is the default and recommended data source for getting started.

!!! warning
    Never commit `.env` to version control. It is gitignored.
