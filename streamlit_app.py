"""Streamlit UI for the local inquiry-to-discovery-brief prototype."""

import streamlit as st

from app.config import get_settings
from app.errors import LLMError
from app.llm_client import GroqClient
from app.pipeline import analyze_inquiry
from app.schemas import AnalysisReport, Requirement, ReviewStatus
from app.validation import InvalidInquiryError

EXAMPLE_INQUIRY = (
    "We run three dental clinics in Jaipur. We want a web app where patients can book "
    "appointments online and get SMS reminders, and our receptionists can see a daily schedule. "
    "We have about 2,000 patients. We would like to launch before March."
)


def _show_requirement(requirement: Requirement) -> None:
    if requirement.origin == "stated":
        st.markdown("**Candidate stated requirement - verify meaning**")
        st.code(requirement.evidence or "")
        st.caption(
            "The application checked that this quote occurs in the inquiry. "
            "It cannot prove the quote supports the requirement; review it against the original."
        )
    else:
        st.markdown("**Inference - not a client-confirmed fact**")
        st.write(requirement.text)


def _show_report(report: AnalysisReport) -> None:
    analysis = report.analysis
    status_text = (
        "DRAFT — HUMAN REVIEW REQUIRED"
        if report.review_status == ReviewStatus.DRAFT
        else report.review_status.value
    )
    st.warning(
        f"{status_text}. {report.disclaimer} "
        "Evidence matching checks quote presence, not semantic entailment."
    )
    for note in report.normalization_notes:
        st.info(note)
    st.caption(
        f"Model: {report.model_name} | Prompt: {report.prompt_version} | "
        f"Attempts: {report.attempts} | Latency: {report.latency_seconds or 0:.2f}s"
    )

    if not analysis.is_relevant:
        st.info(analysis.relevance_note)
        return

    extraction = analysis.extraction
    blueprint = analysis.blueprint
    if extraction is None or blueprint is None:
        st.error("The validated result is incomplete. Generate the draft again.")
        return

    summary_tab, requirements_tab, discovery_tab, blueprint_tab, json_tab = st.tabs(
        ["Summary", "Requirements & evidence", "Discovery", "Blueprint", "JSON"]
    )

    with summary_tab:
        st.subheader("Inquiry excerpt (verbatim; verify intent)")
        st.code(blueprint.business_problem)
        st.write(f"Service categories: {', '.join(c.value for c in extraction.service_categories)}")
        if extraction.objectives:
            st.subheader("Quoted objectives")
            for objective in extraction.objectives:
                st.code(objective)
        st.subheader("Constraints stated in the inquiry")
        constraints = extraction.constraints
        constraint_values = {
            "User scale": constraints.user_scale,
            "Timeline": constraints.timeline,
            "Budget": constraints.budget,
        }
        for label, value in constraint_values.items():
            st.write(f"**{label}:** {value if value is not None else 'Not stated'}")
        for value in constraints.other:
            st.write(f"**Other stated constraint:** {value}")

    with requirements_tab:
        st.subheader("Functional requirements")
        for item in extraction.functional_requirements:
            _show_requirement(item)
        st.subheader("Non-functional requirements")
        for item in extraction.non_functional_requirements:
            _show_requirement(item)
        if not extraction.functional_requirements and not extraction.non_functional_requirements:
            st.info("No requirements were extracted. Review the inquiry and discovery questions.")

    with discovery_tab:
        st.subheader("Missing information")
        for item in extraction.missing_information:
            st.markdown(f"**{item.topic}**")
            st.write(item.why_it_matters)
        st.subheader("Discovery questions")
        for item in extraction.discovery_questions:
            st.markdown(f"- {item.question}  \n  *Gap: {item.missing_information_topic}*")
        st.subheader("Potential contradictions - confirm with the client")
        if extraction.conflicts:
            for conflict in extraction.conflicts:
                st.code(f'A: "{conflict.statement_a}"\nB: "{conflict.statement_b}"')
                st.write(conflict.explanation)
        else:
            st.write("No potential contradictions were identified.")
        st.subheader("Assumptions to confirm")
        for assumption in blueprint.assumptions_to_confirm:
            st.write(f"- {assumption}")

    with blueprint_tab:
        st.subheader("Draft executive summary")
        st.write(blueprint.executive_summary)
        st.subheader("Provisional architecture")
        for item in blueprint.architecture_outline:
            st.write(f"- {item}")
        if blueprint.technology_options:
            st.subheader("Technology options - not selected")
            for option in blueprint.technology_options:
                st.markdown(f"**{option.component}:** {option.suggestion}")
                st.write(option.rationale)
        st.subheader("Provisional phases")
        for phase in blueprint.phases:
            st.markdown(f"**{phase.name}**")
            st.write(phase.description)
        st.subheader("Potential risks")
        for risk in blueprint.risks:
            st.write(f"- {risk}")
        if extraction.overlapping_offerings:
            st.subheader("Public Cynbit offerings that may be relevant")
            for offering in extraction.overlapping_offerings:
                st.write(f"- {offering}")

    with json_tab:
        report_json = report.model_dump_json(indent=2)
        st.download_button(
            "Download validated draft JSON",
            data=report_json,
            file_name="discovery-brief-draft.json",
            mime="application/json",
        )
        st.code(report_json, language="json")


def main() -> None:
    st.set_page_config(page_title="Cynbit Discovery Brief", layout="wide")
    st.title("Client inquiry to discovery brief")
    st.write(
        "Turn a project inquiry into a structured draft for a Cynbit consultant to review. "
        "This prototype does not create a proposal or send a response to a client."
    )
    st.info(
        "The inquiry is sent to the configured Groq API. Do not enter sensitive personal, "
        "financial, health, or confidential information unless you have approval to share it."
    )

    inquiry = st.text_area(
        "Client inquiry",
        value=EXAMPLE_INQUIRY,
        height=180,
        max_chars=4000,
        help="Replace the synthetic example with an inquiry that you are authorized to process.",
    )
    if st.button("Generate discovery draft", type="primary"):
        st.session_state.pop("analysis_report", None)
        try:
            with st.spinner("Generating and validating a draft..."):
                client = GroqClient(get_settings())
                report = analyze_inquiry(inquiry, client)
            st.session_state["analysis_report"] = report.model_dump(mode="json")
        except InvalidInquiryError as exc:
            st.error(str(exc))
        except LLMError as exc:
            st.error(f"{type(exc).__name__}: {exc}")

    report_data = st.session_state.get("analysis_report")
    if report_data:
        _show_report(AnalysisReport.model_validate(report_data))


if __name__ == "__main__":
    main()
