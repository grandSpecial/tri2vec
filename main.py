import openai
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select
from models import ClinicalTrial, TrialVector, SessionLocal  # Import your SQLAlchemy models and session
import os
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
import numpy as np

load_dotenv()

# Security setup
bearer_scheme = HTTPBearer()
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
assert API_AUTH_TOKEN is not None

# Validate token dependency
def validate_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials.scheme != "Bearer" or credentials.credentials != API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials

app = FastAPI(dependencies=[Depends(validate_token)])

# Initialize OpenAI API client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Function to generate vector from input text using OpenAI
def create_vector(text: str):
    try:
        response = client.embeddings.create(
            input=text,
            model="text-embedding-ada-002"
        )
        return np.array(response['data'][0]['embedding'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating vector: {e}")

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Endpoint to search for the closest vector match and return corresponding ClinicalTrial row
@app.post("/search_clinical_trials")
def search_clinical_trial(text: str, db: Session = Depends(get_db)):
    # Generate vector from input text
    vector = create_vector(text)
    
    # Search for the closest vector in the trial_vectors table
    try:
        closest_vector_entry = db.execute(
            select(TrialVector).order_by(TrialVector.vector.l2_distance(vector)).limit(10)
        ).scalar_one_or_none()

        if closest_vector_entry is None:
            raise HTTPException(status_code=404, detail="No matching trial vector found")
        
        # Lookup corresponding ClinicalTrial row by trial_id
        clinical_trial = db.query(ClinicalTrial).filter_by(id=closest_vector_entry.trial_id).first()

        if clinical_trial is None:
            raise HTTPException(status_code=404, detail="Clinical trial not found")

        return {
            "id": clinical_trial.id,
            "trial_id": clinical_trial.trial_id,
            "organization": clinical_trial.organization,
            "brief_title": clinical_trial.brief_title,
            "official_title": clinical_trial.official_title,
            "description": clinical_trial.description,
            "start_date": clinical_trial.start_date,
            "primary_completion_date": clinical_trial.primary_completion_date,
            "completion_date": clinical_trial.completion_date,
            "eligibility_criteria": clinical_trial.eligibility_criteria,
            "minimum_age": clinical_trial.minimum_age,
            "maximum_age": clinical_trial.maximum_age,
            "sex": clinical_trial.sex,
            "healthy_volunteers": clinical_trial.healthy_volunteers,
            "locations": clinical_trial.locations
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching for clinical trial: {e}")

# Endpoint to list all clinical trials with optional pagination
@app.get("/clinical_trials/")
def list_clinical_trials(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
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
