"""Stable, process-independent seed derivation."""

from __future__ import annotations

import hashlib
import json

ROOT_SEED = 0x4A554E4354555245


def derive_seed(*parts: object, root_seed: int = ROOT_SEED) -> int:
    payload = json.dumps(
        [root_seed, *parts], sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")
