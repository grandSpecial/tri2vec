import requests
import json
from openai import OpenAI
from sqlalchemy.dialects.postgresql import insert
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from models import ClinicalTrial, TrialVector, SessionLocal, ClinicalTrialCreate
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
def create_vector(text):
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
        encoding_format="float"  
    )
    return response.data[0].embedding

# Function to upsert clinical trial details
def upsert_clinical_trial(session, trial_data: ClinicalTrialCreate):
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
    )
    result = session.execute(stmt)
    session.flush()
    
    # Fetch the ID of the upserted or existing ClinicalTrial
    if result.inserted_primary_key:
        return result.inserted_primary_key[0]
    else:
        existing_trial = session.query(ClinicalTrial).filter_by(trial_id=trial_data.trial_id).first()
        return existing_trial.id if existing_trial else None

# Function to upsert vector for clinical trial
def upsert_trial_vector(session, trial_id, text):
    vector = create_vector(text)
    stmt = insert(TrialVector).values(
        trial_id=trial_id,
        vector=vector
    ).on_conflict_do_update(
        index_elements=['trial_id'],
        set_={'vector': insert(TrialVector).excluded.vector}
    )
    session.execute(stmt)
    session.commit()

# Manage trial entry and ensure it aligns with current recruiting status
def manage_trial_entry(session, trial_data: ClinicalTrialCreate, overall_status: str):
    # Query for existing ClinicalTrial entry using string trial_id
    existing_trial = session.query(ClinicalTrial).filter_by(trial_id=trial_data.trial_id).first()
    
    if existing_trial:
        if overall_status == "RECRUITING":
            # Use existing_trial.id as the foreign key in TrialVector
            upsert_trial_vector(session, existing_trial.id, trial_data.description)
        else:
            # Delete from TrialVector using the integer `id` from ClinicalTrial
            session.query(TrialVector).filter_by(trial_id=existing_trial.id).delete()
            session.delete(existing_trial)
            session.commit()
    else:
        if overall_status == "RECRUITING":
            # Upsert and use ClinicalTrial.id as the foreign key in TrialVector
            trial_id = upsert_clinical_trial(session, trial_data)
            upsert_trial_vector(session, trial_id, trial_data.description)

# Function to fetch, process, and manage clinical trials from the API
def fetch_and_process_clinical_trials(session, url="https://clinicaltrials.gov/api/v2/studies"):
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

                        # Pass overall_status directly to manage_trial_entry
                        manage_trial_entry(session, trial_data, overall_status)

                        trial_bar.update(1)

                # Update the URL with the next page token if available
                page_token = data.get('nextPageToken')
                url = f"https://clinicaltrials.gov/api/v2/studies?pageToken={page_token}" if page_token else None

                page_bar.update(1)

            except requests.exceptions.RequestException as e:
                print(f"Request error encountered: {e}. Retrying...")

def main():
    session = SessionLocal()
    fetch_and_process_clinical_trials(session)
    session.commit()
    session.close()

if __name__ == "__main__":
    main()
