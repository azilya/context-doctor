import logging
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from pydantic import BaseModel, Field

from . import settings
from .llm_client import parse_response
from .package_resources import read_prompt_steps, read_text


class CategoryResult(BaseModel):
    explanation: str = Field(
        description="1-sentence explanation of why this category applies. Empty string if not applicable."
    )
    matched_rules: list[int] = Field(
        description="Rule numbers affected by the New Rule for this category, ordered by relevance. Empty if none or in case of typos."
    )
    matched_from_schema: list[str] = Field(
        description="Schema Description elements affected by the New Rule for this category, ordered by relevance. Empty if none or in case of typos."
    )


class AcceptNewRule(BaseModel):
    analysis_summary: str = Field(
        description="Overall analysis summary across all categories for validating the <New Rule>."
    )
    typos: list[str] = Field(
        description="Typos in the text of the <New Rule> and incorrectly spelled table and column names."
        'Format: "{incorrect} should be {correct}". Empty list if none found.'
    )
    dialect_inconsistencies: list[str] = Field(
        description="Requirements and features of the <Database SQL Dialect> that SQL samples, used in the rule, don't follow."
        "Empty if none found or rule has no SQL samples."
    )
    contradictions: CategoryResult = Field(
        description="Contradictions between the <New Rule> and <Existing Rules> or <Schema Descriptions>. "
        "Empty if none are present."
    )
    duplications: CategoryResult = Field(
        description="Duplications or reformulations of <Existing Rules> or <Schema Descriptions>. "
        "Empty if none are present."
    )


class RuleValidationResult(BaseModel):
    analysis_summary: str = Field(
        description="Analysis summary for your decision, referencing relevant Guidelines sections"
    )
    violations: list[str] = Field(
        description="List of specific requirements from the Rule Writing Guidelines that the New Rule does not follow. Empty list if none."
    )


conflict_detection_prompt = read_prompt_steps("prompt_template_rule_comparison.yaml")
validation_prompt = read_prompt_steps("prompt_template_rule_validation.yaml")
guidelines = read_text("context_doctor.guidelines", "guidelines.md")


def compare_rules_and_descriptions(rules, dialect, descriptions, new_rule):
    messages = []
    for i, val in enumerate(conflict_detection_prompt):
        messages.append({
            "role": val["role"],
            "content": val["content"].format(
                list_of_rules=rules,
                db_dialect=dialect,
                schema_descriptions=descriptions,
                new_rule=new_rule,
            ),
        })
    return parse_response(messages, AcceptNewRule)


def validate_rule_writing_guidelines(new_rule, guidelines=guidelines):
    messages = []
    for i, val in enumerate(validation_prompt):
        messages.append({
            "role": val["role"],
            "content": val["content"].format(
                guidelines=guidelines,
                new_rule=new_rule,
            ),
        })
    response = parse_response(messages, RuleValidationResult).model_dump()
    response["violations"] = "\n".join(response["violations"])
    response["new_rule"] = new_rule
    return response


def compare_one_rule_for_run(rules, dialect, descriptions, new_rule, i):
    response = compare_rules_and_descriptions(
        rules,
        dialect,
        descriptions,
        new_rule,
    )
    response_df = format_comparison_response(response)
    response_df["run"] = i
    response_df["new_rule"] = new_rule
    return response_df


def format_comparison_response(response):
    response_df = response.model_dump()
    response_df["typos"] = ", ".join(response_df["typos"])
    response_df["dialect_inconsistencies"] = "\n".join(
        response_df["dialect_inconsistencies"]
    )
    for cat in [
        "contradictions",
        "duplications",
    ]:
        response_df[f"{cat}_explained"] = response_df[cat]["explanation"]
        response_df[f"{cat}_with_rules"] = ", ".join(
            map(str, response_df[cat]["matched_rules"])
        )
        response_df[f"{cat}_with_schema"] = ", ".join(
            response_df[cat]["matched_from_schema"]
        )
        del response_df[cat]
    response_df["comparison_analysis_summary"] = response_df.pop("analysis_summary")
    return response_df


def analyze_rule_pipeline(
    new_rule, rules, dialect, descriptions, guidelines=guidelines
):
    first_step = compare_rules_and_descriptions(rules, dialect, descriptions, new_rule)
    final_response = format_comparison_response(first_step)
    second_step = validate_rule_writing_guidelines(new_rule, guidelines)
    second_step["guideline_violations"] = second_step.pop("violations")
    second_step["guideline_analysis_summary"] = second_step.pop("analysis_summary")
    final_response.update(second_step)
    final_response["new_rule"] = new_rule
    final_response_df = beautify_result(final_response)
    # Also return the guidelines text so callers can display it in the UI
    return final_response_df, guidelines


def analyze_single_rule_pipeline(
    new_rule, rules_lst, dialect, descriptions, guidelines=guidelines
):
    rules_lst_cp = rules_lst.copy()
    rules_lst_cp.remove(new_rule)
    rules = "\n".join(rules_lst_cp)
    response, _ = analyze_rule_pipeline(
        new_rule, rules, dialect, descriptions, guidelines
    )
    return response


def all_rules_pipeline(rules, dialect, descriptions, guidelines=guidelines):
    rules_lst = re.split("(^|\n)Rule #", rules)
    rules_lst = ["Rule #" + r for r in rules_lst if len(r) > 1]

    with ThreadPoolExecutor(
        max_workers=settings.MAX_CONCURRENT_RULE_ANALYSES
    ) as executor:
        responses = list(
            executor.map(
                analyze_single_rule_pipeline,
                rules_lst,
                [rules_lst] * len(rules),
                [dialect] * len(rules),
                [descriptions] * len(rules),
            ),
        )
    logging.info(responses[0])
    filtered_responses = [
        df
        for df in responses
        if not all(
            df.set_index("Category").loc[c, "Details"] == ""
            for c in [
                "typos",
                "dialect_inconsistencies",
                "contradictions_explained",
                "contradictions_with_rules",
                "contradictions_with_schema",
                "duplications_explained",
                "duplications_with_rules",
                "duplications_with_schema",
                "guideline_violations",
            ]
        )
    ]
    logging.info(f"Filtered out {len(responses) - len(filtered_responses)} rules")
    for df in filtered_responses:
        df.loc[0, "Category"] = "analyzed_rule"
    return filtered_responses, guidelines


def beautify_result(result) -> pd.DataFrame:
    beautified = [(k, v) for k, v in result.items()]
    b_df = pd.DataFrame(beautified, columns=["Category", "Details"])
    b_df = (
        b_df
        .set_index("Category")
        .reindex([
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
        ])
        .reset_index()
    )
    return b_df
