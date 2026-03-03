# Architecture

TRI2VEC has three moving parts:

1. Trial ingestion (`import.py`)
2. API + SMS service (`main.py`)
3. Postgres + pgvector storage (`models.py`)

## Data Flow

1. `import.py` fetches studies from ClinicalTrials.gov.
2. Recruiting studies are upserted into `clinical_trials`.
3. Embeddings are stored in `trial_vectors`.
4. A patient texts Twilio.
5. `POST /webhooks/twilio/sms` receives message.
6. First-time users text `HELLO` to begin onboarding.
7. Service asks for symptoms, then location.
8. Onboarding text is scrubbed for obvious PII patterns.
9. Scrubbed profile text is embedded and matched to nearest trial vectors by the monitor.
10. Background monitor sends updates when new matches are found.

## Tables

- `clinical_trials`: trial metadata
- `trial_vectors`: one embedding per trial
- `subscriber_profiles`: phone + status + scrubbed profile text + profile embedding
- `subscriber_notifications`: dedupe table to avoid sending same trial repeatedly

## Endpoints

Public:

- `GET /`
- `GET /healthz`
- `POST /webhooks/twilio/sms`

Protected (Bearer token):

- `POST /search_clinical_trials`
- `GET /clinical_trials/`
- `GET /clinical_trial/{trial_id}`
- `POST /admin/run_monitor`
- `POST /admin/refresh_trials`
