from context_doctor.flows import (
    question_analysis as question_analysis_flow,
    rule_analysis as rule_analysis_flow,
    rule_generation as rule_generation_flow,
)


def rendered_prompt_content(call):
    return "\n".join(message["content"] for message in call["messages"])


def assert_prompt_mentions(prompt_content, *expected_fragments):
    missing_fragments = [
        fragment for fragment in expected_fragments if fragment not in prompt_content
    ]
    assert not missing_fragments, f"Prompt omitted: {missing_fragments}"


def test_rule_analysis_comparison_prompt_receives_uploaded_context(
    monkeypatch,
    parse_response_recorder,
    accept_new_rule_response,
    analysis_context,
):
    recorder = parse_response_recorder(accept_new_rule_response)
    monkeypatch.setattr(rule_analysis_flow, "parse_response", recorder)

    response = rule_analysis_flow.compare_rules_and_descriptions(
        analysis_context.rules_text,
        analysis_context.sql_dialect,
        analysis_context.schema_description,
        "Rule #9: Use SUM(orders.revenue).",
    )

    prompt_content = rendered_prompt_content(recorder.only_call())
    assert response == accept_new_rule_response
    assert_prompt_mentions(
        prompt_content,
        analysis_context.rules_text,
        analysis_context.sql_dialect,
        "orders",
        "Order revenue in USD.",
        "Rule #9: Use SUM(orders.revenue).",
    )


def test_rule_validation_prompt_receives_guidelines_and_new_rule(
    monkeypatch,
    parse_response_recorder,
):
    validation_response = rule_analysis_flow.RuleValidationResult(
        analysis_summary="The rule follows the structure.",
        violations=["Missing examples", "Too broad"],
    )
    recorder = parse_response_recorder(validation_response)
    monkeypatch.setattr(rule_analysis_flow, "parse_response", recorder)

    result = rule_analysis_flow.validate_rule_writing_guidelines(
        "Rule #9: Use SUM(orders.revenue).",
        guidelines="GUIDELINE TEXT",
    )

    prompt_content = rendered_prompt_content(recorder.only_call())
    assert result["violations"] == "Missing examples\nToo broad"
    assert result["new_rule"] == "Rule #9: Use SUM(orders.revenue)."
    assert_prompt_mentions(
        prompt_content,
        "GUIDELINE TEXT",
        "Rule #9: Use SUM(orders.revenue).",
    )


def test_question_filtering_prompt_receives_question_rules_and_schema(
    monkeypatch,
    parse_response_recorder,
    relevant_context_response,
    analysis_context,
):
    recorder = parse_response_recorder(relevant_context_response)
    monkeypatch.setattr(question_analysis_flow, "parse_response", recorder)

    question_analysis_flow.filter_relevant_rules_and_descriptions(
        analysis_context.rules_text,
        analysis_context.schema_description,
        "Which region has the most revenue?",
    )

    prompt_content = rendered_prompt_content(recorder.only_call())
    assert_prompt_mentions(
        prompt_content,
        analysis_context.rules_text,
        "orders",
        "Which region has the most revenue?",
    )


def test_question_comparison_prompt_receives_filtered_context_and_dialect(
    monkeypatch,
    parse_response_recorder,
    question_analysis_response,
    relevant_description,
):
    recorder = parse_response_recorder(question_analysis_response)
    monkeypatch.setattr(question_analysis_flow, "parse_response", recorder)

    question_analysis_flow.compare_rules_and_descriptions(
        "Rule #2: Use SUM(orders.revenue).",
        "PostgreSQL",
        [relevant_description],
        "Which region has the most revenue?",
    )

    prompt_content = rendered_prompt_content(recorder.only_call())
    assert_prompt_mentions(
        prompt_content,
        "Rule #2: Use SUM(orders.revenue).",
        "PostgreSQL",
        "orders.revenue",
    )


def test_rule_generation_prompt_receives_problem_question_guidelines_and_context(
    monkeypatch,
    parse_response_recorder,
    rule_suggestion_response,
    analysis_context,
):
    recorder = parse_response_recorder(rule_suggestion_response)
    monkeypatch.setattr(rule_generation_flow, "parse_response", recorder)
    monkeypatch.setattr(rule_generation_flow, "guidelines", "GUIDELINE TEXT")

    rule_generation_flow.generate_rule_suggestion(
        analysis_context.rules_text,
        analysis_context.schema_description,
        analysis_context.sql_dialect,
        "Which region has the most revenue?",
        "Revenue answers use row counts instead of sums.",
    )

    prompt_content = rendered_prompt_content(recorder.only_call())
    assert_prompt_mentions(
        prompt_content,
        analysis_context.rules_text,
        "orders",
        analysis_context.sql_dialect,
        "Which region has the most revenue?",
        "Revenue answers use row counts instead of sums.",
        "GUIDELINE TEXT",
    )
