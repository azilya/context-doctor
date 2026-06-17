from pydantic import BaseModel, Field

from .llm_client import parse_response
from .package_resources import read_prompt_steps, render_prompt_messages
from .utils import ordered_rows


class QuestionAnalysis(BaseModel):
    analysis_summary: str = Field(
        description="Overall analysis summary across all categories for validating the <Existing Rules> and <Schema Descriptions>."
    )
    typos: list[str] = Field(
        description="Typos in the texts of <Existing Rules> and incorrectly spelled table and column names."
        'Format: "#{rule_number}: {incorrect} should be {correct}". Empty list if none found.'
    )
    dialect_inconsistencies: list[str] = Field(
        description="Requirements and features of the <Database SQL Dialect> that SQL samples, used in the <Existing Rules>, don't follow."
        "Empty if none found or rules have no SQL samples."
    )
    contradictions: list[str] = Field(
        description="Contradictions within <Existing Rules> and <Schema Descriptions>."
        "Empty if none are present."
    )
    duplications: list[str] = Field(
        description="<Existing Rules> and <Schema Descriptions> repeating or rephrasing information."
        "Empty if none are present."
    )


class RelevantDescription(BaseModel):
    type: str = Field(
        description="Type of the database object. One of: 'application', 'table' or 'column'."
    )
    name: str = Field(
        description="Name of the database object (table or column). Empty if `type` is 'application'."
    )
    description: str = Field(
        description="Full provided description of the database object."
    )


class RelevantContext(BaseModel):
    analysis_summary: str = Field(
        description="Overall analysis for selecting relevant rules and descriptions."
    )
    relevant_rules: list[str] = Field(
        description="List of rules relevant to the User Question. Each entry should include the rule number and full text of the rule."
    )
    relevant_descriptions: list[RelevantDescription] = Field(
        description="List of schema descriptions relevant to the User Question."
    )


conflict_detection_prompt = read_prompt_steps(
    "prompt_template_question_comparison.yaml"
)
filter_context_prompt = read_prompt_steps("prompt_template_question_filtering.yaml")


def filter_relevant_rules_and_descriptions(rules, descriptions, question):
    messages = render_prompt_messages(
        filter_context_prompt,
        rules=rules,
        descriptions=descriptions,
        question=question,
    )
    return parse_response(messages, RelevantContext)


def compare_rules_and_descriptions(rules, dialect, descriptions, new_rule):
    messages = render_prompt_messages(
        conflict_detection_prompt,
        list_of_rules=rules,
        db_dialect=dialect,
        schema_descriptions=descriptions,
        new_rule=new_rule,
    )
    return parse_response(messages, QuestionAnalysis)


def format_comparison_response(response) -> dict:
    response_df = response.model_dump()
    response_df["typos"] = ", ".join(response_df["typos"])
    for cat in ["contradictions", "duplications", "dialect_inconsistencies"]:
        response_df[cat] = "\n".join(response_df[cat])
    response_df["comparison_analysis_summary"] = response_df.pop("analysis_summary")
    return response_df


def filter_and_compare_question(question, rules, dialect, descriptions):
    filter_result = filter_relevant_rules_and_descriptions(
        rules, descriptions, question
    )

    result = format_filtering_result(filter_result)
    result["question"] = question

    relevant_rules = result["relevant_rules"]
    relevant_descriptions = filter_result.relevant_descriptions

    comparison_result = compare_rules_and_descriptions(
        relevant_rules, dialect, relevant_descriptions, question
    )
    formatted_comparison = format_comparison_response(comparison_result)
    result.update(formatted_comparison)
    result_df = beautify_result(result)
    return result_df


def beautify_result(result) -> list[dict[str, str]]:
    return ordered_rows(
        result,
        [
            "question",
            "relevant_rules",
            "relevant_descriptions",
            "typos",
            "dialect_inconsistencies",
            "contradictions",
            "duplications",
            "filtering_analysis_summary",
            "comparison_analysis_summary",
        ],
    )


def format_filtering_result(filter_result):
    result = filter_result.model_dump()
    result["relevant_rules"] = "\n".join(filter_result.relevant_rules)
    result["relevant_descriptions"] = "\n".join(
        f"- Type: {desc.type}, Name: {desc.name}, Description: {desc.description.replace('\n', ' ')}"
        for desc in filter_result.relevant_descriptions
    )
    result["filtering_analysis_summary"] = result.pop("analysis_summary")
    return result
