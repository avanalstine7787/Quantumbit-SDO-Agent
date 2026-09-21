---
name: revenue-cloud-sdo-setup
description: >
  Sets up Salesforce Agentforce Revenue Management, Revenue Cloud, and Salesforce
  Billing in a target org from Cursor. Asks for the target org first, prompts org
  authorization, assigns admin-for-everyone Revenue Cloud permissions, follows
  Salesforce Help rev_agent_setup, always deploys QuantumBit rlm-base-dev (SDO
  profile) with an optional QuantumBit product set, optionally launches RLM Generic
  Demo Products, then always refreshes decision tables / rebuilds the PCM search
  index. Use when the user asks to set up Revenue Cloud, Agentforce Revenue
  Management, ARM, RLM, Salesforce Billing, QuantumBit, rlm-base-dev, or generic
  demo products on an SDO or demo org.
---

# Revenue Cloud SDO Setup (Cursor Agent)

You are a **Cursor setup agent** — not an in-org Agentforce agent. Drive org setup
with QX MCP, Salesforce CLI (`sf`), and optionally CumulusCI. Do not create or
deploy `AiAuthoringBundle` / `.agent` files.

## Locked policies

1. **Admin-for-everyone** — Assign the full admin/design-time Revenue Cloud,
   Billing, Pricing, PCM, and Agentforce permission set licenses and permission
   sets to every eligible active user (subject to PSL seats).
2. **Always deploy QuantumBit** — After Steps 1–4, always follow
   [references/quantumbit-deploy.md](references/quantumbit-deploy.md) (clone,
   strip branding, Timeline Metadata, `prepare_rlm_org`, resilient recovery).
   Do not permanently edit upstream `cumulusci.yml`.
3. **Optional QuantumBit product set** — Before `prepare_rlm_org`, ask whether to
   load the QuantumBit demo product dataset. **No** →
   `-o qb false -o constraints_data false`. **Yes** → repository defaults.
4. **Optional generic demo products** — After QuantumBit finishes, ask whether to
   launch `rlm-generic-demo-products`. **Yes** → always sync from upstream per
   [references/generic-demo-products.md](references/generic-demo-products.md)
   (overwrite local skill; commit/push if changed), then run. **No** → skip Step 6.
5. **Always refresh index** — After QuantumBit (and Step 6 if run), always run
   `refresh_all_decision_tables` then `rebuild_search_index`.

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

### Step 5 — Always deploy QuantumBit (optional product set)

After Steps 1–4 succeed, **always** deploy QuantumBit per
[references/quantumbit-deploy.md](references/quantumbit-deploy.md).

Before `prepare_rlm_org`, ask exactly:

> Do you want to deploy the QuantumBit product set (demo products and related product data)?

- **Yes** → `cci flow run prepare_rlm_org --org <cci-alias>` (repository defaults;
  `qb` / `constraints_data` on).
- **No** →
  `cci flow run prepare_rlm_org --org <cci-alias> -o qb false -o constraints_data false`
  (QuantumBit apps/metadata still deploy; skip QB product dataset and constraint
  sample product data).

Do **not** ask whether to deploy the QuantumBit repo itself — that is always on.
Keep `billing_ui`, `ux`, `billing`, etc. at defaults. When finished (success or
documented recovery), continue to **Step 6**.

### Step 6 — Optional RLM Generic Demo Products

After QuantumBit finishes, ask exactly:

> Do you want to launch the RLM Generic Demo Products skill for a custom company catalog?

- **Yes** → Follow [references/generic-demo-products.md](references/generic-demo-products.md):
  1. **Always sync first** from
     https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill
     (clone/pull `vendor/cbs-demo-product-builder-skill`, overwrite
     `.cursor/skills/rlm-generic-demo-products/`). No approval ask.
  2. If `git status` shows changes under that skill path, **automatically**
     commit those files and push to remotes `origin` and `sfemu` (skip missing
     remotes; on push failure report and continue). If unchanged, report already
     current.
  3. **Read** `.cursor/skills/rlm-generic-demo-products/SKILL.md` and run it
     end-to-end against the **already-confirmed** target org (Phase 0 still asks
     for company name + website).
  4. **Phase 4b brand image:** always run org brand-image replace **as written**
     in the generic skill (do not skip if the org already looks rebranded).
- **No** → Skip Step 6; continue to **Step 7**.

### Step 7 — Always refresh decision tables + rebuild product index

After Step 5 (and Step 6 if Yes), **always** run from `vendor/rlm-base-dev`:

```bash
cd vendor/rlm-base-dev
cci flow run refresh_all_decision_tables --org <cci-alias> --no-prompt
cci task run rebuild_search_index --org <cci-alias> --no-prompt
```

Run even if both product asks were No.

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
| Generic demo products | Sync upstream then `.cursor/skills/rlm-generic-demo-products/SKILL.md` (optional ask) |
| Decision tables + PCM index | `cci flow run refresh_all_decision_tables`, `cci task run rebuild_search_index` |

Always use `--json` on `sf` commands. Do not invent Help steps when the article is available.

## Completion summary

When finished, report:

- Target org (username, org Id, alias)
- Permissions: users touched, assignments succeeded, seat-exhaustion skips
- Settings enabled (and which irreversible toggles were confirmed)
- Opportunity layouts: Quotes related list updated count
- Agentforce Revenue setup status
- QuantumBit: always deployed; product set Yes/No (`qb` / `constraints_data`);
  recoveries if any
- Generic demo products: skipped / ran (upstream sync status, company, products, Phase 4b)
- Decision tables refreshed + PCM search index rebuild status
