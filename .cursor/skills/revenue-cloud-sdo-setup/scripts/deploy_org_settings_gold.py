#!/usr/bin/env python3
"""Deploy org-settings-gold Settings metadata to a target org.

Order: Quote, Order, RevenueManagement, ProductConfigurator, IndustriesPricing,
Industries (Timeline pref), Billing.
Does not copy org-specific Billing record IDs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = SKILL_ROOT / "references" / "org-settings-gold"

DEPLOY_ORDER = [
    "Quote.settings-meta.xml",
    "Order.settings-meta.xml",
    "RevenueManagement.settings-meta.xml",
    "ProductConfigurator.settings-meta.xml",
    "IndustriesPricing.settings-meta.xml",
    "Industries.settings-meta.xml",
    "Billing.settings-meta.xml",
]


def parse_sf_json(raw: str) -> dict:
    """Parse sf --json output; tolerate leading/trailing non-JSON noise."""
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"sf returned no JSON: {raw[:500]}")
    data, _ = decoder.raw_decode(raw[start:])
    return data


def run_sf(args: list[str]) -> dict:
    proc = subprocess.run(
        ["sf", *args],
        capture_output=True,
        text=True,
    )
    raw = (proc.stdout or "") + (proc.stderr or "")
    data = parse_sf_json(raw)
    if proc.returncode != 0 and data.get("status") not in (0, "0"):
        raise RuntimeError(json.dumps(data, indent=2)[:4000])
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-org", required=True, help="sf org alias or username")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate deploy only (sf project deploy start --dry-run)",
    )
    args = parser.parse_args()

    if not GOLD_DIR.is_dir():
        print(f"Gold directory missing: {GOLD_DIR}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="org-settings-gold-") as tmp:
        settings_dir = Path(tmp) / "force-app" / "main" / "default" / "settings"
        settings_dir.mkdir(parents=True)
        for name in DEPLOY_ORDER:
            src = GOLD_DIR / name
            if not src.is_file():
                print(f"Missing gold file: {src}", file=sys.stderr)
                return 1
            shutil.copy2(src, settings_dir / name)

        # Minimal sfdx-project.json so sf can deploy from temp dir
        (Path(tmp) / "sfdx-project.json").write_text(
            json.dumps(
                {
                    "packageDirectories": [{"path": "force-app", "default": True}],
                    "namespace": "",
                    "sfdcLoginUrl": "https://login.salesforce.com",
                    "sourceApiVersion": "67.0",
                },
                indent=2,
            )
            + "\n"
        )

        cmd = [
            "project",
            "deploy",
            "start",
            "--source-dir",
            str(Path(tmp) / "force-app" / "main" / "default" / "settings"),
            "--target-org",
            args.target_org,
            "--wait",
            "30",
            "--json",
        ]
        if args.dry_run:
            cmd.insert(3, "--dry-run")

        print(f"Deploying gold settings to {args.target_org}...")
        result = run_sf(cmd)
        status = result.get("status")
        print(json.dumps({"status": status, "result": result.get("result")}, indent=2)[:3000])
        if status not in (0, "0", None):
            return 1
        # sf often nests success under result.success
        res = result.get("result") or {}
        if res.get("success") is False:
            return 1
        print("Gold settings deploy completed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
