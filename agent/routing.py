"""Pure language validation and direction routing.

No LiveKit dependencies; fully unit testable.
"""

from __future__ import annotations

SUPPORTED_LANGUAGES = frozenset({"bn", "en"})

_TRACK_PREFIX = "translated-"


class UnsupportedLanguageError(ValueError):
    """Raised when a language is missing or not supported."""


def validate_language(language: str | None) -> str:
    """Return the normalized language code or raise UnsupportedLanguageError."""
    if language is None or not str(language).strip():
        raise UnsupportedLanguageError(
            "A participant language is required. Select 'bn' (Bengali) or 'en' (English)."
        )
    normalized = str(language).strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise UnsupportedLanguageError(
            f"Unsupported language {normalized!r}. Supported languages: "
            + ", ".join(sorted(SUPPORTED_LANGUAGES))
            + "."
        )
    return normalized


def target_language(source_language: str) -> str:
    """Map a validated source language to its translation target.

    Bengali source -> English target; English source -> Bengali target.
    """
    source = validate_language(source_language)
    return "en" if source == "bn" else "bn"


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
