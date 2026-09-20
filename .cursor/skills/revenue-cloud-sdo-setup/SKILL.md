---
name: revenue-cloud-sdo-setup
description: >
  Sets up Salesforce Agentforce Revenue Management, Revenue Cloud, and Salesforce
  Billing in a target org from Cursor. Asks for the target org first, prompts org
  authorization, assigns admin-for-everyone Revenue Cloud permissions, follows
  Salesforce Help rev_agent_setup, optionally deploys QuantumBit rlm-base-dev with
  the SDO deploy profile, then runs RLM Generic Demo Products and refreshes
  decision tables / rebuilds the PCM search index. Use when the user asks to set up
  Revenue Cloud, Agentforce Revenue Management, ARM, RLM, Salesforce Billing,
  QuantumBit, rlm-base-dev, or generic demo products on an SDO or demo org.
---

# Revenue Cloud SDO Setup (Cursor Agent)

You are a **Cursor setup agent** — not an in-org Agentforce agent. Drive org setup
with QX MCP, Salesforce CLI (`sf`), and optionally CumulusCI. Do not create or
deploy `AiAuthoringBundle` / `.agent` files.

## Locked policies

1. **Admin-for-everyone** — Assign the full admin/design-time Revenue Cloud,
   Billing, Pricing, PCM, and Agentforce permission set licenses and permission
   sets to every eligible active user (subject to PSL seats).
2. **QuantumBit SDO deploy profile** — If the user says Yes to QuantumBit, follow
   [references/quantumbit-deploy.md](references/quantumbit-deploy.md): strip
   QuantumBit Lightning branding, ensure Timeline via Metadata, run
   `prepare_rlm_org` with feature defaults (`billing_ui` / `ux` / `qb` kept on),
   and automatically recover from payments-community and `enable_timeline` Robot
   flakes. Do not permanently edit upstream `cumulusci.yml`.
3. **Generic demo products + index refresh** — After Steps 1–4 (and after
   QuantumBit when included), follow
   [references/generic-demo-products.md](references/generic-demo-products.md):
   run project-local `rlm-generic-demo-products`, then
   `refresh_all_decision_tables` and `rebuild_search_index`.
## Hard gate — first question

On the **first turn**, before any other work:

1. Ask: **What is the target Salesforce org?** (alias, username, or org Id)
2. Prompt authorization immediately:
   - Prefer QX MCP `login_to_org` (and `switch_org` / `list_orgs` as needed)
   - Or `sf org login web --alias <alias> --json` / `sf org login device --json`
   - Then `sf config set target-org <alias> --json` and `sf org display --json`
3. Show username, org Id, and instance URL. Wait for explicit user confirmation.
4. **Do not** assign permissions, enable settings, clone repos, or deploy until
   confirmation succeeds.

## Required references

Read and follow these before mutating the org:

- [references/setup-checklist.md](references/setup-checklist.md)
- [references/permission-catalog.md](references/permission-catalog.md)
- [references/quantumbit-deploy.md](references/quantumbit-deploy.md)
- [references/generic-demo-products.md](references/generic-demo-products.md)
- [references/org-settings-gold/](references/org-settings-gold/) (EFM2 gold Settings XML)
- [references/org-settings-gold/billing-guided-setup.md](references/org-settings-gold/billing-guided-setup.md)

At runtime, re-fetch Salesforce Help and treat it as source of truth:

- https://help.salesforce.com/s/articleView?id=ind.rev_agent_setup.htm&type=5
- https://help.salesforce.com/s/articleView?id=ind.admin_permission_sets.htm&type=5
- https://help.salesforce.com/s/articleView?id=ind.revenue_cloud_permission_sets_table.htm&type=5

If Help content cannot be fetched, use the local checklist as sequencing backup
and tell the user you fell back.

## Workflow

### Step 1 — Prerequisites

After org confirmation:

```bash
sf data query --json -q "SELECT Id, DeveloperName, MasterLabel, TotalLicenses, UsedLicenses FROM PermissionSetLicense WHERE TotalLicenses > 0"
sf org display --json
```

- Confirm Revenue Cloud / Billing / related licenses exist (or warn clearly).
- Confirm the running user can assign permission sets and change Setup.
- Before irreversible toggles, warn and get confirmation:
  - Enable Revenue Cloud Features
  - Enhanced Commerce Orders
  - Transaction processing for quotes and orders

### Step 2 — Admin-for-everyone permissions

Order: **PSLs first, then permission sets**.

1. Discover which catalog entries exist in this org (do not hard-fail on missing names).
2. Run the assignment script from the workspace root (or skill directory):

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/assign_revenue_access.py --target-org <alias>
```

3. Summarize assigned vs skipped (seat exhaustion). Continue even if some seats are full.

See [references/permission-catalog.md](references/permission-catalog.md).

### Step 3 — Initial Revenue Cloud / ARM enablement

Follow [references/setup-checklist.md](references/setup-checklist.md) in order.

After irreversible confirms (Core CPQ / Enhanced Commerce Orders / Transaction
Processor), **deploy the EFM2 gold settings bundle** instead of piecemeal
one-off toggles:

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/deploy_org_settings_gold.py \
  --target-org <alias>
```

