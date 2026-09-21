# QuantumBit Deploy (rlm-base-dev)

**Always run** after initial Revenue Cloud / Agentforce Revenue Management setup
(Steps 1–4). Do **not** ask whether to deploy the QuantumBit repo — only ask
whether to load the **QuantumBit product set** (see below).

## Locked policy — SDO deploy profile

1. Always clone/connect `vendor/rlm-base-dev` and run `prepare_rlm_org`.
2. Strip QuantumBit Lightning **org branding** from the local vendor tree.
3. Ensure **Timeline** via Metadata (`Industries` / `enableTimelinePref`).
4. **Automatic recovery** on known flakes (payments community, `enable_timeline`
   Robot) — do not abort the whole run.
5. Keep `billing`, `billing_ui`, `ux`, `tax`, `dro`, `constraints` (engine), etc.
   at repository defaults. Do **not** add `-o billing_ui false` or `-o ux false`.

**Product set (optional ask from SKILL.md Step 5):**

| User answer | CCI command |
|-------------|-------------|
| Yes — deploy QuantumBit product set | `cci flow run prepare_rlm_org --org <cci-alias>` |
| No — skip product / constraint sample data | `cci flow run prepare_rlm_org --org <cci-alias> -o qb false -o constraints_data false` |

`-o qb false` skips the QuantumBit demo product/pricing dataset and related data
loads gated on `qb`. `-o constraints_data false` skips Constraint Builder sample
product/rule data. QuantumBit **apps/metadata** (`quantumbit: true`) still deploy.

Do **not** permanently edit upstream `vendor/rlm-base-dev/cumulusci.yml`.

Upstream docs:

- https://github.com/bgaldino/rlm-base-dev
- https://github.com/bgaldino/rlm-base-dev/blob/main/docs/guides/org-operations.md
- https://github.com/bgaldino/rlm-base-dev/blob/main/docs/guides/prepare-rlm-org-build-guide.md
- https://github.com/bgaldino/rlm-base-dev/blob/main/docs/guides/local-installation.md

## Branch

Default: `main` (Release 264 / API v68.0 as of the repo README).

**Match the org API version.** If `sf org display` reports API **67.0** (Summer '26 /
release 262), clone and deploy branch **`262`** (or `release/262` for the frozen GA
tip) instead of `main`. If the org is on 68.0 / Winter '27, use `main`. Tell the
user which branch you selected and why; only ask when the release is ambiguous.

## Steps

From the **workspace root** (Quantumbit SDO Agent):

### 1. Clone or update

```bash
mkdir -p vendor
# Choose BRANCH=main or BRANCH=262 based on org API version (see Branch above)
BRANCH=main
if [ -d vendor/rlm-base-dev/.git ]; then
  git -C vendor/rlm-base-dev fetch origin
  git -C vendor/rlm-base-dev checkout "$BRANCH"
  git -C vendor/rlm-base-dev pull --ff-only origin "$BRANCH"
else
  git clone --branch "$BRANCH" https://github.com/bgaldino/rlm-base-dev.git vendor/rlm-base-dev
fi
```

### 2. Strip QuantumBit org branding (required)

Removes the active-theme settings and QuantumBit logo static resources so the
SDO is not forced onto a QuantumBit default theme. **Keeps** theme
`QuantumBitSLDSv2` (+ branding set) so Step 6 Phase 4b can replace the Brand Image.

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/strip_quantumbit_branding.py \
  --repo-root vendor/rlm-base-dev
```

This mutates the vendor working tree (expect dirty git / stamp “dirty”). Re-run
after every fresh clone or `git pull` that restores those files.

### 3. Prerequisites

Verify (install if missing per upstream local-installation guide):

- Salesforce CLI (`sf`)
- CumulusCI (`cci`)
- SFDMU plugin **v5.6.4+** (`sf plugins install sfdmu`)
- Python / Node as required by the repo

```bash
cci version
sf plugins list
cd vendor/rlm-base-dev && cci task run validate_setup
```

### 4. Connect the same target org to CumulusCI

CCI aliases are separate from `sf` aliases. Connect the **confirmed** target org:

```bash
# From vendor/rlm-base-dev
cci org connect <cci-alias>
# For a sandbox, use: cci org connect <cci-alias> --sandbox

