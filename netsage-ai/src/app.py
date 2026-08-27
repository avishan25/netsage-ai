"""
app.py — NetSage AI Operations Dashboard (Streamlit)
------------------------------------------------------
Implements the Human-in-the-Loop (HITL) gate described in the technical
documentation: an operator selects a case, runs diagnosis (checker.py first,
LLM fallback via engine.py), reviews the evidence, and must Approve & Deploy,
Edit Commands, or Reject before anything is considered "fixed". Every
decision is written to docs/audit_log.csv, and any case where the AI /
rule-engine answer was Edited or Rejected is also appended to
docs/model_audit_log.md (the Responsible-AI log required by the brief).

Run with:
    streamlit run src/app.py
"""

import os
import sys
import json
import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import diagnose  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
CASES_PATH = BASE_DIR / "data" / "cases.csv"
AUDIT_CSV_PATH = BASE_DIR / "docs" / "audit_log.csv"
AUDIT_MD_PATH = BASE_DIR / "docs" / "model_audit_log.md"

AUDIT_COLUMNS = [
    "timestamp", "case_id", "expected_fault", "ai_root_cause", "ai_osi_layer",
    "ai_confidence", "ai_source", "human_decision", "reviewer_note",
]

st.set_page_config(page_title="NetSage AI — Operations Dashboard", layout="wide")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
@st.cache_data
def load_cases() -> pd.DataFrame:
    return pd.read_csv(CASES_PATH)


def load_audit_log() -> pd.DataFrame:
    if AUDIT_CSV_PATH.exists():
        return pd.read_csv(AUDIT_CSV_PATH)
    return pd.DataFrame(columns=AUDIT_COLUMNS)


def append_audit_row(row: dict) -> None:
    AUDIT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = load_audit_log()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(AUDIT_CSV_PATH, index=False)


