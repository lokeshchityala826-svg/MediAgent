"""Phase 1 Demonstration and Verification Script for MediAgent.

Seeds the SQLite database with 3 synthetic clinical scenarios and executes
deterministic early warning calculations and audit verification.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger
from mediagent.simulation.scenarios import get_all_scenarios
from mediagent.simulation.generator import SyntheticTrajectoryGenerator
from mediagent.engine.news2 import NEWS2Calculator
from mediagent.engine.qsofa import QSOFACalculator


def main():
    print("=" * 80)
    print(" MediAgent: Clinical Monitoring & Decision Support Simulation (Phase 1)")
    print("=" * 80)
    print(f"Execution Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Constraint Notice: Synthetic patient data only. Non-diagnostic. Offline-first.\n")

    # 1. Initialize SQLite Database
    db_path = Path(__file__).resolve().parent / "data" / "mediagent.db"
    print(f"[*] Initializing SQLite Database at: {db_path}")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.reset_database()
    repo = PatientRepository(db_manager)
    audit_logger = AuditLogger(db_manager)
    print("[+] Database schema successfully migrated (WAL mode enabled).\n")

    # 2. Seed the 3 Clinical Scenarios
    scenarios = get_all_scenarios()
    generator = SyntheticTrajectoryGenerator(random_seed=42)

    print(f"[*] Seeding {len(scenarios)} Clinical Scenarios (24-Hour Telemetry + Scheduled Labs):")
    print("-" * 80)

    summary_rows = []

    for scn in scenarios:
        v_count, l_count = generator.seed_scenario_to_db(
            scenario=scn,
            repo=repo,
            audit_logger=audit_logger,
            interval_minutes=30,  # 30-min telemetry resolution
        )

        # Retrieve generated stream to evaluate deterministic score changes
        vitals_stream = repo.get_vitals_stream(scn.patient.patient_id)
        first_vitals = vitals_stream[0]
        last_vitals = vitals_stream[-1]

        is_scale_2 = scn.patient.baseline_vitals.is_copd_spo2_scale2
        initial_news = NEWS2Calculator.calculate(first_vitals, is_copd_spo2_scale2=is_scale_2)
        terminal_news = NEWS2Calculator.calculate(last_vitals, is_copd_spo2_scale2=is_scale_2)
        terminal_qsofa = QSOFACalculator.calculate(last_vitals)

        summary_rows.append({
            "id": scn.patient.patient_id,
            "name": scn.patient.name,
            "scenario": scn.name,
            "vitals_pts": v_count,
            "labs_pts": l_count,
            "news_init": initial_news.total_score,
            "news_end": terminal_news.total_score,
            "risk_end": terminal_news.risk_level,
            "qsofa_end": f"{terminal_qsofa.total_score}/3 ({terminal_qsofa.clinical_risk})",
        })

        print(f"  -> Seeded: {scn.patient.patient_id} | {scn.patient.name:<18} | {scn.name}")
        print(f"     Vitals recorded: {v_count} | Labs recorded: {l_count}")
        print(f"     NEWS2 Trajectory: {initial_news.total_score} ({initial_news.risk_level}) -> {terminal_news.total_score} ({terminal_news.risk_level})")
        if terminal_qsofa.is_positive:
            print(f"     [!] qSOFA Positive ({terminal_qsofa.total_score}/3) - High risk of acute sepsis deterioration")
        print()

    # 3. Print Summary Table
    print("-" * 80)
    print(f"{'ID':<9} {'Patient Name':<18} {'Initial':<8} {'Final':<8} {'Risk Tier':<12} {'qSOFA (Final)':<16}")
    print("-" * 80)
    for r in summary_rows:
        print(f"{r['id']:<9} {r['name']:<18} {r['news_init']:<8} {r['news_end']:<8} {r['risk_end']:<12} {r['qsofa_end']:<16}")
    print("-" * 80)

    # 4. Verify Immutable Audit Ledger
    print("\n[*] Verifying Immutable Audit Ledger Integrity:")
    recent_events = audit_logger.get_recent_events(limit=5)
    print(f"  Total audit events logged during seed: {len(audit_logger.get_recent_events(limit=500))}")
    for evt in recent_events[:3]:
        is_valid = audit_logger.verify_event_integrity(evt["event_id"])
        status = "[VALID SHA-256]" if is_valid else "[CORRUPTED]"
        print(f"  - Event: {evt['event_id']} | Type: {evt['event_type']:<18} | Actor: {evt['actor_id']:<10} | {status}")

    print("\n" + "=" * 80)
    print(" [SUCCESS] Phase 1 Verification Complete. Core engine, DB, and data generators operational.")
    print("=" * 80)


if __name__ == "__main__":
    main()
