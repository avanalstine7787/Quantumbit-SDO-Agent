# RLM Generic Demo Products + Index Refresh

**Optional Step 6** after QuantumBit always completes. Only run the generic
products skill when the user answers **Yes** to the Step 6 ask in SKILL.md.
**Step 7** (decision tables + PCM index) **always** runs last afterward, whether
Step 6 ran or was skipped. The SDO orchestrator skips prepare steps 32–33 so
this is the only refresh/index pass.

Upstream skill source:

- https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill
- Local path (project skill): `.cursor/skills/rlm-generic-demo-products/`
- Upstream mirror: `vendor/cbs-demo-product-builder-skill/` (gitignored)

## Required preflight — always sync before run

**Before reading or running** `.cursor/skills/rlm-generic-demo-products/SKILL.md`,
**always** sync from upstream. Do not ask for approval. Skip this entire section
only when the user answered **No** to Step 6.

### 1. Clone or pull vendor mirror

```bash
mkdir -p vendor
if [ -d vendor/cbs-demo-product-builder-skill/.git ]; then
  git -C vendor/cbs-demo-product-builder-skill fetch origin
  git -C vendor/cbs-demo-product-builder-skill checkout main
  git -C vendor/cbs-demo-product-builder-skill pull --ff-only origin main
else
  git clone --branch main \
    https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill.git \
    vendor/cbs-demo-product-builder-skill
fi
```

### 2. Overwrite local skill copy

```bash
rm -rf .cursor/skills/rlm-generic-demo-products
cp -R vendor/cbs-demo-product-builder-skill/rlm-generic-demo-products \
  .cursor/skills/rlm-generic-demo-products
```

### 3. Compare and commit/push if changed

```bash
git status --short -- .cursor/skills/rlm-generic-demo-products/
```

- **No output** → Report that the local skill is already current; continue to Step 6 run.
- **Any changes** → Automatically commit and push (do not ask):

```bash
git add -- .cursor/skills/rlm-generic-demo-products/
git commit -m "$(cat <<'EOF'
Sync rlm-generic-demo-products from upstream.

Refresh the vendored skill from aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill before running Step 6.
EOF
)"
git push origin HEAD
git push sfemu HEAD
```

Push to **both** remotes `origin` and `sfemu` when they exist. If a remote is
missing, skip it. If one push fails, report the error and **continue** with the
skill run (do not abort setup).

Stage **only** paths under `.cursor/skills/rlm-generic-demo-products/`.

**SOURCE OF TRUTH after sync:** Always read and follow
`.cursor/skills/rlm-generic-demo-products/SKILL.md` (the project-local copy).
Do not use a global/personal install of this skill.

## Sequencing (locked)

1. Steps 1–4 (Revenue Cloud / ARM setup)
2. Step 5 — **always** QuantumBit via `run_prepare_rlm_org_sdo.py` (product set
   Yes/No; Full vs SDO-fast profile)
3. Ask: launch RLM Generic Demo Products?
   - **Yes** → required preflight (sync) → Step 6 below → **always** Step 7
   - **No** → skip to Step 7
4. Step 7 — **always last**: refresh decision tables + rebuild PCM search index

## Step 6 — Run generic demo products (only if user said Yes)

1. Complete **Required preflight** above (sync + commit/push if needed).
2. **Read** `.cursor/skills/rlm-generic-demo-products/SKILL.md` and execute it
   with the overlays below.
3. **Org handoff (locked):** Always use the org confirmed in revenue-cloud-sdo-setup
   Step 1. **Never** run the generic skill’s Phase 4 org-picker, never list other
   connected orgs for selection, never re-auth from scratch. Pass that
   username/alias as `--target-org` / helper-script third arg on every command.
   Still print/verify username + org Id before any upload.
4. **Phase 0** still asks for company name + website (interactive).

### Branding (Phase 4b — company-logo match skip)

Run Phase 4b **as written** in `.cursor/skills/rlm-generic-demo-products/SKILL.md`
unless the org is **already branded for this run’s company**.

**Skip Phase 4b** only when theme `QuantumBitSLDSv2` Brand Image (`BRAND_IMAGE`
`/file-asset/…`) already corresponds to **this company’s** logo — e.g. ContentAsset
developer name / master label matches the sanitized company asset name for this
run (such as `TollBrothers_BrandLogo`), or the asset is clearly from this company’s
Phase 1 logo.

**Otherwise** run Phase 4b (`update-theme-brand-image.sh`). If theme
`QuantumBitSLDSv2` is missing, stop and inform the user (upstream behavior — do
not invent an alternate theme).

SDO QuantumBit strip **preserves** theme `QuantumBitSLDSv2` (and its branding
set) so Phase 4b can run when needed; it only removes the active-theme settings
and logo static resources so QuantumBit is not forced as the org default theme.

**Auth token:** `sf org display --json` redacts `accessToken`. Local helper
scripts under `.cursor/skills/rlm-generic-demo-products/scripts/` must use
`sf org auth show-access-token --json` (patched in this project). Re-apply that
patch after an upstream skill sync if overwritten.

**One-Time selling model:** omit `ProrationPolicyId` on `ProductSellingModelOption`
(org rejects proration for One-Time).

Scripts under `.cursor/skills/rlm-generic-demo-products/scripts/` (e.g.
`update-theme-brand-image.sh`, `upload-static-resource.sh`) must receive the
confirmed org username as their org argument. Never `sf config set --global`.

## Step 7 — Refresh decision tables + rebuild product index (always last)

“Design tables” means **decision tables**. From `vendor/rlm-base-dev` (already
cloned in Step 5). Always run after Step 5 and after Step 6 if it ran:

```bash
cd vendor/rlm-base-dev
cci flow run refresh_all_decision_tables --org <cci-alias> --no-prompt
cci task run rebuild_search_index --org <cci-alias> --no-prompt
```

`refresh_all_decision_tables` includes `sync_pricing_data` then decision-table
refreshes. `rebuild_search_index` rebuilds the Product Catalog (PCM) search index.

Run even when Step 6 was skipped and when the QuantumBit product set was declined.
