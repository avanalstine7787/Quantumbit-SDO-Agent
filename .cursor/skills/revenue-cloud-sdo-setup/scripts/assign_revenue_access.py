#!/usr/bin/env python3
"""Assign Revenue Cloud / Billing / Agentforce admin access to System Administrators.

Discovers matching Permission Set Licenses and Permission Sets in the target org,
then assigns PSLs and the permission sets that consume them only to active users
whose profile is System Administrator. Seat exhaustion and missing names are
reported; they do not abort the run.

Uses Salesforce Composite sObject Collections (batches of up to 200) instead of
one CLI create per row. Falls back to single-record create if Composite fails.

Requires Salesforce CLI (`sf`) on PATH and an authenticated target org.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Permission set API names from references/permission-catalog.md
PERMISSION_SET_NAMES: list[str] = [
    "ProductCatalogManagementAdministrator",
    "ProductCatalogManagementViewer",
    "ProductDiscoveryAdmin",
    "ProductDiscoveryUser",
    "CorePricingAdmin",
    "CorePricingDesignTimeUser",
    "CorePricingManager",
    "CorePricingRunTimeUser",
    "BREDesigner",
    "BRERuntime",
    "RevenueLifecycleManagementBillingAdmin",
    "RevenueLifecycleManagementBillingOperations",
    "RevenueLifecycleManagementBillingTaxAdmin",
    "RevenueLifecycleManagementTaxConfiguration",
    "RevenueLifecycleManagementBillingCreateInvoiceFromBillingScheduleApi",
    "RevenueLifecycleManagementBillingVoidPostedInvoiceApi",
    "RevenueLifecycleManagementCreateBillingScheduleFromBillingTransactionApi",
    "RevLifecycleManagementCalculateTaxesApi",
    "RevLifecycleManagementCreateOrderFromQuote",
    "RevLifecycleManagementCoreCPQAssetization",
    "RevLifecycleManagementQuotePricesTaxes",
    "RevLifecycleManagementCalculatePricesApi",
    "RevLifecycleManagementPlaceOrderApi",
    "RevLifecycleManagementCreateContractApi",
    "RevLifecycleManagementInitiateAmendmentApi",
    "RevLifecycleManagementInitiateCancellationApi",
    "RevLifecycleManagementInitiateRenewalApi",
    "RevLifecycleManagementProductAndPriceConfigurationApi",
    "RevLifecycleManagementProductImportApi",
    "OrderSubmitUser",
    "RevLifecycleManagementUsageDesignUser",
    "UsageManagementDesigner",
    "UsageManagementRunTimeUser",
    "RatingAdmin",
    "RatingDesignTimeUser",
    "RatingManager",
    "RatingRunTimeUser",
    "WalletManagementUser",
    "DecimalQuantityDesigntime",
    "DecimalQuantityRuntime",
    "DocGenDesigner",
    "DocGenUser",
    "DocumentBuilderUser",
    "OmniStudioAdmin",
    "AnalyticsStoreUser",
    "DataProcessingEngineUser",
    "CLMAdminUser",
    "CLMRuntimeUser",
    "ClauseDesigner",
    "ClauseUser",
    "DfoAdminUser",
    "DFODesignerUser",
    "DFOManagerOperatorUser",
    "DROOrderSubmitInitiateUser",
    "ObligationAssignee",
    "ObligationManager",
    "ObligationUser",
]

# PSL MasterLabel patterns (case-insensitive substring or exact).
# Keep Revenue Cloud / Billing / Pricing focused; Agentforce patterns are narrow
# to avoid assigning every Einstein add-on in an SDO.
PSL_LABEL_PATTERNS: list[str] = [
    "Revenue Cloud User",
    "Product Catalog Management Administrator",
    "Product Catalog Management Viewer",
    "Salesforce Pricing Design Time",
    "Salesforce Pricing Run Time",
    "Billing",
    "Billing Advanced",
    "Product Discovery User",
    "Product Configuration User",
    "Business Rules Engine Designer",
    "Business Rules Engine Runtime",
    "Data Pipelines Base User",
    "Data Processing Engine",
    "OmniStudio",
    "DocGen Designer",
    "Document Builder User",
    "Rate Management Design Time",
    "Rate Management Run Time",
    "Usage Management Design Time",
    "Usage Management Run Time",
    "Wallet Management User",
    "Decimal Quantity DesignTime User",
    "Decimal Quantity Runtime User",
    "Contract LifeCycle Management User",
    "Clause Management User",
    "Microsoft Word 365",
    "Fulfillment User",
    "Obligation Management User",
    "Agentforce (Default)",
    "Agentforce Platform Developer and Admin",
    "Agentforce Platform User",
    "Einstein Agent",
    "Einstein Prompt Templates",
]

# Explicit Agentforce / Einstein names only — do NOT LIKE-scan %Einstein% on SDOs
# (hundreds of permsets × users makes assign take hours).
AGENTFORCE_PERMISSION_SET_NAMES: list[str] = [
    "AgentforceDefaultAdmin",
    "AgentforceDefaultAgentUser",
    # AgentforceServiceAgentUser requires a bot/user license — skip for Standard users
    "EinsteinGPTPromptTemplateManager",
    "EinsteinGPTPromptTemplateUser",
    "PromptTemplateManager",
    "PromptTemplateUser",
    "ManageAIAgents",
    "AgentPlatformBuilder",
]

EXCLUDE_USERNAME_SUBSTRINGS: list[str] = [
    "autoproc@",
    "automatedprocess",
    "platformintegration",
    "chatterguest",
    "chatterfree",
]

API_VERSION = "67.0"
COMPOSITE_BATCH_SIZE = 200


@dataclass
class Report:
    users_considered: int = 0
    users_skipped_not_admin: int = 0
    psls_found: list[str] = field(default_factory=list)
    permsets_found: list[str] = field(default_factory=list)
    psl_assigned: int = 0
    psl_skipped_existing: int = 0
    psl_skipped_seats: int = 0
    psl_errors: list[str] = field(default_factory=list)
    ps_assigned: int = 0
    ps_skipped_existing: int = 0
    ps_errors: list[str] = field(default_factory=list)
    seat_exhaustion: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    composite_batches: int = 0
    fallback_creates: int = 0


def parse_sf_json(raw: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0:
        start = raw.find("[")
    if start < 0:
        raise RuntimeError(f"sf returned no JSON: {raw[:500]}")
    data, _ = decoder.raw_decode(raw[start:])
    if isinstance(data, list):
        return {"result": data}
    return data


def run_sf(args: list[str], target_org: str | None = None) -> dict[str, Any]:
    cmd = ["sf", *args, "--json"]
    if target_org:
        cmd.extend(["--target-org", target_org])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    raw = (proc.stdout or "") + (proc.stderr or "")
    try:
        payload = parse_sf_json(raw) if raw.strip() else {}
    except RuntimeError:
        raise RuntimeError(f"sf did not return JSON: {' '.join(cmd)}\n{raw}") from None
    status = payload.get("status", proc.returncode)
    if status not in (0, "0", None) and "result" not in payload:
        message = payload.get("message") or payload.get("error") or raw
        raise RuntimeError(f"sf command failed ({status}): {message}")
    return payload


def query_data(soql: str, target_org: str) -> list[dict[str, Any]]:
    payload = run_sf(["data", "query", "--query", soql], target_org)
    result = payload.get("result") or {}
    return list(result.get("records") or [])


def create_record(sobject: str, values: dict[str, str], target_org: str) -> dict[str, Any]:
    value_str = " ".join(f"{k}={v}" for k, v in values.items())
    return run_sf(
        ["data", "create", "record", "--sobject", sobject, "--values", value_str],
        target_org,
    )


def composite_create(
    sobject: str,
    records: list[dict[str, str]],
    target_org: str,
) -> list[dict[str, Any]]:
    """Create records via Composite sObject Collections. Returns per-record results."""
    if not records:
        return []

    body = {
        "allOrNone": False,
        "records": [
            {"attributes": {"type": sobject}, **rec} for rec in records
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(body, tmp)
        tmp_path = tmp.name

    try:
        cmd = [
            "sf",
            "api",
            "request",
            "rest",
            f"/services/data/v{API_VERSION}/composite/sobjects",
            "--method",
            "POST",
            "--body",
            f"@{tmp_path}",
            "--target-org",
            target_org,
            "--header",
            "Content-Type:application/json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        raw = (proc.stdout or "") + (proc.stderr or "")
        # Response may be a bare JSON array or wrapped
        try:
            payload = parse_sf_json(raw)
        except RuntimeError as exc:
            raise RuntimeError(f"Composite create failed to parse: {raw[:1500]}") from exc

        # Prefer array result
        if isinstance(payload.get("result"), list):
            return list(payload["result"])
        # Bare list was wrapped as {"result": [...]} by parse_sf_json
        # Or response is {"hasErrors":..., "results":[...]}
        if "results" in payload:
            return list(payload["results"])
        # Some CLI versions print the array as top-level via result key missing —
        # try decoding array directly from raw
        arr_start = raw.find("[")
        if arr_start >= 0:
            arr, _ = json.JSONDecoder().raw_decode(raw[arr_start:])
            if isinstance(arr, list):
                return list(arr)
        raise RuntimeError(f"Unexpected Composite response: {raw[:1500]}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def is_system_admin(user: dict[str, Any]) -> bool:
    profile = user.get("Profile") or {}
    name = (profile.get("Name") or "").strip().lower()
    return name == "system administrator"


def is_excluded_user(user: dict[str, Any]) -> bool:
    username = (user.get("Username") or "").lower()
    user_type = (user.get("UserType") or "").lower()
    if user_type in {
        "automatedprocess",
        "cspliteportal",
        "csnonly",
        "chatterfree",
        "chatterguest",
        "guest",
    }:
        return True
    for needle in EXCLUDE_USERNAME_SUBSTRINGS:
        if needle in username:
            return True
    return False


def psl_matches(master_label: str, developer_name: str) -> bool:
    label = master_label or ""
    dev = developer_name or ""
    combined = f"{label} {dev}".lower()
    for pattern in PSL_LABEL_PATTERNS:
        if pattern.lower() in combined or pattern.lower() == label.lower():
            return True
    return False


def discover_psls(target_org: str) -> list[dict[str, Any]]:
    try:
        records = query_data(
            "SELECT Id, DeveloperName, MasterLabel, TotalLicenses, UsedLicenses, Status "
            "FROM PermissionSetLicense",
            target_org,
        )
    except RuntimeError:
        records = query_data(
            "SELECT Id, DeveloperName, MasterLabel, TotalLicenses, UsedLicenses "
            "FROM PermissionSetLicense",
            target_org,
        )
    matched = []
    for r in records:
        status = (r.get("Status") or "Active").lower()
        if status not in {"active", ""}:
            continue
        if int(r.get("TotalLicenses") or 0) <= 0:
            continue
        if psl_matches(r.get("MasterLabel") or "", r.get("DeveloperName") or ""):
            matched.append(r)
    return matched


def discover_permsets(target_org: str) -> list[dict[str, Any]]:
    all_names = list(dict.fromkeys(PERMISSION_SET_NAMES + AGENTFORCE_PERMISSION_SET_NAMES))
    by_id: dict[str, dict[str, Any]] = {}
    chunk_size = 100
    for i in range(0, len(all_names), chunk_size):
        chunk = all_names[i : i + chunk_size]
        names = "','".join(chunk)
        named = query_data(
            f"SELECT Id, Name, Label FROM PermissionSet WHERE Name IN ('{names}') "
            "AND IsOwnedByProfile = false",
            target_org,
        )
        for r in named:
            by_id[r["Id"]] = r
    return list(by_id.values())


def existing_psl_assignments(target_org: str) -> set[tuple[str, str]]:
    records = query_data(
        "SELECT AssigneeId, PermissionSetLicenseId FROM PermissionSetLicenseAssign",
        target_org,
    )
    return {(r["AssigneeId"], r["PermissionSetLicenseId"]) for r in records}


def existing_ps_assignments(target_org: str) -> set[tuple[str, str]]:
    records = query_data(
        "SELECT AssigneeId, PermissionSetId FROM PermissionSetAssignment",
        target_org,
    )
    return {(r["AssigneeId"], r["PermissionSetId"]) for r in records}


def _err_text(result: dict[str, Any]) -> str:
    errors = result.get("errors") or []
    if isinstance(errors, list) and errors:
        parts = []
        for e in errors:
            if isinstance(e, dict):
                parts.append(e.get("message") or e.get("statusCode") or str(e))
            else:
                parts.append(str(e))
        return "; ".join(parts)
    return str(result)


def flush_composite_batch(
    sobject: str,
    pending: list[dict[str, Any]],
    target_org: str,
    report: Report,
    *,
    kind: str,
    used: dict[str, int] | None = None,
    totals: dict[str, int] | None = None,
) -> None:
    """Flush a pending Composite batch. pending items: {fields, meta}.

    Seat counts for PSLs are pre-reserved when items are queued; on success we do
    not increment ``used`` again. On license failure we release the reservation.
    """
    if not pending:
        return

    def release_seat(item: dict[str, Any]) -> None:
        if kind != "psl" or used is None:
            return
        pid = item["fields"]["PermissionSetLicenseId"]
        used[pid] = max(0, used.get(pid, 0) - 1)

    for i in range(0, len(pending), COMPOSITE_BATCH_SIZE):
        chunk = pending[i : i + COMPOSITE_BATCH_SIZE]
        records = [item["fields"] for item in chunk]
        report.composite_batches += 1
        try:
            results = composite_create(sobject, records, target_org)
        except Exception as exc:  # noqa: BLE001
            print(f"Composite batch failed ({kind}), falling back: {exc}", flush=True)
            for item in chunk:
                report.fallback_creates += 1
                try:
                    create_record(sobject, item["fields"], target_org)
                    if kind == "psl":
                        report.psl_assigned += 1
                    else:
                        report.ps_assigned += 1
                except Exception as row_exc:  # noqa: BLE001
                    uname = item["meta"]["username"]
                    label = item["meta"]["label"]
                    err = str(row_exc)
                    release_seat(item)
                    if kind == "psl" and (
                        "LICENSE_LIMIT" in err.upper() or "LICENSE" in err.upper()
                    ):
                        report.psl_skipped_seats += 1
                        report.seat_exhaustion.append(f"{label} — {uname}: {err}")
                        if used is not None and totals is not None:
                            pid = item["fields"]["PermissionSetLicenseId"]
                            used[pid] = totals.get(pid, used.get(pid, 0))
                    elif kind == "psl":
                        report.psl_errors.append(f"{uname} / {label}: {err}")
                    else:
                        report.ps_errors.append(f"{uname} / {label}: {err}")
            continue

        if len(results) != len(chunk):
            print(
                f"Warning: Composite returned {len(results)} results for "
                f"{len(chunk)} {kind} records",
                flush=True,
            )

        for item, result in zip(chunk, results):
            uname = item["meta"]["username"]
            label = item["meta"]["label"]
            if bool(result.get("success")):
                if kind == "psl":
                    report.psl_assigned += 1
                else:
                    report.ps_assigned += 1
                continue

            err = _err_text(result)
            release_seat(item)
            if kind == "psl" and (
                "LICENSE_LIMIT" in err.upper()
                or "LICENSE" in err.upper()
                or "DUPLICATE" in err.upper()
            ):
                if "DUPLICATE" in err.upper():
                    report.psl_skipped_existing += 1
                else:
                    report.psl_skipped_seats += 1
                    report.seat_exhaustion.append(f"{label} — {uname}: {err}")
                    if used is not None and totals is not None:
                        pid = item["fields"]["PermissionSetLicenseId"]
                        used[pid] = totals.get(pid, used.get(pid, 0))
            elif kind == "psl":
                report.psl_errors.append(f"{uname} / {label}: {err}")
            elif "DUPLICATE" in err.upper():
                report.ps_skipped_existing += 1
            else:
                report.ps_errors.append(f"{uname} / {label}: {err}")


def assign_all(target_org: str, dry_run: bool = False) -> Report:
    t0 = time.monotonic()
    report = Report()
    users = query_data(
        "SELECT Id, Username, Name, UserType, Profile.Name FROM User WHERE IsActive = true",
        target_org,
    )
    eligible = [u for u in users if not is_excluded_user(u)]
    users = [u for u in eligible if is_system_admin(u)]
    report.users_skipped_not_admin = len(eligible) - len(users)

    # Prefer the org's default/running user first so scarce seats go to the
    # automation user QuantumBit prepare_rlm_org needs (avoid seat exhaustion).
    running_user_id: str | None = None
    try:
        display = run_sf(["org", "display"], target_org)
        running_user_id = (display.get("result") or {}).get("userId") or None
        if not running_user_id:
            # Fall back: match username from org display
            run_username = ((display.get("result") or {}).get("username") or "").lower()
            for u in users:
                if (u.get("Username") or "").lower() == run_username:
                    running_user_id = u["Id"]
                    break
    except Exception:  # noqa: BLE001
        running_user_id = None

    if running_user_id:
        users = sorted(
            users,
            key=lambda u: (0 if u["Id"] == running_user_id else 1, u.get("Username") or ""),
        )

    report.users_considered = len(users)

    psls = discover_psls(target_org)
    permsets = discover_permsets(target_org)
    report.psls_found = [f"{p.get('MasterLabel')} ({p.get('DeveloperName')})" for p in psls]
    report.permsets_found = [f"{p.get('Name')}" for p in permsets]

    existing_psl = existing_psl_assignments(target_org)
    existing_ps = existing_ps_assignments(target_org)

    used: dict[str, int] = {
        p["Id"]: int(p.get("UsedLicenses") or 0) for p in psls
    }
    totals: dict[str, int] = {
        p["Id"]: int(p.get("TotalLicenses") or 0) for p in psls
    }
    # Reserve 1 seat on scarce licenses for the running user when they are a
    # System Administrator and do not already hold the PSL (TotalLicenses <= 20).
    reserved: dict[str, int] = {}
    admin_ids = {u["Id"] for u in users}
    if running_user_id and running_user_id in admin_ids:
        for p in psls:
            pid = p["Id"]
            total = totals.get(pid, 0)
            if total <= 0 or total > 20:
                continue
            if (running_user_id, pid) in existing_psl:
                continue
            reserved[pid] = 1
    psl_labels = {
        p["Id"]: (p.get("MasterLabel") or p.get("DeveloperName") or p["Id"]) for p in psls
    }
    ps_labels = {p["Id"]: (p.get("Name") or p["Id"]) for p in permsets}

    pending_psl: list[dict[str, Any]] = []
    pending_ps: list[dict[str, Any]] = []

    for user in users:
        uid = user["Id"]
        uname = user.get("Username") or uid
        is_runner = running_user_id is not None and uid == running_user_id

        for psl in psls:
            pid = psl["Id"]
            label = psl_labels[pid]
            if (uid, pid) in existing_psl:
                report.psl_skipped_existing += 1
                continue
            # Effective capacity: leave reserved seats for the running user
            reserve = 0 if is_runner else reserved.get(pid, 0)
            effective_total = max(0, totals.get(pid, 0) - reserve)
            if effective_total > 0 and used.get(pid, 0) >= effective_total:
                report.psl_skipped_seats += 1
                msg = f"PSL seat reserved/exhausted: {label} — skipped {uname}"
                if msg not in report.seat_exhaustion:
                    report.seat_exhaustion.append(msg)
                continue
            if totals.get(pid, 0) > 0 and used.get(pid, 0) >= totals[pid]:
                report.psl_skipped_seats += 1
                msg = f"PSL seat exhausted: {label} — skipped {uname}"
                if msg not in report.seat_exhaustion:
                    report.seat_exhaustion.append(msg)
                continue
            # Reserve seat locally so later users in the same build don't over-queue
            used[pid] = used.get(pid, 0) + 1
            if is_runner and pid in reserved:
                reserved[pid] = 0  # reservation consumed
            if dry_run:
                report.psl_assigned += 1
                continue
            pending_psl.append(
                {
                    "fields": {
                        "AssigneeId": uid,
                        "PermissionSetLicenseId": pid,
                    },
                    "meta": {"username": uname, "label": label},
                }
            )
            existing_psl.add((uid, pid))

        for ps in permsets:
            psid = ps["Id"]
            name = ps_labels[psid]
            if (uid, psid) in existing_ps:
                report.ps_skipped_existing += 1
                continue
            if dry_run:
                report.ps_assigned += 1
                continue
            pending_ps.append(
                {
                    "fields": {"AssigneeId": uid, "PermissionSetId": psid},
                    "meta": {"username": uname, "label": name},
                }
            )
            existing_ps.add((uid, psid))

        # Flush periodically so progress is visible and memory stays bounded
        if not dry_run and (
            len(pending_psl) >= COMPOSITE_BATCH_SIZE
            or len(pending_ps) >= COMPOSITE_BATCH_SIZE
        ):
            flush_composite_batch(
                "PermissionSetLicenseAssign",
                pending_psl,
                target_org,
                report,
                kind="psl",
                used=used,
                totals=totals,
            )
            pending_psl.clear()
            flush_composite_batch(
                "PermissionSetAssignment",
                pending_ps,
                target_org,
                report,
                kind="ps",
            )
            pending_ps.clear()
            print(
                f"Progress: flushed through {uname} "
                f"(PSL +{report.psl_assigned} / PS +{report.ps_assigned}; "
                f"batches={report.composite_batches})",
                flush=True,
            )

    if not dry_run:
        flush_composite_batch(
            "PermissionSetLicenseAssign",
            pending_psl,
            target_org,
            report,
            kind="psl",
            used=used,
            totals=totals,
        )
        flush_composite_batch(
            "PermissionSetAssignment",
            pending_ps,
            target_org,
            report,
            kind="ps",
        )
        print(
            f"Progress: final flush "
            f"(PSL +{report.psl_assigned} / PS +{report.ps_assigned}; "
            f"batches={report.composite_batches})",
            flush=True,
        )

    report.elapsed_seconds = time.monotonic() - t0
    return report


def print_report(report: Report, dry_run: bool) -> None:
    prefix = "[dry-run] " if dry_run else ""
    print(f"{prefix}Users considered (System Administrator): {report.users_considered}")
    print(f"{prefix}Skipped (not System Administrator): {report.users_skipped_not_admin}")
    print(f"{prefix}Elapsed seconds: {report.elapsed_seconds:.1f}")
    print(f"{prefix}Composite batches: {report.composite_batches}")
    print(f"{prefix}Fallback single creates: {report.fallback_creates}")
    print(f"{prefix}PSLs found ({len(report.psls_found)}):")
    for item in report.psls_found:
        print(f"  - {item}")
    print(f"{prefix}Permission sets found ({len(report.permsets_found)}):")
    for item in report.permsets_found:
        print(f"  - {item}")
    print(f"{prefix}PSL assigned: {report.psl_assigned}")
    print(f"{prefix}PSL already present: {report.psl_skipped_existing}")
    print(f"{prefix}PSL skipped (seats): {report.psl_skipped_seats}")
    print(f"{prefix}Permset assigned: {report.ps_assigned}")
    print(f"{prefix}Permset already present: {report.ps_skipped_existing}")
    if report.seat_exhaustion:
        print(f"{prefix}Seat exhaustion details:")
        for item in report.seat_exhaustion:
            print(f"  - {item}")
    if report.psl_errors:
        print(f"{prefix}PSL errors ({len(report.psl_errors)}):")
        for item in report.psl_errors[:50]:
            print(f"  - {item}")
    if report.ps_errors:
        print(f"{prefix}Permset errors ({len(report.ps_errors)}):")
        for item in report.ps_errors[:50]:
            print(f"  - {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-org",
        "-o",
        required=True,
        help="Salesforce CLI alias or username for the target org",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and count assignments without writing",
    )
    args = parser.parse_args()

    try:
        report = assign_all(args.target_org, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_report(report, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
