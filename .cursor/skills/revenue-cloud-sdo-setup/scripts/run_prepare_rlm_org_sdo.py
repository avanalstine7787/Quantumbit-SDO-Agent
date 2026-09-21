#!/usr/bin/env python3
"""SDO-optimized runner for rlm-base-dev prepare_rlm_org.

Runs prepare_rlm_org steps in order via discrete `cci flow|task run` calls so
the skill can:

  - Preflight-rename Payments Webhook Network (avoid create timeout loops)
  - Expand prepare_billing and skip Robot enable_timeline when Industries
    Timeline Metadata (enableTimelinePref) is already on
  - Skip prepare steps 32–33 (decision tables + catalog index); skill Step 7
    always runs those last, after optional generic products
  - Emit per-step timings
  - Resume from a given step after failure
  - Pass Full vs SDO-fast -o flags without editing cumulusci.yml

Usage (from workspace root or any cwd; --repo-root required if not default):

  python3 scripts/run_prepare_rlm_org_sdo.py \\
    --org SDOTest5 \\
    --repo-root vendor/rlm-base-dev \\
    --profile full \\
    --product-set yes \\
    --timings-file /tmp/prepare_rlm_org_timings.jsonl

Do not pass --org to local-only tasks (handled automatically).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = Path(__file__).resolve().parents[3] / "vendor" / "rlm-base-dev"
STATE_DIR = SKILL_ROOT / ".run-state"
PAYMENTS_DISPLAY_NAME = "Payments Webhook"
PAYMENTS_PREFIX_HINTS = ("sfpwebhook", "payments", "webhook")

# Local-only CCI tasks: never pass --org
LOCAL_ONLY_TASKS = frozenset(
    {
        "revert_payments_site_after_deploy",
        "apply_context_billing_order",
        "revert_network_email_after_deploy",
    }
)

# Top-level prepare_rlm_org steps (cumulusci.yml). prepare_billing is expanded.
PREPARE_RLM_ORG: list[dict[str, Any]] = [
    {"n": 1, "kind": "flow", "name": "prepare_core"},
    {"n": 2, "kind": "flow", "name": "prepare_decision_tables"},
    {"n": 3, "kind": "flow", "name": "prepare_expression_sets"},
    {"n": 4, "kind": "flow", "name": "prepare_payments", "preflight": "payments"},
    {"n": 5, "kind": "task", "name": "deploy_full"},
    {"n": 6, "kind": "flow", "name": "prepare_price_adjustment_schedules"},
    {"n": 7, "kind": "flow", "name": "prepare_quantumbit"},
    {"n": 8, "kind": "flow", "name": "prepare_product_data"},
    {"n": 9, "kind": "flow", "name": "prepare_pricing_data"},
    {"n": 10, "kind": "flow", "name": "prepare_docgen"},
    {"n": 11, "kind": "flow", "name": "prepare_dro"},
    {"n": 12, "kind": "flow", "name": "prepare_tax"},
    {"n": 13, "kind": "billing", "name": "prepare_billing"},
    {"n": 14, "kind": "flow", "name": "prepare_collections"},
    {"n": 15, "kind": "flow", "name": "prepare_analytics"},
    {"n": 16, "kind": "flow", "name": "prepare_clm"},
    {"n": 17, "kind": "flow", "name": "prepare_rating"},
    {"n": 18, "kind": "task", "name": "activate_and_deploy_expression_sets"},
    {"n": 19, "kind": "flow", "name": "prepare_tso"},
    {"n": 20, "kind": "flow", "name": "prepare_procedureplans"},
    {"n": 21, "kind": "flow", "name": "prepare_prm"},
    {"n": 22, "kind": "flow", "name": "prepare_agents"},
    {"n": 23, "kind": "flow", "name": "prepare_constraints"},
    {"n": 24, "kind": "flow", "name": "prepare_guidedselling"},
    {"n": 25, "kind": "flow", "name": "prepare_revenue_settings"},
    {"n": 26, "kind": "flow", "name": "prepare_pricing_discovery"},
    {"n": 27, "kind": "flow", "name": "prepare_large_stx"},
    {"n": 28, "kind": "flow", "name": "prepare_personas"},
    {"n": 29, "kind": "flow", "name": "prepare_ux"},
    {"n": 30, "kind": "flow", "name": "prepare_inapp"},
    {"n": 31, "kind": "flow", "name": "prepare_scratch"},
    # Deferred to skill Step 7 (always last, after optional generic catalog).
    {"n": 32, "kind": "flow", "name": "refresh_all_decision_tables", "defer_step7": True},
    {"n": 33, "kind": "task", "name": "rebuild_search_index", "defer_step7": True},
    {"n": 34, "kind": "flow", "name": "stamp_git_commit"},
]

# prepare_billing substeps — enable_timeline skipped when Timeline Metadata is on
BILLING_SUBSTEPS: list[dict[str, Any]] = [
    {"kind": "task", "name": "deploy_post_billing"},
    {"kind": "task", "name": "insert_billing_data"},
    {"kind": "task", "name": "insert_q3_billing_data"},
    {"kind": "task", "name": "create_sequence_policies"},
    {
        "kind": "task",
        "name": "activate_flow",
        "extra": ["--developer_names", "RLM_Order_to_Billing_Schedule_Flow"],
    },
    {"kind": "task", "name": "activate_default_payment_term"},
    {"kind": "task", "name": "activate_billing_records"},
    {"kind": "task", "name": "enable_timeline", "skip_if_timeline_meta": True},
    {"kind": "task", "name": "deploy_billing_id_settings"},
    {"kind": "task", "name": "deploy_billing_template_settings"},
    {"kind": "task", "name": "deploy_post_billing_ui"},
    {
        "kind": "task",
        "name": "assign_permission_sets",
        "extra": ["--api_names", "RLM_BillingUI"],
    },
    {"kind": "task", "name": "apply_context_billing_order"},
    {"kind": "flow", "name": "prepare_billing_portal"},
]

# SDO-fast profile: skip heavy communities / agents / collections. Keep billing_ui + ux.
FAST_FLAGS: list[tuple[str, str]] = [
    ("payments", "false"),
    ("billing_portal", "false"),
    ("prm", "false"),
    ("agents", "false"),
    ("collections", "false"),
]


@dataclass
class RunContext:
    org: str
    sf_org: str
    repo: Path
    profile: str
    product_set: bool
    timings_path: Path
    state_path: Path
    skip_timeline_robot: bool
    dry_run: bool


def parse_json_blob(raw: str) -> dict:
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"no JSON in output: {raw[:400]}")
    data, _ = decoder.raw_decode(raw[start:])
    return data


def run_cmd(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def log_timing(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")
    print(json.dumps(event, default=str), flush=True)


def cci_option_args(ctx: RunContext) -> list[str]:
    opts: list[str] = []
    if not ctx.product_set:
        opts += ["-o", "qb", "false", "-o", "constraints_data", "false"]
    if ctx.profile == "fast":
        for key, val in FAST_FLAGS:
            opts += ["-o", key, val]
    return opts


def build_cci_cmd(
    ctx: RunContext,
    kind: str,
    name: str,
    extra: list[str] | None = None,
) -> list[str]:
    cmd = ["cci", kind, "run", name]
    if name not in LOCAL_ONLY_TASKS:
        cmd += ["--org", ctx.org]
    cmd += ["--no-prompt"]
    cmd += cci_option_args(ctx)
    # Task-specific options: CumulusCI uses -o option_name value for task options too
    if extra:
        # Convert --developer_names X into -o developer_names X
        i = 0
        while i < len(extra):
            flag = extra[i]
            if flag.startswith("--") and i + 1 < len(extra):
                opt_name = flag.lstrip("-")
                cmd += ["-o", opt_name, extra[i + 1]]
                i += 2
            else:
                cmd.append(flag)
                i += 1
    return cmd


def timeline_metadata_enabled(sf_org: str) -> bool:
    """Return True if Industries enableTimelinePref is already true."""
    with __import__("tempfile").TemporaryDirectory() as tmp:
        out = Path(tmp) / "settings"
        proc = run_cmd(
            [
                "sf",
                "project",
                "retrieve",
                "start",
                "--metadata",
                "Settings:Industries",
                "--target-org",
                sf_org,
                "--output-dir",
                str(out),
                "--json",
            ]
        )
        if proc.returncode != 0:
            print(
                f"WARN: could not retrieve Industries settings ({proc.stderr[:200]}); "
                "assuming Timeline Metadata NOT confirmed — will still skip Robot "
                "only if --skip-timeline-robot was forced.",
                file=sys.stderr,
            )
            return False
        matches = list(out.rglob("Industries.settings-meta.xml"))
        if not matches:
            return False
        xml = matches[0].read_text(encoding="utf-8")
        compact = "".join(xml.split())
        return "<enableTimelinePref>true</enableTimelinePref>" in compact


def payments_preflight(sf_org: str, *, dry_run: bool) -> dict[str, Any]:
    """Rename Live payments webhook Network display Name to Payments Webhook if needed."""
    q = (
        "SELECT Id, Name, UrlPathPrefix, Status FROM Network "
        "WHERE Status = 'Live' ORDER BY LastModifiedDate DESC"
    )
    proc = run_cmd(
        ["sf", "data", "query", "--target-org", sf_org, "--json", "-q", q]
    )
    result: dict[str, Any] = {"action": "none", "networks": []}
    if proc.returncode != 0:
        result["error"] = (proc.stderr or proc.stdout)[:500]
        print(f"WARN: payments preflight query failed: {result['error']}", file=sys.stderr)
        return result
    try:
        data = parse_json_blob(proc.stdout or proc.stderr)
        records = (data.get("result") or {}).get("records") or []
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        return result

    result["networks"] = [
        {"Id": r.get("Id"), "Name": r.get("Name"), "UrlPathPrefix": r.get("UrlPathPrefix")}
        for r in records
    ]

    exact = [r for r in records if (r.get("Name") or "") == PAYMENTS_DISPLAY_NAME]
    if exact:
        result["action"] = "already_named"
        result["id"] = exact[0]["Id"]
        print(f"Payments preflight: Network already named '{PAYMENTS_DISPLAY_NAME}' ({exact[0]['Id']})")
        return result

    candidates = []
    for r in records:
        prefix = (r.get("UrlPathPrefix") or "").lower()
        name = (r.get("Name") or "").lower()
        if any(h in prefix for h in PAYMENTS_PREFIX_HINTS) or any(
            h in name for h in ("sfpwebhook", "payment", "webhook")
        ):
            candidates.append(r)

    if not candidates:
        print("Payments preflight: no existing Live payments Network found — create will run normally")
        result["action"] = "none_found"
        return result

    target = candidates[0]
    result["id"] = target["Id"]
    result["from_name"] = target.get("Name")
    print(
        f"Payments preflight: renaming Network {target['Id']} "
        f"'{target.get('Name')}' → '{PAYMENTS_DISPLAY_NAME}'"
    )
    if dry_run:
        result["action"] = "would_rename"
        return result

    upd = run_cmd(
        [
            "sf",
            "data",
            "update",
            "record",
            "--sobject",
            "Network",
            "--record-id",
            target["Id"],
            "--values",
            f"Name='{PAYMENTS_DISPLAY_NAME}'",
            "--target-org",
            sf_org,
            "--json",
        ]
    )
    if upd.returncode != 0:
        result["action"] = "rename_failed"
        result["error"] = (upd.stderr or upd.stdout)[:500]
        print(f"WARN: rename failed: {result['error']}", file=sys.stderr)
        return result
    result["action"] = "renamed"
    print("Payments preflight: rename succeeded")
    return result


def write_state(ctx: RunContext, payload: dict[str, Any]) -> None:
    ctx.state_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_one(
    ctx: RunContext,
    *,
    step_n: int,
    label: str,
    kind: str,
    name: str,
    extra: list[str] | None = None,
) -> int:
    cmd = build_cci_cmd(ctx, kind, name, extra)
    start = time.time()
    log_timing(
        ctx.timings_path,
        {
            "event": "step_start",
            "step": step_n,
            "label": label,
            "kind": kind,
            "name": name,
            "cmd": cmd,
            "epoch": int(start),
        },
    )
    if ctx.dry_run:
        print("DRY-RUN:", " ".join(cmd))
        log_timing(
            ctx.timings_path,
            {
                "event": "step_end",
                "step": step_n,
                "label": label,
                "name": name,
                "seconds": 0,
                "exit": 0,
                "dry_run": True,
            },
        )
        return 0

    proc = run_cmd(cmd, cwd=ctx.repo)
    # Stream a short tail for visibility
    out = (proc.stdout or "") + (proc.stderr or "")
    if out:
        tail = "\n".join(out.splitlines()[-40:])
        print(tail)
    elapsed = int(time.time() - start)
    log_timing(
        ctx.timings_path,
        {
            "event": "step_end",
            "step": step_n,
            "label": label,
            "name": name,
            "seconds": elapsed,
            "exit": proc.returncode,
        },
    )
    return proc.returncode


def run_billing(ctx: RunContext, step_n: int) -> int:
    timeline_on = ctx.skip_timeline_robot
    if timeline_on:
        probed = timeline_metadata_enabled(ctx.sf_org)
        print(f"Timeline Metadata probe enableTimelinePref={probed}")
        if not probed:
            print(
                "WARN: Timeline Metadata not confirmed true; still skipping Robot "
                "enable_timeline per SDO profile (gold Industries should have set it). "
                "If billing UI deploy fails for timeline, re-run gold Industries then resume.",
                file=sys.stderr,
            )
        # SDO profile: always skip Robot when orchestrator is used (gold path).
        skip_robot = True
    else:
        skip_robot = False

    for sub in BILLING_SUBSTEPS:
        name = sub["name"]
        label = f"{step_n}:{name}"
        if sub.get("skip_if_timeline_meta") and skip_robot:
            log_timing(
                ctx.timings_path,
                {
                    "event": "step_skip",
                    "step": step_n,
                    "label": label,
                    "name": name,
                    "reason": "timeline_metadata_sdo_skip_robot",
                },
            )
            print(f"SKIP {label} (Timeline via Metadata; not invoking Robot)")
            continue
        ec = run_one(
            ctx,
            step_n=step_n,
            label=label,
            kind=sub["kind"],
            name=name,
            extra=sub.get("extra"),
        )
        if ec != 0:
            return ec
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="CCI org alias")
    parser.add_argument(
        "--sf-org",
        default="",
        help="sf CLI username/alias for preflight queries (default: same as --org)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO,
        help="Path to vendor/rlm-base-dev",
    )
    parser.add_argument(
        "--profile",
        choices=("full", "fast"),
        default="full",
        help="full = default feature flags; fast = skip payments/billing_portal/prm/agents/collections",
    )
    parser.add_argument(
        "--product-set",
        choices=("yes", "no"),
        default="yes",
        help="yes = qb/constraints_data defaults; no = -o qb false -o constraints_data false",
    )
    parser.add_argument(
        "--from-step",
        type=int,
        default=1,
        help="Resume from this prepare_rlm_org step number (1-34)",
    )
    parser.add_argument(
        "--to-step",
        type=int,
        default=34,
        help="Stop after this prepare_rlm_org step number",
    )
    parser.add_argument(
        "--timings-file",
        type=Path,
        default=Path("/tmp/prepare_rlm_org_sdo_timings.jsonl"),
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=STATE_DIR / "last-prepare-rlm-org.json",
        help="Written on success/failure for resume and timings (not Step 7 gating)",
    )
    parser.add_argument(
        "--skip-timeline-robot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip enable_timeline Robot when using SDO Metadata Timeline (default: true)",
    )
    parser.add_argument(
        "--skip-payments-preflight",
        action="store_true",
        help="Do not rename existing payments Network before prepare_payments",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    if not (repo / "cumulusci.yml").is_file():
        print(f"ERROR: cumulusci.yml not found under {repo}", file=sys.stderr)
        return 2

    ctx = RunContext(
        org=args.org,
        sf_org=args.sf_org or args.org,
        repo=repo,
        profile=args.profile,
        product_set=args.product_set == "yes",
        timings_path=args.timings_file,
        state_path=args.state_file,
        skip_timeline_robot=args.skip_timeline_robot,
        dry_run=args.dry_run,
    )

    log_timing(
        ctx.timings_path,
        {
            "event": "run_start",
            "org": ctx.org,
            "sf_org": ctx.sf_org,
            "profile": ctx.profile,
            "product_set": ctx.product_set,
            "from_step": args.from_step,
            "to_step": args.to_step,
            "repo": str(repo),
            "epoch": int(time.time()),
        },
    )

    completed: list[int] = []
    skipped: list[int] = []
    run_start = time.time()

    for step in PREPARE_RLM_ORG:
        n = step["n"]
        if n < args.from_step or n > args.to_step:
            continue

        if step.get("defer_step7"):
            label = f"{n}:{step['name']}"
            log_timing(
                ctx.timings_path,
                {
                    "event": "step_skip",
                    "step": n,
                    "label": label,
                    "name": step["name"],
                    "reason": "deferred_to_skill_step_7",
                },
            )
            print(f"SKIP {label} (deferred to skill Step 7 — last step of the full setup)")
            skipped.append(n)
            continue

        if step.get("preflight") == "payments" and not args.skip_payments_preflight:
            # Only relevant when payments feature is on (full profile)
            if ctx.profile == "full":
                pf = payments_preflight(ctx.sf_org, dry_run=ctx.dry_run)
                log_timing(
                    ctx.timings_path,
                    {"event": "payments_preflight", "step": n, **pf},
                )

        if step["kind"] == "billing":
            ec = run_billing(ctx, n)
        else:
            ec = run_one(
                ctx,
                step_n=n,
                label=f"{n}:{step['name']}",
                kind=step["kind"],
                name=step["name"],
            )

        if ec != 0:
            log_timing(
                ctx.timings_path,
                {
                    "event": "run_failed",
                    "step": n,
                    "name": step["name"],
                    "exit": ec,
                    "completed_steps": completed,
                    "seconds_total": int(time.time() - run_start),
                },
            )
            if not ctx.dry_run:
                write_state(
                    ctx,
                    {
                        "org": ctx.org,
                        "sf_org": ctx.sf_org,
                        "profile": ctx.profile,
                        "product_set": ctx.product_set,
                        "status": "failed",
                        "failed_step": n,
                        "failed_name": step["name"],
                        "completed_steps": completed,
                        "skipped_steps": skipped,
                        "resume_hint": f"--from-step {n}",
                        "timings_file": str(ctx.timings_path),
                    },
                )
            print(
                f"FAILED at step {n} ({step['name']}) exit={ec}. "
                f"Resume with --from-step {n} after fixing, or --from-step {n + 1} "
                f"to skip (enable_timeline already handled by orchestrator).",
                file=sys.stderr,
            )
            return ec

        completed.append(n)

    total = int(time.time() - run_start)
    if not ctx.dry_run:
        write_state(
            ctx,
            {
                "org": ctx.org,
                "sf_org": ctx.sf_org,
                "profile": ctx.profile,
                "product_set": ctx.product_set,
                "status": "success",
                "completed_steps": completed,
                "skipped_steps": skipped,
                "seconds_total": total,
                "timings_file": str(ctx.timings_path),
                "epoch": int(time.time()),
            },
        )
    log_timing(
        ctx.timings_path,
        {
            "event": "run_success",
            "completed_steps": completed,
            "skipped_steps": skipped,
            "seconds_total": total,
            "dry_run": ctx.dry_run,
        },
    )
    print(f"SUCCESS: prepare_rlm_org SDO orchestrator finished in {total}s")
    if not ctx.dry_run:
        print(f"State written: {ctx.state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
