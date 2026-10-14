"""Vine - A lightweight AI Agent Harness.

Fuses Trellis lifecycle management & hook injection,
Ponytail minimalist pragmatic coding philosophy,
and grill-with-docs Socratic brainstorming and living documentation.
"""

__version__ = "0.1.0"

__all__ = ["__version__", "mem"]

from . import mem  # noqa: E402  (submodule export; keeps `vine.mem` importable)
