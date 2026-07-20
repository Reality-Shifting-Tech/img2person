#!/usr/bin/env python3
"""Checkpoint download CLI, gated by models/manifest.json (ADR-0003).

Usage:
    uv run python models/download.py --list
    uv run python models/download.py <name>
    uv run python models/download.py <name> --accept-terms <name>
    uv run python models/download.py --all [--accept-terms <name> ...]

Downloads land under models/checkpoints/ (gitignored). Entries with
licenseStatus "verified" download normally. Entries with licenseStatus
"disputed" require an explicit --accept-terms flag naming the checkpoint;
acceptance prints the dispute text and records a per-checkpoint marker file
(.accepted-<name>.json) so later runs (e.g. container start) need no flag.
SHA-256 is verified whenever the manifest provides one. No weights are ever
committed to the repository.
"""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"
CHECKPOINTS_DIR = Path(__file__).resolve().parent / "checkpoints"

# License statuses per ADR-0003. "verified" permits commercial use and
# redistribution; "disputed" requires explicit operator acceptance.
VERIFIED = "verified"
DISPUTED = "disputed"

Fetcher = Callable[[str, Path], None]


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def fetch_url(url: str, dest: Path) -> None:
    """Default network fetch; tests inject a fake."""
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _marker_path(checkpoints_dir: Path, name: str) -> Path:
    return checkpoints_dir / f".accepted-{name}.json"


def _record_acceptance(entry: dict, checkpoints_dir: Path) -> Path:
    marker = _marker_path(checkpoints_dir, entry["name"])
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "name": entry["name"],
                "license": entry["license"],
                "licenseStatus": entry["licenseStatus"],
                "dispute": entry.get("dispute", ""),
                "acceptedAt": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return marker


def _print_dispute(entry: dict) -> None:
    print(f"license dispute for {entry['name']!r} ({entry['license']}):")
    print(f"  {entry.get('dispute', 'no dispute text recorded')}")


def download_entry(entry: dict, checkpoints_dir: Path, fetcher: Fetcher) -> None:
    dest_dir = checkpoints_dir / entry["dest"]
    for file_entry in entry["files"]:
        target = dest_dir / file_entry["path"]
        if target.exists() and not file_entry.get("unpack"):
            expected = file_entry.get("sha256")
            if expected is None or _sha256(target) == expected:
                print(f"skip {target} (already present)")
                continue
            print(f"re-downloading {target} (hash mismatch)")
        dest_dir.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            print(f"fetch {file_entry['url']}")
            fetcher(file_entry["url"], tmp_path)
            expected = file_entry.get("sha256")
            if expected is not None:
                actual = _sha256(tmp_path)
                if actual != expected:
                    raise ValueError(
                        f"SHA-256 mismatch for {file_entry['path']}: "
                        f"expected {expected}, got {actual}"
                    )
            else:
                print(f"warning: no sha256 for {file_entry['path']}; skipping verification")
            if file_entry.get("unpack") == "zip":
                with zipfile.ZipFile(tmp_path) as zf:
                    zf.extractall(target.parent)
                tmp_path.unlink()
                print(f"unpacked {file_entry['path']} -> {target.parent}")
            else:
                shutil.move(str(tmp_path), target)
                print(f"wrote {target}")
        finally:
            tmp_path.unlink(missing_ok=True)


def _check_acceptance(entry: dict, accepted: set[str], checkpoints_dir: Path) -> bool:
    """True when the entry may download; prints the reason when refused."""
    if entry.get("licenseStatus") == VERIFIED:
        return True
    if entry.get("licenseStatus") != DISPUTED:
        print(
            f"error: {entry['name']!r} has unknown licenseStatus "
            f"{entry.get('licenseStatus')!r}; refusing (ADR-0003).",
            file=sys.stderr,
        )
        return False
    if _marker_path(checkpoints_dir, entry["name"]).exists():
        return True
    _print_dispute(entry)
    if entry["name"] not in accepted:
        print(
            f"error: {entry['name']!r} has a disputed license. Re-run with "
            f"--accept-terms {entry['name']} to accept the terms above and download.",
            file=sys.stderr,
        )
        return False
    marker = _record_acceptance(entry, checkpoints_dir)
    print(f"acceptance recorded in {marker}")
    return True


def main(
    argv: list[str] | None = None,
    *,
    manifest_path: Path = MANIFEST_PATH,
    checkpoints_dir: Path = CHECKPOINTS_DIR,
    fetcher: Fetcher = fetch_url,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="checkpoint name from the manifest")
    parser.add_argument("--list", action="store_true", help="list registered checkpoints")
    parser.add_argument("--all", action="store_true", help="download every eligible checkpoint")
    parser.add_argument(
        "--accept-terms",
        action="append",
        default=[],
        metavar="NAME",
        help="accept the license dispute for checkpoint NAME (required once per disputed entry)",
    )
    args = parser.parse_args(argv)

    checkpoints = load_manifest(manifest_path)["checkpoints"]

    if args.list:
        if not checkpoints:
            print("No checkpoints registered. Mock mode needs none.")
        for cp in checkpoints:
            print(f"{cp['name']}\t{cp['licenseStatus']}\t{cp['license']}")
        return 0

    if not args.name and not args.all:
        parser.error("provide a checkpoint name, --all, or --list")

    if args.all:
        entries = checkpoints
    else:
        entry = next((cp for cp in checkpoints if cp["name"] == args.name), None)
        if entry is None:
            print(
                f"error: {args.name!r} is not in models/manifest.json. "
                "Checkpoints must be registered with source URL, SHA-256, and a "
                "license verified for commercial use (ADR-0003).",
                file=sys.stderr,
            )
            return 1
        entries = [entry]

    accepted = set(args.accept_terms)
    unknown_accepts = accepted - {cp["name"] for cp in checkpoints}
    if unknown_accepts:
        print(
            f"error: --accept-terms for unknown checkpoint(s): {sorted(unknown_accepts)}",
            file=sys.stderr,
        )
        return 1

    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for entry in entries:
        if not _check_acceptance(entry, accepted, checkpoints_dir):
            failed = True
            continue
        try:
            download_entry(entry, checkpoints_dir, fetcher)
        except Exception as exc:
            print(f"error: download of {entry['name']!r} failed: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
