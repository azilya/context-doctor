"""Browser integration coverage for every Context Doctor analysis flow."""

from __future__ import annotations

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


def test_home_page_renders_live_analysis_form(ui_page):
    ui_page.goto("/", wait_until="networkidle")

    expect(ui_page.locator("form[data-analysis-form]")).to_be_visible()
    expect(ui_page.locator("#flow")).to_have_value("rule_analysis")
    expect(ui_page.get_by_role("button", name="Run Analysis")).to_be_visible()


def test_rule_analysis_uploads_context_and_renders_analysis(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        comparison_response("Initial rule comparison."),
        validation_response("Initial rule validation."),
    )
    ui_page.goto("/")
    ui_page.locator("#new_rule").fill("Rule #9: Use SUM(orders.revenue).")
    upload_context(ui_page, context_files)
    submit(ui_page)

    expect(ui_page.get_by_text("Initial rule comparison.")).to_be_visible()
    expect(ui_page.get_by_text("Initial rule validation.")).to_be_visible()
    llm_dispatcher.assert_drained()


def test_question_analysis_uploads_context_and_renders_analysis(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        relevant_context_response(), question_response("Initial question comparison.")
    )
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("question_analysis")
    ui_page.locator("#question").fill("Which region has the most revenue?")
    upload_context(ui_page, context_files)
    submit(ui_page)

    expect(ui_page.get_by_text("Initial question comparison.")).to_be_visible()
    llm_dispatcher.assert_drained()


def test_rule_generation_uploads_context_and_renders_analysis(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        relevant_context_response(),
        suggestion_response("Initial generated rule."),
        comparison_response("Initial generated comparison."),
        validation_response("Initial generated validation."),
    )
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("rule_generation")
    ui_page.locator("#question").fill("Which region has the most revenue?")
    ui_page.locator("#problem").fill("Revenue answers use row counts.")
    upload_context(ui_page, context_files)
    submit(ui_page)

    expect(ui_page.get_by_text("Initial generated rule.")).to_be_visible()
    expect(ui_page.get_by_text("Initial generated comparison.")).to_be_visible()
    llm_dispatcher.assert_drained()


def test_all_rules_analysis_uploads_context_and_reaches_completed_ui_state(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        comparison_response("Initial all-rules first comparison."),
        validation_response("Initial all-rules first validation."),
        comparison_response("Initial all-rules second comparison."),
        validation_response("Initial all-rules second validation."),
    )
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
    llm_dispatcher.assert_drained()


def test_rule_analysis_reuses_uploaded_context_for_a_new_rule(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        comparison_response("Initial rule comparison."),
        validation_response("Initial rule validation."),
        comparison_response("Second rule comparison."),
        validation_response("Second rule validation."),
    )
    ui_page.goto("/")
    ui_page.locator("#new_rule").fill("Rule #9: Use SUM(orders.revenue).")
    upload_context(ui_page, context_files)
    submit(ui_page)
    context_id = ui_page.locator("#context_id").input_value()

    assert context_id
    assert ui_page.locator("#schema_file").input_value() == ""
    assert ui_page.locator("#rules_file").input_value() == ""
    ui_page.locator("#new_rule").fill("Rule #10: Group revenue by region.")
    submit(ui_page)

    expect(ui_page.get_by_text("Second rule comparison.")).to_be_visible()
    llm_dispatcher.assert_drained()


def test_question_analysis_reuses_uploaded_context_for_a_new_question(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        relevant_context_response(),
        question_response("Initial question comparison."),
        relevant_context_response(),
        question_response("Second question comparison."),
    )
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("question_analysis")
    ui_page.locator("#question").fill("Which region has the most revenue?")
    upload_context(ui_page, context_files)
    submit(ui_page)

    assert ui_page.locator("#context_id").input_value()
    assert ui_page.locator("#schema_file").input_value() == ""
    assert ui_page.locator("#rules_file").input_value() == ""
    ui_page.locator("#question").fill("Which month has the most revenue?")
    submit(ui_page)

    expect(ui_page.get_by_text("Second question comparison.")).to_be_visible()
    llm_dispatcher.assert_drained()


def test_rule_generation_reuses_uploaded_context_for_a_new_problem(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        relevant_context_response(),
        suggestion_response("Initial generated rule."),
        comparison_response("Initial generated comparison."),
        validation_response("Initial generated validation."),
        relevant_context_response(),
        suggestion_response("Second generated rule."),
        comparison_response("Second generated comparison."),
        validation_response("Second generated validation."),
    )
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("rule_generation")
    ui_page.locator("#question").fill("Which region has the most revenue?")
    ui_page.locator("#problem").fill("Revenue answers use row counts.")
    upload_context(ui_page, context_files)
    submit(ui_page)

    assert ui_page.locator("#context_id").input_value()
    assert ui_page.locator("#schema_file").input_value() == ""
    assert ui_page.locator("#rules_file").input_value() == ""
    ui_page.locator("#problem").fill("Revenue answers omit SUM.")
    submit(ui_page)

    expect(ui_page.get_by_text("Second generated rule.")).to_be_visible()
    expect(ui_page.get_by_text("Second generated comparison.")).to_be_visible()
    llm_dispatcher.assert_drained()


def test_all_rules_analysis_reuses_uploaded_context_for_a_rerun(
    ui_page, context_files, llm_dispatcher
):
    llm_dispatcher.queue(
        comparison_response("Initial all-rules first comparison."),
        validation_response("Initial all-rules first validation."),
        comparison_response("Initial all-rules second comparison."),
        validation_response("Initial all-rules second validation."),
        comparison_response("Second all-rules first comparison."),
        validation_response("Second all-rules first validation."),
        comparison_response("Second all-rules second comparison."),
        validation_response("Second all-rules second validation."),
    )
    ui_page.goto("/")
    ui_page.locator("#flow").select_option("all_rules_analysis")
    upload_context(ui_page, context_files)
    submit(ui_page)
    expect(ui_page.locator("#page_indicator")).to_have_text("1 / 2", timeout=10_000)

    assert ui_page.locator("#context_id").input_value()
    assert ui_page.locator("#schema_file").input_value() == ""
    assert ui_page.locator("#rules_file").input_value() == ""
    submit(ui_page)

    expect(ui_page.get_by_text("Second all-rules first comparison.")).to_be_visible(
        timeout=10_000
    )
    expect(ui_page.locator("#page_indicator")).to_have_text("1 / 2", timeout=10_000)
    ui_page.get_by_role("button", name="Next ▶").click()
    expect(ui_page.get_by_text("Second all-rules second validation.")).to_be_visible(
        timeout=10_000
    )
    expect(ui_page.locator("#loadingOverlay")).to_be_hidden(timeout=10_000)
    llm_dispatcher.assert_drained()
