# HelloTrial (TRI2VEC Repo)

HelloTrial is an open-source SMS service that helps patients discover recruiting clinical trials using plain-language text messages.

This project is built as a social enterprise initiative for patient access. The code is intentionally simple, transparent, and auditable.

## Why This Exists

Many patients never find relevant studies because search tools are difficult to use.

HelloTrial lets patients text what they are looking for (condition, symptoms, location), then replies with matching clinical trial links.

## Trust and Transparency

- Open-source codebase (MIT license)
- Pattern-based PII scrubbing before matching
- Explicit SMS disclosures and opt-out commands
- Twilio webhook signature validation
- No ad-tech or resale logic in code

Read more:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [PRIVACY.md](PRIVACY.md)
- [SECURITY.md](SECURITY.md)

## Features

- Ingests recruiting studies from ClinicalTrials.gov
- Generates embeddings with OpenAI (`text-embedding-3-small`)
- Uses PostgreSQL + pgvector nearest-neighbor matching
- Handles SMS via Twilio (`HELLO`, `STOP`, `HELP`)
- Sends follow-up alerts for newly matched trials
- Includes a clinic-friendly landing page poster at `/`

## Repository Layout

- `main.py`: FastAPI app + SMS webhook + monitor loop
- `import.py`: ClinicalTrials.gov ingestion and indexing
- `models.py`: SQLAlchemy models and DB setup
- `settings.py`: environment loading and validation
- `privacy.py`: PII scrubbing and phone formatting helpers
- `landing_page.py`: landing page rendering
- `static/landing.html`, `static/landing.css`: poster UI

## Requirements

- Python 3.12.x
- PostgreSQL with `pgvector`
- OpenAI API key
- Twilio account + SMS-capable number

## Environment Variables

Copy `.env.example` to `.env` and set:

- `OPENAI_API_KEY`
- `API_AUTH_TOKEN`
- `DATABASE_URL`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `MONITOR_INTERVAL_MINUTES` (default `60`)
- `MONITOR_MATCH_LIMIT` (default `3`)
- `DONATION_URL`

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Enable pgvector:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Create tables:

```bash
python models.py
```

Ingest trials:

```bash
python import.py
```

Run API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Twilio Setup

1. Configure an SMS-enabled number in Twilio.
2. Set webhook URL to `https://<your-domain>/webhooks/twilio/sms` (POST).
3. Add Twilio credentials to `.env`.

## SMS User Flow

1. User texts `HELLO` to begin.
2. Service asks for symptoms.
3. Service asks for location.
4. Service stores scrubbed preferences and subscribes user for monitoring.
5. Service texts users when new trial matches are found.

## Landing Page Assets

- Landing page is static HTML/CSS at:
  - `static/landing.html`
  - `static/landing.css`

## API Endpoints

Public:

- `GET /`
- `GET /healthz`
- `POST /webhooks/twilio/sms`

Protected (`Authorization: Bearer <API_AUTH_TOKEN>`):

- `POST /search_clinical_trials?text=<query>&limit=<n>`
- `GET /clinical_trials/?skip=<n>&limit=<n>`
- `GET /clinical_trial/{trial_id}`
- `POST /admin/run_monitor`
- `POST /admin/refresh_trials`

## Operational Notes

- `STOP` must immediately unsubscribe users.
- This is informational software, not medical advice.
- In emergencies users should call 911.

## Publish-Ready Checklist

1. Rotate credentials before going public.
2. Verify `.env` is not tracked.
3. Scan for secrets in files and history.
4. Confirm legal/privacy language for your jurisdiction.
5. Add issue templates and CI checks for contributors.
