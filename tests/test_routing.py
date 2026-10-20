"""Language validation and direction routing tests."""

from __future__ import annotations

import pytest

from agent.routing import (
    DEFAULT_PAIR,
    DEFAULT_PAIR_CODE,
    LANGUAGE_PAIRS,
    LanguagePair,
    UnsupportedLanguageError,
    UnsupportedPairError,
    pair_from_metadata,
    parse_pair,
    target_language,
    target_language_from_track_name,
    track_name_for,
    validate_language,
)

BN_EN = LANGUAGE_PAIRS["bn-en"]
BN_JA = LANGUAGE_PAIRS["bn-ja"]


class TestValidateLanguage:
    def test_accepts_bengali(self) -> None:
        assert validate_language("bn") == "bn"

    def test_accepts_english(self) -> None:
        assert validate_language("en") == "en"

    def test_accepts_japanese(self) -> None:
        assert validate_language("ja") == "ja"

    def test_normalizes_case_and_whitespace(self) -> None:
        assert validate_language("  BN ") == "bn"
        assert validate_language("En") == "en"
        assert validate_language("JA") == "ja"

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
        for code in ("bn", "en", "ja"):
            assert code in message


class TestLanguagePairs:
    def test_registry_contains_both_pairs(self) -> None:
        assert set(LANGUAGE_PAIRS) == {"bn-en", "bn-ja"}

    def test_default_pair_is_bengali_english(self) -> None:
        assert DEFAULT_PAIR_CODE == "bn-en"
        assert DEFAULT_PAIR == BN_EN

    @pytest.mark.parametrize(
        ("value", "expected_code"),
        [
            ("bn-en", "bn-en"),
            ("en-bn", "bn-en"),
            ("BN_EN", "bn-en"),
            ("bn-ja", "bn-ja"),
            ("ja-bn", "bn-ja"),
            (" ja , bn ", "bn-ja"),
        ],
    )
    def test_parse_pair_normalizes(self, value: str, expected_code: str) -> None:
        pair = parse_pair(value)
        assert isinstance(pair, LanguagePair)
        assert pair.code == expected_code
        assert parse_pair(value) == LANGUAGE_PAIRS[expected_code]

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_parse_pair_rejects_missing(self, bad: str | None) -> None:
        with pytest.raises(UnsupportedPairError, match="required"):
            parse_pair(bad)

    @pytest.mark.parametrize("bad", ["en-ja", "bn", "bn-en-ja", "bn-bn", "bn-fr", "xx"])
    def test_parse_pair_rejects_unsupported(self, bad: str) -> None:
        with pytest.raises((UnsupportedPairError, UnsupportedLanguageError)):
            parse_pair(bad)

    def test_partner_returns_other_language(self) -> None:
        assert BN_JA.partner("bn") == "ja"
        assert BN_JA.partner("ja") == "bn"
        assert BN_EN.partner("en") == "bn"

    def test_partner_rejects_language_outside_pair(self) -> None:
        with pytest.raises(UnsupportedLanguageError, match="not valid in this room"):
            BN_JA.partner("en")
        with pytest.raises(UnsupportedLanguageError, match="not valid in this room"):
            BN_EN.partner("ja")

    def test_contains(self) -> None:
        assert BN_JA.contains("ja")
        assert not BN_JA.contains("en")


class TestPairFromMetadata:
    @pytest.mark.parametrize("bad", [None, "", "   ", "not json", "{}"])
    def test_falls_back_to_default(self, bad: str | None) -> None:
        assert pair_from_metadata(bad) == DEFAULT_PAIR

    def test_reads_json_pair_field(self) -> None:
        assert pair_from_metadata('{"pair": "bn-ja"}') == BN_JA

    def test_reads_bare_pair_code(self) -> None:
        assert pair_from_metadata("bn-ja") == BN_JA

    def test_unknown_json_pair_falls_back(self) -> None:
        assert pair_from_metadata('{"pair": "en-ja"}') == DEFAULT_PAIR


class TestTargetLanguage:
    def test_bengali_source_targets_english_by_default(self) -> None:
        assert target_language("bn") == "en"

    def test_english_source_targets_bengali_by_default(self) -> None:
        assert target_language("en") == "bn"

    def test_japanese_pair_maps_both_directions(self) -> None:
        assert target_language("ja", BN_JA) == "bn"
        assert target_language("bn", BN_JA) == "ja"

    def test_both_directions_are_crossed(self) -> None:
        for pair in (BN_EN, BN_JA):
            for source in pair.languages:
                assert target_language(source, pair) != source

    def test_language_not_in_pair_is_rejected(self) -> None:
        with pytest.raises(UnsupportedLanguageError):
            target_language("en", BN_JA)
        with pytest.raises(UnsupportedLanguageError):
            target_language("ja", BN_EN)

    @pytest.mark.parametrize("bad", ["fr", None, ""])
    def test_invalid_source_is_rejected(self, bad: str | None) -> None:
        with pytest.raises(UnsupportedLanguageError):
            target_language(bad)  # type: ignore[arg-type]


class TestTrackNames:
    def test_track_name_for_target(self) -> None:
        assert track_name_for("en") == "translated-en"
        assert track_name_for("bn") == "translated-bn"
        assert track_name_for("ja") == "translated-ja"

    def test_invalid_target_rejected(self) -> None:
        with pytest.raises(UnsupportedLanguageError):
            track_name_for("fr")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("translated-en", "en"),
            ("translated-bn", "bn"),
            ("translated-ja", "ja"),
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
