import openai
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select
from models import (
    ClinicalTrial,
    TrialVector,
    User,
    SentNotification,
    SessionLocal,
    UserCreate,
)
from twilio.rest import Client
import os
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from typing import List
import numpy as np
from datetime import datetime

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

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


@app.get("/", include_in_schema=False)
def landing_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "templates", "index.html"))

# Initialize OpenAI API client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sms_client = (
    Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
    else None
)

# Function to generate vectors using OpenAI
def create_vector(text):
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
        encoding_format="float"
    )
    return response.data[0].embedding


def send_sms(to_number: str, message: str):
    if not sms_client or not TWILIO_FROM_NUMBER:
        raise RuntimeError("Twilio is not configured")
    sms_client.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=to_number)

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/users")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    vector = create_vector(user.description)
    db_user = User(phone_number=user.phone_number, description=user.description, vector=vector)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"id": db_user.id}


@app.post("/notify_users")
def notify_users(limit: int = 5, db: Session = Depends(get_db)):
    users = db.query(User).all()
    for user in users:
        results = db.execute(
            select(TrialVector).order_by(TrialVector.vector.cosine_distance(user.vector)).limit(limit)
        ).scalars().all()
        for entry in results:
            exists = db.query(SentNotification).filter_by(user_id=user.id, trial_id=entry.trial_id).first()
            if exists:
                continue
            trial = db.query(ClinicalTrial).filter_by(id=entry.trial_id).first()
            if not trial:
                continue
            url = f"https://clinicaltrials.gov/study/{trial.trial_id}"
            message = f"Potential trial match: {trial.brief_title} - {url}"
            send_sms(user.phone_number, message)
            db.add(SentNotification(user_id=user.id, trial_id=entry.trial_id, sent_at=datetime.utcnow().isoformat()))
            db.commit()
    return {"status": "done"}

@app.post("/search_clinical_trials")
def search_clinical_trial(text: str, limit: int = 10, db: Session = Depends(get_db)):
    # Generate vector from input text
    vector = create_vector(text)
    
    # Search for the closest vectors in the trial_vectors table, limited by the 'limit' parameter
    try:
        closest_vector_entries = db.execute(
            select(TrialVector).order_by(TrialVector.vector.l2_distance(vector)).limit(limit)
        ).scalars().all()  # Fetch up to 'limit' closest entries

        if not closest_vector_entries:
            raise HTTPException(status_code=404, detail="No matching trial vectors found")
        
        # Lookup corresponding ClinicalTrial rows by trial_id
        clinical_trials = []
        for entry in closest_vector_entries:
            clinical_trial = db.query(ClinicalTrial).filter_by(id=entry.trial_id).first()
            if clinical_trial:
                clinical_trials.append({
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
                })

        # If no clinical trials are found, raise an error
        if not clinical_trials:
            raise HTTPException(status_code=404, detail="No clinical trials found for matched vectors")

        return clinical_trials
    
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
