import logging

from pydantic import BaseModel, Field

from .question_analysis_flow import (
    filter_relevant_rules_and_descriptions,
)
from .llm_client import parse_response
from .package_resources import read_prompt_steps
from .rule_analysis_flow import analyze_rule_pipeline, guidelines


class RuleSuggestion(BaseModel):
    analysis_summary: str = Field(
        description="Structured analysis summary for solving the problem based on the provided context."
    )
    suggested_rule: str = Field(
        description="The newly suggested rule, following the provided <Rule Formatting Guidelines> format"
    )


rule_generation_prompt = read_prompt_steps("prompt_template_rule_generation.yaml")


def generate_rule_suggestion(
    rules, descriptions, dialect, question, problem, feedback=None
):
    messages = []
    for i, val in enumerate(rule_generation_prompt):
        messages.append(
            {
                "role": val["role"],
                "content": val["content"].format(
                    rules=rules,
                    descriptions=descriptions,
                    dialect=dialect,
                    question=question,
                    problem=problem,
                    guidelines=guidelines,
                ),
            }
        )
    # if feedback and isinstance(feedback, pd.DataFrame):
    #     messages.append(
    #         {
    #             "role": "user",
    #             "content": f"Here is your previous suggestion and feedback on it:\n{feedback.to_markdown(index=False)}",
    #         }
    #     )
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
    rule_eval.loc[len(rule_eval)] = [
        "generation_analysis_summary",
        rule_suggestion.analysis_summary,
    ]
    rule_eval = (
        rule_eval.set_index("Category")
        .reindex(
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
            ]
        )
        .reset_index()
    )

    return rule_eval, guidelines
