import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ClinicalTrial, SessionLocal, TrialVector

load_dotenv()
logger = logging.getLogger(__name__)

# Security setup
bearer_scheme = HTTPBearer()
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not API_AUTH_TOKEN:
    raise RuntimeError("Missing required environment variable: API_AUTH_TOKEN")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing required environment variable: OPENAI_API_KEY")

# Validate token dependency
def validate_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials.scheme != "Bearer" or credentials.credentials != API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials

app = FastAPI(
    title="TRI2VEC",
    description="Semantic search over recruiting clinical trials via pgvector embeddings.",
    dependencies=[Depends(validate_token)],
)

# Initialize OpenAI API client
client = OpenAI(api_key=OPENAI_API_KEY)

# Function to generate vectors using OpenAI
def create_vector(text: str) -> list[float]:
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
        encoding_format="float",
    )
    return response.data[0].embedding

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def serialize_trial(trial: ClinicalTrial) -> dict[str, Any]:
    return {
        "id": trial.id,
        "trial_id": trial.trial_id,
        "organization": trial.organization,
        "brief_title": trial.brief_title,
        "official_title": trial.official_title,
        "description": trial.description,
        "start_date": trial.start_date,
        "primary_completion_date": trial.primary_completion_date,
        "completion_date": trial.completion_date,
        "eligibility_criteria": trial.eligibility_criteria,
        "minimum_age": trial.minimum_age,
        "maximum_age": trial.maximum_age,
        "sex": trial.sex,
        "healthy_volunteers": trial.healthy_volunteers,
        "locations": trial.locations,
    }


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/search_clinical_trials")
def search_clinical_trial(
    text: str,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Generate vector from input text
    vector = create_vector(text)

    try:
        # Direct join avoids an additional query per match.
        closest_trials = db.execute(
            select(ClinicalTrial)
            .join(TrialVector, TrialVector.trial_id == ClinicalTrial.id)
            .order_by(TrialVector.vector.l2_distance(vector))
            .limit(limit)
        ).scalars().all()

        if not closest_trials:
            raise HTTPException(status_code=404, detail="No matching trial vectors found")

        return [serialize_trial(trial) for trial in closest_trials]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while searching clinical trials")
        raise HTTPException(status_code=500, detail="Internal error while searching clinical trials")

# Endpoint to list all clinical trials with optional pagination
@app.get("/clinical_trials/")
def list_clinical_trials(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    trials = db.query(ClinicalTrial).offset(skip).limit(limit).all()
    if not trials:
        raise HTTPException(status_code=404, detail="No clinical trials found")
    return trials

# Endpoint to retrieve a specific clinical trial by trial_id
@app.get("/clinical_trial/{trial_id}")
def get_clinical_trial(trial_id: int, db: Session = Depends(get_db)):
    clinical_trial = db.query(ClinicalTrial).filter(ClinicalTrial.id == trial_id).first()
    if clinical_trial is None:
        raise HTTPException(status_code=404, detail="Clinical trial not found")
    return clinical_trial
