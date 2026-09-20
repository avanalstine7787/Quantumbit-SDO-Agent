#!/usr/bin/env python3
"""Assign Revenue Cloud / Billing / Agentforce admin access to all active users.

Admin-for-everyone: discovers matching Permission Set Licenses and Permission Sets
in the target org, assigns PSLs first, then permission sets. Seat exhaustion and
missing names are reported; they do not abort the run.

Requires Salesforce CLI (`sf`) on PATH and an authenticated target org.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
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

AGENTFORCE_PS_PATTERNS: list[str] = [
    "agentforce",
    "einstein",
    "genai",
    "prompttemplate",
    "manage ai agents",
]

EXCLUDE_USERNAME_SUBSTRINGS: list[str] = [
    "autoproc@",
    "automatedprocess",
    "platformintegration",
    "chatterguest",
    "chatterfree",
]


@dataclass
class Report:
    users_considered: int = 0
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


def run_sf(args: list[str], target_org: str | None = None) -> dict[str, Any]:
    cmd = ["sf", *args, "--json"]
    if target_org:
        cmd.extend(["--target-org", target_org])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
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
    # sf data create record --sobject X --values "Field=Value Field2=Value2"
    value_str = " ".join(f"{k}={v}" for k, v in values.items())
    return run_sf(
        ["data", "create", "record", "--sobject", sobject, "--values", value_str],
        target_org,
    )


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
        # Skip unusable licenses (0 seats) — assigning them only produces errors
        if int(r.get("TotalLicenses") or 0) <= 0:
            continue
        if psl_matches(r.get("MasterLabel") or "", r.get("DeveloperName") or ""):
            matched.append(r)
    return matched


def discover_permsets(target_org: str) -> list[dict[str, Any]]:
    names = "','".join(PERMISSION_SET_NAMES)
    named = query_data(
        f"SELECT Id, Name, Label FROM PermissionSet WHERE Name IN ('{names}') AND IsOwnedByProfile = false",
        target_org,
    )
    # Agentforce / Einstein pattern scan (broader set; filter in Python)
    extra = query_data(
        "SELECT Id, Name, Label FROM PermissionSet WHERE IsOwnedByProfile = false "
        "AND (Name LIKE '%Agentforce%' OR Name LIKE '%Einstein%' OR Name LIKE '%GenAI%' "
        "OR Name LIKE '%Prompt%' OR Label LIKE '%Agentforce%' OR Label LIKE '%Einstein%' "
        "OR Label LIKE '%AI Agent%')",
        target_org,
    )
    by_id: dict[str, dict[str, Any]] = {r["Id"]: r for r in named}
    for r in extra:
        label = f"{r.get('Name') or ''} {r.get('Label') or ''}".lower()
        if any(p in label for p in AGENTFORCE_PS_PATTERNS):
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


def assign_all(target_org: str, dry_run: bool = False) -> Report:
    report = Report()
    users = query_data(
        "SELECT Id, Username, Name, UserType, Profile.Name FROM User WHERE IsActive = true",
        target_org,
    )
    users = [u for u in users if not is_excluded_user(u)]
    report.users_considered = len(users)

    psls = discover_psls(target_org)
    permsets = discover_permsets(target_org)
    report.psls_found = [f"{p.get('MasterLabel')} ({p.get('DeveloperName')})" for p in psls]
    report.permsets_found = [f"{p.get('Name')}" for p in permsets]

    existing_psl = existing_psl_assignments(target_org)
    existing_ps = existing_ps_assignments(target_org)

    # Track used seats locally so we stop when TotalLicenses is hit mid-run
    used: dict[str, int] = {
        p["Id"]: int(p.get("UsedLicenses") or 0) for p in psls
    }
    totals: dict[str, int] = {
        p["Id"]: int(p.get("TotalLicenses") or 0) for p in psls
    }

    for user in users:
        uid = user["Id"]
        uname = user.get("Username") or uid

        for psl in psls:
            pid = psl["Id"]
            label = psl.get("MasterLabel") or psl.get("DeveloperName")
            if (uid, pid) in existing_psl:
                report.psl_skipped_existing += 1
                continue
            if totals.get(pid, 0) > 0 and used.get(pid, 0) >= totals[pid]:
                report.psl_skipped_seats += 1
                msg = f"PSL seat exhausted: {label} — skipped {uname}"
                if msg not in report.seat_exhaustion:
                    report.seat_exhaustion.append(msg)
                continue
            if dry_run:
                report.psl_assigned += 1
                used[pid] = used.get(pid, 0) + 1
                continue
            try:
                create_record(
                    "PermissionSetLicenseAssign",
                    {
                        "AssigneeId": uid,
                        "PermissionSetLicenseId": pid,
                    },
                    target_org,
                )
                report.psl_assigned += 1
                used[pid] = used.get(pid, 0) + 1
                existing_psl.add((uid, pid))
            except Exception as exc:  # noqa: BLE001 — continue on per-user failures
                err = str(exc)
                if "LICENSE_LIMIT" in err.upper() or "LICENSE" in err.upper():
                    report.psl_skipped_seats += 1
                    report.seat_exhaustion.append(f"{label} — {uname}: {err}")
                    used[pid] = totals.get(pid, used.get(pid, 0))
                else:
                    report.psl_errors.append(f"{uname} / {label}: {err}")

        for ps in permsets:
            psid = ps["Id"]
            name = ps.get("Name") or psid
            if (uid, psid) in existing_ps:
                report.ps_skipped_existing += 1
                continue
            if dry_run:
                report.ps_assigned += 1
                continue
            try:
                # Prefer CLI assign when possible for clearer errors
                run_sf(
                    ["org", "assign", "permset", "--name", name, "--on-behalf-of", uname],
                    target_org,
                )
                report.ps_assigned += 1
                existing_ps.add((uid, psid))
            except Exception:
                try:
                    create_record(
                        "PermissionSetAssignment",
                        {"AssigneeId": uid, "PermissionSetId": psid},
                        target_org,
                    )
                    report.ps_assigned += 1
                    existing_ps.add((uid, psid))
                except Exception as exc:  # noqa: BLE001
                    report.ps_errors.append(f"{uname} / {name}: {exc}")

    return report


def print_report(report: Report, dry_run: bool) -> None:
    prefix = "[dry-run] " if dry_run else ""
    print(f"{prefix}Users considered: {report.users_considered}")
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
