---
name: salesforce-rlm-generic-demo-products
description: Creates Salesforce ARM/RLM demo product records for any target company. Researches the company website, proposes products and pricing, generates product images, builds a proposal canvas, asks the user to choose consolidated pricing-policy settings, replaces the org Themes and Branding brand image with the company logo, and creates catalog/product records with runtime org ID lookups. Use when the user wants to seed generic demo product data in a Salesforce RLM/ARM org.
---

# Salesforce RLM Generic Demo — Product Creator

> **Skill version: 2026-09-09.1**
>
> **SOURCE OF TRUTH — READ THIS FIRST.** This skill is distributed inside each demo project. Always run the copy that lives **inside the currently open project folder** (relative `./SKILL.md`, with `./sf-objects-reference.md` and `./scripts/`). If you were invoked from a globally/personally installed copy (`~/.cursor/skills/…`, `~/.claude/skills/…`) or any path outside this project, **discard it and re-read the local project copy**, which is always the authoritative, most up-to-date version. Never mix instructions between a global copy and the local one. Also discard any leftover `salesforce-rlm-homeservices-demo-products` skill.

Automates end-to-end creation of generic product catalog data in a Salesforce ARM/RLM org. This is not Salesforce CPQ/Steelbrick.

For detailed field-level reference on all objects used, see [sf-objects-reference.md](sf-objects-reference.md).

## Prerequisites
- Salesforce CLI (`sf`) installed
- Run local scripts from project root
- `GenerateImage` and canvas tooling available if image generation + canvas output are required
- This folder is **not** an SFDX project (`sfdx-project.json` is absent). Never `sf config set --global`. Pass `--target-org` (or `SF_TARGET_ORG`) on every `sf` command and as the third argument to helper scripts.

## Questions (required)

For every user **decision or confirmation** after Phase 0, use Cursor’s structured question UI (`AskQuestion`): selectable options, not numbered lists in chat. The built-in **Other** option is how the user types extra detail (edits, overrides, a username not in the list). Do not invent extra choices beyond those listed in each phase.

**Exception — Phase 0:** ask the exact freeform kickoff sentence in chat and nothing else first. That prompt collects company name + URL, not a choice.

**Exception — Phase 2 confirmation:** keep `AskQuestion` for confirm/edit, but that turn **must not** be AskQuestion-only. A user-visible chat message with a markdown link to the proposal canvas is required in that same turn (or a prior turn in the same phase). Writing the `.canvas.tsx` file does not count as showing it.

## Phase 0 - Kickoff Prompt (required)

Before any research or org work, ask this exact question first:

`Please tell me the name of the company you want me to research and share the company website URL.`

If the user provides only one item, ask only for the missing item (company name or website URL) before continuing.

## Phase 1 - Research

Use the provided company name/URL to research products or services and propose 5-10 demo products.

Rules:
- Include at least one bundle parent with 2-3 optional add-ons
- Propose realistic pricing
- Create concise product codes
- Write concise product descriptions

Create an internal list with:
- Product name
- Product code
- Product type (standalone, bundle parent, bundle add-on)
- Proposed price
- Parent bundle reference (for add-ons)
- Description

Also capture the company logo from the researched website. Do **not** use `GenerateImage` for the logo — download the real logo.

Logo capture rules:
- Prefer the header/nav logo over favicon or `og:image`
- Prefer a downloaded JPG, PNG, or GIF header logo and store it under `./assets/<company>/`
- If the header/nav logo is SVG, rasterize it locally to PNG (qlmanage, sips, or Pillow). Do **not** use `GenerateImage`. Do **not** fall back to favicon or `og:image` while a header SVG exists.
- Crop padded thumbnails to the actual wordmark before Phase 4b. `qlmanage -t` often produces a 1200×1200 canvas; contain+pad to 600×120 on that padded image makes a tiny logo.
- The logo will be resized to 600x120 px in Phase 4b (contain+pad; do not stretch)
- Only stop and ask for a local image path if rasterization fails or no header logo exists

