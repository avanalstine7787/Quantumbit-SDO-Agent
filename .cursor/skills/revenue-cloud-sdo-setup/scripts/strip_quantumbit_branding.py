#!/usr/bin/env python3
"""Strip QuantumBit Lightning org branding from a local rlm-base-dev checkout.

Removes the active-theme settings and QuantumBit logo static resources so
deploy_quantumbit does not force QuantumBit as the org's Lightning theme.

**Keeps** theme ``QuantumBitSLDSv2``, its branding set, and the rectangle
ContentAsset so Step 6 Phase 4b (rlm-generic-demo-products) can replace the
Brand Image as written. Does not activate that theme.

Mutates the vendor working tree (expect dirty git / stamp \"dirty\").
Run after clone/checkout and before prepare_rlm_org.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Paths relative to rlm-base-dev repo root
FILES_TO_REMOVE = [
    # Do not activate QuantumBit as the org default theme
    "unpackaged/post_quantumbit/settings/LightningExperience.settings-meta.xml",
    # Extra QB theme (keep only QuantumBitSLDSv2 for Phase 4b)
    "unpackaged/post_quantumbit/lightningExperienceThemes/QuantumBit.lightningExperienceTheme-meta.xml",
    "unpackaged/post_quantumbit/brandingSets/LEXTHEMINGQuantumBit.brandingSet-meta.xml",
]

# Logo static resource basenames (delete binary + -meta.xml)
LOGO_STATIC_BASENAMES = [
    "RLM_quantum_bit_logo",
    "RLM_quantumBit_logo_sq",
]


def remove_path(path: Path, removed: list[str], missing: list[str]) -> None:
    if not path.exists():
        missing.append(str(path))
        return
    if path.is_dir():
        import shutil

        shutil.rmtree(path)
    else:
        path.unlink()
    removed.append(str(path))


def strip_branding(repo_root: Path) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    missing: list[str] = []

    for rel in FILES_TO_REMOVE:
        remove_path(repo_root / rel, removed, missing)

    static_dir = repo_root / "unpackaged/post_quantumbit/staticresources"
    if static_dir.is_dir():
        for base in LOGO_STATIC_BASENAMES:
            for path in static_dir.glob(f"{base}*"):
                if path.is_file():
                    remove_path(path, removed, missing)
    else:
        missing.append(str(static_dir))

    # Preserve QuantumBitSLDSv2 theme + branding set + rectangle ContentAsset
    keep_theme = (
        repo_root
        / "unpackaged/post_quantumbit/lightningExperienceThemes"
        / "QuantumBitSLDSv2.lightningExperienceTheme-meta.xml"
    )
    keep_brand = (
        repo_root
        / "unpackaged/post_quantumbit/brandingSets"
        / "LEXTHEMINGQuantumBitSLDSv2.brandingSet-meta.xml"
    )
    if not keep_theme.is_file():
        missing.append(f"REQUIRED for Phase 4b (missing): {keep_theme}")
    if not keep_brand.is_file():
        missing.append(f"REQUIRED for Phase 4b (missing): {keep_brand}")

    return removed, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
        help="Path to local rlm-base-dev checkout",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if not root.is_dir():
        print(f"Repo root not found: {root}", file=sys.stderr)
        return 1

    removed, missing = strip_branding(root)
    print(f"Stripped QuantumBit branding under {root}")
    for path in removed:
        print(f"  removed: {path}")
    for path in missing:
        print(f"  note: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
