# RLM Generic Demo Products + Index Refresh

**Optional Step 6** after QuantumBit always completes. Only run the generic
products skill when the user answers **Yes** to the Step 6 ask in SKILL.md.
**Step 7** (decision tables + PCM index) **always** runs afterward, even if
Step 6 was skipped.

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

1. Steps 1–4 (Revenue Cloud / ARM setup)
2. Step 5 — **always** QuantumBit (`prepare_rlm_org`; product set Yes/No via `qb` /
   `constraints_data`)
3. Ask: launch RLM Generic Demo Products?
   - **Yes** → Step 6 below
   - **No** → skip to Step 7
4. Step 7 — **always** refresh decision tables + rebuild PCM search index

## Step 6 — Run generic demo products (only if user said Yes)

1. Ensure the project skill copy exists (commands above).
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

## Step 7 — Refresh decision tables + rebuild product index (always)

“Design tables” means **decision tables**. From `vendor/rlm-base-dev` (already
cloned in Step 5):

```bash
cd vendor/rlm-base-dev
cci flow run refresh_all_decision_tables --org <cci-alias> --no-prompt
cci task run rebuild_search_index --org <cci-alias> --no-prompt
```

`refresh_all_decision_tables` includes `sync_pricing_data` then decision-table
refreshes. `rebuild_search_index` rebuilds the Product Catalog (PCM) search index.

Run even when Step 6 was skipped and when the QuantumBit product set was declined.