## Phase 2 - Propose and Confirm

Generate one image per product using `GenerateImage` when available. Capture the exact absolute image path returned by the tool **and** copy each file into `./assets/` (use the project copies for the canvas and `upload-static-resource.sh`).

Create a proposal canvas in the Cursor canvases directory — not in this git repo:

`~/.cursor/projects/<workspace>/canvases/<company>-product-proposal.canvas.tsx`

The canvas must include:
- The captured company logo
- Product name
- Product code
- Product type
- Proposed price
- Description

Required show-then-ask order (do not skip or reorder; do not continue until confirmed):

1. Write the canvas to the path above.
2. **Show it** in chat: include a markdown link to that `.canvas.tsx` file (full absolute path, short label). Tell the user they can open it beside the chat to review products and pricing. If this is the first `.canvas.tsx` in that canvases directory, add one sentence explaining what a canvas is. A markdown table in chat is not a substitute for the canvas link.
3. **Then** call `AskQuestion`. Never skip step 2. Never make this confirmation an AskQuestion-only turn.

Prompt: `Review the proposal canvas, then confirm the proposed catalog`

Options:
- `Confirm as proposed`
- `Request edits` (details go in Other, including replacing the logo if needed)
- `Open the proposal canvas first`

If the user picks `Open the proposal canvas first`: re-send the markdown link, do **not** treat it as confirmation, then re-ask the same question.

## Phase 3 - Consolidated Pricing/Policy Step (required)

After proposal confirmation, run one consolidated decision phase for selling model, billing policy, and usage selection. Ask every question in this phase with structured selectable options (Other for extra text). Keep this option wording; do not invent extra choices.

Selling model values (use exactly these labels):
- One-Time
- Term Annual
- Term Based - Quarterly
- Term Based - Semi - Annual
- Term Monthly

Billing policy values (use exactly these labels):
- Advance
- Arrears

Ask in this order:

1. Prompt: `How would you like to configure pricing, billing policy, and usage pricing for these products?`

   Options:
   - `1. Use default selling model and default billing policy, with optional per-product overrides`
   - `2. Specify selling model and billing policy per product`

2. If option 1 (same form or immediate follow-up):
   - Default selling model — the five selling-model values above
   - Default billing policy for non-One-Time products — Advance / Arrears
   - Any product-specific overrides? — `No — use the defaults for every product` / `Yes — I will list product-specific overrides` (list in Other)

3. If option 2:
   - One selling-model question per product (same five values)
   - Billing policy per non-One-Time product (Advance / Arrears)

4. Usage (same consolidated phase):
   - Prompt: `Do any products need usage pricing configuration?`
   - Options: `No — none of these products need usage pricing` / `Yes — I will list which products need usage configured`
   - If yes: follow up with a **multi-select** of the proposed product names
   - Do not collect detailed usage configuration in this phase
   - Note: detailed usage setup is handled in a later step

Field rules:
- `TaxPolicyId` must always be set
- `BillingPolicyId` is set only when selling model is not `One-Time`

## Phase 4 - Org Authentication and Runtime ID Lookup

Ask which org to target with structured options. Run `sf org list`, then present **connected** usernames/aliases as selectable options. The user can pick Other to type a username that is not listed. Do not skip this list even if only one org is connected.

Then authenticate and verify that org. Print/verify `username` and org Id before any upload. Never `sf config set --global`. Pass `--target-org "<orgUsername>"` (or `SF_TARGET_ORG`) on every `sf` command.

Query IDs by name at runtime (never hardcode IDs):
- `TaxPolicy` where `Name='Default Tax Policy'`
- `BillingPolicy` where `Name='Billing Policy - Advance'`
- `BillingPolicy` where `Name='Billing Policy - Arrears'`
- `ProductSellingModel` for each selected selling model name
- `Pricebook2` standard price book
- `ProductRelationshipType` for bundle component relationships
- `ProrationPolicy` where `Name='Default Proration Policy'`

