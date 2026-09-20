#!/usr/bin/env python3
"""Strip QuantumBit Lightning org branding from a local rlm-base-dev checkout.

Removes BrandingSets, LightningExperienceThemes, active-theme settings, and
QuantumBit logo static resources from unpackaged/post_quantumbit so
deploy_quantumbit does not overwrite the SDO's Lightning theme.

Mutates the vendor working tree (expect dirty git / stamp \"dirty\").
Run after clone/checkout and before prepare_rlm_org.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Paths relative to rlm-base-dev repo root
DIRS_TO_REMOVE = [
    "unpackaged/post_quantumbit/brandingSets",
    "unpackaged/post_quantumbit/lightningExperienceThemes",
]

FILES_TO_REMOVE = [
    "unpackaged/post_quantumbit/settings/LightningExperience.settings-meta.xml",
]

# Logo static resource basenames (delete binary + -meta.xml; SFDMU uses .png)
LOGO_STATIC_BASENAMES = [
    "RLM_quantum_bit_logo",
    "RLM_quantumBit_logo_sq",
]
LOGO_SUFFIXES = (
    ".resource",
    ".resource-meta.xml",
    ".png",
    ".png-meta.xml",
)


def remove_path(path: Path, removed: list[str], missing: list[str]) -> None:
    if not path.exists():
        missing.append(str(path))
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    removed.append(str(path))


def strip_branding(repo_root: Path) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    missing: list[str] = []

    for rel in DIRS_TO_REMOVE:
        remove_path(repo_root / rel, removed, missing)

    for rel in FILES_TO_REMOVE:
        remove_path(repo_root / rel, removed, missing)

    static_dir = repo_root / "unpackaged/post_quantumbit/staticresources"
    if static_dir.is_dir():
        for base in LOGO_STATIC_BASENAMES:
            for path in static_dir.glob(f"{base}*"):
                if path.is_file():
                    remove_path(path, removed, missing)
            for suffix in LOGO_SUFFIXES:
                exact = static_dir / f"{base}{suffix}"
                if exact.exists() and str(exact) not in removed:
                    remove_path(exact, removed, missing)
    else:
        missing.append(str(static_dir))

    return removed, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Path to rlm-base-dev (default: <workspace>/vendor/rlm-base-dev)",
    )
    args = parser.parse_args()

    if args.repo_root is not None:
        repo_root = args.repo_root.resolve()
    else:
        # scripts/ → skill → .cursor → workspace
        workspace = Path(__file__).resolve().parents[3]
        repo_root = workspace / "vendor" / "rlm-base-dev"

    if not repo_root.is_dir():
        print(f"rlm-base-dev not found: {repo_root}", file=sys.stderr)
        return 1

    post_qb = repo_root / "unpackaged" / "post_quantumbit"
    if not post_qb.is_dir():
        print(f"post_quantumbit missing under {repo_root}", file=sys.stderr)
        return 1

    removed, missing = strip_branding(repo_root)
    print(f"Stripped QuantumBit branding under {repo_root}")
    for p in removed:
        print(f"  removed: {p}")
    for p in missing:
        print(f"  already absent: {p}")
    if not removed and missing:
        print("Nothing removed (paths already stripped or missing).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
