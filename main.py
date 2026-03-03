import asyncio
import contextlib
import importlib
import logging
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from landing_page import render_about_page, render_landing_page
from models import (
    Base,
    ClinicalTrial,
    SessionLocal,
    SubscriberNotification,
    SubscriberProfile,
    TrialVector,
    ensure_pgvector_extension,
    engine,
)
from privacy import normalize_phone, scrub_pii
from settings import Settings, load_settings

try:
    from twilio.request_validator import RequestValidator
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.messaging_response import MessagingResponse
except Exception:  # pragma: no cover - optional runtime dependency
    RequestValidator = None
    TwilioClient = None
    MessagingResponse = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings: Settings = load_settings()

if settings.twilio_enabled and (TwilioClient is None or RequestValidator is None or MessagingResponse is None):
    raise RuntimeError("Twilio credentials are set but twilio package is not installed")

bearer_scheme = HTTPBearer()
openai_client = OpenAI(api_key=settings.openai_api_key)
twilio_client = (
    TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token) if settings.twilio_enabled else None
)
request_validator = RequestValidator(settings.twilio_auth_token) if settings.twilio_enabled else None

app = FastAPI(
    title="HelloTrial",
    description="HelloTrial: clinical trial SMS matching service with PII scrubbing and monitor alerts.",
)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

monitor_task: asyncio.Task | None = None
ONBOARD_KEYWORDS = {"HELLO", "START"}
STATE_AWAITING_SYMPTOMS = "__AWAITING_SYMPTOMS__"
STATE_AWAITING_LOCATION_PREFIX = "__AWAITING_LOCATION__::"
SUPPORT_TEXT = (
    "Text HELLO (or START) to start. We'll ask for symptoms and location, then text matches. "
    "Learn more: https://www.hellotrial.ca/about"
)


def validate_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> HTTPAuthorizationCredentials:
    if credentials.scheme != "Bearer" or credentials.credentials != settings.api_auth_token:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_vector(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
        encoding_format="float",
    )
    return response.data[0].embedding


def trial_link(trial: ClinicalTrial) -> str:
    return f"https://clinicaltrials.gov/study/{trial.trial_id}"


def serialize_trial(trial: ClinicalTrial) -> dict:
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


def find_matching_trials(db: Session, vector: list[float], limit: int) -> list[ClinicalTrial]:
    return db.execute(
        select(ClinicalTrial)
        .join(TrialVector, TrialVector.trial_id == ClinicalTrial.id)
        .order_by(TrialVector.vector.l2_distance(vector))
        .limit(limit)
    ).scalars().all()


def get_or_create_subscriber(db: Session, phone_e164: str) -> SubscriberProfile:
    subscriber = db.query(SubscriberProfile).filter_by(phone_e164=phone_e164).first()
    if subscriber:
        return subscriber

    subscriber = SubscriberProfile(phone_e164=phone_e164, active=True)
    db.add(subscriber)
    db.flush()
    return subscriber


def filter_unsent_trials(db: Session, subscriber_id: int, trials: list[ClinicalTrial]) -> list[ClinicalTrial]:
    trial_ids = [trial.id for trial in trials]
    if not trial_ids:
        return []

    sent_ids = {
        row[0]
        for row in db.query(SubscriberNotification.trial_id)
        .filter(
            SubscriberNotification.subscriber_id == subscriber_id,
            SubscriberNotification.trial_id.in_(trial_ids),
        )
        .all()
    }
    return [trial for trial in trials if trial.id not in sent_ids]


def record_notifications(db: Session, subscriber_id: int, trials: list[ClinicalTrial]) -> None:
    for trial in trials:
        db.add(SubscriberNotification(subscriber_id=subscriber_id, trial_id=trial.id))


def purge_subscriber_data(db: Session, subscriber: SubscriberProfile) -> None:
    db.query(SubscriberNotification).filter(
        SubscriberNotification.subscriber_id == subscriber.id
    ).delete()
    db.delete(subscriber)


def format_match_message(trial: ClinicalTrial) -> str:
    title = trial.brief_title or trial.official_title or trial.trial_id
    return f"{title}: {trial_link(trial)}\n\nReply STOP to unsubscribe."


