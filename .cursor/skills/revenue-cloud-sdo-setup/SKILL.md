---
name: revenue-cloud-sdo-setup
description: >
  Sets up Salesforce Agentforce Revenue Management, Revenue Cloud, and Salesforce
  Billing in a target org from Cursor. Asks for the target org first, prompts org
  authorization, assigns Revenue Cloud permission set licenses and permission sets
  to System Administrators only, follows
  Salesforce Help rev_agent_setup, always deploys QuantumBit rlm-base-dev (SDO
  profile) via the SDO prepare orchestrator with an optional QuantumBit product
  set and Full vs fast profile, optionally launches RLM Generic Demo Products,
  then always refreshes decision tables / rebuilds the PCM search index as the
  last step. Use when the user asks to set up Revenue Cloud, Agentforce Revenue
  Management, ARM, RLM, Salesforce Billing, QuantumBit, rlm-base-dev, or generic
  demo products on an SDO or demo org.
---

# Revenue Cloud SDO Setup (Cursor Agent)

You are a **Cursor setup agent** — not an in-org Agentforce agent. Drive org setup
with QX MCP, Salesforce CLI (`sf`), and optionally CumulusCI. Do not create or
deploy `AiAuthoringBundle` / `.agent` files.

## Locked policies

1. **System Administrators only** — Assign the catalog Revenue Cloud, Billing,
   Pricing, PCM, and Agentforce permission set licenses, and the permission sets
   that consume them, only to active users whose profile is System Administrator
   (subject to PSL seats). Non-admin demo users do not receive these licenses.
2. **Always deploy QuantumBit** — After Steps 1–4, always follow
   [references/quantumbit-deploy.md](references/quantumbit-deploy.md) (clone,
   strip branding, Timeline Metadata, **SDO orchestrator** for `prepare_rlm_org`,
   proactive payments/timeline flake avoidance). Do not permanently edit upstream
   `cumulusci.yml`.
3. **Optional QuantumBit product set** — Before prepare, ask whether to load the
   QuantumBit demo product dataset. **No** → `--product-set no`. **Yes** →
   `--product-set yes`.
4. **SDO profile (Full vs fast)** — Before prepare, ask Full QuantumBit vs SDO
   fast. Fast passes `-o payments|billing_portal|prm|agents|collections false`
   via the orchestrator; `billing_ui` and `ux` stay on.
5. **Optional generic demo products** — After QuantumBit finishes, ask whether to
   launch `rlm-generic-demo-products`. **Yes** → always sync from upstream per
   [references/generic-demo-products.md](references/generic-demo-products.md)
   (overwrite local skill; commit/push if changed), then run against the **Step 1
   org only** (no Phase 4 org-picker); skip Phase 4b only if Brand Image already
   matches this company’s logo. **No** → skip Step 6.
6. **Decision tables + PCM index (always last)** — After Step 5 and after Step 6
   if it ran, always run `refresh_all_decision_tables` then `rebuild_search_index`.
   The SDO orchestrator skips prepare steps 32–33 so this happens exactly once,
   after any generic catalog is created.

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

### Step 2 — System Administrator permissions

Order: **PSLs first**, then the permission sets that consume them. Both go only
to active users with the **System Administrator** profile.

