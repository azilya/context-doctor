from unittest.mock import Mock

import pytest

from context_doctor import logic


def test_run_analysis_dispatches_rule_analysis(monkeypatch, analysis_context):
    analyze_rule_pipeline = Mock(return_value=("rule-output", "GUIDELINES"))
    monkeypatch.setattr(logic, "analyze_rule_pipeline", analyze_rule_pipeline)

    result = logic.run_analysis(
        logic.AnalysisParams(
            flow="rule_analysis",
            context=analysis_context,
            new_rule=" Rule #9: Use SUM(orders.revenue). ",
        )
    )

    analyze_rule_pipeline.assert_called_once_with(
        "Rule #9: Use SUM(orders.revenue).",
        analysis_context.rules_text,
        analysis_context.sql_dialect,
        analysis_context.schema_description,
    )
    assert result == (
        "rule-output",
        analysis_context.rules_text,
        analysis_context.schema_description,
        "GUIDELINES",
    )


def test_run_analysis_dispatches_question_analysis(monkeypatch, analysis_context):
    filter_and_compare_question = Mock(return_value="question-output")
    monkeypatch.setattr(
        logic, "filter_and_compare_question", filter_and_compare_question
    )

    result = logic.run_analysis(
        logic.AnalysisParams(
            flow="question_analysis",
            context=analysis_context,
            question=" Which region has the most revenue? ",
        )
    )

    filter_and_compare_question.assert_called_once_with(
        "Which region has the most revenue?",
        analysis_context.rules_text,
        analysis_context.sql_dialect,
        analysis_context.schema_description,
    )
    assert result == (
        "question-output",
        analysis_context.rules_text,
        analysis_context.schema_description,
        "",
    )


def test_run_analysis_dispatches_rule_generation_with_optional_question(
    monkeypatch,
    analysis_context,
):
    generate_rule_pipeline = Mock(return_value=("generation-output", "GUIDELINES"))
    monkeypatch.setattr(logic, "generate_rule_pipeline", generate_rule_pipeline)

    result = logic.run_analysis(
        logic.AnalysisParams(
            flow="rule_generation",
            context=analysis_context,
            question=None,
            problem=" Revenue answers use row counts instead of sums. ",
        )
    )

    generate_rule_pipeline.assert_called_once_with(
        analysis_context.rules_text,
        analysis_context.schema_description,
        "",
        "Revenue answers use row counts instead of sums.",
        analysis_context.sql_dialect,
    )
    assert result == (
        "generation-output",
        analysis_context.rules_text,
        analysis_context.schema_description,
        "GUIDELINES",
    )


def test_run_analysis_dispatches_all_rules_analysis(monkeypatch, analysis_context):
    all_rules_pipeline = Mock(return_value=("all-output", "GUIDELINES"))
    monkeypatch.setattr(logic, "all_rules_pipeline", all_rules_pipeline)

    result = logic.run_analysis(
        logic.AnalysisParams(flow="all_rules_analysis", context=analysis_context)
    )

    all_rules_pipeline.assert_called_once_with(
        analysis_context.rules_text,
        analysis_context.sql_dialect,
        analysis_context.schema_description,
    )
    assert result == (
        "all-output",
        analysis_context.rules_text,
        analysis_context.schema_description,
        "GUIDELINES",
    )


@pytest.mark.parametrize(
    ("params", "expected_message"),
    [
        ({"flow": "rule_analysis", "new_rule": None}, "New rule is required"),
        ({"flow": "rule_analysis", "new_rule": "  "}, "New rule is required"),
        ({"flow": "question_analysis", "question": None}, "Question is required"),
        ({"flow": "question_analysis", "question": "  "}, "Question is required"),
        ({"flow": "rule_generation", "problem": None}, "Problem description"),
        ({"flow": "rule_generation", "problem": "  "}, "Problem description"),
        ({"flow": "unknown_flow"}, "Unknown flow: unknown_flow"),
    ],
)
def test_run_analysis_fails_loudly_for_invalid_inputs(
    params,
    expected_message,
    analysis_context,
):
    with pytest.raises(ValueError, match=expected_message):
        logic.run_analysis(logic.AnalysisParams(context=analysis_context, **params))


@pytest.mark.parametrize("empty_output", [None, "", []])
def test_run_analysis_fails_loudly_for_empty_flow_response(
    monkeypatch,
    analysis_context,
    empty_output,
):
    monkeypatch.setattr(
        logic,
        "analyze_rule_pipeline",
        Mock(return_value=(empty_output, "GUIDELINES")),
    )

    with pytest.raises(ValueError, match="rule_analysis returned an empty response"):
        logic.run_analysis(
            logic.AnalysisParams(
                flow="rule_analysis",
                context=analysis_context,
                new_rule="Rule #9: Use SUM(orders.revenue).",
            )
        )
