import requests
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from requests.adapters import HTTPAdapter
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from tqdm import tqdm
from urllib3.util.retry import Retry

from models import ClinicalTrial, ClinicalTrialCreate, SessionLocal, TrialVector

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing required environment variable: OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Configure retry strategy for network requests
retry_strategy = Retry(
    total=5,  # Number of retry attempts
    backoff_factor=1,  # Wait time multiplier (in seconds) for each retry
    status_forcelist=[429, 500, 502, 503, 504],  # Retry for these HTTP status codes
    raise_on_status=False,  # Don't raise an exception for bad status codes
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)

# Function to generate vectors using OpenAI
def create_vector(text: str) -> list[float]:
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
        encoding_format="float",
    )
    return response.data[0].embedding

# Function to upsert clinical trial details
def upsert_clinical_trial(session: Session, trial_data: ClinicalTrialCreate) -> int:
    stmt = insert(ClinicalTrial).values(
        trial_id=trial_data.trial_id,
        organization=trial_data.organization,
        brief_title=trial_data.brief_title,
        official_title=trial_data.official_title,
        description=trial_data.description,
        start_date=trial_data.start_date,
        primary_completion_date=trial_data.primary_completion_date,
        completion_date=trial_data.completion_date,
        eligibility_criteria=trial_data.eligibility_criteria,
        minimum_age=trial_data.minimum_age,
        maximum_age=trial_data.maximum_age,
        sex=trial_data.sex,
        healthy_volunteers=trial_data.healthy_volunteers,
        locations=trial_data.locations
    ).on_conflict_do_update(
        index_elements=['trial_id'],
        set_={
            'organization': insert(ClinicalTrial).excluded.organization,
            'brief_title': insert(ClinicalTrial).excluded.brief_title,
            'official_title': insert(ClinicalTrial).excluded.official_title,
            'description': insert(ClinicalTrial).excluded.description,
            'start_date': insert(ClinicalTrial).excluded.start_date,
            'primary_completion_date': insert(ClinicalTrial).excluded.primary_completion_date,
            'completion_date': insert(ClinicalTrial).excluded.completion_date,
            'eligibility_criteria': insert(ClinicalTrial).excluded.eligibility_criteria,
            'minimum_age': insert(ClinicalTrial).excluded.minimum_age,
            'maximum_age': insert(ClinicalTrial).excluded.maximum_age,
            'sex': insert(ClinicalTrial).excluded.sex,
            'healthy_volunteers': insert(ClinicalTrial).excluded.healthy_volunteers,
            'locations': insert(ClinicalTrial).excluded.locations
        }
    ).returning(ClinicalTrial.id)
    result = session.execute(stmt)
    trial_id = result.scalar_one()
    session.flush()
    return trial_id

# Function to upsert vector for clinical trial
def upsert_trial_vector(session: Session, trial_id: int, text: str) -> None:
    vector = create_vector(text)
    stmt = insert(TrialVector).values(
        trial_id=trial_id,
        vector=vector
    ).on_conflict_do_update(
        index_elements=['trial_id'],
        set_={'vector': insert(TrialVector).excluded.vector}
    )
    session.execute(stmt)
    session.flush()


def build_embedding_text(trial_data: ClinicalTrialCreate) -> Optional[str]:
    components = [
        trial_data.brief_title,
        trial_data.official_title,
        trial_data.description,
        trial_data.eligibility_criteria,
    ]
    text = "\n\n".join(part.strip() for part in components if part and part.strip())
    return text or None

# Manage trial entry and ensure it aligns with current recruiting status
def manage_trial_entry(session: Session, trial_data: ClinicalTrialCreate, overall_status: Optional[str]) -> None:
    # Query for existing ClinicalTrial entry using string trial_id
    existing_trial = session.query(ClinicalTrial).filter_by(trial_id=trial_data.trial_id).first()

    if overall_status != "RECRUITING":
        if existing_trial:
            session.query(TrialVector).filter_by(trial_id=existing_trial.id).delete()
            session.delete(existing_trial)
            session.flush()
        return

    trial_id = upsert_clinical_trial(session, trial_data)
    embedding_text = build_embedding_text(trial_data)
    if embedding_text:
        upsert_trial_vector(session, trial_id, embedding_text)

# Function to fetch, process, and manage clinical trials from the API
def fetch_and_process_clinical_trials(
    session: Session,
    url: str = "https://clinicaltrials.gov/api/v2/studies",
) -> None:
    page_count = 0
    with tqdm(desc="Fetching pages", unit="page") as page_bar:
        while url:
            page_count += 1
            page_bar.set_postfix({"Page": page_count})

            try:
                response = http.get(url)
                response.raise_for_status()
                data = response.json()
                studies = data.get('studies', [])

                with tqdm(total=len(studies), desc=f"Processing trials in page {page_count}", unit="trial") as trial_bar:
                    for s in studies:
                        status_obj = s.get('protocolSection', {}).get('statusModule', {})
                        overall_status = status_obj.get('overallStatus')
                        
                        protocol_section = s.get('protocolSection', {})
                        identification_module = protocol_section.get('identificationModule', {})
                        description_module = protocol_section.get('descriptionModule', {})
                        eligibility_module = protocol_section.get('eligibilityModule', {})
                        locations_module = protocol_section.get('contactsLocationsModule', {})

                        trial_data = ClinicalTrialCreate(
                            trial_id=identification_module.get('nctId'),
                            organization=identification_module.get('organization', {}).get('fullName'),
                            brief_title=identification_module.get('briefTitle'),
                            official_title=identification_module.get('officialTitle'),
                            description=description_module.get('briefSummary'),
                            start_date=status_obj.get('startDateStruct', {}).get('date'),
                            primary_completion_date=status_obj.get('primaryCompletionDateStruct', {}).get('date'),
                            completion_date=status_obj.get('completionDateStruct', {}).get('date'),
                            eligibility_criteria=eligibility_module.get('eligibilityCriteria'),
                            minimum_age=eligibility_module.get('minimumAge'),
                            maximum_age=eligibility_module.get('maximumAge'),
                            sex=eligibility_module.get('sex'),
                            healthy_volunteers=eligibility_module.get('healthyVolunteers'),
                            locations=[
                                {
                                    "facility": loc.get('facility'),
                                    "city": loc.get('city'),
                                    "state": loc.get('state'),
                                    "country": loc.get('country'),
                                    "zip": loc.get('zip'),
                                }
                                for loc in locations_module.get('locations', [])
                            ]
                        )

                        if not trial_data.trial_id:
                            trial_bar.update(1)
                            continue

                        manage_trial_entry(session, trial_data, overall_status)

                        trial_bar.update(1)

                # Update the URL with the next page token if available
                page_token = data.get('nextPageToken')
                url = f"https://clinicaltrials.gov/api/v2/studies?pageToken={page_token}" if page_token else None
                session.commit()

                page_bar.update(1)

            except requests.exceptions.RequestException as e:
                print(f"Request error encountered: {e}. Retrying...")
            except Exception:
                session.rollback()
                raise

def main():
    session = SessionLocal()
    try:
        fetch_and_process_clinical_trials(session)
        session.commit()
    finally:
        session.close()

if __name__ == "__main__":
    main()
