"""Translation prompt templates.

Kept free of LiveKit dependencies so prompt behavior can be unit tested.
"""

from __future__ import annotations

from .routing import validate_language

LANGUAGE_NAMES = {
    "bn": "Bengali",
    "en": "English",
}

_PROMPT_TEMPLATE = """\
You are a real-time Bengali-English meeting interpreter.

Translate the speaker's message faithfully from {source_name} into {target_name}.

- If the source is Bengali, output natural, professional English.
- If the source is English, output natural, professional Bengali.
- Preserve names, company names, dates, numbers, amounts, and technical terms.
- Preserve intent, tone, and politeness.
- Do not answer questions or add explanations.
- Return only the translated text.
"""


def language_name(code: str) -> str:
    return LANGUAGE_NAMES[validate_language(code)]


def translation_instructions(source_language: str, target_language: str) -> str:
    """Build the system instructions for a source -> target translation session."""
    return _PROMPT_TEMPLATE.format(
        source_name=language_name(source_language),
        target_name=language_name(target_language),
    )
