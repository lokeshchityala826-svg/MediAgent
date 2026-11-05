"""Patient profile and baseline clinical history data models."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PatientGender(str, Enum):
    """Biological sex for clinical baseline calculation."""
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class CodeStatus(str, Enum):
    """Resuscitation status preferences."""
    FULL_CODE = "FULL_CODE"
    DNR_DNI = "DNR_DNI"  # Do Not Resuscitate / Do Not Intubate
    DNI_ONLY = "DNI_ONLY"


class Comorbidity(BaseModel):
    """Clinical comorbidity condition with ICD-10 coding and severity."""
    code: str = Field(..., description="ICD-10 or clinical code, e.g., 'I10' or 'E11.9'")
    description: str = Field(..., description="Human-readable diagnosis description")
    severity: str = Field(default="MODERATE", description="Severity category: MILD, MODERATE, SEVERE")
    notes: Optional[str] = Field(default=None, description="Optional clinical contextual notes")


class Medication(BaseModel):
    """Active or recently administered medication."""
    name: str = Field(..., description="Generic pharmaceutical name")
    dosage: str = Field(..., description="Strength and units, e.g., '5 mg'")
    route: str = Field(..., description="Route of administration: Oral, IV, Inhalation, etc.")
    frequency: str = Field(..., description="Administration frequency, e.g., 'Once daily'")
    is_active: bool = Field(default=True, description="True if medication is currently active")
    notes: Optional[str] = Field(default=None, description="Hold orders, PRN indications, or titration targets")


class BaselineVitals(BaseModel):
    """Individualized baseline vital signs for delta detection."""
    heart_rate: float = Field(72.0, ge=30.0, le=220.0, description="Resting baseline pulse (bpm)")
    systolic_bp: float = Field(120.0, ge=50.0, le=260.0, description="Resting baseline systolic BP (mmHg)")
    diastolic_bp: float = Field(80.0, ge=30.0, le=160.0, description="Resting baseline diastolic BP (mmHg)")
    respiratory_rate: float = Field(16.0, ge=4.0, le=60.0, description="Resting baseline respiratory rate (breaths/min)")
    spo2: float = Field(98.0, ge=50.0, le=100.0, description="Resting baseline oxygen saturation (%)")
    temperature_c: float = Field(36.8, ge=30.0, le=44.0, description="Resting core temperature (°C)")
    is_copd_spo2_scale2: bool = Field(
        default=False,
        description="Flag indicating patient qualifies for NEWS2 SpO2 Scale 2 (e.g. chronic hypercapnic respiratory failure)"
    )


class Patient(BaseModel):
    """Core synthetic patient demographic and clinical admission record."""
    patient_id: str = Field(..., description="Unique alphanumeric identifier (e.g., 'PAT-001')")
    name: str = Field(..., description="Synthetic patient full name")
    age: int = Field(..., ge=0, le=125, description="Patient age in years")
    gender: PatientGender = Field(..., description="Biological sex")
    admission_id: str = Field(..., description="Current hospital encounter/admission ID")
    admission_date: datetime = Field(default_factory=datetime.now, description="Admission timestamp")
    admission_reason: str = Field(..., description="Chief complaint or primary diagnosis")
    code_status: CodeStatus = Field(default=CodeStatus.FULL_CODE, description="Resuscitation preferences")
    room_bed: str = Field(..., description="Location, e.g. 'Ward 4B - Bed 12'")
    baseline_vitals: BaselineVitals = Field(default_factory=BaselineVitals, description="Individualized baseline vitals")
    comorbidities: List[Comorbidity] = Field(default_factory=list, description="Active past medical history")
    medications: List[Medication] = Field(default_factory=list, description="Active medication regimen")
    allergies: List[str] = Field(default_factory=list, description="Documented allergies (e.g. ['Penicillin'])")
