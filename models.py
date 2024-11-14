from typing import Union, Optional
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, JSON, ForeignKey, create_engine
from sqlalchemy.orm import relationship, sessionmaker, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize the database base and engine
Base = declarative_base()

# Database setup
# Database connection details
DATABASE_URL = os.getenv('DATABASE_URL')
# SQLalchemy only accepts urls like "postgresql://"
# but heroku will not provide so we have to make it ourselves
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# SQLAlchemy Models
class ClinicalTrial(Base):
    __tablename__ = 'clinical_trials'
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    trial_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    organization: Mapped[Optional[str]] = mapped_column(String)
    brief_title: Mapped[Optional[str]] = mapped_column(String)
    official_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String)
    start_date: Mapped[Optional[str]] = mapped_column(String)
    primary_completion_date: Mapped[Optional[str]] = mapped_column(String)
    completion_date: Mapped[Optional[str]] = mapped_column(String)
    eligibility_criteria: Mapped[Optional[str]] = mapped_column(String)
    minimum_age: Mapped[Optional[str]] = mapped_column(String)
    maximum_age: Mapped[Optional[str]] = mapped_column(String)
    sex: Mapped[Optional[str]] = mapped_column(String)
    healthy_volunteers: Mapped[Optional[Union[str, bool]]] = mapped_column(String)
    locations: Mapped[Optional[dict]] = mapped_column(JSON)  # Store locations as JSON

class TrialVector(Base):
    __tablename__ = 'trial_vectors'
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey('clinical_trials.id'), unique=True)
    vector: Mapped[Optional[list[float]]] = mapped_column(Vector(1536))  # pgvector column for storing embeddings
    trial = relationship("ClinicalTrial", back_populates="vector")

ClinicalTrial.vector = relationship("TrialVector", uselist=False, back_populates="trial")

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
    locations: Optional[list] = None

# Create the database tables if they don't already exist
if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
