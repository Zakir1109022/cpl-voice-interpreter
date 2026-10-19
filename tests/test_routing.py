"""Language validation and direction routing tests."""

from __future__ import annotations

import pytest

from agent.routing import (
    UnsupportedLanguageError,
    target_language,
    target_language_from_track_name,
    track_name_for,
    validate_language,
)


class TestValidateLanguage:
    def test_accepts_bengali(self) -> None:
        assert validate_language("bn") == "bn"

    def test_accepts_english(self) -> None:
        assert validate_language("en") == "en"

    def test_normalizes_case_and_whitespace(self) -> None:
        assert validate_language("  BN ") == "bn"
        assert validate_language("En") == "en"

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_rejects_missing_language(self, bad: str | None) -> None:
        with pytest.raises(UnsupportedLanguageError, match="required"):
            validate_language(bad)

    @pytest.mark.parametrize("bad", ["fr", "hi", "bn-IN", "english", "1"])
    def test_rejects_unsupported_language(self, bad: str) -> None:
        with pytest.raises(UnsupportedLanguageError, match="Unsupported"):
            validate_language(bad)

    def test_error_lists_supported_languages(self) -> None:
        with pytest.raises(UnsupportedLanguageError) as exc:
            validate_language("xx")
        message = str(exc.value)
        assert "bn" in message and "en" in message


class TestTargetLanguage:
    def test_bengali_source_targets_english(self) -> None:
        assert target_language("bn") == "en"

    def test_english_source_targets_bengali(self) -> None:
        assert target_language("en") == "bn"

    def test_both_directions_are_crossed(self) -> None:
        for source in ("bn", "en"):
            assert target_language(source) != source

    @pytest.mark.parametrize("bad", ["fr", None, ""])
    def test_invalid_source_is_rejected(self, bad: str | None) -> None:
        with pytest.raises(UnsupportedLanguageError):
            target_language(bad)  # type: ignore[arg-type]


class TestTrackNames:
    def test_track_name_for_target(self) -> None:
        assert track_name_for("en") == "translated-en"
        assert track_name_for("bn") == "translated-bn"

    def test_invalid_target_rejected(self) -> None:
        with pytest.raises(UnsupportedLanguageError):
            track_name_for("fr")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("translated-en", "en"),
            ("translated-bn", "bn"),
            ("translated-fr", None),
            ("roomio_audio", None),
            ("translated-", None),
            ("translated-bengali", None),
            (None, None),
            ("", None),
        ],
    )
    def test_parse_track_name(self, name: str | None, expected: str | None) -> None:
        assert target_language_from_track_name(name) == expected
