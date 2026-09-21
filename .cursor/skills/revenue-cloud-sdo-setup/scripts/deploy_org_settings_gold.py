#!/usr/bin/env python3
"""Deploy org-settings-gold Settings metadata to a target org.

Order: Quote, Order, RevenueManagement, ProductConfigurator, IndustriesPricing,
Industries (Timeline pref), Billing.
Does not copy org-specific Billing record IDs.

Skip-if-done: retrieves current Settings first and skips deploy when gold key
fields already match.

On Metadata field rejects, strips the named fields from the temp package and
retries (common on API 67 / release-262 SDOs).
"""

from __future__ import annotations

import argparse
import json
import re
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

# Key fields that must match gold before we skip deploy (per settings file stem).
KEY_FIELDS: dict[str, list[str]] = {
    "Quote": ["enableQuote"],
    "Order": [
        "enableEnhancedCommerceOrders",
        "enableOptionalPricebook",
        "enableOrderEvents",
        "enableZeroQuantity",
    ],
    "RevenueManagement": [
        "enableCoreCPQ",
        "enableTransactionProcessor",
        "enableAsIsRenewals",
    ],
    "ProductConfigurator": ["enableProductConfigurator"],
    "IndustriesPricing": ["enableSalesforcePricing"],
    "Industries": ["enableTimelinePref"],
    "Billing": [
        "enableBillingSetup",
        "enableInvoicePdfGeneration",
        "enablePaymentApplicationToPostedInvoices",
    ],
}

MAX_OMIT_RETRIES = 8


def parse_sf_json(raw: str) -> dict:
    """Parse sf --json output; tolerate leading/trailing non-JSON noise."""
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"sf returned no JSON: {raw[:500]}")
    data, _ = decoder.raw_decode(raw[start:])
    return data


