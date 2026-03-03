import os
from typing import Any, Optional, Union

from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint, create_engine, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

load_dotenv()

# Initialize the database base and engine
Base = declarative_base()

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("Missing required environment variable: DATABASE_URL")

# SQLalchemy only accepts urls like "postgresql://"
# but heroku will not provide so we have to make it ourselves
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_pgvector_extension() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

# SQLAlchemy Models
class ClinicalTrial(Base):
    __tablename__ = 'clinical_trials'
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    trial_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    organization: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    brief_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    official_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    primary_completion_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    completion_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    eligibility_criteria: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    minimum_age: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    maximum_age: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sex: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    healthy_volunteers: Mapped[Optional[Union[str, bool]]] = mapped_column(String, nullable=True)
    locations: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)

class TrialVector(Base):
    __tablename__ = 'trial_vectors'
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey('clinical_trials.id'), unique=True)
    vector: Mapped[Optional[list[float]]] = mapped_column(Vector(1536))  # pgvector column for storing embeddings
    trial = relationship("ClinicalTrial", back_populates="vector")

ClinicalTrial.vector = relationship("TrialVector", uselist=False, back_populates="trial")


class SubscriberProfile(Base):
    __tablename__ = "subscriber_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    phone_e164: Mapped[str] = mapped_column(String, unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scrubbed_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preference_vector: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    notifications = relationship("SubscriberNotification", back_populates="subscriber", cascade="all, delete-orphan")


class SubscriberNotification(Base):
    __tablename__ = "subscriber_notifications"
    __table_args__ = (UniqueConstraint("subscriber_id", "trial_id", name="uq_subscriber_trial"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscriber_profiles.id"), index=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("clinical_trials.id"), index=True)
    sent_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subscriber = relationship("SubscriberProfile", back_populates="notifications")
    trial = relationship("ClinicalTrial")

# Pydantic Models
class ClinicalTrialCreate(BaseModel):
    trial_id: str
    organization: Optional[str] = None
    brief_title: Optional[str] = None
    official_title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    primary_completion_date: Optional[str] = None
    completion_date: Optional[str] = None
    eligibility_criteria: Optional[str] = None
    minimum_age: Optional[str] = None
    maximum_age: Optional[str] = None
    sex: Optional[str] = None
    healthy_volunteers: Optional[Union[str, bool]] = None  # Allow str or bool
    locations: Optional[list[dict[str, Any]]] = None

# Create the database tables if they don't already exist
if __name__ == "__main__":
    ensure_pgvector_extension()
    Base.metadata.create_all(bind=engine)
