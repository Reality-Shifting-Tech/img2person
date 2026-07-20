"""Deterministic mock identity scoring.

Identity in mock mode is a fiction, but it must be a stable one: the same
photo must always produce the same score so the web UI and e2e tests are
reproducible. All jitter derives from the image content hash.
"""

import hashlib


def _unit(hash_bytes: bytes, salt: bytes) -> float:
    digest = hashlib.sha256(salt + hash_bytes).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def score(image_hash: bytes) -> tuple[float, dict[str, float]]:
    identity = 0.82 + 0.12 * _unit(image_hash, b"identity")
    confidence = {
        "front": 0.85 + 0.10 * _unit(image_hash, b"front"),
        "profile": 0.55 + 0.15 * _unit(image_hash, b"profile"),
        "back": 0.30 + 0.15 * _unit(image_hash, b"back"),
    }
    return round(identity, 4), {k: round(v, 4) for k, v in confidence.items()}
