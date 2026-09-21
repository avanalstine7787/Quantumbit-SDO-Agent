# Revenue Cloud / ARM Setup Checklist

Ordered enablement for Agentforce Revenue Management (ARM), Revenue Cloud, and
Billing. Re-fetch Salesforce Help each run and prefer Help over this file when
they disagree.

## Primary Help

- [Set Up Agentforce for Revenue Management](https://help.salesforce.com/s/articleView?id=ind.rev_agent_setup.htm&type=5)
- [Assign Revenue Management Permission Sets to System Admin](https://help.salesforce.com/s/articleView?id=ind.admin_permission_sets.htm&type=5)
- [Revenue Cloud permission sets table](https://help.salesforce.com/s/articleView?id=ind.revenue_cloud_permission_sets_table.htm&type=5)

## Irreversible toggles (confirm before enabling)

| Setting | Notes |
|---------|-------|
| Enable Revenue Cloud Features | Platform switch; cannot disable |
| Enhanced Commerce Orders | Permanent once on |
| Transaction processing for quotes and orders | Permanent once on |

## Phase A — Foundation (before Agentforce)

1. **Permission set licenses, then permission sets**
   - Assign only to active System Administrator users via `scripts/assign_revenue_access.py`
     (Composite batched assigns; summary includes elapsed time and how many
     non-admin users were skipped)
   - See [permission-catalog.md](permission-catalog.md)

2. **Release Update: Enable New Order Save Behavior**
   - Setup → Release Updates → enable if present
   - Required for correct parent-order logic with Revenue Cloud

3. **Deploy EFM2 gold org settings (required)**
   - Confirm irreversible toggles with the user first (Core CPQ, Enhanced Commerce
     Orders, Transaction Processor)
   - Run:
     ```bash
     python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/deploy_org_settings_gold.py \
       --target-org <alias>
     ```
   - Skip-if-done when gold key fields already match (`--force` to redeploy)
   - Source: [org-settings-gold/](org-settings-gold/) — Quote, Order,
     RevenueManagement, ProductConfigurator, IndustriesPricing, Industries
     (`enableTimelinePref` for Billing UI / Timeline), Billing (portable toggles
     only; **no** Billing record IDs)
   - Verify retrieve of each Settings type matches gold key fields
     (`enableCoreCPQ`, `enableProductConfigurator`, `enableSalesforcePricing`,
     `enableTimelinePref`, Billing `enable*` flags). Do not require
     `enableContextReuse` (omitted when Metadata rejects it).

3b. **Add Quotes related list to Opportunity layouts**
   - After Quotes are enabled (gold Quote settings), run:
     ```bash
     python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/add_quotes_related_list_to_opportunity_layouts.py \
       --target-org <alias>
     ```
   - Adds `RelatedQuoteList` to every Opportunity page layout that lacks it
     (idempotent; short-circuits when all layouts already have it). Required so
     Opportunity records show Quotes in related lists.

## Phase B — Configurator and pricing (post-gold)

4. **Configure Products at Runtime** — already in gold
   (`enableProductConfigurator=true`). Re-verify retrieve; do not skip if gold
   deploy failed.
5. **Rules engines (as available)** — BRE and/or CRE after configurator is on
6. **Salesforce Pricing** — gold sets `enableSalesforcePricing=true`; still
   enable Context Definitions, extend/activate contexts, clone/activate default
   pricing procedures, assign procedures in Pricing + Revenue Settings, run
   **Sync Pricing Data**
7. **Product Discovery Settings** — point at extended context and procedure

## Phase C — Billing (when Billing license present)

8. Gold Billing toggles are deployed in Phase A (see
   [org-settings-gold/billing-guided-setup.md](org-settings-gold/billing-guided-setup.md))
9. Confirm Billing Admin and related PSLs were assigned in Phase A
10. After billing data exists (e.g. QuantumBit `prepare_billing`), resolve
    legal entity / treatments / templates / GL account **IDs** via SOQL — never
    copy EFM2 IDs verbatim

## Phase D — Transactions and renewals

11. Keep default flows when possible:
    - Create orders from quotes: `revenue_adv_q2o__CreateOrdersFromQuote`
    - Asset amend/renew/cancel: `runtime_revenue_arcflows__arcFlow`
    - Create contracts from quotes: `rev_contracts__CreateCntrFromQuote`
12. Transaction processing — only after explicit irreversible confirm
13. As-Is Renewals / Customize Contract Pricing — match demo story; ask if unsure

## Phase E — Agentforce for Revenue Management

14. Follow [rev_agent_setup](https://help.salesforce.com/s/articleView?id=ind.rev_agent_setup.htm&type=5) exactly:
    - Einstein Generative AI / Agentforce org prerequisites
    - Manage AI Agents and agent-type permissions
    - Any Revenue agent template, topic, or action prerequisites listed in Help
15. Re-assign any newly required Agentforce permission sets via the assignment script if they appear only after enablement

## Phase F — Verify

Smoke-check (adjust to what the org licenses):

- App Launcher opens Product Catalog Management, Quotes, Orders, Billing (if licensed) for a System Administrator
- Do not expect a non-admin sample user to open those apps; catalog PSLs are not assigned to them
- Pricing Sync completed without error when pricing was configured

## Phase G — Products (optional) + index refresh (always last)

16. **QuantumBit** — Always deploy per [quantumbit-deploy.md](quantumbit-deploy.md)
    using `scripts/run_prepare_rlm_org_sdo.py`. Before prepare, ask:
    - **Product set** — Yes → `--product-set yes`; No → `--product-set no`
    - **SDO profile** — Full → `--profile full`; SDO fast → `--profile fast`
      (`payments` / `billing_portal` / `prm` / `agents` / `collections` off;
      `billing_ui` + `ux` stay on)
    The orchestrator skips prepare steps 32–33.
17. **RLM Generic Demo Products (optional)** — After QuantumBit, ask whether to
    launch the skill. If Yes, **always sync** from
    https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill
    (overwrite local skill; auto commit/push to `origin` + `sfemu` if changed),
    then follow [generic-demo-products.md](generic-demo-products.md).
    Always use the Step 1 confirmed org (no Phase 4 org-picker). Skip Phase 4b
    only if `QuantumBitSLDSv2` Brand Image already matches this company’s logo;
    otherwise rebrand as written.
18. **Refresh decision tables + rebuild PCM search index (always last)**
    ```bash
    cd vendor/rlm-base-dev
    cci flow run refresh_all_decision_tables --org <cci-alias> --no-prompt
    cci task run rebuild_search_index --org <cci-alias> --no-prompt
    ```
    Run even if both product asks were No. Note: PCM index language soft-fails
    (`PCM_RUNTIME_SNAPSHOT_DEPLOY_014`) may still need a manual UI pass until a
    reliable API fix exists. Do not treat that as a setup abort.

## Automation note

Always follow the **SDO deploy profile** in [quantumbit-deploy.md](quantumbit-deploy.md):
strip QuantumBit Lightning branding, re-apply Timeline via Industries gold, run
the **SDO orchestrator** (payments preflight + skip Timeline Robot; optional
Full vs fast `-o` flags; product set via `--product-set`). Do not edit
`cumulusci.yml` to shorten Step 5. Full-profile baseline before orchestrator:
~81 min (SDOTest5). Validate future Full timed runs against that baseline.
Steps 2–3 are already short on a fresh org after Composite assign and one-pass
gold deploy; do not micro-optimize them unless a run exceeds a couple of minutes.
Generic demo product image research is not a speed target. Complete Phases A–E
first. After QuantumBit, ask about optional generic demo products, then always
run the decision-table / PCM index refresh as the last step. PCM index
language soft-fails (`PCM_RUNTIME_SNAPSHOT_DEPLOY_014`) stay a manual UI fix.
