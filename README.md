# SaaS Manager

Full-stack SaaS management platform. One `docker compose up` runs everything.

## Quick start

```bash
# 1. Fill in your config
cp .env.example .env
# Open .env and set SECRET_KEY (required) + Okta/Azure credentials

# 2. Start everything
docker compose up
```

That's it. Visit **http://localhost** for the dashboard.

The first run takes a few minutes to build the images. After that, starts in seconds.

## What's running

| Service | URL | Description |
|---------|-----|-------------|
| UI | http://localhost | React dashboard (Nginx) |
| API | http://localhost:8000/docs | FastAPI + Swagger docs |
| DB | localhost:5432 | Postgres 16 |
| Redis | localhost:6379 | Job queue |

## Updating

```bash
git pull
docker compose up --build
```

Migrations run automatically on every start.

## Stopping

```bash
docker compose down          # stop, keep data
docker compose down -v       # stop, wipe all data
```
