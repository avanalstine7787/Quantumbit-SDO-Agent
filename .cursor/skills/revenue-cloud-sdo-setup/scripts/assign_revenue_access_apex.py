#!/usr/bin/env python3
"""Fast admin-for-everyone assignment via Anonymous Apex batches."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap


PERMSET_NAMES = [
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
    "OrderSubmitUser",
    "UsageManagementDesigner",
    "UsageManagementRunTimeUser",
    "RatingAdmin",
    "RatingDesignTimeUser",
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
    "ObligationManager",
    "ObligationUser",
]

PSL_LABELS = [
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
    "Data Processing Engine Psl",
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
    "Fulfillment User PSL",
    "Obligation Management User",
    "Agentforce (Default)",
    "Agentforce Platform Developer and Admin",
    "Einstein Agent",
    "Einstein Prompt Templates",
]


def run_sf(args: list[str], target_org: str) -> dict:
    cmd = ["sf", *args, "--target-org", target_org, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    raw = (proc.stdout or proc.stderr or "").strip()
    start = raw.find("{")
    payload = json.loads(raw[start:]) if start >= 0 else {}
    return payload


def build_apex() -> str:
    names_literal = ", ".join(f"'{n}'" for n in PERMSET_NAMES)
    labels_literal = ", ".join(f"'{l}'" for l in PSL_LABELS)
    return textwrap.dedent(
        f"""
        List<String> psNames = new List<String>{{ {names_literal} }};
        List<String> pslLabels = new List<String>{{ {labels_literal} }};

        List<User> users = [
            SELECT Id, Username FROM User
            WHERE IsActive = true AND UserType = 'Standard'
        ];

        List<PermissionSetLicense> psls = [
            SELECT Id, MasterLabel, TotalLicenses, UsedLicenses
            FROM PermissionSetLicense
            WHERE MasterLabel IN :pslLabels AND TotalLicenses > 0
        ];

        List<PermissionSet> psets = [
            SELECT Id, Name FROM PermissionSet
            WHERE Name IN :psNames AND IsOwnedByProfile = false
        ];
        // Agentforce / Einstein Prompt pattern extras
        psets.addAll([
            SELECT Id, Name FROM PermissionSet
            WHERE IsOwnedByProfile = false
            AND (Name LIKE '%Agentforce%' OR Label LIKE '%Agentforce%'
                 OR Name LIKE '%PromptTemplate%' OR Label LIKE '%Prompt Template%')
            LIMIT 50
        ]);

        Set<Id> userIds = new Map<Id, User>(users).keySet();
        Set<Id> pslIds = new Map<Id, PermissionSetLicense>(psls).keySet();
        Set<Id> psIds = new Map<Id, PermissionSet>(psets).keySet();

        Map<Id, Integer> used = new Map<Id, Integer>();
        Map<Id, Integer> total = new Map<Id, Integer>();
        for (PermissionSetLicense p : psls) {{
            used.put(p.Id, Integer.valueOf(p.UsedLicenses));
            total.put(p.Id, Integer.valueOf(p.TotalLicenses));
        }}

        Set<String> existingPsl = new Set<String>();
        for (PermissionSetLicenseAssign a : [
            SELECT AssigneeId, PermissionSetLicenseId
            FROM PermissionSetLicenseAssign
            WHERE AssigneeId IN :userIds AND PermissionSetLicenseId IN :pslIds
        ]) {{
            existingPsl.add(String.valueOf(a.AssigneeId) + ':' + String.valueOf(a.PermissionSetLicenseId));
        }}

        Set<String> existingPs = new Set<String>();
        for (PermissionSetAssignment a : [
            SELECT AssigneeId, PermissionSetId
            FROM PermissionSetAssignment
            WHERE AssigneeId IN :userIds AND PermissionSetId IN :psIds
        ]) {{
            existingPs.add(String.valueOf(a.AssigneeId) + ':' + String.valueOf(a.PermissionSetId));
        }}

        List<PermissionSetLicenseAssign> pslInserts = new List<PermissionSetLicenseAssign>();
        Integer pslSkippedSeats = 0;
        Integer pslSkippedExisting = 0;
        for (User u : users) {{
            for (PermissionSetLicense p : psls) {{
                String key = String.valueOf(u.Id) + ':' + String.valueOf(p.Id);
                if (existingPsl.contains(key)) {{
                    pslSkippedExisting++;
                    continue;
                }}
                Integer uUsed = used.get(p.Id);
                Integer uTotal = total.get(p.Id);
                if (uTotal != null && uUsed != null && uUsed >= uTotal) {{
                    pslSkippedSeats++;
                    continue;
                }}
                pslInserts.add(new PermissionSetLicenseAssign(
                    AssigneeId = u.Id,
                    PermissionSetLicenseId = p.Id
                ));
                used.put(p.Id, (uUsed == null ? 0 : uUsed) + 1);
            }}
        }}

        Integer pslOk = 0;
        Integer pslFail = 0;
        if (!pslInserts.isEmpty()) {{
            Database.SaveResult[] srs = Database.insert(pslInserts, false);
            for (Database.SaveResult sr : srs) {{
                if (sr.isSuccess()) pslOk++; else pslFail++;
            }}
        }}

        List<PermissionSetAssignment> psInserts = new List<PermissionSetAssignment>();
        Integer psSkippedExisting = 0;
        for (User u : users) {{
            for (PermissionSet p : psets) {{
                String key = String.valueOf(u.Id) + ':' + String.valueOf(p.Id);
                if (existingPs.contains(key)) {{
                    psSkippedExisting++;
                    continue;
                }}
                psInserts.add(new PermissionSetAssignment(
                    AssigneeId = u.Id,
                    PermissionSetId = p.Id
                ));
            }}
        }}

        Integer psOk = 0;
        Integer psFail = 0;
        if (!psInserts.isEmpty()) {{
            // chunk to stay under DML row limits
            Integer chunk = 200;
            for (Integer i = 0; i < psInserts.size(); i += chunk) {{
                Integer endIdx = Math.min(i + chunk, psInserts.size());
                List<PermissionSetAssignment> slice = new List<PermissionSetAssignment>();
                for (Integer j = i; j < endIdx; j++) slice.add(psInserts[j]);
                Database.SaveResult[] srs = Database.insert(slice, false);
                for (Database.SaveResult sr : srs) {{
                    if (sr.isSuccess()) psOk++; else psFail++;
                }}
            }}
        }}

        System.debug('USERS=' + users.size());
        System.debug('PSLS_FOUND=' + psls.size());
        System.debug('PERMSETS_FOUND=' + psets.size());
        System.debug('PSL_ASSIGNED=' + pslOk);
        System.debug('PSL_FAIL=' + pslFail);
        System.debug('PSL_SKIP_EXISTING=' + pslSkippedExisting);
        System.debug('PSL_SKIP_SEATS=' + pslSkippedSeats);
        System.debug('PS_ASSIGNED=' + psOk);
        System.debug('PS_FAIL=' + psFail);
        System.debug('PS_SKIP_EXISTING=' + psSkippedExisting);
        """
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-org", "-o", required=True)
    args = parser.parse_args()

    apex = build_apex()
    apex_path = "/tmp/assign_revenue_access.apex"
    with open(apex_path, "w", encoding="utf-8") as fh:
        fh.write(apex)

    payload = run_sf(["apex", "run", "--file", apex_path], args.target_org)
    print(json.dumps(payload, indent=2)[:20000])
    result = payload.get("result") or {}
    logs = result.get("logs") or payload.get("logs") or ""
    if isinstance(logs, str):
        for line in logs.splitlines():
            if any(
                k in line
                for k in (
                    "USERS=",
                    "PSLS_FOUND=",
                    "PERMSETS_FOUND=",
                    "PSL_ASSIGNED=",
                    "PSL_FAIL=",
                    "PSL_SKIP",
                    "PS_ASSIGNED=",
                    "PS_FAIL=",
                    "PS_SKIP",
                    "EXCEPTION",
                    "Error",
                )
            ):
                print(line)
    status = payload.get("status", 1)
    return 0 if status in (0, "0") else 1


if __name__ == "__main__":
    raise SystemExit(main())