1. Discover which catalog entries exist in this org (do not hard-fail on missing names).
2. Run the assignment script from the workspace root (or skill directory):

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/assign_revenue_access.py --target-org <alias>
```

Uses **Composite sObject Collections** (batches of up to 200) for
`PermissionSetLicenseAssign` / `PermissionSetAssignment`. Expect minutes on a
typical SDO, not hours. Summary includes elapsed seconds and batch counts.
Assigns the org's running user first and **reserves 1 seat** on scarce PSLs
(`TotalLicenses <= 20`) so QuantumBit `prepare_rlm_org` can still assign core
licenses to the automation user.

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

Skip-if-done: the script retrieves Settings first and **skips deploy** when gold
key fields already match (`--force` to redeploy anyway).

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
does not already have it. Short-circuits (no second retrieve/deploy) when every
Opportunity layout already includes `RelatedQuoteList`.

Continue with BRE/CRE, Context Definitions, Sync Pricing Data, and Agentforce
steps as in the checklist. Warn: `enableTransactionProcessor` is irreversible
(already true on gold).

### Step 4 — Agentforce for Revenue Management

Complete [Set Up Agentforce for Revenue Management](https://help.salesforce.com/s/articleView?id=ind.rev_agent_setup.htm&type=5)
after base Revenue Cloud is enabled. Typical themes (verify against Help each run):

- Einstein Generative AI / Agentforce prerequisites
- Manage AI Agents and related agent permissions
- Revenue agent template / topic / action prerequisites

### Step 5 — Always deploy QuantumBit (optional product set + profile)

After Steps 1–4 succeed, **always** deploy QuantumBit per
[references/quantumbit-deploy.md](references/quantumbit-deploy.md).

Before prepare, ask **both**:

1. > Do you want to deploy the QuantumBit product set (demo products and related product data)?
   - **Yes** → `--product-set yes`
   - **No** → `--product-set no` (apps/metadata still deploy; skip QB product
     dataset and constraint sample data)

2. > Which QuantumBit SDO profile should Step 5 use?
   - **Full QuantumBit** → `--profile full` (all default feature flags;
     orchestration wins only: payments preflight + skip Timeline Robot)
   - **SDO fast** → `--profile fast` (also `-o payments false`,
     `-o billing_portal false`, `-o prm false`, `-o agents false`,
     `-o collections false`). Keep `billing_ui` and `ux` on.

Do **not** ask whether to deploy the QuantumBit repo itself — that is always on.
Do **not** permanently edit `cumulusci.yml`. Do **not** use `-o tso true` to skip
Timeline Robot.

**Primary command** (after clone, branding strip, Timeline gold):

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/run_prepare_rlm_org_sdo.py \
  --org <cci-alias> \
  --sf-org <sf-alias-or-username> \
  --repo-root vendor/rlm-base-dev \
  --profile <full|fast> \
  --product-set <yes|no> \
  --timings-file /tmp/prepare_rlm_org_sdo_timings.jsonl
```

**Expect a long Step 5** (still upstream-dominated; Full baseline ~81 min on
SDOTest5 before this orchestrator). The orchestrator removes Timeline Robot
abort/resume and payments create timeout loops; include the per-step timing
table in the completion summary. Resume with `--from-step N` on failure.

When finished (success or documented recovery), continue to **Step 6**.

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
     end-to-end. Phase 0 still asks for company name + website.
  4. **Org (locked):** Always use the org confirmed in Step 1. **Do not** run the
     generic skill’s Phase 4 org-picker / org list. Pass that username/alias on
     every `sf` command and helper script; still print/verify username + org Id
     before uploads.
  5. **Phase 4b brand image:** Skip **only** if theme `QuantumBitSLDSv2` Brand
     Image already matches **this run’s company** logo (ContentAsset name/label
     for this company). Otherwise run Phase 4b as written. If the theme is
     missing, stop and inform (upstream behavior).
- **No** → Skip Step 6; continue to **Step 7**.

Generic catalog research and image generation are not a speed target. Leave that
path as written unless a timing table shows Step 6 is the second-largest step
after prepare.

### Step 7 — Always refresh decision tables + rebuild catalog index (last)

After Step 5 (and Step 6 if Yes), **always** run from `vendor/rlm-base-dev`.
This is the last step of the entire process. The orchestrator does not run
prepare steps 32–33.

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
| QuantumBit prepare (SDO) | `scripts/run_prepare_rlm_org_sdo.py` + CumulusCI in `vendor/rlm-base-dev` |
| Generic demo products | Sync upstream then `.cursor/skills/rlm-generic-demo-products/SKILL.md` (optional ask) |
| Decision tables + PCM index | `cci flow run refresh_all_decision_tables`, `cci task run rebuild_search_index` (always Step 7, last) |

Always use `--json` on `sf` commands. Do not invent Help steps when the article is available.

## Completion summary

When finished, report:

- Target org (username, org Id, alias)
- Permissions: users touched, assignments succeeded, seat-exhaustion skips
- Settings enabled (and which irreversible toggles were confirmed)
- Opportunity layouts: Quotes related list updated count
- Agentforce Revenue setup status
- QuantumBit: always deployed; **profile** Full/fast; product set Yes/No;
  orchestrator timings (per-step table); Timeline Robot skipped; payments
  preflight action; recoveries if any
- Generic demo products: skipped / ran (upstream sync status, company, products,
  Phase 4b ran/skipped-for-matching-logo)
- Decision tables refreshed + PCM search index rebuild status (always last)
- Validation note: Full Step 5 vs SDOTest5 ~81 min baseline when timed