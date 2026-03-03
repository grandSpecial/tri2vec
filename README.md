# TRI2VEC

TRI2VEC is a semantic search API for clinical trials. It ingests study data from [ClinicalTrials.gov](https://clinicaltrials.gov/), stores recruiting trials in Postgres, generates vector embeddings with OpenAI, and serves nearest-neighbor search over `pgvector`.

## What It Does

- Fetches studies from the ClinicalTrials.gov v2 API
- Keeps only `RECRUITING` trials in the local index
- Generates embeddings (`text-embedding-3-small`) for each trial
- Stores structured trial data + vectors in PostgreSQL (`pgvector`)
- Exposes a token-protected FastAPI service for semantic trial search

## Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy
- PostgreSQL + pgvector
- OpenAI embeddings API

## Project Structure

- `main.py`: FastAPI service and search endpoints
- `import.py`: ingestion/upsert pipeline from ClinicalTrials.gov
- `models.py`: SQLAlchemy models and DB session setup
- `Procfile`: Heroku-style web command
- `.env.example`: required environment variables

## Setup

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create your env file from the template.

```bash
cp .env.example .env
```

3. Fill in values in `.env`:

- `OPENAI_API_KEY`
- `API_AUTH_TOKEN` (random secret for API access)
- `DATABASE_URL` (Postgres connection string)

4. Ensure Postgres has `pgvector` enabled:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

5. Create tables:

```bash
python models.py
```

## Ingest Data

Run the importer to fetch and index trials:

```bash
python import.py
```

## Run API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The app requires Bearer auth for all endpoints.

## API Endpoints

- `GET /healthz`
- `POST /search_clinical_trials?text=<query>&limit=<n>`
- `GET /clinical_trials/?skip=<n>&limit=<n>`
- `GET /clinical_trial/{trial_id}`

Example search request:

```bash
curl -X POST "http://localhost:8000/search_clinical_trials?text=metastatic+breast+cancer&limit=5" \
  -H "Authorization: Bearer $API_AUTH_TOKEN"
```

## Security Notes

- No secrets are committed in this repo.
- `.env` files are ignored by git.
- API tokens and OpenAI keys are read from environment variables only.
- The API no longer returns raw internal exception messages to clients.

## Public Release Checklist

Before switching this repository to public:

1. Rotate `OPENAI_API_KEY` and `API_AUTH_TOKEN` if they were ever used in this project previously.
2. Verify `.env` is not tracked: `git ls-files | rg "^\\.env$"` should return nothing.
3. Run a quick secret scan:
   `rg -n --hidden -S "(sk-|OPENAI_API_KEY|API_AUTH_TOKEN|BEGIN PRIVATE KEY|AKIA)" . --glob '!.git'`
4. Review commit history for accidental secrets before publishing.

## Future Improvements

- Add unit/integration tests for import and search behavior
- Add DB migrations (Alembic) instead of ad-hoc table creation
- Add structured logging and metrics for ingestion and query latency