def send_sms(to_phone: str, body: str) -> None:
    if not settings.twilio_enabled or twilio_client is None:
        logger.info("Twilio disabled; skipping SMS send to %s", to_phone)
        return

    twilio_client.messages.create(
        body=body,
        from_=settings.twilio_phone_number,
        to=to_phone,
    )


def run_monitoring_cycle() -> None:
    if not settings.twilio_enabled:
        return

    db = SessionLocal()
    try:
        subscribers = (
            db.query(SubscriberProfile)
            .filter(SubscriberProfile.active.is_(True), SubscriberProfile.preference_vector.isnot(None))
            .all()
        )

        for subscriber in subscribers:
            matches = find_matching_trials(db, subscriber.preference_vector, settings.monitor_match_limit * 4)
            unsent = filter_unsent_trials(db, subscriber.id, matches)[: settings.monitor_match_limit]
            if not unsent:
                continue

            top_trial = unsent[0]
            send_sms(subscriber.phone_e164, format_match_message(top_trial))
            record_notifications(db, subscriber.id, [top_trial])
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Monitoring cycle failed")
    finally:
        db.close()


def refresh_trials_index() -> None:
    importer = importlib.import_module("import")
    db = SessionLocal()
    try:
        importer.fetch_and_process_clinical_trials(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def monitoring_loop() -> None:
    logger.info("Background monitoring started; interval=%s minutes", settings.monitor_interval_minutes)
    while True:
        run_monitoring_cycle()
        await asyncio.sleep(settings.monitor_interval_minutes * 60)


def ensure_twilio_signature(request: Request, form_data: dict[str, str]) -> None:
    if not settings.twilio_enabled or request_validator is None:
        return

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    if not request_validator.validate(str(request.url), form_data, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@app.on_event("startup")
async def startup_event() -> None:
    global monitor_task
    ensure_pgvector_extension()
    Base.metadata.create_all(bind=engine)
    if settings.twilio_enabled:
        monitor_task = asyncio.create_task(monitoring_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global monitor_task
    if monitor_task:
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task


@app.get("/", response_class=HTMLResponse)
def landing_page() -> str:
    return render_landing_page(
        static_dir=static_dir,
        phone=settings.twilio_phone_number,
    )


@app.get("/about", response_class=HTMLResponse)
def about_page() -> str:
    return render_about_page(
        static_dir=static_dir,
        phone=settings.twilio_phone_number,
    )


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/twilio/sms")
async def twilio_sms_webhook(request: Request) -> Response:
    raw_body = (await request.body()).decode("utf-8")
    parsed = parse_qs(raw_body, keep_blank_values=True)
    form_data = {k: v[0] for k, v in parsed.items()}
    body = form_data.get("Body", "")
    from_phone = form_data.get("From", "")
    ensure_twilio_signature(request, form_data)

    if MessagingResponse is None:
        raise HTTPException(status_code=500, detail="Twilio library unavailable")

    response = MessagingResponse()
    phone = normalize_phone(from_phone)
    if not phone:
        response.message("Could not parse your phone number. Please try again.")
        return Response(content=str(response), media_type="application/xml")

    incoming_text = body.strip()
    first_token = incoming_text.split(maxsplit=1)[0].strip(".,!?;:").upper() if incoming_text else ""
    db = SessionLocal()
    try:
        subscriber = get_or_create_subscriber(db, phone)

        if first_token == "STOP":
            purge_subscriber_data(db, subscriber)
            db.commit()
            response.message("You're unsubscribed. Thanks for using HelloTrial.")
            return Response(content=str(response), media_type="application/xml")

        if first_token in {"INFO", "HELP"}:
            response.message(SUPPORT_TEXT)
            return Response(content=str(response), media_type="application/xml")

        if not incoming_text:
            response.message("Text HELLO to start.")
            return Response(content=str(response), media_type="application/xml")

        # New onboarding flow:
        # 1) HELLO or START -> ask for symptoms
        # 2) symptoms -> ask for location
        # 3) location -> confirm subscription
        if first_token in ONBOARD_KEYWORDS:
            subscriber.active = True
            subscriber.preference_vector = None
            subscriber.scrubbed_message = STATE_AWAITING_SYMPTOMS
            db.commit()
            response.message("Hi! Thanks for subscribing. Please describe your symptoms.")
            return Response(content=str(response), media_type="application/xml")

        state = subscriber.scrubbed_message or ""
        if state == STATE_AWAITING_SYMPTOMS:
            symptoms = scrub_pii(incoming_text)
            if not symptoms:
                response.message("Please describe your symptoms.")
                return Response(content=str(response), media_type="application/xml")
            subscriber.active = True
            subscriber.preference_vector = None
            subscriber.scrubbed_message = f"{STATE_AWAITING_LOCATION_PREFIX}{symptoms}"
            db.commit()
            response.message("Thank you. Where are you located?")
            return Response(content=str(response), media_type="application/xml")

        if state.startswith(STATE_AWAITING_LOCATION_PREFIX):
            symptoms = state[len(STATE_AWAITING_LOCATION_PREFIX):].strip()
            location = scrub_pii(incoming_text)
            if not location:
                response.message("Please share your location (city, province/state, or country).")
                return Response(content=str(response), media_type="application/xml")
            profile_text = f"Symptoms: {symptoms}\\nLocation: {location}"
            subscriber.active = True
            subscriber.scrubbed_message = profile_text
            subscriber.preference_vector = create_vector(profile_text)
            matches = find_matching_trials(db, subscriber.preference_vector, settings.monitor_match_limit)

            if matches:
                unsent_matches = filter_unsent_trials(db, subscriber.id, matches)
                immediate_trial = unsent_matches[0] if unsent_matches else matches[0]
                if unsent_matches:
                    record_notifications(db, subscriber.id, [immediate_trial])
                db.commit()
                response.message(format_match_message(immediate_trial))
                return Response(content=str(response), media_type="application/xml")

            db.commit()
            response.message(
                "Thank you. We don't have any matching trials yet, but we'll keep an eye out for you. "
                "Text INFO or STOP anytime."
            )
            return Response(content=str(response), media_type="application/xml")

        response.message("You are already subscribed. Text HELLO to update your symptoms and location, or INFO/STOP.")
        return Response(content=str(response), media_type="application/xml")
    except Exception:
        db.rollback()
        logger.exception("Inbound SMS handling failed")
        response.message("Sorry, something went wrong. Please try again shortly.")
        return Response(content=str(response), media_type="application/xml")
    finally:
        db.close()


@app.post("/search_clinical_trials")
def search_clinical_trial(
    text: str,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _auth: HTTPAuthorizationCredentials = Depends(validate_token),
):
    vector = create_vector(text)
    try:
        closest_trials = find_matching_trials(db, vector, limit)
        if not closest_trials:
            raise HTTPException(status_code=404, detail="No matching trial vectors found")
        return [serialize_trial(trial) for trial in closest_trials]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error while searching clinical trials")
        raise HTTPException(status_code=500, detail="Internal error while searching clinical trials")


@app.get("/clinical_trials/")
def list_clinical_trials(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _auth: HTTPAuthorizationCredentials = Depends(validate_token),
):
    trials = db.query(ClinicalTrial).offset(skip).limit(limit).all()
    if not trials:
        raise HTTPException(status_code=404, detail="No clinical trials found")
    return trials


@app.get("/clinical_trial/{trial_id}")
def get_clinical_trial(
    trial_id: int,
    db: Session = Depends(get_db),
    _auth: HTTPAuthorizationCredentials = Depends(validate_token),
):
    clinical_trial = db.query(ClinicalTrial).filter(ClinicalTrial.id == trial_id).first()
    if clinical_trial is None:
        raise HTTPException(status_code=404, detail="Clinical trial not found")
    return clinical_trial


@app.post("/admin/run_monitor")
def run_monitor(
    _auth: HTTPAuthorizationCredentials = Depends(validate_token),
) -> dict[str, str]:
    run_monitoring_cycle()
    return {"status": "ok", "message": "Monitoring cycle completed"}


@app.post("/admin/refresh_trials")
def refresh_trials(
    _auth: HTTPAuthorizationCredentials = Depends(validate_token),
) -> dict[str, str]:
    refresh_trials_index()
    return {"status": "ok", "message": "Trial index refresh completed"}
