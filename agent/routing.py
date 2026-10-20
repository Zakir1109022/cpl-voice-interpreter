"""Pure language validation and direction routing.

A room runs exactly one *language pair* (for example ``bn-en`` or ``bn-ja``); each
participant selects one language from that pair and receives speech translated into
the partner language. Keeping the pair explicit is what makes more than two languages
unambiguous.

No LiveKit dependencies; fully unit testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

SUPPORTED_LANGUAGES = frozenset({"bn", "en", "ja"})

# canonical order used to normalize pair codes ("ja-bn" -> "bn-ja")
_LANGUAGE_ORDER = ("bn", "en", "ja")

_TRACK_PREFIX = "translated-"


class UnsupportedLanguageError(ValueError):
    """Raised when a language is missing or not supported."""


class UnsupportedPairError(ValueError):
    """Raised when a language pair is missing or not supported."""


def validate_language(language: str | None) -> str:
    """Return the normalized language code or raise UnsupportedLanguageError."""
    if language is None or not str(language).strip():
        raise UnsupportedLanguageError(
            "A participant language is required. Select one of: "
            + ", ".join(sorted(SUPPORTED_LANGUAGES))
            + "."
        )
    normalized = str(language).strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise UnsupportedLanguageError(
            f"Unsupported language {normalized!r}. Supported languages: "
            + ", ".join(sorted(SUPPORTED_LANGUAGES))
            + "."
        )
    return normalized


@dataclass(frozen=True)
class LanguagePair:
    """An unordered pair of languages that translate into each other."""

    code: str
    languages: tuple[str, str]

    def partner(self, language: str) -> str:
        """Return the other language of the pair.

        Raises UnsupportedLanguageError when ``language`` is not part of this pair,
        so callers can report "choose one of ..." to the participant.
        """
        source = validate_language(language)
        if source not in self.languages:
            raise UnsupportedLanguageError(
                f"Language {source!r} is not valid in this room. "
                "Choose one of: " + ", ".join(self.languages) + "."
            )
        return self.languages[1] if source == self.languages[0] else self.languages[0]

    def contains(self, language: str) -> bool:
        return language in self.languages


def _normalize_pair_code(first: str, second: str) -> str:
    return "-".join(sorted((first, second), key=_LANGUAGE_ORDER.index))


LANGUAGE_PAIRS: dict[str, LanguagePair] = {
    _normalize_pair_code("bn", "en"): LanguagePair(_normalize_pair_code("bn", "en"), ("bn", "en")),
    _normalize_pair_code("bn", "ja"): LanguagePair(_normalize_pair_code("bn", "ja"), ("bn", "ja")),
}

DEFAULT_PAIR_CODE = _normalize_pair_code("bn", "en")
DEFAULT_PAIR = LANGUAGE_PAIRS[DEFAULT_PAIR_CODE]


def parse_pair(value: str | None) -> LanguagePair:
    """Normalize and validate a pair code such as ``"bn-ja"`` or ``"ja-bn"``."""
    if value is None or not str(value).strip():
        raise UnsupportedPairError(
            "A language pair is required. Supported pairs: "
            + ", ".join(sorted(LANGUAGE_PAIRS))
            + "."
        )
    normalized = str(value).strip().lower().replace("_", "-").replace(",", "-")
    parts = [part.strip() for part in normalized.split("-") if part.strip()]
    if len(parts) != 2 or parts[0] == parts[1]:
        raise UnsupportedPairError(
            f"Unsupported language pair {normalized!r}. Supported pairs: "
            + ", ".join(sorted(LANGUAGE_PAIRS))
            + "."
        )
    for part in parts:
        validate_language(part)
    code = _normalize_pair_code(parts[0], parts[1])
    pair = LANGUAGE_PAIRS.get(code)
    if pair is None:
        raise UnsupportedPairError(
            f"Unsupported language pair {normalized!r}. Supported pairs: "
            + ", ".join(sorted(LANGUAGE_PAIRS))
            + "."
        )
    return pair


def pair_from_metadata(metadata: str | None) -> LanguagePair:
    """Resolve a room pair from dispatch/room metadata.

    Accepts a JSON object with a ``pair`` field (``{"pair": "bn-ja"}``) or a bare
    pair code, and falls back to DEFAULT_PAIR when nothing usable is present.
    """
    raw = (metadata or "").strip()
    if not raw:
        return DEFAULT_PAIR
    candidate = raw
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return DEFAULT_PAIR
        if isinstance(parsed, dict):
            candidate = str(parsed.get("pair") or "").strip()
    if not candidate:
        return DEFAULT_PAIR
    try:
        return parse_pair(candidate)
    except UnsupportedPairError:
        return DEFAULT_PAIR


def target_language(source_language: str, pair: LanguagePair = DEFAULT_PAIR) -> str:
    """Map a validated source language to its translation target within ``pair``."""
    return pair.partner(source_language)


def track_name_for(target: str) -> str:
    """Name of the audio track carrying speech translated into ``target``."""
    return _TRACK_PREFIX + validate_language(target)


def target_language_from_track_name(name: str | None) -> str | None:
    """Extract the target language from a translated track name, if valid."""
    if not name or not name.startswith(_TRACK_PREFIX):
        return None
    candidate = name[len(_TRACK_PREFIX) :]
    try:
        return validate_language(candidate)
    except UnsupportedLanguageError:
        return None
