"""Browser integration coverage for every Context Doctor analysis flow."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from context_doctor.flows import (
    question_analysis as question_analysis_flow,
    rule_analysis as rule_analysis_flow,
    rule_generation as rule_generation_flow,
)


def category_result() -> rule_analysis_flow.CategoryResult:
    return rule_analysis_flow.CategoryResult(
        explanation="Revenue guidance overlaps.",
        matched_rules=[2],
        matched_from_schema=["orders.revenue"],
    )


def comparison_response(summary: str) -> rule_analysis_flow.AcceptNewRule:
    return rule_analysis_flow.AcceptNewRule(
        analysis_summary=summary,
        typos=[],
        dialect_inconsistencies=["Use PostgreSQL aggregate syntax."],
        contradictions=category_result(),
        duplications=category_result(),
    )


def validation_response(summary: str) -> rule_analysis_flow.RuleValidationResult:
    return rule_analysis_flow.RuleValidationResult(
        analysis_summary=summary,
        violations=["Use a complete rule sentence."],
    )


def relevant_context_response() -> question_analysis_flow.RelevantContext:
    return question_analysis_flow.RelevantContext(
        analysis_summary="Relevant revenue context.",
        relevant_rules=["Rule #2: Use SUM(orders.revenue) for revenue totals."],
        relevant_descriptions=[
            question_analysis_flow.RelevantDescription(
                type="column", name="orders.revenue", description="Revenue in USD."
            )
        ],
    )


def question_response(summary: str) -> question_analysis_flow.QuestionAnalysis:
    return question_analysis_flow.QuestionAnalysis(
        analysis_summary=summary,
        typos=[],
        dialect_inconsistencies=[],
        contradictions=[],
        duplications=[],
    )


def suggestion_response(summary: str) -> rule_generation_flow.RuleSuggestion:
    return rule_generation_flow.RuleSuggestion(
        analysis_summary=summary,
        suggested_rule="Rule #3: Aggregate revenue with SUM(orders.revenue).",
    )


def upload_context(page, context_files) -> None:
    page.locator("#schema_file").set_input_files(context_files.schema)
    page.locator("#rules_file").set_input_files(context_files.rules)


def submit(page) -> None:
    page.get_by_role("button", name="Run Analysis").click()
    page.wait_for_load_state("networkidle")


def configure_sync_flow(page, flow: str, stage: str) -> None:
    if flow != "rule_analysis":
        page.locator("#flow").select_option(flow)

    if flow == "rule_analysis":
        page.locator("#new_rule").fill(
            f"Rule #9: {stage} revenue with SUM(orders.revenue)."
        )
    elif flow == "question_analysis":
        page.locator("#question").fill(f"Which region has {stage} revenue?")
    else:
        page.locator("#question").fill("Which region has the most revenue?")
        page.locator("#problem").fill(f"Revenue answers {stage} SUM.")


def queue_sync_responses(dispatcher, flow: str, stage: str) -> str:
    if flow == "rule_analysis":
        marker = f"{stage} rule comparison."
        dispatcher.queue(comparison_response(marker), validation_response("validation"))
    elif flow == "question_analysis":
        marker = f"{stage} question comparison."
        dispatcher.queue(relevant_context_response(), question_response(marker))
    else:
        marker = f"{stage} generated rule."
        dispatcher.queue(
            relevant_context_response(),
            suggestion_response(marker),
            comparison_response("comparison"),
            validation_response("validation"),
        )
    return marker


def assert_context_was_saved(page) -> None:
    assert page.locator("#context_id").input_value()
    assert page.locator("#schema_file").input_value() == ""
    assert page.locator("#rules_file").input_value() == ""


def queue_all_rules_responses(dispatcher, stage: str) -> None:
    dispatcher.queue(
        comparison_response(f"{stage} all-rules first comparison."),
        validation_response(f"{stage} all-rules first validation."),
        comparison_response(f"{stage} all-rules second comparison."),
        validation_response(f"{stage} all-rules second validation."),
    )


@pytest.fixture
def uploaded_sync_context(ui_page, context_files, llm_dispatcher, request):
    flow = request.param
    queue_sync_responses(llm_dispatcher, flow, "Initial")
    ui_page.goto("/")
    configure_sync_flow(ui_page, flow, "initial")
    upload_context(ui_page, context_files)
    submit(ui_page)
    assert_context_was_saved(ui_page)
    return ui_page, flow


@pytest.fixture
def uploaded_all_rules_context(ui_page, context_files, llm_dispatcher):
    queue_all_rules_responses(llm_dispatcher, "Initial")
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("all_rules_analysis")
    upload_context(ui_page, context_files)
    submit(ui_page)
    expect(ui_page.locator("#loadingOverlay")).to_be_hidden(timeout=10_000)
    assert_context_was_saved(ui_page)
    return ui_page


def test_home_page_renders_live_analysis_form(ui_page):
    ui_page.goto("/", wait_until="networkidle")

    expect(ui_page.locator("form[data-analysis-form]")).to_be_visible()
    expect(ui_page.locator("#flow")).to_have_value("rule_analysis")
    expect(ui_page.get_by_role("button", name="Run Analysis")).to_be_visible()


@pytest.mark.parametrize(
    "flow", ["rule_analysis", "question_analysis", "rule_generation"]
)
def test_sync_flow_uploads_context_and_renders_analysis(
    ui_page, context_files, llm_dispatcher, flow
):
    marker = queue_sync_responses(llm_dispatcher, flow, "Initial")
    ui_page.goto("/")
    configure_sync_flow(ui_page, flow, "initial")
    upload_context(ui_page, context_files)
    submit(ui_page)

    expect(ui_page.get_by_text(marker)).to_be_visible()
    assert_context_was_saved(ui_page)
    llm_dispatcher.assert_drained()


def test_all_rules_analysis_uploads_context_and_reaches_completed_ui_state(
    ui_page, context_files, llm_dispatcher
):
    queue_all_rules_responses(llm_dispatcher, "Initial")
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("all_rules_analysis")
    upload_context(ui_page, context_files)
    submit(ui_page)

    expect(ui_page.get_by_text("Initial all-rules first comparison.")).to_be_visible(
        timeout=10_000
    )
    expect(ui_page.locator("#page_indicator")).to_have_text("1 / 2", timeout=10_000)
    ui_page.get_by_role("button", name="Next ▶").click()
    expect(ui_page.get_by_text("Initial all-rules second validation.")).to_be_visible(
        timeout=10_000
    )
    expect(ui_page.locator("#loadingOverlay")).to_be_hidden(timeout=10_000)
    assert_context_was_saved(ui_page)
    llm_dispatcher.assert_drained()


@pytest.mark.parametrize(
    "uploaded_sync_context",
    ["rule_analysis", "question_analysis", "rule_generation"],
    indirect=True,
)
def test_sync_flow_reuses_uploaded_context(uploaded_sync_context, llm_dispatcher):
    page, flow = uploaded_sync_context
    marker = queue_sync_responses(llm_dispatcher, flow, "Second")
    configure_sync_flow(page, flow, "second")
    submit(page)

    expect(page.get_by_text(marker)).to_be_visible()
    llm_dispatcher.assert_drained()


def test_all_rules_analysis_reuses_uploaded_context_for_a_rerun(
    uploaded_all_rules_context, llm_dispatcher
):
    queue_all_rules_responses(llm_dispatcher, "Second")
    submit(uploaded_all_rules_context)

    expect(
        uploaded_all_rules_context.get_by_text("Second all-rules first comparison.")
    ).to_be_visible(timeout=10_000)
    expect(uploaded_all_rules_context.locator("#page_indicator")).to_have_text(
        "1 / 2", timeout=10_000
    )
    uploaded_all_rules_context.get_by_role("button", name="Next ▶").click()
    expect(
        uploaded_all_rules_context.get_by_text("Second all-rules second validation.")
    ).to_be_visible(timeout=10_000)
    expect(uploaded_all_rules_context.locator("#loadingOverlay")).to_be_hidden(
        timeout=10_000
    )
    llm_dispatcher.assert_drained()
