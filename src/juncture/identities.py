"""Stable cryptographic identities for schema-v2 simulation rows."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_id(kind: str, value: dict[str, Any]) -> str:
    """Return a portable ID; unlike ``hash()``, this is process independent."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{kind}_{hashlib.sha256(payload).hexdigest()[:24]}"
