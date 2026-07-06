"""Minimal sample module for R8 external AIBOM generation."""

__version__ = "0.1.0"


def summarize_public_note(text: str) -> str:
    """Return a short deterministic summary for public sample text."""
    normalized = " ".join(text.split())
    if len(normalized) <= 80:
        return normalized
    return normalized[:77] + "..."
