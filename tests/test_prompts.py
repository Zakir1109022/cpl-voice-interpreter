"""Translation prompt behavior tests."""

from __future__ import annotations

import pytest

from agent.prompts import translation_instructions
from agent.routing import UnsupportedLanguageError

REQUIRED_PHRASES = [
    "real-time Bengali-English meeting interpreter",
    "Preserve names, company names, dates, numbers, amounts, and technical terms",
    "Preserve intent, tone, and politeness",
    "Do not answer questions or add explanations",
    "Return only the translated text",
    "faithfully",
]


class TestTranslationInstructions:
    @pytest.mark.parametrize(
        ("source", "target"),
        [("bn", "en"), ("en", "bn")],
    )
    def test_contains_interpreter_contract(self, source: str, target: str) -> None:
        prompt = translation_instructions(source, target)
        for phrase in REQUIRED_PHRASES:
            assert phrase in prompt, f"missing {phrase!r} in {source}->{target} prompt"

    @pytest.mark.parametrize(
        ("source", "target", "source_name", "target_name"),
        [
            ("bn", "en", "Bengali", "English"),
            ("en", "bn", "English", "Bengali"),
        ],
    )
    def test_names_source_and_target_languages(
        self, source: str, target: str, source_name: str, target_name: str
    ) -> None:
        prompt = translation_instructions(source, target)
        assert f"from {source_name} into {target_name}" in prompt

    def test_direction_prompts_differ(self) -> None:
        bn_to_en = translation_instructions("bn", "en")
        en_to_bn = translation_instructions("en", "bn")
        assert bn_to_en != en_to_bn
        assert "from Bengali into English" in bn_to_en
        assert "from English into Bengali" in en_to_bn

    @pytest.mark.parametrize("bad", ["fr", "xx", ""])
    def test_invalid_language_rejected(self, bad: str) -> None:
        with pytest.raises(UnsupportedLanguageError):
            translation_instructions(bad, "en")

    def test_prompt_directs_translation_only_no_answers(self) -> None:
        prompt = translation_instructions("en", "bn")
        assert "Do not answer questions" in prompt
        assert "only the translated text" in prompt
