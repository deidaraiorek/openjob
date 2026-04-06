# OpenJob

OpenJob is a personal job-application autopilot. The first implementation slice sets up the React portal, FastAPI backend, local development stack, and owner-only authentication shell.

## Stack

- `frontend/`: React, TypeScript, Vite, Tailwind CSS
- `backend/`: FastAPI, SQLAlchemy, Celery-ready Python app shell
- `docker-compose.yml`: local Postgres, Redis, backend, and frontend services

## Local Development

1. Copy `.env.example` to `.env` and update the owner credentials plus session secret.
2. Start the stack with `docker compose up --build`.
3. Open `http://localhost:5173` for the portal and `http://localhost:8000/api/health` for the API.

## Manual Host Setup

If you prefer to run services outside Docker:

1. Create a Python virtualenv and install the backend package from `backend/`.
2. Run the FastAPI server with `uvicorn app.main:app --reload --app-dir backend`.
3. In `frontend/`, run `npm install` and `npm run dev`.

## Current Scope

This scaffold intentionally stops at the platform shell:

- owner login/logout
- protected dashboard bootstrap
- health endpoint
- frontend router and API client
- local development infrastructure

The job-source ingestion, data model, and application automation units come next.
