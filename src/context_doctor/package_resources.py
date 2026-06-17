"""Package-relative resource loading helpers."""

from importlib import resources

import yaml


def read_text(package: str, name: str) -> str:
    return resources.files(package).joinpath(name).read_text()


def read_prompt_steps(name: str) -> list[dict]:
    return yaml.safe_load(read_text("context_doctor.prompts", name))["prompt_steps"]


def render_prompt_messages(prompt: list[dict], **values) -> list[dict]:
    return [
        {"role": step["role"], "content": step["content"].format(**values)}
        for step in prompt
    ]
