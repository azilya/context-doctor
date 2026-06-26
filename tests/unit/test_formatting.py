from unittest.mock import Mock

from context_doctor import (
    question_analysis_flow,
    rule_analysis_flow,
    rule_generation_flow,
)
from context_doctor.utils import prettify_html


def details_by_category(rows):
    return {row["Category"]: row["Details"] for row in rows}


def categories(rows):
    return [row["Category"] for row in rows]


def test_rule_analysis_format_comparison_response_joins_nested_fields(
    accept_new_rule_response,
):
    formatted = rule_analysis_flow.format_comparison_response(accept_new_rule_response)

    assert formatted["typos"] == "revnue should be revenue"
    assert formatted["dialect_inconsistencies"] == "Use DATE_TRUNC for PostgreSQL."
    assert formatted["contradictions_explained"] == (
        "Conflicts with an existing revenue rule."
    )
    assert formatted["contradictions_with_rules"] == "2, 4"
    assert formatted["contradictions_with_schema"] == "orders.revenue, customers.region"
    assert formatted["comparison_analysis_summary"] == (
        "The new rule overlaps with revenue guidance."
    )
    assert "contradictions" not in formatted
    assert "analysis_summary" not in formatted


def test_rule_analysis_beautify_result_has_stable_category_order():
    result = {
        "comparison_analysis_summary": "Comparison summary",
        "new_rule": "Rule #9",
        "guideline_analysis_summary": "Guideline summary",
        "typos": "",
        "dialect_inconsistencies": "",
        "contradictions_explained": "",
        "contradictions_with_rules": "",
        "contradictions_with_schema": "",
        "duplications_explained": "Duplicate",
        "duplications_with_rules": "2",
        "duplications_with_schema": "orders.revenue",
        "guideline_violations": "",
    }

    rows = rule_analysis_flow.beautify_result(result)

    assert categories(rows) == [
        "new_rule",
        "typos",
        "dialect_inconsistencies",
        "contradictions_explained",
        "contradictions_with_rules",
        "contradictions_with_schema",
        "duplications_explained",
        "duplications_with_rules",
        "duplications_with_schema",
        "guideline_violations",
        "comparison_analysis_summary",
        "guideline_analysis_summary",
    ]
    assert details_by_category(rows)["duplications_explained"] == "Duplicate"


def test_question_formatting_joins_lists_and_descriptions(
    relevant_context_response,
    question_analysis_response,
):
    filtering_result = question_analysis_flow.format_filtering_result(
        relevant_context_response
    )
    comparison_result = question_analysis_flow.format_comparison_response(
        question_analysis_response
    )

    assert filtering_result["relevant_rules"] == "Rule #2: Use SUM(orders.revenue)."
    assert filtering_result["relevant_descriptions"] == (
        "- Type: column, Name: orders.revenue, Description: Order revenue in USD."
    )
    assert filtering_result["filtering_analysis_summary"] == (
        "Revenue rules and columns are relevant."
    )
    assert comparison_result["typos"] == "#1: custmer should be customer"
    assert comparison_result["contradictions"] == "Rule #1 conflicts with the schema."
    assert comparison_result["duplications"] == (
        "Rule #2 repeats the revenue column description."
    )
    assert comparison_result["comparison_analysis_summary"] == (
        "The filtered rules answer the question."
    )


def test_question_beautify_result_has_stable_category_order():
    rows = question_analysis_flow.beautify_result({
        "comparison_analysis_summary": "Comparison summary",
        "filtering_analysis_summary": "Filtering summary",
        "question": "Question?",
        "relevant_rules": "Rule #2",
        "relevant_descriptions": "orders.revenue",
        "typos": "",
        "dialect_inconsistencies": "",
        "contradictions": "",
        "duplications": "",
    })

    assert categories(rows) == [
        "question",
        "relevant_rules",
        "relevant_descriptions",
        "typos",
        "dialect_inconsistencies",
        "contradictions",
        "duplications",
        "filtering_analysis_summary",
        "comparison_analysis_summary",
    ]


def test_rule_generation_pipeline_reorders_generation_summary(
    monkeypatch,
    rule_suggestion_response,
    analysis_context,
):
    base_rule_eval = [
        {"Category": "new_rule", "Details": rule_suggestion_response.suggested_rule},
        {"Category": "typos", "Details": ""},
        {"Category": "dialect_inconsistencies", "Details": ""},
        {"Category": "contradictions_explained", "Details": ""},
        {"Category": "contradictions_with_rules", "Details": ""},
        {"Category": "contradictions_with_schema", "Details": ""},
        {"Category": "duplications_explained", "Details": ""},
        {"Category": "duplications_with_rules", "Details": ""},
        {"Category": "duplications_with_schema", "Details": ""},
        {"Category": "guideline_violations", "Details": ""},
        {"Category": "comparison_analysis_summary", "Details": "Comparison summary"},
        {"Category": "guideline_analysis_summary", "Details": "Guideline summary"},
    ]
    generate_rule_suggestion = Mock(return_value=rule_suggestion_response)
    analyze_rule_pipeline = Mock(return_value=(base_rule_eval, "GUIDELINES"))
    monkeypatch.setattr(
        rule_generation_flow, "generate_rule_suggestion", generate_rule_suggestion
    )
    monkeypatch.setattr(
        rule_generation_flow, "analyze_rule_pipeline", analyze_rule_pipeline
    )

    rows, guidelines = rule_generation_flow.generate_rule_pipeline(
        analysis_context.rules_text,
        analysis_context.schema_description,
        "",
        "Revenue answers use row counts instead of sums.",
        analysis_context.sql_dialect,
    )

    assert guidelines == "GUIDELINES"
    assert categories(rows) == [
        "new_rule",
        "typos",
        "dialect_inconsistencies",
        "contradictions_explained",
        "contradictions_with_rules",
        "contradictions_with_schema",
        "duplications_explained",
        "duplications_with_rules",
        "duplications_with_schema",
        "guideline_violations",
        "generation_analysis_summary",
        "comparison_analysis_summary",
        "guideline_analysis_summary",
    ]
    assert details_by_category(rows)["generation_analysis_summary"] == (
        "A revenue aggregation rule solves the problem."
    )
    generate_rule_suggestion.assert_called_once_with(
        analysis_context.rules_text,
        analysis_context.schema_description,
        analysis_context.sql_dialect,
        "",
        "Revenue answers use row counts instead of sums.",
    )
    analyze_rule_pipeline.assert_called_once_with(
        rule_suggestion_response.suggested_rule,
        analysis_context.rules_text,
        analysis_context.sql_dialect,
        analysis_context.schema_description,
    )


def test_prettify_html_escapes_values_and_preserves_newlines():
    html = prettify_html([
        {"Category": "new_rule", "Details": "<script>x</script>\nnext"},
    ])

    assert '<table class="analysis-result-table">' in html
    assert "border=" not in html
    assert "<th>Category</th>" in html
    assert "<td>New Rule</td>" in html
    assert "&lt;script&gt;x&lt;/script&gt;<br>next" in html
