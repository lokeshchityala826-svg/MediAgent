"""Telemetry stream and laboratory observation models."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class ConsciousnessLevel(str, Enum):
    """Standard AVPU scale used in clinical deterioration scoring (NEWS2)."""
    ALERT = "ALERT"          # Fully awake, spontaneous eye opening
    VOICE = "VOICE"          # Responds only when spoken to
    PAIN = "PAIN"            # Responds only to painful stimulus
    UNRESPONSIVE = "UNRESPONSIVE"  # Flaccid, no response to pain/voice


class OxygenDevice(str, Enum):
    """Respiratory support delivery mechanisms."""
    ROOM_AIR = "ROOM_AIR"
    NASAL_CANNULA = "NASAL_CANNULA"
    VENTURI_MASK = "VENTURI_MASK"
    NON_REBREATHER = "NON_REBREATHER"
    HFNC = "HFNC"                       # High Flow Nasal Cannula
    CPAP_BIPAP = "CPAP_BIPAP"           # Non-invasive positive pressure ventilation
    MECHANICAL_VENTILATION = "MECHANICAL_VENTILATION"


class VitalSigns(BaseModel):
    """Point-in-time physiological telemetry snapshot."""
    timestamp: datetime = Field(..., description="Timestamp of telemetry capture")
    patient_id: str = Field(..., description="Associated patient ID")
    heart_rate: float = Field(..., ge=20.0, le=260.0, description="Heart rate in beats per minute (bpm)")
    systolic_bp: float = Field(..., ge=40.0, le=280.0, description="Systolic blood pressure (mmHg)")
    diastolic_bp: float = Field(..., ge=20.0, le=180.0, description="Diastolic blood pressure (mmHg)")
    mean_arterial_pressure: Optional[float] = Field(
        default=None,
        description="Calculated MAP: (2 * DBP + SBP) / 3 (mmHg)"
    )
    respiratory_rate: float = Field(..., ge=2.0, le=70.0, description="Respiratory rate (breaths/min)")
    spo2: float = Field(..., ge=40.0, le=100.0, description="Peripheral pulse oximetry percentage (%)")
    temperature_c: float = Field(..., ge=28.0, le=44.0, description="Core body temperature in Celsius (°C)")
    on_supplemental_oxygen: bool = Field(default=False, description="True if patient is receiving supplemental O2")
    oxygen_flow_lpm: Optional[float] = Field(default=0.0, ge=0.0, le=60.0, description="Oxygen flow in Liters/min")
    oxygen_device: OxygenDevice = Field(default=OxygenDevice.ROOM_AIR, description="Delivery apparatus")
    consciousness: ConsciousnessLevel = Field(default=ConsciousnessLevel.ALERT, description="AVPU assessment")
    gcs: int = Field(default=15, ge=3, le=15, description="Glasgow Coma Scale score (3-15)")

    @model_validator(mode="after")
    def compute_map_if_missing(self) -> "VitalSigns":
        """Compute Mean Arterial Pressure (MAP) if not explicitly supplied."""
        if self.mean_arterial_pressure is None:
            calc_map = (2.0 * self.diastolic_bp + self.systolic_bp) / 3.0
            self.mean_arterial_pressure = round(calc_map, 1)
        return self


class LabPanelType(str, Enum):
    """Clinical laboratory panel classifications."""
    CBC = "CBC"              # Complete Blood Count (WBC, Hb, Platelets)
    BMP = "BMP"              # Basic Metabolic Panel (Na, K, Cl, CO2, BUN, Cr, Glucose)
    CMP = "CMP"              # Comprehensive Metabolic Panel (BMP + Liver Enzymes, Albumin)
    LACTATE = "LACTATE"      # Serum Lactate
    ABG = "ABG"              # Arterial Blood Gas (pH, pO2, pCO2, HCO3, SaO2)
    COAGULATION = "COAGULATION" # PT/INR, PTT
    CARDIAC = "CARDIAC"      # Troponin, BNP/NT-proBNP


class LabItem(BaseModel):
    """Individual analyte within a laboratory panel."""
    test_code: str = Field(..., description="Standard test code, e.g., 'WBC', 'LACTATE', 'CREATININE'")
    test_name: str = Field(..., description="Descriptive name, e.g., 'Serum Lactate'")
    value: float = Field(..., description="Observed numeric value")
    unit: str = Field(..., description="Measurement units, e.g., 'mmol/L', 'mg/dL'")
    ref_range_low: float = Field(..., description="Lower limit of normal reference range")
    ref_range_high: float = Field(..., description="Upper limit of normal reference range")
    is_abnormal: bool = Field(default=False, description="True if value falls outside reference range")
    is_critical: bool = Field(default=False, description="True if value crosses life-threatening threshold")

    @model_validator(mode="after")
    def evaluate_abnormality(self) -> "LabItem":
        """Automatically flag abnormality if value breaches reference range."""
        if self.value < self.ref_range_low or self.value > self.ref_range_high:
            self.is_abnormal = True
        return self


class LabResult(BaseModel):
    """Complete episodic laboratory report."""
    lab_id: str = Field(..., description="Unique specimen/order ID")
    patient_id: str = Field(..., description="Associated patient ID")
    timestamp: datetime = Field(..., description="Timestamp of collection/result availability")
    panel_type: LabPanelType = Field(..., description="Panel classification")
    items: List[LabItem] = Field(..., min_length=1, description="List of individual lab analytes")
