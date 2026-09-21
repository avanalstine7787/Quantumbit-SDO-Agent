# RLM Generic Demo Products + Index Refresh

**Optional Step 6** after QuantumBit always completes. Only run the generic
products skill when the user answers **Yes** to the Step 6 ask in SKILL.md.
**Step 7** (decision tables + PCM index) **always** runs afterward, even if
Step 6 was skipped.

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
2. Step 5 — **always** QuantumBit (`prepare_rlm_org`; product set Yes/No via `qb` /
   `constraints_data`)
3. Ask: launch RLM Generic Demo Products?
   - **Yes** → required preflight (sync) → Step 6 below
   - **No** → skip to Step 7
4. Step 7 — **always** refresh decision tables + rebuild PCM search index

## Step 6 — Run generic demo products (only if user said Yes)

1. Complete **Required preflight** above (sync + commit/push if needed).
2. **Read** `.cursor/skills/rlm-generic-demo-products/SKILL.md` and execute it.
3. **Org handoff:** Use the org already confirmed in revenue-cloud-sdo-setup Step 1.
   When Phase 4 asks for org, pre-select that username/alias — do not re-auth from scratch.
4. **Phase 0** still asks for company name + website (interactive).

### Branding (no skip overlay)

Always run Phase 4b and any other branding steps **as written** in
`.cursor/skills/rlm-generic-demo-products/SKILL.md` (org Themes and Branding
brand-image replace on `QuantumBitSLDSv2`, etc.). Do **not** skip rebranding
because the org already looks rebranded.

SDO QuantumBit strip **preserves** theme `QuantumBitSLDSv2` (and its branding
set) so Phase 4b can run; it only removes the active-theme settings and logo
static resources so QuantumBit is not forced as the org default theme.

**Auth token:** `sf org display --json` redacts `accessToken`. Local helper
scripts under `.cursor/skills/rlm-generic-demo-products/scripts/` must use
`sf org auth show-access-token --json` (patched in this project). Re-apply that
patch after an upstream skill sync if overwritten.

**One-Time selling model:** omit `ProrationPolicyId` on `ProductSellingModelOption`
(org rejects proration for One-Time).

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
