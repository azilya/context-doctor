import logging

from pydantic import BaseModel

from .context_store import AnalysisContext
from .question_analysis_flow import filter_and_compare_question
from .rule_analysis_flow import (
    all_rules_pipeline,
    analyze_rule_pipeline,
)
from .rule_generation_flow import generate_rule_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="{asctime} - {levelname:>8} - {module} - {message}",
    style="{",
)


class AnalysisParams(BaseModel):
    flow: str
    context: AnalysisContext
    new_rule: str | None = None
    question: str | None = None
    problem: str | None = None


def run_analysis(params: AnalysisParams):
    logging.info("Preparing uploaded context...")
    schema_description = params.context.schema_description
    sql_dialect = params.context.sql_dialect
    rules = params.context.rules_text
    logging.info(f"Context prepared, SQL dialect: {sql_dialect}")

    if params.flow == "rule_analysis":
        logging.info("Using single rule analysis flow")
        if not params.new_rule:
            raise ValueError("New rule is required for rule_analysis flow")
        new_rule = params.new_rule.strip()
        analysis_output, guidelines_text = analyze_rule_pipeline(
            new_rule, rules, sql_dialect, schema_description
        )
        logging.info("Rule analyzed")
        logging.info(f"{analysis_output}")
    elif params.flow == "all_rules_analysis":
        logging.info("Using all rules analysis flow")
        analysis_output, guidelines_text = all_rules_pipeline(
            rules, sql_dialect, schema_description
        )
        logging.info("All rules analyzed")
        logging.info(f"{analysis_output}"[:1000])
    elif params.flow == "question_analysis":
        logging.info("Using question analysis flow")
        if not params.question:
            raise ValueError("Question is required for question_analysis flow")
        question = params.question.strip()
        analysis_output = filter_and_compare_question(
            question, rules, sql_dialect, schema_description
        )
        guidelines_text = ""
        logging.info("Questions analyzed")
        logging.info(f"{analysis_output}")
    elif params.flow == "rule_generation":
        logging.info("Using rule generation flow")
        if not params.problem:
            raise ValueError("Problem description is required for rule_generation flow")
        # question is optional in the form; default to empty string if not provided
        question = params.question.strip() if params.question else ""
        problem = params.problem.strip()
        analysis_output, guidelines = generate_rule_pipeline(
            rules, schema_description, question, problem, sql_dialect
        )
        guidelines_text = guidelines
        logging.info("Rule generated")
        logging.info(f"{analysis_output}")
    else:
        raise ValueError(f"Unknown flow: {params.flow}")

    # Return the analysis output along with the downloaded rules and schema description
    # and guidelines_text (empty string for flows that don't provide it)
    return analysis_output, rules, schema_description, guidelines_text
