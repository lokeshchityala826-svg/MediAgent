"""Phase 2 Demonstration and Multi-Agent Intelligence Verification Script.

Executes domain specialist agents, multi-agent coordinator synthesis, and human-in-the-loop doctor sign-off.
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
from mediagent.coordinator.coordinator import MultiAgentCoordinator
from mediagent.workflow.approval_engine import ApprovalEngine


def main():
    print("=" * 85)
    print(" MediAgent: Multi-Agent Clinical Decision Support & Governance (Phase 2)")
    print("=" * 85)
    print(f"Execution Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Safety Notice: Synthetic telemetry only. Deterministic decision-support. Non-prescriptive.\n")

    # 1. Initialize SQLite Database
    db_path = Path(__file__).resolve().parent / "data" / "mediagent.db"
    print(f"[*] Initializing SQLite Database at: {db_path}")
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.reset_database()
    repo = PatientRepository(db_manager)
    audit_logger = AuditLogger(db_manager)
    print("[+] Database initialized with WAL mode.\n")

    # 2. Seed the 3 Scenarios
    scenarios = get_all_scenarios()
    generator = SyntheticTrajectoryGenerator(random_seed=100)

    print("[*] Seeding 24-Hour Clinical Trajectories for Synthetic Patients:")
    for scn in scenarios:
        v_count, l_count = generator.seed_scenario_to_db(scn, repo, audit_logger, interval_minutes=30)
        print(f"  - [{scn.patient.patient_id}] {scn.patient.name:<18} ({scn.name}): {v_count} vitals, {l_count} labs seeded.")
    print()

    # 3. Multi-Agent Deliberation & Coordination
    coordinator = MultiAgentCoordinator(repo=repo, audit_logger=audit_logger)
    approval_engine = ApprovalEngine(repo=repo, audit_logger=audit_logger)

    print("=" * 85)
    print(" Multi-Agent Deliberation & Cross-Domain Evidence Triangulation")
    print("=" * 85)

    proposals = []
    for scn in scenarios:
        pid = scn.patient.patient_id
        print(f"\n>>> Running Deliberation for Patient: {pid} ({scn.patient.name})")
        print("-" * 85)

        # Run Coordinator
        proposal = coordinator.coordinate_patient(pid)
        proposals.append(proposal)

        # Fetch findings generated during deliberation
        findings = repo.get_agent_findings(pid)
        print(f"  [*] Domain Agent Findings Generated: {len(findings)}")
        for f in findings:
            ev = f.evidence
            print(f"    - [{f.agent_name}] {f.severity.value:<8} | {f.title}")
            print(f"      Metric: {ev.metric} = {ev.observed_value} (Baseline: {ev.baseline_value or 'N/A'})")
            if ev.delta_change:
                print(f"      Delta: {ev.delta_change}")
            print(f"      Guideline: {ev.clinical_guideline}")

        print(f"\n  [+] Synthesized Proposal [{proposal.proposal_id}] (Urgency: {proposal.urgency.value}):")
        print(f"      Primary Concern: {proposal.primary_concern}")
        print(f"      Composite Risk Score: {proposal.composite_risk_score} ({proposal.scoring_system})")
        print(f"      Status: {proposal.status.value}")
        print("      Recommended Clinical Actions for Physician Review:")
        for idx, act in enumerate(proposal.recommended_actions, 1):
            print(f"        {idx}. [{act.intervention_type}] {act.description}")
            print(f"           Rationale: {act.rationale}")

    # 4. Human-in-the-Loop Physician Review Workflow
    print("\n" + "=" * 85)
    print(" Human-in-the-Loop Physician Governance Workflows")
    print("=" * 85)

    # Workflow 1: Doctor Approves Sepsis Proposal (PAT-002)
    sepsis_prop = next(p for p in proposals if p.patient_id == "PAT-002")
    act_1 = approval_engine.approve_proposal(
        proposal_id=sepsis_prop.proposal_id,
        physician_id="MD-4091",
        physician_name="Dr. Elizabeth Warren, MD",
        clinical_notes="Patient assessed at bedside. Clear signs of septic shock. Initiated 30 mL/kg balanced crystalloids; blood cultures drawn, broad-spectrum IV antibiotics ordered.",
    )
    print(f"\n[1] Action on Proposal {sepsis_prop.proposal_id} ({sepsis_prop.patient_id}):")
    print(f"    Physician: {act_1.physician_name} ({act_1.physician_id})")
    print(f"    Decision: {act_1.action.value}")
    print(f"    Clinical Notes: {act_1.clinical_notes}")

    # Workflow 2: Doctor Modifies Respiratory Proposal (PAT-003)
    resp_prop = next(p for p in proposals if p.patient_id == "PAT-003")
    act_2 = approval_engine.modify_proposal(
        proposal_id=resp_prop.proposal_id,
        physician_id="MD-5120",
        physician_name="Dr. Robert House, MD",
        modified_actions=[
            "Initiate Non-Invasive Ventilation (BiPAP) trial: IPAP 14 cmH2O, EPAP 5 cmH2O, FiO2 titrated to SpO2 88-92%.",
            "Hold morning lisinopril; administer nebulized ipratropium/albuterol Q2H.",
            "Repeat Arterial Blood Gas in 45 minutes to assess PaCO2 clearance.",
            "Family and patient re-confirmed DNI (Do Not Intubate) advance directive.",
        ],
        clinical_notes="Patient experiencing severe respiratory muscle exhaustion and CO2 retention. DNI confirmed. BiPAP trial initiated.",
    )
    print(f"\n[2] Action on Proposal {resp_prop.proposal_id} ({resp_prop.patient_id}):")
    print(f"    Physician: {act_2.physician_name} ({act_2.physician_id})")
    print(f"    Decision: {act_2.action.value}")
    print(f"    Modified Interventions: {len(act_2.modified_actions)} customized actions recorded.")
    print(f"    Clinical Notes: {act_2.clinical_notes}")

    # Workflow 3: Doctor Dismisses / Reviews Stable Proposal (PAT-001)
    stable_prop = next(p for p in proposals if p.patient_id == "PAT-001")
    act_3 = approval_engine.dismiss_proposal(
        proposal_id=stable_prop.proposal_id,
        physician_id="MD-1088",
        physician_name="Dr. Sarah Jenkins, MD",
        clinical_notes="Patient ambulating on ward; surgical site clean, vitals stable. Routine protocol sufficient.",
    )
    print(f"\n[3] Action on Proposal {stable_prop.proposal_id} ({stable_prop.patient_id}):")
    print(f"    Physician: {act_3.physician_name} ({act_3.physician_id})")
    print(f"    Decision: {act_3.action.value}")
    print(f"    Clinical Notes: {act_3.clinical_notes}")

    # 5. Audit Trail Verification
    print("\n" + "=" * 85)
    print(" Immutable Cryptographic Audit Ledger Status")
    print("=" * 85)
    recent_events = audit_logger.get_recent_events(limit=10)
    print(f"Total events recorded in audit ledger: {len(audit_logger.get_recent_events(limit=500))}")
    for evt in recent_events[:6]:
        valid = audit_logger.verify_event_integrity(evt["event_id"])
        status = "[VALID SHA-256]" if valid else "[INTEGRITY COMPROMISED]"
        print(f"  - {evt['event_id']} | {evt['event_type']:<26} | Actor: {evt['actor_id']:<22} | {status}")

    print("\n" + "=" * 85)
    print(" [SUCCESS] Phase 2 Verification Complete. Multi-Agent Intelligence fully operational.")
    print("=" * 85)


if __name__ == "__main__":
    main()
