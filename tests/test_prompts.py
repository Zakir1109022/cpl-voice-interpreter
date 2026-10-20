"""Translation prompt behavior tests."""

from __future__ import annotations

import pytest

from agent.prompts import translation_instructions
from agent.routing import LANGUAGE_PAIRS, UnsupportedLanguageError

REQUIRED_PHRASES = [
    "real-time meeting interpreter",
    "Preserve names, company names, dates, numbers, amounts, and technical terms",
    "Preserve intent, tone, and politeness",
    "Do not answer questions or add explanations",
    "Return only the translated text",
    "faithfully",
]

DIRECTIONS = [
    (pair, source, pair.partner(source))
    for pair in LANGUAGE_PAIRS.values()
    for source in pair.languages
]


class TestTranslationInstructions:
    @pytest.mark.parametrize(("pair", "source", "target"), DIRECTIONS)
    def test_contains_interpreter_contract(
        self, pair: object, source: str, target: str
    ) -> None:
        prompt = translation_instructions(source, target)
        for phrase in REQUIRED_PHRASES:
            assert phrase in prompt, f"missing {phrase!r} in {source}->{target} prompt"

    @pytest.mark.parametrize(
        ("source", "target", "source_name", "target_name"),
        [
            ("bn", "en", "Bengali", "English"),
            ("en", "bn", "English", "Bengali"),
            ("bn", "ja", "Bengali", "Japanese"),
            ("ja", "bn", "Japanese", "Bengali"),
            ("en", "ja", "English", "Japanese"),
            ("ja", "en", "Japanese", "English"),
        ],
    )
    def test_names_source_and_target_languages(
        self, source: str, target: str, source_name: str, target_name: str
    ) -> None:
        prompt = translation_instructions(source, target)
        assert f"from {source_name} into {target_name}" in prompt
        assert f"professional {target_name}" in prompt

    @pytest.mark.parametrize(
        ("source", "target"),
        [("bn", "en"), ("bn", "ja"), ("ja", "bn"), ("en", "bn"), ("en", "ja"), ("ja", "en")],
    )
    def test_direction_prompts_differ(self, source: str, target: str) -> None:
        assert translation_instructions(source, target) != translation_instructions(target, source)

    def test_is_language_agnostic(self) -> None:
        # The prompt must not hardcode a single pair.
        assert "Bengali-English" not in translation_instructions("bn", "en")

    @pytest.mark.parametrize("bad", ["fr", "xx", ""])
    def test_invalid_language_rejected(self, bad: str) -> None:
        with pytest.raises(UnsupportedLanguageError):
            translation_instructions(bad, "en")

    def test_prompt_directs_translation_only_no_answers(self) -> None:
        prompt = translation_instructions("en", "bn")
        assert "Do not answer questions" in prompt
        assert "only the translated text" in prompt
