# MediAgent Frontend (Streamlit)

This folder is the **frontend only**. It imports the existing `mediagent` package and reads/writes the existing backend SQLite database. It does not contain backend source, tests, a copied database, seeded patients, mock agents, or frontend-side clinical scoring rules.

## Expected folder layout

Keep the frontend and backend as sibling folders:

```text
MediAgent_Project/
├── MediAgent_Backend/       # Your existing backend; do not replace it
│   ├── mediagent/
│   ├── data/mediagent.db
│   └── requirements.txt
└── MediAgent_Frontend/      # This delivery
    ├── app.py
    ├── backend_adapter.py
    ├── requirements.txt
    ├── README.md
    └── .streamlit/config.toml
```

The adapter also supports an explicit backend path using `MEDIAGENT_BACKEND_PATH`.

## Install and run (Windows PowerShell)

1. Open the `MediAgent_Frontend` folder in VS Code.
2. Open the integrated terminal and create a frontend virtual environment:

   ```powershell
   py -3.14 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

3. Confirm that the backend folder is beside `MediAgent_Frontend` and that its existing `data\mediagent.db` is present.
4. If your backend is in another location, set its absolute path before starting Streamlit:

   ```powershell
   $env:MEDIAGENT_BACKEND_PATH = "C:\path\to\MediAgent_Backend"
   ```

5. Start the dashboard:

   ```powershell
   python -m streamlit run app.py
   ```

6. Open the local URL printed by Streamlit (normally `http://localhost:8501`). Stop with `Ctrl+C`.

If PowerShell blocks environment activation, you can skip activation and run the venv executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Integration boundary / backend contract

`backend_adapter.py` resolves the backend root, adds it to `sys.path`, and constructs these existing objects against `<backend-root>/data/mediagent.db`:

- `DatabaseManager(db_path=...)`
- `PatientRepository(db_manager)`
- `AuditLogger(db_manager)`
- `MultiAgentCoordinator(repo=..., audit_logger=...)`
- `ApprovalEngine(repo=..., audit_logger=...)`

The dashboard uses these existing repository methods:

| Existing backend method | Frontend use |
|---|---|
| `PatientRepository.list_patients()` | Patient selector and roster |
| `PatientRepository.get_patient(patient_id)` | Patient lookup through backend coordinator |
| `PatientRepository.get_vitals_stream(patient_id, limit=None)` | Time-series monitoring |
| `PatientRepository.get_agent_findings(patient_id)` | Agent findings and alert evidence |
| `PatientRepository.get_clinical_proposals(patient_id)` | Proposal list |
| `PatientRepository.list_all_proposals()` | Dashboard review count |
| `PatientRepository.get_doctor_actions(patient_id=None)` | Review history |
| `MultiAgentCoordinator.coordinate_patient(patient_id, current_time=None)` | Explicit user-triggered analysis using the existing agents |
| `ApprovalEngine.get_pending_proposals(patient_id=None)` | Human review queue |
| `ApprovalEngine.approve_proposal(proposal_id, physician_id, physician_name, clinical_notes=None)` | Approve proposal |
| `ApprovalEngine.modify_proposal(proposal_id, physician_id, physician_name, modified_actions, clinical_notes)` | Modify proposal |
| `ApprovalEngine.dismiss_proposal(proposal_id, physician_id, physician_name, clinical_notes)` | Dismiss proposal |

The UI imports the existing `NEWS2Calculator.calculate(vitals, is_copd_spo2_scale2=False)` and `QSOFACalculator.calculate(vitals)` from `mediagent.engine`. No thresholds, scores, or risk bands are independently implemented in the frontend.

## Data structures read by the dashboard

The UI expects the existing Pydantic backend models and their attributes:

- `Patient`: `patient_id`, `name`, `age`, `room_bed`, `code_status`, `baseline_vitals.is_copd_spo2_scale2`, `admission_reason`, `comorbidities[].description`, `medications[].name/is_active`, `allergies`.
- `VitalSigns`: `timestamp`, `patient_id`, `heart_rate`, `spo2`, `respiratory_rate`, `systolic_bp`, `temperature_c`; backend score engines also use `on_supplemental_oxygen`, `consciousness`, and `gcs`.
- `AgentFinding`: `finding_id`, `agent_name`, `patient_id`, `timestamp`, `severity`, `category`, `title`, `narrative_summary`, and `evidence` (`metric`, `observed_value`, `reference_range`, `baseline_value`, `delta_change`, `clinical_guideline`).
- `ClinicalProposal`: `proposal_id`, `patient_id`, `urgency`, `status`, `primary_concern`, `composite_risk_score`, `scoring_system`, `recommended_actions[]` (`intervention_type`, `description`, `rationale`), `contributing_agent_findings`.
- `DoctorAction`: `proposal_id`, `action`, `physician_id`, `physician_name`, `reviewed_at`, `clinical_notes`, `action_id`.
- NEWS2 result: `total_score`, `risk_level`, `clinical_response`, `parameter_scores`.
- qSOFA result: `total_score`, `clinical_risk`, `criteria_met`, `guideline_statement`.

## Pages and current scope

- Dashboard, Patient Monitoring, AI Agents, Risk Assessment, Alert Management, Doctor Review, Medicine Scanner.
- Medicine Scanner is intentionally a preview-only placeholder because the supplied backend has no medicine catalogue, barcode decoder, or verification service. It does not fabricate medicine matches.
- The dashboard does not initialize, seed, or reset the database. Run the backend's own setup/seed process separately if the database has not been initialized.

## Important

The backend remains the source of truth. Keep `MediAgent_Backend/mediagent`, its tests, and its database in place. Do not copy this frontend's adapter into the backend package. The project is a synthetic hackathon demonstration, not a medical device or a substitute for qualified clinical judgment.