cci org default <cci-alias>
```

Confirm:

```bash
cci org info <cci-alias>
```

### 5. Ensure Timeline via Metadata (required before prepare_billing)

Robot `enable_timeline` flakes on many SDOs and aborts billing UI before
`prepare_ux`. Deploy gold Industries settings (includes `enableTimelinePref=true`)
immediately before the long CCI run:

```bash
# From workspace root — deploys full gold bundle including Industries
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/deploy_org_settings_gold.py \
  --target-org <alias>
```

Or deploy only `Settings:Industries` from
[org-settings-gold/Industries.settings-meta.xml](org-settings-gold/Industries.settings-meta.xml)
if gold was already applied earlier in the same session.

### 6. prepare_rlm_org (product set from user ask)

Ask the product-set question in SKILL.md Step 5, then run one of:

```bash
cd vendor/rlm-base-dev
# Product set Yes:
cci flow run prepare_rlm_org --org <cci-alias>

# Product set No:
cci flow run prepare_rlm_org --org <cci-alias> -o qb false -o constraints_data false
```

### 7. Long-running builds and automatic recovery

`prepare_rlm_org` can take a long time. Monitor output. On the failures below,
**recover automatically** (do not stop the skill or ask the user to “try again”
as the only action).

CCI 7.x has no `--from-step`. After a mid-flow failure, run remaining tasks/flows
in `prepare_rlm_org` order from the failed step onward.

#### Payments community timeout (`create_payments_webhook`)

If create times out but a Live Network already exists (`UrlPathPrefix` like
`sfpwebhook`, name may be `sfpwebhook`):

1. Do **not** create a second community.
2. Rename the existing Network display Name in place to `Payments Webhook` if needed
   so `skip_existing` matches.
3. Continue payments: if site XML was already patched (placeholder gone), run
   `deploy_post_payments_site` then `revert_payments_site_after_deploy` (**no**
   `--org` on revert — local file task). Else restore placeholder
   `payments-site-admin@example.com` in
   `unpackaged/post_payments/sites/Payments_Webhook.site-meta.xml` and re-run
   `prepare_payments` (create will skip).
4. Finish remaining payment tasks: `publish_community` (name `Payments Webhook`),
   `deploy_post_payments_settings`, `deploy_post_payments_ext`,
   `assign_permission_sets` (`RLM_Payments`).
5. Continue `prepare_rlm_org` from step 5 (`deploy_full`) through `stamp_git_commit`.

#### `enable_timeline` Robot failure

If Timeline Metadata was deployed and Robot still fails:

1. Skip Robot — do not re-run `enable_timeline`.
2. Continue `prepare_billing` from step 9 onward:
   - `deploy_billing_id_settings`
   - `deploy_billing_template_settings`
   - `deploy_post_billing_ui`
   - `assign_permission_sets` (`RLM_BillingUI`)
   - `apply_context_billing_order` (**no** `--org` — uses CCI default org)
   - `cci flow run prepare_billing_portal`
3. Continue remaining `prepare_rlm_org` steps including `prepare_ux`.

#### Local-only CCI tasks

Never pass `--org` to:

- `revert_payments_site_after_deploy`
- `apply_context_billing_order` (pass nothing; relies on `cci org default`)

## Success criteria

- Flow completes (with documented recoveries if needed)
- QuantumBit apps/metadata deployed; product dataset present only if user said Yes
- SDO Lightning theme **not** replaced by QuantumBit branding
- Summarize duration, org alias, product-set Yes/No, branding strip, recoveries

#### PCM search index language error (`PCM_RUNTIME_SNAPSHOT_DEPLOY_014`)

If `rebuild_search_index` warns with HTTP 400
`Specify a valid supported language and a valid default language` and continues:

1. Do **not** abort `prepare_rlm_org` — upstream already warns and continues by default.
2. In Setup, open **Product Catalog Management** / **Build Catalog Index** (or Product
   Discovery index settings) and set **Supported Languages** and **Default Language**
   (typically `en_US`), then rebuild from the UI component.
3. Document in the completion summary that Step 7 / index rebuild may need a manual
   language fix before a successful Connect API rebuild.

## After this file

Return to SKILL.md: ask about optional **RLM Generic Demo Products**, then
**always** run Step 7 (decision tables + PCM search index rebuild).