When usage-priced products were selected in Phase 3, also resolve:
- `UnitOfMeasureClass` where `Name='Case'` → `UnitOfMeasureClassId`
- `UnitOfMeasure` where `Name='Each'` → `DefaultUnitOfMeasureId`
- `UnitOfMeasure` where `Name='USD'` → `RateUnitOfMeasureId`
- `UsageResourceBillingPolicy` where `Name='Monthly Total'` → `UsageResourceBillingPolicyId` (also reuse for `UsageAggregationPolicyId` on `ProductUsageResourcePolicy`)
- `UsageOveragePolicy` where `Name='Default Usage Overage Policy'` → `UsageOveragePolicyId`
- `RatingFrequencyPolicy` where `Name='Monthly Rating Frequency'` → `RatingFrequencyPolicyId`
- `RateCard` where `Name='Base Rate Card'` → `RateCardId`

`UsageDefinitionProductId` uses the already-created `Product2` Id for the product being configured (from Phase 5).
`ProductSellingModelId` on `ProductUsageResourcePolicy` and `RateCardEntry` uses the same selling-model Id already chosen for that product in Phase 3 / applied via `ProductSellingModelOption` in Phase 5.

If a required lookup record is missing, stop and inform the user.

## Phase 4b - Replace Org Brand Image

Run immediately after Phase 4 authentication and lookups, before catalog create, so branding is applied even if later product steps fail.

From the setup menu, under Themes and Branding, there will always be an existing active record: QuantumBitSLDSv2 (Developer Name). The existing Brand Image will need to be replaced with the logo from the researched company.

The logo image from the researched company will need to be 600x120 px.

Steps:
1. Sanitize a ContentAsset developer name (alphanumeric + underscores, must start with a letter, max 40 characters), e.g. `<Company>_BrandLogo`.
2. Run the helper. It resizes the logo to 600x120 with contain+pad (does not stretch), uploads it as a ContentAsset, and replaces `BRAND_IMAGE` on theme `QuantumBitSLDSv2`:

```bash
bash scripts/update-theme-brand-image.sh "<absoluteLogoPath>" "<sanitizedAssetName>" "<orgUsername>"
```

3. Do not change other theme properties (colors, banner, etc.).
4. Query the theme by Developer Name `QuantumBitSLDSv2` at runtime (never hardcode the theme Id). If the theme or its branding set is missing, stop and inform the user.

## Phase 5 - Create Catalog and Product Records

Use idempotent create flow:
1. Ensure catalog exists (create if missing)
2. Ensure category exists (create if missing)
3. Upload static resources for product images when available:

```bash
bash scripts/upload-static-resource.sh "<absoluteImagePath>" "<sanitizedResourceName>" "<orgUsername>"
```

   Use the `./assets/` copies. Pass the same org username used in Phase 4.
4. Create or reuse `Product2`
5. Create or reuse category assignment
6. Create or reuse `ProductSellingModelOption`
7. Create or reuse `PricebookEntry`
8. Create bundle structures (`ProductComponentGroup`, `ProductRelatedComponent`) where applicable

Use runtime-selected policy/model IDs:
- Set `TaxPolicyId` on each product
- Set `BillingPolicyId` only for non-One-Time products
- For any product identified in Phase 3 as needing usage pricing, set `UsageModelType` to `Anchor` on `Product2` create. Omit `UsageModelType` for all other products.
- If the idempotent flow reuses an existing `Product2` for a usage product and `UsageModelType` is blank or not `Anchor`, update that record to `Anchor` before continuing.

Do not run milestone billing schedule setup and do not rely on milestone billing scripts in this skill version.

## Phase 6 - Usage Configuration

Only run if the user identified usage-priced products in Phase 3. Keep this separate from the consolidated pricing/policy selection step.

### Step 1 - Create UsageResource

For **each** usage-priced product, create one `UsageResource` record.

