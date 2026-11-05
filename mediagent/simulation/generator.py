"""Synthetic clinical trajectory generator with physiological micro-fluctuations."""

import random
from datetime import datetime, timedelta
from typing import List, Tuple

from mediagent.models.patient import Patient
from mediagent.models.telemetry import (
    VitalSigns,
    LabResult,
    LabItem,
    LabPanelType,
    ConsciousnessLevel,
    OxygenDevice,
)
from mediagent.simulation.scenarios import ScenarioDefinition
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


class SyntheticTrajectoryGenerator:
    """Generates reproducible, realistic synthetic clinical data."""

    def __init__(self, random_seed: int = 42) -> None:
        self.random_seed = random_seed
        self.rng = random.Random(random_seed)

    def generate_scenario_telemetry(
        self,
        scenario: ScenarioDefinition,
        interval_minutes: int = 30,
        start_time: datetime = None,
    ) -> Tuple[List[VitalSigns], List[LabResult]]:
        """Generate time-series vitals and scheduled lab results for a scenario.

        Args:
            scenario: Target ScenarioDefinition
            interval_minutes: Cadence of vitals capture (e.g., every 30 or 60 mins)
            start_time: Simulated admission/start timestamp (defaults to 24h ago)

        Returns:
            Tuple of (vitals_list, labs_list)
        """
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=scenario.duration_hours)

        total_steps = int((scenario.duration_hours * 60) / interval_minutes)
        vitals_list: List[VitalSigns] = []

        for step in range(total_steps + 1):
            elapsed_minutes = step * interval_minutes
            elapsed_hours = elapsed_minutes / 60.0
            current_time = start_time + timedelta(minutes=elapsed_minutes)

            # Retrieve underlying curve
            raw = scenario.vitals_progression_fn(elapsed_hours)

            # Apply small clinical micro-variations (jitter)
            hr_jitter = self.rng.uniform(-1.5, 1.5)
            sbp_jitter = self.rng.uniform(-2.5, 2.5)
            dbp_jitter = self.rng.uniform(-2.0, 2.0)
            rr_jitter = self.rng.uniform(-0.8, 0.8)
            spo2_jitter = self.rng.uniform(-0.5, 0.5)
            temp_jitter = self.rng.uniform(-0.08, 0.08)

            hr = max(30.0, min(220.0, round(raw["heart_rate"] + hr_jitter, 1)))
            sbp = max(50.0, min(240.0, round(raw["systolic_bp"] + sbp_jitter, 1)))
            dbp = max(30.0, min(140.0, round(raw["diastolic_bp"] + dbp_jitter, 1)))
            rr = max(6.0, min(60.0, round(raw["respiratory_rate"] + rr_jitter, 1)))
            spo2 = max(50.0, min(100.0, round(raw["spo2"] + spo2_jitter, 1)))
            temp = max(30.0, min(42.5, round(raw["temperature_c"] + temp_jitter, 1)))

            vitals = VitalSigns(
                timestamp=current_time,
                patient_id=scenario.patient.patient_id,
                heart_rate=hr,
                systolic_bp=sbp,
                diastolic_bp=dbp,
                respiratory_rate=rr,
                spo2=spo2,
                temperature_c=temp,
                on_supplemental_oxygen=raw["on_supplemental_oxygen"],
                oxygen_flow_lpm=raw.get("oxygen_flow_lpm", 0.0),
                oxygen_device=OxygenDevice(raw["oxygen_device"]),
                consciousness=ConsciousnessLevel(raw["consciousness"]),
                gcs=raw.get("gcs", 15),
            )
            vitals_list.append(vitals)

        # Generate scheduled lab panels
        labs_list: List[LabResult] = []
        for lab_spec in scenario.lab_schedule:
            lab_time = start_time + timedelta(hours=lab_spec["hour"])
            panel_type = LabPanelType(lab_spec["panel"])
            items = []

            for item_spec in lab_spec["items"]:
                item = LabItem(
                    test_code=item_spec["test_code"],
                    test_name=item_spec["test_name"],
                    value=item_spec["value"],
                    unit=item_spec["unit"],
                    ref_range_low=item_spec["ref_low"],
                    ref_range_high=item_spec["ref_high"],
                    is_abnormal=item_spec.get("is_abnormal", False),
                    is_critical=item_spec.get("is_critical", False),
                )
                items.append(item)

            lab_result = LabResult(
                lab_id=f"LAB-{scenario.patient.patient_id}-{int(lab_spec['hour'])}H-{panel_type.value}",
                patient_id=scenario.patient.patient_id,
                timestamp=lab_time,
                panel_type=panel_type,
                items=items,
            )
            labs_list.append(lab_result)

        return vitals_list, labs_list

    def seed_scenario_to_db(
        self,
        scenario: ScenarioDefinition,
        repo: PatientRepository,
        audit_logger: AuditLogger,
        interval_minutes: int = 30,
    ) -> Tuple[int, int]:
        """Generate and persist complete synthetic patient scenario to database.

        Returns:
            Tuple of (vitals_count, labs_count)
        """
        # 1. Upsert Patient
        repo.upsert_patient(scenario.patient)
        audit_logger.log_event(
            event_type="PATIENT_ADMITTED",
            actor_type="SYSTEM",
            actor_id="SIMULATOR",
            patient_id=scenario.patient.patient_id,
            payload={
                "scenario_id": scenario.scenario_id,
                "name": scenario.patient.name,
                "admission_reason": scenario.patient.admission_reason,
            },
        )

        # 2. Generate and Insert Telemetry
        vitals, labs = self.generate_scenario_telemetry(scenario, interval_minutes=interval_minutes)
        repo.insert_vitals_batch(vitals)
        repo.insert_labs_batch(labs)

        audit_logger.log_event(
            event_type="SIMULATION_SEEDED",
            actor_type="SYSTEM",
            actor_id="SIMULATOR",
            patient_id=scenario.patient.patient_id,
            payload={
                "vitals_count": len(vitals),
                "labs_count": len(labs),
                "duration_hours": scenario.duration_hours,
            },
        )

        return len(vitals), len(labs)
