"""Schema constants and backwards-compatible row classification."""

from __future__ import annotations

RAW_SCHEMA_VERSION = 2
ANALYSIS_SCHEMA_VERSION = 2


def is_schema_v2(frame: object) -> bool:
    """Whether a tabular object carries the v2 raw-row marker."""
    columns = getattr(frame, "columns", ())
    return "raw_schema_version" in columns