def run_sf(args: list[str], *, cwd: Path | None = None, check: bool = True) -> dict:
    proc = subprocess.run(
        ["sf", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    raw = (proc.stdout or "") + (proc.stderr or "")
    data = parse_sf_json(raw)
    if check and proc.returncode != 0 and data.get("status") not in (0, "0"):
        raise RuntimeError(json.dumps(data, indent=2)[:4000])
    return data


def extract_tag(xml: str, tag: str) -> str | None:
    m = re.search(
        rf"<{tag}>\s*([^<]*?)\s*</{tag}>",
        xml,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    return m.group(1).strip().lower()


def gold_matches_org(org_xml: str, gold_xml: str, fields: list[str]) -> bool:
    for tag in fields:
        gold_val = extract_tag(gold_xml, tag)
        if gold_val is None:
            continue  # gold omits this field — don't require it
        org_val = extract_tag(org_xml, tag)
        if org_val != gold_val:
            return False
    return True


def write_mini_project(root: Path) -> None:
    (root / "sfdx-project.json").write_text(
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
    (root / "force-app" / "main" / "default").mkdir(parents=True, exist_ok=True)


def already_matches_gold(target_org: str) -> bool:
    """Return True when all key gold fields already match the org."""
    with tempfile.TemporaryDirectory(prefix="gold-check-") as tmp:
        tmp_path = Path(tmp)
        write_mini_project(tmp_path)
        meta_types = [name.replace(".settings-meta.xml", "") for name in DEPLOY_ORDER]
        meta_args: list[str] = []
        for name in meta_types:
            meta_args.extend(["--metadata", f"Settings:{name}"])
        try:
            run_sf(
                [
                    "project",
                    "retrieve",
                    "start",
                    *meta_args,
                    "--target-org",
                    target_org,
                    "--json",
                ],
                cwd=tmp_path,
            )
        except RuntimeError as exc:
            print(f"Skip-check retrieve failed; will deploy. ({exc})", flush=True)
            return False

        for filename in DEPLOY_ORDER:
            stem = filename.replace(".settings-meta.xml", "")
            gold_path = GOLD_DIR / filename
            gold_xml = gold_path.read_text(encoding="utf-8")
            hits = list(tmp_path.rglob(f"{stem}.settings-meta.xml"))
            if not hits:
                print(f"Skip-check: {stem} not retrieved — will deploy.", flush=True)
                return False
            org_xml = hits[0].read_text(encoding="utf-8")
            fields = KEY_FIELDS.get(stem, [])
            if fields and not gold_matches_org(org_xml, gold_xml, fields):
                print(f"Skip-check: {stem} differs from gold — will deploy.", flush=True)
                return False
        return True


def failure_field_names(result: dict) -> list[str]:
    res = result.get("result") or {}
    details = res.get("details") or {}
    fails = details.get("componentFailures") or []
    names: list[str] = []
    for fail in fails:
        problem = (fail.get("problem") or "").strip()
        # Salesforce often returns just the field API name as the problem
        if problem and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", problem):
            names.append(problem)
    return list(dict.fromkeys(names))


def omit_fields_from_settings(settings_dir: Path, field_names: list[str]) -> int:
    """Remove <field>...</field> tags from all settings XML. Returns count removed."""
    removed = 0
    for path in settings_dir.glob("*.settings-meta.xml"):
        text = path.read_text(encoding="utf-8")
        original = text
        for name in field_names:
            text, n = re.subn(
                rf"\s*<{name}>[^<]*</{name}>\s*",
                "\n",
                text,
                flags=re.IGNORECASE,
            )
            removed += n
            # Also strip XML comments that only mention the field? skip.
        if text != original:
            # Annotate once
            note = (
                f"    <!-- auto-omitted rejected fields: {', '.join(field_names)} -->\n"
            )
            if "auto-omitted rejected fields" not in text:
                text = text.replace(
                    ">",
                    ">\n" + note,
                    1,
                )
            path.write_text(text, encoding="utf-8")
    return removed


def deploy_once(tmp: Path, target_org: str, dry_run: bool) -> dict:
    cmd = [
        "project",
        "deploy",
        "start",
        "--source-dir",
        str(tmp / "force-app" / "main" / "default" / "settings"),
        "--target-org",
        target_org,
        "--wait",
        "30",
        "--json",
    ]
    if dry_run:
        cmd.insert(3, "--dry-run")
    return run_sf(cmd, check=False)


def deploy_succeeded(result: dict) -> bool:
    status = result.get("status")
    res = result.get("result") or {}
    if status in (0, "0", None) and res.get("success") is not False:
        fails = (res.get("details") or {}).get("componentFailures") or []
        return not fails
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-org", required=True, help="sf org alias or username")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate deploy only (sf project deploy start --dry-run)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Deploy even when gold key fields already match",
    )
    args = parser.parse_args()

    if not GOLD_DIR.is_dir():
        print(f"Gold directory missing: {GOLD_DIR}", file=sys.stderr)
        return 1

    if not args.force and not args.dry_run:
        print(f"Checking whether gold settings already match on {args.target_org}...")
        if already_matches_gold(args.target_org):
            print("Gold key fields already match — skipping deploy.")
            return 0

    with tempfile.TemporaryDirectory(prefix="org-settings-gold-") as tmp:
        tmp_path = Path(tmp)
        settings_dir = tmp_path / "force-app" / "main" / "default" / "settings"
        settings_dir.mkdir(parents=True)
        for name in DEPLOY_ORDER:
            src = GOLD_DIR / name
            if not src.is_file():
                print(f"Missing gold file: {src}", file=sys.stderr)
                return 1
            shutil.copy2(src, settings_dir / name)

        write_mini_project(tmp_path)

        print(f"Deploying gold settings to {args.target_org}...")
        omitted: list[str] = []
        result: dict = {}
        for attempt in range(1, MAX_OMIT_RETRIES + 1):
            result = deploy_once(tmp_path, args.target_org, args.dry_run)
            if deploy_succeeded(result):
                if omitted:
                    print(f"Gold settings deploy completed (omitted: {', '.join(omitted)}).")
                else:
                    print("Gold settings deploy completed.")
                return 0

            fields = failure_field_names(result)
            if not fields or args.dry_run:
                break

            print(
                f"Attempt {attempt}: Metadata rejected field(s) {fields} — "
                "omitting and retrying...",
                flush=True,
            )
            n = omit_fields_from_settings(settings_dir, fields)
            if n == 0:
                print(
                    f"Could not strip rejected fields {fields} from temp package.",
                    file=sys.stderr,
                )
                break
            omitted.extend(f for f in fields if f not in omitted)

        print(json.dumps({"status": result.get("status"), "result": result.get("result")}, indent=2)[:4000])
        # Soft-ok if key irreversibles likely applied (Quote/Order/Rev/etc succeeded)
        res = result.get("result") or {}
        details = res.get("details") or {}
        successes = {
            (c.get("fullName") or "")
            for c in (details.get("componentSuccesses") or [])
            if c.get("componentType")
        }
        required = {
            "Quote",
            "Order",
            "RevenueManagement",
            "ProductConfigurator",
            "IndustriesPricing",
            "Industries",
        }
        if required.issubset(successes):
            print(
                "Gold key Settings types deployed; remaining failures are "
                f"non-blocking: {failure_field_names(result) or 'see log'}.",
                flush=True,
            )
            return 0
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
