# RLM Generic Demo Products + Index Refresh

After revenue-cloud-sdo-setup Steps 1–4 (and Step 5 QuantumBit when Yes), run
company-specific demo products, then refresh decision tables and rebuild the
PCM search index.

Upstream skill source:

- https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill
- Local path (project skill): `.cursor/skills/rlm-generic-demo-products/`
- Optional upstream mirror for updates: `vendor/cbs-demo-product-builder-skill/`
  (gitignored; re-clone and copy into `.cursor/skills/` when refreshing)

## Clone / update

The project ships a copy under `.cursor/skills/rlm-generic-demo-products/`.
To refresh from upstream:

```bash
mkdir -p vendor
if [ -d vendor/cbs-demo-product-builder-skill/.git ]; then
  git -C vendor/cbs-demo-product-builder-skill pull --ff-only origin main
else
  git clone --depth 1 \
    https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill.git \
    vendor/cbs-demo-product-builder-skill
fi
rm -rf .cursor/skills/rlm-generic-demo-products
cp -R vendor/cbs-demo-product-builder-skill/rlm-generic-demo-products \
  .cursor/skills/rlm-generic-demo-products
```

**SOURCE OF TRUTH:** Always read and follow
`.cursor/skills/rlm-generic-demo-products/SKILL.md` (the project-local copy).
Do not use a global/personal install of this skill.

## Sequencing (locked)

| QuantumBit answer | When Step 6 runs |
|-------------------|------------------|
| No (skipped) | Immediately after Steps 1–4 and the Step 5 “No” |
| Yes | Only after `prepare_rlm_org` finishes (success or documented recovery) |

Then **Step 7** always runs after Step 6 completes.

## Step 6 — Run generic demo products

1. Ensure the vendor clone + symlink exist (commands above).
2. **Read** `.cursor/skills/rlm-generic-demo-products/SKILL.md` and execute it.
3. **Org handoff:** Use the org already confirmed in revenue-cloud-sdo-setup Step 1.
   When Phase 4 asks for org, pre-select that username/alias — do not re-auth from scratch.
4. **Phase 0** still asks for company name + website (interactive).

### Phase 4b — Company brand image (locked overlay)

Run Phase 4b **only if the org has not already been rebranded for the company**
being productized in this run.

**Skip Phase 4b** when either is true:

- Active Lightning theme / branding set brand image is already the company logo
  captured in Phase 1 for this company, or
- Org name / documented prior run already matches this company and a brand asset
  for it is present

**Run Phase 4b** when not rebranded:

- Prefer theme `QuantumBitSLDSv2` when present
- Otherwise update the org’s **current active** Lightning Experience theme /
  branding set brand image
- Do **not** re-deploy stripped QuantumBit themes solely to satisfy Phase 4b if
  another active theme exists

If no suitable theme/branding set exists, warn and continue product create.

Scripts under `.cursor/skills/rlm-generic-demo-products/scripts/` (e.g.
`update-theme-brand-image.sh`, `upload-static-resource.sh`) must receive the
confirmed org username as their org argument. Never `sf config set --global`.

## Step 7 — Refresh decision tables + rebuild product index

“Design tables” means **decision tables**. From `vendor/rlm-base-dev` (clone the
API-matched branch per [quantumbit-deploy.md](quantumbit-deploy.md) if missing;
CCI-connect the same org; do **not** run full `prepare_rlm_org` solely for this):

```bash
cd vendor/rlm-base-dev
cci flow run refresh_all_decision_tables --org <cci-alias> --no-prompt
cci task run rebuild_search_index --org <cci-alias> --no-prompt
```

`refresh_all_decision_tables` includes `sync_pricing_data` then decision-table
refreshes. `rebuild_search_index` rebuilds the Product Catalog (PCM) search index.
