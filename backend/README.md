# SaaS Manager — In-house SaaS management platform

A self-hosted alternative to Zylo. Discovers, tracks, and optimizes your SaaS portfolio.

## Features

- **Discovery** — sync all apps from Okta and/or Azure AD automatically
- **Shadow IT detection** — flag apps found in expense data but not in IdP
- **License management** — track seats purchased vs. active, calculate waste
- **Contract tracking** — renewal calendar with automated Slack/email alerts
- **Usage analytics** — utilization trends by app and department
- **CSV import** — bulk-import apps, licenses, and contracts

## Tech stack

- **API**: FastAPI + SQLAlchemy (async) + PostgreSQL
- **Jobs**: Celery + Redis (scheduled syncs, renewal alerts)
- **Storage**: S3-compatible (contract PDFs)

## Quick start

```bash
# 1. Clone and copy env
cp .env.example .env
# Edit .env with your Okta/Azure credentials

# 2. Start services
docker-compose up -d db redis

# 3. Install dependencies
poetry install

# 4. Run migrations
alembic upgrade head

# 5. Start the API
uvicorn app.main:app --reload

# 6. Start the Celery worker (separate terminal)
celery -A app.worker worker --loglevel=info -Q default,sync

# 7. Start Celery beat scheduler (separate terminal)
celery -A app.worker beat --loglevel=info
```

Or run everything with Docker:
```bash
docker-compose up
```

## API docs

After starting: http://localhost:8000/docs

## Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/dashboard | Summary stats (spend, waste, renewals) |
| GET | /api/v1/apps | List all apps (filter by status, category, shadow IT) |
| POST | /api/v1/apps | Add an app manually |
| GET | /api/v1/contracts | List contracts (filter by expiring soon) |
| POST | /api/v1/contracts | Add a contract |
| POST | /api/v1/contracts/{id}/upload | Attach a PDF to a contract |
| POST | /api/v1/sync/okta | Trigger Okta sync manually |
| POST | /api/v1/sync/azure-ad | Trigger Azure AD sync manually |
| POST | /api/v1/sync/import/csv | Bulk import via CSV |
| GET | /api/v1/sync/jobs | Sync job history |

## CSV import format

**apps.csv**: `name, vendor, category, status, owner_email, department, website`

**licenses.csv**: `app_name, license_type, seats_purchased, cost_per_seat_cents, total_annual_cost_cents, currency, billing_cycle`

**contracts.csv**: `app_name, start_date, end_date, auto_renews, cancellation_notice_days, total_value_cents, currency, owner_email, notes`

## Project structure

```
app/
  api/v1/endpoints/   # Route handlers
  core/               # Config, auth
  db/                 # SQLAlchemy session
  integrations/       # Okta + Azure AD clients
  models/             # DB models
  schemas/            # Pydantic request/response schemas
  services/           # Business logic (sync, import, alerts)
  worker.py           # Celery tasks + beat schedule
  main.py             # FastAPI app
alembic/              # DB migrations
```

## Next steps

1. Add auth middleware (JWT or forward-auth to your IdP)
2. Build the React dashboard frontend
3. Add license endpoint (`/api/v1/licenses`)
4. Add the finance/ERP connectors when ready (NetSuite, Concur)
5. Add utilization trend snapshots (cron job that saves daily utilization to a timeseries table)
