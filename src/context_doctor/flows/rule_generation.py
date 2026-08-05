import logging

from pydantic import BaseModel, Field

from .question_analysis import (
    filter_relevant_rules_and_descriptions,
)
from ..llm_client import parse_response
from ..package_resources import read_prompt_steps, render_prompt_messages
from ..utils import details_by_category, ordered_rows
from .rule_analysis import analyze_rule_pipeline, guidelines


class RuleSuggestion(BaseModel):
    analysis_summary: str = Field(
        description="Structured analysis summary for solving the problem based on the provided context."
    )
    suggested_rule: str = Field(
        description="The newly suggested rule, following the provided <Rule Formatting Guidelines> format"
    )


rule_generation_prompt = read_prompt_steps("prompt_template_rule_generation.yaml")


def generate_rule_suggestion(rules, descriptions, dialect, question, problem):
    messages = render_prompt_messages(
        rule_generation_prompt,
        rules=rules,
        descriptions=descriptions,
        dialect=dialect,
        question=question,
        problem=problem,
        guidelines=guidelines,
    )
    return parse_response(messages, RuleSuggestion)


def generate_rule_pipeline(rules, descriptions, question, problem, dialect):
    # filter context
    if question.strip() != "":
        filtered_context = filter_relevant_rules_and_descriptions(
            rules, descriptions, question
        )
        filtered_descriptions = filtered_context.relevant_descriptions
    else:
        filtered_descriptions = descriptions
    logging.info(
        f"Filtered descriptions for question '{question}': {filtered_descriptions}"
    )

    # generate rule
    rule_suggestion = generate_rule_suggestion(
        rules, filtered_descriptions, dialect, question, problem
    )
    logging.info(f"Suggestion for '{question}': {rule_suggestion}")

    # evaluate the generated rule
    rule_eval, guidelines = analyze_rule_pipeline(
        rule_suggestion.suggested_rule, rules, dialect, descriptions
    )

    # add generation analysis summary to final result and reorder
    result = details_by_category(rule_eval)
    result["generation_analysis_summary"] = rule_suggestion.analysis_summary
    rule_eval = ordered_rows(
        result,
        [
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
        ],
    )

    return rule_eval, guidelines
