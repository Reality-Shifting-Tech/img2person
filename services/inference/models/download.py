#!/usr/bin/env python3
"""Checkpoint download CLI, gated by models/manifest.json (ADR-0003).

Usage:
    uv run python models/download.py --list
    uv run python models/download.py <name>

Refuses anything not registered in the manifest with a license verified to
permit commercial use and redistribution. No weights are ever committed to
the repository.
"""

import argparse
import json
import sys
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# Licenses verified per ADR-0003 to permit commercial use and redistribution.
ELIGIBLE_LICENSES = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "CC-BY-4.0"}


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="checkpoint name from the manifest")
    parser.add_argument("--list", action="store_true", help="list registered checkpoints")
    args = parser.parse_args()

    checkpoints = load_manifest()["checkpoints"]

    if args.list:
        if not checkpoints:
            print("No checkpoints registered. Mock mode needs none; lhm mode is not yet available.")
        for cp in checkpoints:
            print(f"{cp['name']}\t{cp['license']}\t{cp['url']}")
        return 0

    if not args.name:
        parser.error("provide a checkpoint name or --list")

    entry = next((cp for cp in checkpoints if cp["name"] == args.name), None)
    if entry is None:
        print(
            f"error: {args.name!r} is not in models/manifest.json. "
            "Checkpoints must be registered with source URL, SHA-256, and a "
            "license verified for commercial use (ADR-0003).",
            file=sys.stderr,
        )
        return 1
    if entry["license"] not in ELIGIBLE_LICENSES:
        print(
            f"error: {args.name!r} has license {entry['license']!r}, which is not verified "
            "to permit commercial use and redistribution (ADR-0003). Refusing to download.",
            file=sys.stderr,
        )
        return 1

    # TODO: fetch entry["url"], verify SHA-256 against entry["sha256"], then unpack.
    print(
        f"error: download not implemented yet. {args.name!r} is eligible; "
        "fetching is intentionally left unimplemented until an eligible checkpoint exists.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