Deploy order (handled by the script): Quote → Order → RevenueManagement →
ProductConfigurator → IndustriesPricing → Industries (Timeline pref) → Billing
(portable toggles only; **no** Billing record IDs).

Gold fixtures live in [references/org-settings-gold/](references/org-settings-gold/).
Map Billing Guided Setup assistants in
[billing-guided-setup.md](references/org-settings-gold/billing-guided-setup.md).

Then verify by retrieving the same Settings types and confirming key fields
(`enableCoreCPQ`, `enableProductConfigurator`, `enableSalesforcePricing`,
`enableTimelinePref`, Billing `enable*` flags). Do not require
`enableContextReuse` (omitted from gold when Metadata rejects it).

**Add Quotes related list to Opportunity layouts** (after Quotes are on):

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/add_quotes_related_list_to_opportunity_layouts.py \
  --target-org <alias>
```

Idempotent: appends `RelatedQuoteList` to every Opportunity page layout that
does not already have it.

Continue with BRE/CRE, Context Definitions, Sync Pricing Data, and Agentforce
steps as in the checklist. Warn: `enableTransactionProcessor` is irreversible
(already true on gold).

### Step 4 — Agentforce for Revenue Management

Complete [Set Up Agentforce for Revenue Management](https://help.salesforce.com/s/articleView?id=ind.rev_agent_setup.htm&type=5)
after base Revenue Cloud is enabled. Typical themes (verify against Help each run):

- Einstein Generative AI / Agentforce prerequisites
- Manage AI Agents and related agent permissions
- Revenue agent template / topic / action prerequisites

### Step 5 — QuantumBit optional deploy

After initial setup succeeds, ask exactly:

> Do you want to deploy the QuantumBit repo from https://github.com/bgaldino/rlm-base-dev ?

- **Yes** → Follow [references/quantumbit-deploy.md](references/quantumbit-deploy.md)
  (clone, strip branding, Timeline Metadata, CCI connect, `prepare_rlm_org` with
  SDO recovery rules). When finished (success or documented recovery), continue
  to **Step 6**.
- **No** → Skip QuantumBit and continue to **Step 6** immediately.

### Step 6 — RLM Generic Demo Products

Follow [references/generic-demo-products.md](references/generic-demo-products.md):

1. Ensure `vendor/cbs-demo-product-builder-skill` is cloned and
   `.cursor/skills/rlm-generic-demo-products` points at it.
2. **Read** `.cursor/skills/rlm-generic-demo-products/SKILL.md` and run it
   end-to-end against the **already-confirmed** target org (Phase 0 still asks
   for company name + website).
3. **Phase 4b brand image:** run only if the org is **not** already rebranded
   for that company; skip if it already is. Prefer `QuantumBitSLDSv2` when
   present; otherwise update the active Lightning theme. See
   [generic-demo-products.md](references/generic-demo-products.md).

### Step 7 — Refresh decision tables + rebuild product index

After Step 6 completes, from `vendor/rlm-base-dev` (clone API-matched branch and
CCI-connect if needed; do not run full `prepare_rlm_org` solely for this):

```bash
cd vendor/rlm-base-dev
cci flow run refresh_all_decision_tables --org <cci-alias> --no-prompt
cci task run rebuild_search_index --org <cci-alias> --no-prompt
```

Details: [references/generic-demo-products.md](references/generic-demo-products.md).

## Tooling map

| Need | Prefer |
|------|--------|
| Org auth / switch | QX MCP `login_to_org`, `switch_org`, `list_orgs`; DX `list_all_orgs`, `get_username` |
| Queries / display | `sf data query --json`, `sf org display --json` |
| Perm assignment | `scripts/assign_revenue_access.py`, `sf org assign permset` |
| Gold org settings | `scripts/deploy_org_settings_gold.py` |
| Quotes on Opportunity layouts | `scripts/add_quotes_related_list_to_opportunity_layouts.py` |
| Strip QB branding | `scripts/strip_quantumbit_branding.py` |
| QuantumBit | Shell + CumulusCI in `vendor/rlm-base-dev` |
| Generic demo products | `.cursor/skills/rlm-generic-demo-products/SKILL.md` |
| Decision tables + PCM index | `cci flow run refresh_all_decision_tables`, `cci task run rebuild_search_index` |

Always use `--json` on `sf` commands. Do not invent Help steps when the article is available.

## Completion summary

When finished, report:

- Target org (username, org Id, alias)
- Permissions: users touched, assignments succeeded, seat-exhaustion skips
- Settings enabled (and which irreversible toggles were confirmed)
- Opportunity layouts: Quotes related list updated count
- Agentforce Revenue setup status
- QuantumBit: skipped / succeeded / recovered (branding strip, Timeline Metadata,
  payments or timeline recoveries)
- Generic demo products: company, products created/reused, Phase 4b ran or skipped
- Decision tables refreshed + PCM search index rebuild status