Required fields:
- `Name` — product-relevant meter name (e.g. Shirt → `Per Replacement`; Emergency/After Hours visit → `Per Visit`)
- `Code` — invent a unique code (e.g. `UR-<ProductCode>`)
- `Category` — always `Usage`
- `Status` — always `Draft` on create; activate only after all usage creation steps finish

Lookups (from Phase 4 / Phase 5):
- `UnitOfMeasureClassId` — `Case` UoM class
- `DefaultUnitOfMeasureId` — `Each` UoM
- `UsageDefinitionProductId` — target product’s `Product2` Id
- `UsageResourceBillingPolicyId` — `Monthly Total` policy

Flow:
1. Resolve lookups (or reuse IDs already fetched in Phase 4).
2. Create `UsageResource` via `sf data create record` (or equivalent).
3. Store the new Id for later Phase 6 steps.
4. Do **not** set `Status=Active` in this step.

Continue with Step 2 for each created `UsageResource`.

### Step 2a - Create ProductUsageResource

For **each** usage-priced product (after its `UsageResource` exists), create one `ProductUsageResource` record.

Fields:
- `ProductId` — target product’s `Product2` Id
- `UsageResourceId` — Id from Step 1
- `Status` — always `Draft` (activate later)
- `EffectiveStartDate` — always November 1 of the **previous calendar year** relative to run date (e.g. run in 2026 → `2025-11-01`)

Flow:
1. Create `ProductUsageResource` via `sf data create record` (or equivalent).
2. Store the new Id.
3. Do **not** set `Status=Active` in this step.

### Step 2b - Create ProductUsageResourcePolicy

Immediately after each new `ProductUsageResource`, create one related `ProductUsageResourcePolicy` record.

Fields:
- `ProductUsageResourceId` — Master-Detail to the new PUR Id
- `ProductSellingModelId` — same selling model Id used for that product
- `UsageAggregationPolicyId` — `Monthly Total` (`UsageResourceBillingPolicy`)
- `UsageOveragePolicyId` — `Default Usage Overage Policy`
- `RatingFrequencyPolicyId` — `Monthly Rating Frequency`

Do not activate in this step. Continue with Step 3 after all Draft records for a product are created.

### Step 3 - Activate UsageResource and ProductUsageResource

After Steps 1–2b are complete for a usage-priced product, activate in this order (required):

1. Update the `UsageResource` — set `Status='Active'`
2. Update the `ProductUsageResource` — set `Status='Active'`

Do not reverse this order. Activate via `sf data update record` (or equivalent) using the Ids stored from Steps 1 and 2a.

Continue with Step 4 for each usage-priced product.

### Step 4 - Create and activate RateCardEntry

For **each** usage-priced product, after Steps 1–3 are complete, create one `RateCardEntry` record.

Fields:
- `UsageResourceId` — UsageResource Id from Step 1
- `ProductId` — target product’s `Product2` Id
- `Status` — always `Draft` on create
- `RateCardId` — Master-Detail to `Base Rate Card`
- `DefaultUnitOfMeasureId` — `Each`
- `ProductSellingModelId` — same selling model Id used for that product
- `RateUnitOfMeasureId` — `USD`
- `Rate` — Number(12, 6); use the product’s proposed price from Phase 1 research / confirmed proposal
- `RateNegotiation` — always `Negotiable`
- `EffectiveFrom` — Date/Time; November 1 of the **previous calendar year** relative to run date (e.g. run in 2026 → `2025-11-01`)

Flow:
1. Create `RateCardEntry` via `sf data create record` (or equivalent) with `Status='Draft'`.
2. Immediately update the same record — set `Status='Active'`.
3. Store the RateCardEntry Id for the run summary.

## Completion

Provide a concise summary:
- Company researched
- Product proposal accepted
- Pricing/policy choices captured
- Usage-product list captured (if any)
- Org brand image replaced on theme QuantumBitSLDSv2 (ContentAsset name, `/file-asset/…` value, or skipped and why)
- Records created/reused with key IDs
- Any skipped steps and why