def append_markdown_correction(row: dict) -> None:
    """Appends a row to docs/model_audit_log.md ONLY for Edited/Rejected
    decisions — this is the required 'Responsible AI log' of at least 5
    cases where the AI answer was corrected by a human."""
    AUDIT_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not AUDIT_MD_PATH.exists():
        AUDIT_MD_PATH.write_text(
            "# NetSage AI — Model Audit Log\n\n"
            "Cases where the AI / rule-engine diagnosis was corrected "
            "(Edited) or rejected by a human reviewer.\n\n"
            "| Timestamp | Case ID | AI Root Cause | Human Decision | Reviewer Note |\n"
            "|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with open(AUDIT_MD_PATH, "a", encoding="utf-8") as f:
        f.write(
            f"| {row['timestamp']} | {row['case_id']} | {row['ai_root_cause']} "
            f"| {row['human_decision']} | {row['reviewer_note']} |\n"
        )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("🛰️ NetSage AI — Operations Dashboard")
st.caption("Automated network diagnostics with a mandatory human review gate.")

tab_diagnose, tab_dashboard, tab_audit = st.tabs(
    ["🔎 Diagnose a Case", "📊 Summary Dashboard", "📝 Audit Log"]
)

cases_df = load_cases()

# --- Tab 1: Diagnose a case -------------------------------------------------
with tab_diagnose:
    col_select, col_detail = st.columns([1, 2])

    with col_select:
        case_id = st.selectbox("Select Case ID", cases_df["case_id"].tolist())

    case_row = cases_df[cases_df["case_id"] == case_id].iloc[0]

    with col_detail:
        st.subheader(f"{case_row['case_id']} — {case_row['symptom']}")
        st.write(f"**Topology note:** {case_row['topology_note']}")
        st.code(case_row["show_outputs"], language="text")
        badge_col1, badge_col2, badge_col3 = st.columns(3)
        badge_col1.metric("OSI Layer", case_row["osi_layer"])
        badge_col2.metric("Severity", case_row["severity"])
        badge_col3.metric("Concept", case_row["concept_tag"])

    st.divider()

    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    use_llm = st.checkbox(
        "🤖 Also run AI (LLM) diagnosis",
        value=True,
        help="Calls the Anthropic API using prompts/diagnose_prompt.md. "
             "Requires ANTHROPIC_API_KEY to be set (see .env.example)."
    )
    if use_llm and not api_key_set:
        st.warning(
            "No ANTHROPIC_API_KEY found. Copy `.env.example` to `.env` in the project "
            "root and paste your key in, then restart the app. Diagnosis will still run "
            "using the rule engine in the meantime."
        )

    if st.button("▶️ Run Diagnosis", type="primary"):
        case_dict = case_row.to_dict()
        with st.spinner("Running deterministic checker" + (" and AI diagnosis..." if use_llm else "...")):
            result = diagnose(case_dict, use_llm=use_llm)
        st.session_state["last_result"] = result
        st.session_state["last_case_id"] = case_id

    result = st.session_state.get("last_result")
    if result and st.session_state.get("last_case_id") == case_id:
        rule_diag = result.get("rule_diagnosis")
        llm_diag = result.get("llm_diagnosis")

        st.markdown("### Diagnostic Output")

        col_rule, col_llm = st.columns(2)

        def render_diag(container, title, diag):
            with container:
                st.markdown(f"**{title}**")
                if diag is None:
                    st.caption("Not run / no match.")
                    return
                st.write(f"Root cause: {diag['root_cause']}")
                st.write(f"OSI layer: {diag['osi_layer']}")
                st.write(f"Confidence: {diag['confidence']:.2f}")
                st.write(f"Evidence: `{diag['evidence']}`")
                st.write(f"Next command: `{diag['next_command']}`")

        render_diag(col_rule, "🔧 Rule Engine (deterministic)", rule_diag)
        render_diag(col_llm, "🤖 AI / LLM Diagnosis", llm_diag)

        st.divider()
        options = []
        if rule_diag is not None:
            options.append("Rule Engine")
        if llm_diag is not None:
            options.append("AI / LLM")
        if not options:
            st.stop()
        chosen_source = st.radio("Which diagnosis do you want to act on?", options, horizontal=True)
        diagnosis = rule_diag if chosen_source == "Rule Engine" else llm_diag
        st.caption(f"Acting on: **{chosen_source}** diagnosis (source tag: `{diagnosis.get('source', 'n/a')}`)")

        st.markdown("**Proposed fix steps (editable before deployment):**")
        editable_fix = st.text_area(
            "fix_steps",
            value="\n".join(diagnosis["fix_steps"]),
            height=140,
            label_visibility="collapsed",
        )

        st.markdown("### Human Review Gate")
        reviewer_note = st.text_input(
            "Reviewer note (required for Edit / Reject)",
            placeholder="e.g. 'AI evidence was correct but fix needed the right VLAN id filled in'",
        )

        b1, b2, b3 = st.columns(3)
        decision = None
        if b1.button("✅ Approve & Deploy"):
            decision = "Approved"
        if b2.button("✏️ Edit Commands & Deploy"):
            decision = "Edited"
        if b3.button("❌ Reject (False Positive)"):
            decision = "Rejected"

        if decision:
            row = {
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "case_id": case_id,
                "expected_fault": case_row["expected_fault"],
                "ai_root_cause": diagnosis["root_cause"],
                "ai_osi_layer": diagnosis["osi_layer"],
                "ai_confidence": diagnosis["confidence"],
                "ai_source": diagnosis.get("source", "n/a"),
                "human_decision": decision,
                "reviewer_note": reviewer_note or "(no note provided)",
            }
            append_audit_row(row)
            if decision in ("Edited", "Rejected"):
                append_markdown_correction(row)
            st.toast(f"Decision '{decision}' logged for {case_id}.", icon="✅")
            st.rerun()

# --- Tab 2: Summary dashboard ------------------------------------------------
with tab_dashboard:
    st.subheader("Case Coverage")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Cases by concept tag**")
        st.bar_chart(cases_df["concept_tag"].value_counts())
    with c2:
        st.write("**Cases by severity**")
        st.bar_chart(cases_df["severity"].value_counts())

    st.divider()
    st.subheader("AI vs Human Agreement")
    audit_df = load_audit_log()
    if audit_df.empty:
        st.info("No diagnoses have been reviewed yet. Go to the Diagnose tab and review a case.")
    else:
        decision_counts = audit_df["human_decision"].value_counts()
        st.bar_chart(decision_counts)

        total = len(audit_df)
        approved = (audit_df["human_decision"] == "Approved").sum()
        agreement_rate = (approved / total * 100) if total else 0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Reviewed", total)
        m2.metric("Approved (AI agreed with)", int(approved))
        m3.metric("Edited/Rejected", int(total - approved))
        m4.metric("Agreement Rate", f"{agreement_rate:.1f}%")

# --- Tab 3: Raw audit log ----------------------------------------------------
with tab_audit:
    st.subheader("Full Review Log")
    audit_df = load_audit_log()
    if audit_df.empty:
        st.info("No entries yet.")
    else:
        st.dataframe(audit_df, use_container_width=True)
        st.download_button(
            "Download audit_log.csv",
            audit_df.to_csv(index=False),
            file_name="audit_log.csv",
            mime="text/csv",
        )

    st.divider()
    st.subheader("Responsible AI Log (Corrected Cases)")
    if AUDIT_MD_PATH.exists():
        st.markdown(AUDIT_MD_PATH.read_text(encoding="utf-8"))
    else:
        st.info("No corrections logged yet — this file is created automatically once you "
                 "Edit or Reject a diagnosis (need at least 5 for the assignment requirement).")
