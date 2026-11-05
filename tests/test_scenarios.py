"""Unit tests for synthetic patient scenario generation and clinical fidelity."""

import tempfile
from pathlib import Path
import pytest

from mediagent.simulation.scenarios import (
    get_all_scenarios,
    get_scenario_by_id,
)
from mediagent.simulation.generator import SyntheticTrajectoryGenerator
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def test_scenario_catalog():
    scenarios = get_all_scenarios()
    assert len(scenarios) == 3

    ids = [s.scenario_id for s in scenarios]
    assert "SCN-STABLE-01" in ids
    assert "SCN-SEPSIS-02" in ids
    assert "SCN-RESP-03" in ids


def test_stable_scenario_progression():
    scenario = get_scenario_by_id("SCN-STABLE-01")
    assert scenario is not None
    assert scenario.expected_risk_category == "LOW"

    generator = SyntheticTrajectoryGenerator(random_seed=123)
    vitals, labs = generator.generate_scenario_telemetry(scenario, interval_minutes=30)

    # 24 hours at 30-min intervals = 48 intervals + 1 endpoint = 49 data points
    assert len(vitals) == 49
    assert len(labs) >= 1

    # Check stability across entire stream
    for v in vitals:
        assert 65.0 <= v.heart_rate <= 80.0
        assert 115.0 <= v.systolic_bp <= 130.0
        assert 12.0 <= v.respiratory_rate <= 18.0
        assert 95.0 <= v.spo2 <= 100.0
        assert v.on_supplemental_oxygen is False
        assert v.consciousness.value == "ALERT"


def test_sepsis_scenario_deterioration():
    scenario = get_scenario_by_id("SCN-SEPSIS-02")
    assert scenario is not None
    assert scenario.expected_risk_category == "CRITICAL"

    generator = SyntheticTrajectoryGenerator(random_seed=456)
    vitals, labs = generator.generate_scenario_telemetry(scenario, interval_minutes=30)

    assert len(vitals) == 49
    assert len(labs) >= 3

    initial_vitals = vitals[0]
    final_vitals = vitals[-1]

    # In initial hours, vitals should be near baseline
    assert initial_vitals.heart_rate < 90.0
    assert initial_vitals.systolic_bp > 115.0

    # In terminal hours (hour 24), septic shock must be manifest
    assert final_vitals.heart_rate > 120.0       # Tachycardia
    assert final_vitals.systolic_bp < 90.0       # Severe hypotension
    assert final_vitals.respiratory_rate >= 24.0 # Tachypnea
    assert final_vitals.temperature_c < 36.5     # Late septic hypothermia

    # Check scheduled labs for lactate spike
    lactate_labs = [
        item for lab in labs for item in lab.items if item.test_code == "LACTATE"
    ]
    assert len(lactate_labs) >= 2
    # Late lactate must be critical (> 4.0 mmol/L)
    assert lactate_labs[-1].value >= 4.0
    assert lactate_labs[-1].is_critical is True


def test_respiratory_scenario_progression():
    scenario = get_scenario_by_id("SCN-RESP-03")
    assert scenario is not None
    assert scenario.patient.baseline_vitals.is_copd_spo2_scale2 is True

    generator = SyntheticTrajectoryGenerator(random_seed=789)
    vitals, labs = generator.generate_scenario_telemetry(scenario, interval_minutes=30)

    assert len(vitals) == 49
    final_vitals = vitals[-1]

    # Patient should be on supplemental oxygen
    assert final_vitals.on_supplemental_oxygen is True
    assert final_vitals.oxygen_device.value == "VENTURI_MASK"
    assert final_vitals.spo2 <= 85.0

    # Check ABG progression
    abg_labs = [lab for lab in labs if lab.panel_type.value == "ABG"]
    assert len(abg_labs) == 3
    final_abg = abg_labs[-1]

    ph_item = next(i for i in final_abg.items if i.test_code == "PH")
    pco2_item = next(i for i in final_abg.items if i.test_code == "PCO2")

    assert ph_item.value < 7.25      # Severe acidemia
    assert ph_item.is_critical is True
    assert pco2_item.value > 65.0    # Severe hypercapnia
    assert pco2_item.is_critical is True


def test_seed_scenario_to_db():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_seed.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)

    generator = SyntheticTrajectoryGenerator(random_seed=111)
    scenario = get_scenario_by_id("SCN-STABLE-01")

    v_count, l_count = generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    # 24 hours at 60 min intervals = 25 vitals
    assert v_count == 25
    assert l_count == len(scenario.lab_schedule)

    stored_patient = repo.get_patient(scenario.patient.patient_id)
    assert stored_patient is not None
    assert stored_patient.patient_id == "PAT-001"

    stored_vitals = repo.get_vitals_stream("PAT-001")
    assert len(stored_vitals) == 25

    # Check audit log contains admission and seed events
    events = audit.get_recent_events(limit=10)
    event_types = [e["event_type"] for e in events]
    assert "PATIENT_ADMITTED" in event_types
    assert "SIMULATION_SEEDED" in event_types
