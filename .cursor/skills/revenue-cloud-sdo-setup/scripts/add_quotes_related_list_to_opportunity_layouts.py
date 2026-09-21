#!/usr/bin/env python3
"""Add Quotes related list (RelatedQuoteList) to all Opportunity page layouts.

Retrieves Opportunity layouts from the target org, appends the standard Quotes
related list when missing, and redeploys. Idempotent.

Prerequisite: Quotes enabled (gold Quote settings / enableQuote=true).
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

RELATED_QUOTE_BLOCK = """    <relatedLists>
        <fields>QUOTE.QUOTENUMBER</fields>
        <fields>QUOTE.NAME</fields>
        <fields>QUOTE.ISSYNCING</fields>
        <fields>QUOTE.EXPIRATIONDATE</fields>
        <fields>QUOTE.SUBTOTAL</fields>
        <fields>QUOTE.TOTALPRICE</fields>
        <fields>CreatedBy</fields>
        <relatedList>RelatedQuoteList</relatedList>
    </relatedLists>
"""


def parse_sf_json(raw: str) -> dict:
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"sf returned no JSON: {raw[:500]}")
    data, _ = decoder.raw_decode(raw[start:])
    return data


def run_sf(args: list[str], *, check: bool = True, cwd: Path | None = None) -> dict:
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


def quotes_enabled(target_org: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="quote-settings-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "sfdx-project.json").write_text(
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
        (tmp_path / "force-app" / "main" / "default").mkdir(parents=True)
        # Run retrieve with cwd=tmp so output stays inside this mini-project
        # (parent workspace may also be an sf project).
        run_sf(
            [
                "project",
                "retrieve",
                "start",
                "--metadata",
                "Settings:Quote",
                "--target-org",
                target_org,
                "--json",
            ],
            cwd=tmp_path,
        )
        hits = list(tmp_path.rglob("Quote.settings-meta.xml"))
        if not hits:
            return False
        text = hits[0].read_text(encoding="utf-8")
        return bool(
            re.search(
                r"<enableQuote>\s*true\s*</enableQuote>",
                text,
                flags=re.IGNORECASE,
            )
        )


def list_opportunity_layout_names(target_org: str) -> list[str]:
    data = run_sf(
        [
            "org",
            "list",
            "metadata",
            "--metadata-type",
            "Layout",
            "--target-org",
            target_org,
            "--json",
        ]
    )
    records = data.get("result") or []
    if isinstance(records, dict):
        records = records.get("layouts") or records.get("result") or []
    names: list[str] = []
    for rec in records:
        full = rec.get("fullName") or ""
        if not full:
            continue
        # Opportunity layouts are named Opportunity-<Layout Label>
        if full.startswith("Opportunity-"):
            names.append(full)
    return sorted(set(names))


def layouts_already_have_quotes(target_org: str, layout_names: list[str]) -> bool:
    """True when every Opportunity layout already includes RelatedQuoteList.

    Uses a lightweight Metadata retrieve into a temp project; returns False on
    any retrieve/parse issue so the main path can still patch.
    """
    if not layout_names:
        return False
    with tempfile.TemporaryDirectory(prefix="opp-quotes-check-") as tmp:
        tmp_path = Path(tmp)
        project = tmp_path / "project"
        (project / "force-app" / "main" / "default").mkdir(parents=True)
        (project / "sfdx-project.json").write_text(
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
        batch_size = 20
        try:
            for i in range(0, len(layout_names), batch_size):
                batch = layout_names[i : i + batch_size]
                meta_args: list[str] = []
                for name in batch:
                    meta_args.extend(["--metadata", f"Layout:{name}"])
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
                    cwd=project,
                )
        except RuntimeError as exc:
            print(f"Quotes short-circuit check failed; will continue. ({exc})", flush=True)
            return False

        layout_files = sorted(project.rglob("Opportunity-*.layout-meta.xml"))
        if len(layout_files) < len(layout_names):
            print(
                f"Quotes short-circuit: retrieved {len(layout_files)}/"
                f"{len(layout_names)} layouts — will continue.",
                flush=True,
            )
            return False
        missing = [p.name for p in layout_files if "RelatedQuoteList" not in p.read_text(encoding="utf-8")]
        if missing:
            print(
                f"Quotes short-circuit: {len(missing)} layout(s) lack RelatedQuoteList.",
                flush=True,
            )
            return False
        return True


def patch_layout_xml(text: str) -> tuple[str, bool]:
    """Return (new_text, changed)."""
    if "RelatedQuoteList" in text:
        return text, False

    block = RELATED_QUOTE_BLOCK.rstrip("\n") + "\n"

    # Insert after the last </relatedLists>, else before </Layout>
    matches = list(re.finditer(r"</relatedLists>\s*", text))
    if matches:
        last = matches[-1]
        insert_at = last.end()
        new_text = text[:insert_at] + block + text[insert_at:]
        return new_text, True

    close = re.search(r"</Layout>\s*$", text)
    if not close:
        raise ValueError("No </Layout> closing tag found")
    new_text = text[: close.start()] + block + text[close.start() :]
    return new_text, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-org", required=True, help="sf org alias or username")
    args = parser.parse_args()
    target = args.target_org

    print(f"Checking Quotes enabled on {target}...")
    if not quotes_enabled(target):
        print(
            "Quotes are not enabled (enableQuote!=true). "
            "Deploy gold settings first:\n"
            "  python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/"
            "deploy_org_settings_gold.py --target-org "
            f"{target}",
            file=sys.stderr,
        )
        return 1

    print("Listing Opportunity layouts...")
    layout_names = list_opportunity_layout_names(target)
    if not layout_names:
        print("No Opportunity layouts found.", file=sys.stderr)
        return 1
    print(f"Found {len(layout_names)} Opportunity layout(s).")

    print("Checking whether RelatedQuoteList is already on all layouts...")
    if layouts_already_have_quotes(target, layout_names):
        print(
            f"Done. updated=0 already-present={len(layout_names)} "
            "(skip retrieve/deploy — all layouts have RelatedQuoteList)."
        )
        return 0

    with tempfile.TemporaryDirectory(prefix="opp-layouts-") as tmp:
        tmp_path = Path(tmp)
        project = tmp_path / "project"
        layouts_dir = project / "force-app" / "main" / "default" / "layouts"
        layouts_dir.mkdir(parents=True)
        (project / "sfdx-project.json").write_text(
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

        # Retrieve in batches to avoid huge CLI argv
        batch_size = 20
        for i in range(0, len(layout_names), batch_size):
            batch = layout_names[i : i + batch_size]
            meta_args: list[str] = []
            for name in batch:
                meta_args.extend(["--metadata", f"Layout:{name}"])
            print(f"Retrieving layouts {i + 1}-{i + len(batch)}...")
            run_sf(
                [
                    "project",
                    "retrieve",
                    "start",
                    *meta_args,
                    "--target-org",
                    target,
                    "--json",
                ],
                cwd=project,
            )

        layout_files = sorted(layouts_dir.glob("Opportunity-*.layout-meta.xml"))
        if not layout_files:
            # sf may nest under layouts/ with different casing
            layout_files = sorted(project.rglob("Opportunity-*.layout-meta.xml"))
        if not layout_files:
            print("Retrieve produced no Opportunity layout files.", file=sys.stderr)
            return 1

        updated: list[str] = []
        already: list[str] = []
        for path in layout_files:
            original = path.read_text(encoding="utf-8")
            try:
                new_text, changed = patch_layout_xml(original)
            except ValueError as exc:
                print(f"  skip {path.name}: {exc}", file=sys.stderr)
                continue
            if changed:
                path.write_text(new_text, encoding="utf-8")
                updated.append(path.name)
                print(f"  patched: {path.name}")
            else:
                already.append(path.name)
                print(f"  already has RelatedQuoteList: {path.name}")

        if not updated:
            print(
                f"Done. updated=0 already-present={len(already)} "
                "(nothing to deploy)."
            )
            return 0

        # Deploy only updated files into a clean source-dir
        deploy_root = tmp_path / "deploy"
        deploy_layouts = deploy_root / "force-app" / "main" / "default" / "layouts"
        deploy_layouts.mkdir(parents=True)
        (deploy_root / "sfdx-project.json").write_text(
            (project / "sfdx-project.json").read_text(encoding="utf-8")
        )
        for name in updated:
            src = next(p for p in layout_files if p.name == name)
            shutil.copy2(src, deploy_layouts / name)

        print(f"Deploying {len(updated)} patched layout(s)...")
        result = run_sf(
            [
                "project",
                "deploy",
                "start",
                "--source-dir",
                "force-app/main/default/layouts",
                "--target-org",
                target,
                "--wait",
                "30",
                "--json",
            ],
            check=False,
            cwd=deploy_root,
        )
        status = result.get("status")
        res = result.get("result") or {}
        success = res.get("success")
        if status not in (0, "0", None) or success is False:
            fails = (res.get("details") or {}).get("componentFailures") or []
            print(json.dumps(fails or result, indent=2)[:4000], file=sys.stderr)
            print(
                f"Deploy failed. updated-attempted={len(updated)} "
                f"already-present={len(already)}",
                file=sys.stderr,
            )
            return 1

        print(
            f"Done. updated={len(updated)} already-present={len(already)} "
            "failed=0"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
