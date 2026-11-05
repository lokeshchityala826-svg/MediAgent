from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_adapter import get_services
from mediagent.engine.news2 import NEWS2Calculator
from mediagent.engine.qsofa import QSOFACalculator
from mediagent.models.proposal import ActionState

st.set_page_config(page_title="MediAgent | Clinical Monitoring", page_icon="🩺", layout="wide")

st.markdown("""
<style>
:root { --navy:#10243a; --teal:#0d9488; --ink:#203247; --muted:#64748b; }
.block-container {padding-top:1.5rem; padding-bottom:2rem; max-width:1500px;}
[data-testid="stSidebar"] {background:#f3f7fb;}
[data-testid="stMetric"] {background:white;border:1px solid #e5edf4;padding:14px 16px;border-radius:12px;}
.hero {background:linear-gradient(120deg,#10243a,#155e75);padding:24px 28px;border-radius:16px;color:white;margin-bottom:18px;}
.hero p {color:#dbeafe;margin-bottom:0;}
.small-muted {color:#64748b;font-size:0.88rem;}
.section-card {background:#fff;border:1px solid #e5edf4;border-radius:12px;padding:16px 18px;margin-bottom:12px;}
div[data-testid="stButton"] button {border-radius:9px;}
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("## 🩺 MediAgent")
st.sidebar.caption("Agentic AI monitoring demo")
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Patient Monitoring", "AI Agents", "Risk Assessment",
     "Alert Management", "Doctor Review", "Medicine Scanner"],
)
st.sidebar.divider()
st.sidebar.caption("Synthetic data only • Offline-first demo")
st.sidebar.caption("Not for clinical diagnosis or treatment.")

try:
    svc = get_services()
    repo, audit, coordinator, approval = svc["repo"], svc["audit"], svc["coordinator"], svc["approval"]
    patients = repo.list_patients()
except Exception as exc:
    st.error(f"Could not connect to the MediAgent database: {exc}")
    st.info("Check that data/mediagent.db exists and the project dependencies are installed.")
    st.stop()

if not patients:
    st.warning("No patient records were found in the supplied database. The dashboard will not invent patient data.")
    st.stop()

patient_map = {f"{p.patient_id} — {p.name}": p for p in patients}
selected_label = st.sidebar.selectbox("Selected patient", list(patient_map))
patient = patient_map[selected_label]
pid = patient.patient_id

def get_patient_snapshot(p):
    stream = repo.get_vitals_stream(p.patient_id)
    latest = stream[-1] if stream else None
    news = NEWS2Calculator.calculate(
        latest, is_copd_spo2_scale2=p.baseline_vitals.is_copd_spo2_scale2
    ) if latest else None
    qsofa = QSOFACalculator.calculate(latest) if latest else None
    return stream, latest, news, qsofa

def risk_color(level):
    return {"HIGH":"🔴","MEDIUM":"🟠","LOW_MEDIUM":"🟡","LOW":"🟢"}.get(level,"⚪")

def header(title, subtitle):
    st.markdown(f'<div class="hero"><h2 style="margin:0;color:white">{title}</h2><p>{subtitle}</p></div>', unsafe_allow_html=True)

def patient_summary(p):
    a,b,c,d = st.columns(4)
    a.metric("Patient ID", p.patient_id)
    b.metric("Age", f"{p.age} years")
    c.metric("Location", p.room_bed)
    d.metric("Code status", p.code_status.value.replace("_"," "))

if page == "Dashboard":
    header("Clinical Overview", "Evidence-led view of the supplied synthetic patient database")
    stream, latest, news, qsofa = get_patient_snapshot(patient)
    all_proposals = repo.list_all_proposals()
    pending = [x for x in all_proposals if x.status == ActionState.PENDING_REVIEW]
    all_findings = [f for p in patients for f in repo.get_agent_findings(p.patient_id)]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Synthetic patients", len(patients))
    c2.metric("Pending reviews", len(pending))
    c3.metric("Agent findings", len(all_findings))
    c4.metric("Vitals records", sum(len(repo.get_vitals_stream(p.patient_id)) for p in patients))
    st.subheader("Selected patient")
    patient_summary(patient)
    if latest:
        x1,x2,x3,x4,x5 = st.columns(5)
        x1.metric("Heart rate", f"{latest.heart_rate:.0f} bpm")
        x2.metric("SpO₂", f"{latest.spo2:.0f}%")
        x3.metric("Respiratory rate", f"{latest.respiratory_rate:.0f}/min")
        x4.metric("Temperature", f"{latest.temperature_c:.1f} °C")
        x5.metric("NEWS2", f"{news.total_score} · {news.risk_level}")
        st.caption(f"Latest recorded telemetry: {latest.timestamp:%d %b %Y, %H:%M} · qSOFA {qsofa.total_score}/3 ({qsofa.clinical_risk})")
    else:
        st.info("No vital-sign records are available for this patient.")
    left,right=st.columns([1.3,1])
    with left:
        st.subheader("Latest patient risk snapshot")
        if news:
            st.write(f"**NEWS2:** {risk_color(news.risk_level)} {news.risk_level} — score {news.total_score}")
            st.write(f"**qSOFA:** {qsofa.total_score}/3 — {qsofa.clinical_risk}")
            st.caption("Scores are calculated by the backend engines from the latest stored observation.")
        else:
            st.info("Risk scores require a recorded vital-sign observation.")
    with right:
        st.subheader("Review queue")
        if pending:
            for prop in pending[:5]:
                st.warning(f"{prop.patient_id} · {prop.urgency.value} · {prop.primary_concern}")
        else:
            st.success("No pending proposals in the current database.")
    st.subheader("Patient roster")
    roster=[]
    for p in patients:
        vs=repo.get_vitals_stream(p.patient_id)
        n=NEWS2Calculator.calculate(vs[-1],p.baseline_vitals.is_copd_spo2_scale2) if vs else None
        roster.append({"Patient":p.patient_id,"Name":p.name,"Age":p.age,"Bed":p.room_bed,
                       "Latest NEWS2":n.total_score if n else "—","Risk":n.risk_level if n else "No data"})
    st.dataframe(pd.DataFrame(roster),use_container_width=True,hide_index=True)

elif page == "Patient Monitoring":
    header("Patient Monitoring", "Recorded telemetry and patient context from SQLite")
    patient_summary(patient)
    stream,latest,news,qsofa=get_patient_snapshot(patient)
    if not stream:
        st.info("No telemetry is stored for this patient.")
    else:
        df=pd.DataFrame([{"Time":v.timestamp,"Heart rate (bpm)":v.heart_rate,
            "SpO₂ (%)":v.spo2,"Respiratory rate":v.respiratory_rate,
            "Systolic BP (mmHg)":v.systolic_bp,"Temperature (°C)":v.temperature_c}
            for v in stream])
        range_choice=st.selectbox("Time window",["All recorded data","Last 12 hours","Last 6 hours"])
        if range_choice != "All recorded data":
            hours=12 if "12" in range_choice else 6
            df=df[df["Time"] >= df["Time"].max()-pd.Timedelta(hours=hours)]
        metric=st.selectbox("Trend to display",["Heart rate (bpm)","SpO₂ (%)","Respiratory rate","Systolic BP (mmHg)","Temperature (°C)"])
        fig=px.line(df,x="Time",y=metric,markers=True,title=f"{metric} over recorded time")
        fig.update_layout(height=390,margin=dict(l=10,r=10,t=55,b=10),xaxis_title="")
        st.plotly_chart(fig,use_container_width=True)
        st.subheader("Latest observation")
        st.dataframe(df.tail(1),use_container_width=True,hide_index=True)
        st.subheader("Patient background")
        st.write("**Admission reason:**",patient.admission_reason)
        st.write("**Comorbidities:**",", ".join(c.description for c in patient.comorbidities) or "None recorded")
        st.write("**Active medications:**",", ".join(m.name for m in patient.medications if m.is_active) or "None recorded")
        st.write("**Allergies:**",", ".join(patient.allergies) or "None recorded")

elif page == "AI Agents":
    header("AI Agent Activity", "Three specialist agents coordinated by the existing backend")
    st.write("The backend defines VitalsMonitoringAgent, LaboratoryAnalysisAgent and EHRAnalysisAgent. Findings appear here after an analysis run.")
    if st.button("Run coordinator for selected patient",type="primary"):
        try:
            with st.spinner("Running the existing multi-agent coordinator..."):
                proposal=coordinator.coordinate_patient(pid)
            st.success(f"Coordinator completed. Proposal {proposal.proposal_id} was saved for physician review.")
            st.rerun()
        except Exception as exc:
            st.error(f"Coordinator failed: {exc}")
    findings=repo.get_agent_findings(pid)
    agent_names=["VitalsMonitoringAgent","LaboratoryAnalysisAgent","EHRAnalysisAgent"]
    cols=st.columns(3)
    for col,name in zip(cols,agent_names):
        matches=[f for f in findings if f.agent_name==name]
        with col:
            st.markdown(f"### {name.replace('Agent',' Agent')}")
            st.metric("Stored findings",len(matches))
            st.caption("Has stored findings" if matches else "No findings stored yet")
    st.subheader("Evidence findings")
    if findings:
        for f in reversed(findings):
            with st.expander(f"{f.severity.value} · {f.title} · {f.timestamp:%d %b %H:%M}",expanded=False):
                st.write(f.narrative_summary)
                st.write(f"**Agent:** {f.agent_name} · **Category:** {f.category}")
                st.write(f"**Evidence:** {f.evidence.metric} = {f.evidence.observed_value} {f.evidence.reference_range or ''}")
                if f.evidence.baseline_value is not None: st.write(f"**Baseline:** {f.evidence.baseline_value}")
                if f.evidence.delta_change: st.write(f"**Change:** {f.evidence.delta_change}")
                st.caption(f.evidence.clinical_guideline)
    else:
        st.info("No agent findings exist for this patient yet. Use the coordinator button to generate and persist findings.")

elif page == "Risk Assessment":
    header("Risk Assessment", "Backend NEWS2 and qSOFA calculations — no frontend threshold replacement")
    stream,latest,news,qsofa=get_patient_snapshot(patient)
    if latest:
        a,b=st.columns(2)
        with a:
            st.subheader("NEWS2")
            st.metric("Total score",news.total_score,help="Calculated by mediagent.engine.news2.NEWS2Calculator")
            st.write(f"**Risk band:** {risk_color(news.risk_level)} {news.risk_level}")
            st.write(news.clinical_response)
            st.dataframe(pd.DataFrame([{"Parameter":k.replace("_"," ").title(),"Score":v} for k,v in news.parameter_scores.items()]),use_container_width=True,hide_index=True)
        with b:
            st.subheader("qSOFA")
            st.metric("Total score",f"{qsofa.total_score}/3")
            st.write(f"**Screening band:** {qsofa.clinical_risk}")
            st.write(qsofa.guideline_statement)
            st.dataframe(pd.DataFrame([{"Criterion":k.replace("_"," ").title(),"Met":v} for k,v in qsofa.criteria_met.items()]),use_container_width=True,hide_index=True)
        st.caption(f"Based on latest observation at {latest.timestamp:%d %b %Y, %H:%M}. This is a synthetic educational demonstration, not a diagnosis.")
    else:
        st.info("Risk assessment is unavailable until telemetry exists.")

elif page == "Alert Management":
    header("Alert Management", "Agent-generated findings with their supporting evidence")
    findings=[f for f in repo.get_agent_findings(pid)]
    proposals=repo.get_clinical_proposals(pid)
    if proposals:
        st.subheader("Coordinator proposals")
        for p in reversed(proposals):
            with st.expander(f"{p.urgency.value} · {p.status.value} · {p.proposal_id}"):
                st.write(p.primary_concern)
                st.write(f"Composite score: {p.composite_risk_score} ({p.scoring_system})")
                for act in p.recommended_actions:
                    st.markdown(f"- **{act.intervention_type}:** {act.description}")
                    st.caption(act.rationale)
                st.write("Contributing finding IDs:",", ".join(p.contributing_agent_findings) or "None")
    st.subheader("Evidence-backed findings")
    if findings:
        for f in reversed(findings):
            st.markdown(f"**{f.severity.value} — {f.title}**")
            st.write(f"{f.narrative_summary}")
            st.caption(f"{f.evidence.metric}: {f.evidence.observed_value} · {f.timestamp:%d %b %Y %H:%M} · {f.agent_name}")
            st.caption(f"Guideline context: {f.evidence.clinical_guideline}")
            st.divider()
    else:
        st.info("No findings are stored. Run the coordinator from AI Agents to populate this page.")

elif page == "Doctor Review":
    header("Doctor Review", "Human-in-the-loop proposal review using the existing ApprovalEngine")
    proposals=approval.get_pending_proposals(pid)
    if not proposals:
        st.success("No pending proposals for the selected patient.")
    else:
        chosen=st.selectbox("Pending proposal",proposals,format_func=lambda p:f"{p.proposal_id} · {p.urgency.value}")
        st.markdown(f"**Primary concern:** {chosen.primary_concern}")
        st.write(f"**Urgency:** {chosen.urgency.value} · **Composite score:** {chosen.composite_risk_score} ({chosen.scoring_system})")
        st.subheader("Proposed actions")
        for item in chosen.recommended_actions:
            st.markdown(f"- **{item.intervention_type}:** {item.description}")
            st.caption(item.rationale)
        st.subheader("Review record")
        with st.form(f"review_{chosen.proposal_id}"):
            physician_id=st.text_input("Reviewer ID",placeholder="e.g. DEMO-REVIEWER")
            physician_name=st.text_input("Reviewer name",placeholder="Enter authorized demo reviewer name")
            decision=st.radio("Decision",["Approve","Modify","Dismiss"],horizontal=True)
            modified=st.text_area("Modified actions (one per line)",disabled=decision!="Modify")
            notes=st.text_area("Review notes / justification",help="Required for Modify and Dismiss.")
            submitted=st.form_submit_button("Submit review",type="primary")
            if submitted:
                if not physician_id.strip() or not physician_name.strip():
                    st.error("Reviewer ID and name are required.")
                elif decision in ("Modify","Dismiss") and not notes.strip():
                    st.error("Review notes are required for Modify and Dismiss.")
                elif decision=="Modify" and not [x.strip() for x in modified.splitlines() if x.strip()]:
                    st.error("Enter at least one modified action.")
                else:
                    try:
                        if decision=="Approve":
                            action=approval.approve_proposal(chosen.proposal_id,physician_id.strip(),physician_name.strip(),notes.strip() or None)
                        elif decision=="Modify":
                            action=approval.modify_proposal(chosen.proposal_id,physician_id.strip(),physician_name.strip(),[x.strip() for x in modified.splitlines() if x.strip()],notes.strip())
                        else:
                            action=approval.dismiss_proposal(chosen.proposal_id,physician_id.strip(),physician_name.strip(),notes.strip())
                        st.success(f"Review recorded: {action.action.value} · {action.action_id}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Review was not recorded: {exc}")
    st.subheader("Previously recorded doctor actions")
    actions=repo.get_doctor_actions(pid)
    if actions:
        st.dataframe(pd.DataFrame([{"Proposal":a.proposal_id,"Decision":a.action.value,"Reviewer":a.physician_name,"Reviewer ID":a.physician_id,"Reviewed":a.reviewed_at,"Notes":a.clinical_notes} for a in reversed(actions)]),use_container_width=True,hide_index=True)
    else:
        st.caption("No doctor actions have been recorded for this patient.")

elif page == "Medicine Scanner":
    header("Medicine Scanner", "Offline-first interface placeholder")
    st.info("The supplied backend ZIP does not include a medicine catalogue, barcode decoder, or medicine-verification service. This page intentionally does not call an external product API or invent medicine details.")
    st.markdown("**To complete this page offline:** add a reviewed local medicine catalogue and a locally installed barcode decoder, then display only catalogue matches with a clear 'not found' state.")
    uploaded=st.file_uploader("Optional barcode image (preview only)",type=["png","jpg","jpeg"])
    if uploaded:
        st.image(uploaded,caption="Uploaded image preview — barcode is not decoded by this build.",use_container_width=True)

st.sidebar.divider()
st.sidebar.caption(f"Selected: {pid}")
st.sidebar.caption(f"Dashboard refreshed: {datetime.now():%H:%M:%S}")
st.caption("MediAgent is a synthetic-data hackathon demonstration. It is not a medical device, diagnostic system, or substitute for qualified clinical judgment.")
