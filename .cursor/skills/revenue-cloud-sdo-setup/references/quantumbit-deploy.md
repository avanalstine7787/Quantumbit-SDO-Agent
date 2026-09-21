# QuantumBit Deploy (rlm-base-dev)

**Always run** after initial Revenue Cloud / Agentforce Revenue Management setup
(Steps 1–4). Do **not** ask whether to deploy the QuantumBit repo — only ask
whether to load the **QuantumBit product set** and which **SDO profile** to use
(see below).

## Locked policy — SDO deploy profile

1. Always clone/connect `vendor/rlm-base-dev` and run prepare via the **SDO
   orchestrator** (not a single monolithic `cci flow run prepare_rlm_org`).
2. Strip QuantumBit Lightning **org branding** from the local vendor tree.
3. Ensure **Timeline** via Metadata (`Industries` / `enableTimelinePref`).
4. **Proactive flake avoidance** (primary): payments Network rename before
   `prepare_payments`; skip Robot `enable_timeline` when Timeline Metadata is on.
5. **Automatic recovery** on remaining flakes remains the fallback — do not abort
   the whole run.
6. Keep `billing_ui` and `ux` at repository defaults (`true`). Do **not** pass
   `-o billing_ui false` or `-o ux false`. Do **not** permanently edit upstream
   `cumulusci.yml`. Do **not** use `-o tso true` as a Timeline shortcut (it
   changes unrelated prepare_core / PRM / commerce gates).

### Product set (ask from SKILL.md Step 5)

| User answer | Orchestrator flag |
|-------------|-------------------|
| Yes — deploy QuantumBit product set | `--product-set yes` |
| No — skip product / constraint sample data | `--product-set no` (= `-o qb false -o constraints_data false`) |

### SDO profile (ask from SKILL.md Step 5)

| User answer | Orchestrator flag | Extra `-o` flags |
|-------------|-------------------|------------------|
| Full QuantumBit | `--profile full` | (none beyond product-set) |
| SDO fast | `--profile fast` | `payments`, `billing_portal`, `prm`, `agents`, `collections` → `false` |

`billing_ui` and `ux` stay **on** in both profiles.

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

### 5. Ensure Timeline via Metadata (required before billing UI)

Robot `enable_timeline` flakes on many SDOs. Deploy gold Industries settings
(includes `enableTimelinePref=true`) immediately before the long CCI run. The
orchestrator then **skips** Robot `enable_timeline` entirely.

```bash
# From workspace root — deploys full gold bundle including Industries
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/deploy_org_settings_gold.py \
  --target-org <alias>
```

Or deploy only `Settings:Industries` from
[org-settings-gold/Industries.settings-meta.xml](org-settings-gold/Industries.settings-meta.xml)
if gold was already applied earlier in the same session.

### 6. prepare_rlm_org via SDO orchestrator (primary)

Ask the product-set and SDO-profile questions in SKILL.md Step 5, then run:

```bash
# From workspace root
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/run_prepare_rlm_org_sdo.py \
  --org <cci-alias> \
  --sf-org <sf-alias-or-username> \
  --repo-root vendor/rlm-base-dev \
  --profile full \          # or: fast
  --product-set yes \       # or: no
  --timings-file /tmp/prepare_rlm_org_sdo_timings.jsonl
```

What the orchestrator does:

1. Runs prepare_rlm_org steps **1–31** and **34** as discrete `cci flow|task run`
   calls.
2. **Skips steps 32–33** (`refresh_all_decision_tables`, `rebuild_search_index`)
   so skill Step 7 can run them once, last, after optional generic products.
3. **Payments preflight** (full profile): if a Live Network looks like the
   payments webhook under another display name, renames it to `Payments Webhook`
   so create `skip_existing` matches (avoids 300s×N timeout loops).
4. **Expands `prepare_billing`** and **skips** Robot `enable_timeline` (Timeline
   already on via Metadata).
5. Appends per-step timings to `--timings-file`.
6. On success, writes
   `.cursor/skills/revenue-cloud-sdo-setup/.run-state/last-prepare-rlm-org.json`
   with `completed_steps` and `skipped_steps` (resume/timings only).
7. On failure, prints `--from-step N` resume hint; state file includes
   `failed_step` / `completed_steps`.

Resume after fixing a failure:

```bash
python3 .cursor/skills/revenue-cloud-sdo-setup/scripts/run_prepare_rlm_org_sdo.py \
  --org <cci-alias> --sf-org <sf-alias> --repo-root vendor/rlm-base-dev \
  --profile <full|fast> --product-set <yes|no> \
  --from-step <N>
```

Do **not** default to a single `cci flow run prepare_rlm_org` — that reintroduces
the Timeline Robot abort. Monolithic CCI remains an emergency fallback only if
the orchestrator itself cannot run.

### 7. Long-running builds and automatic recovery (fallback)

If a discrete step still fails, recover automatically (do not stop the skill or
ask the user to “try again” as the only action), then resume the orchestrator
with `--from-step`.

#### Payments community timeout (`create_payments_webhook`)

If create times out but a Live Network already exists (`UrlPathPrefix` like
`sfpwebhook`, name may be `sfpwebhook`):

1. Do **not** create a second community.
2. Rename the existing Network display Name in place to `Payments Webhook` if needed
   so `skip_existing` matches (orchestrator preflight usually already did this).
3. Continue payments: if site XML was already patched (placeholder gone), run
   `deploy_post_payments_site` then `revert_payments_site_after_deploy` (**no**
   `--org` on revert — local file task). Else restore placeholder
   `payments-site-admin@example.com` in
   `unpackaged/post_payments/sites/Payments_Webhook.site-meta.xml` and re-run
   from orchestrator `--from-step 4` or the remaining payment tasks.
4. Finish remaining payment tasks: `publish_community` (name `Payments Webhook`),
   `deploy_post_payments_settings`, `deploy_post_payments_ext`,
   `assign_permission_sets` (`RLM_Payments`).
5. Resume orchestrator from step 5 (`deploy_full`) through `stamp_git_commit`.

#### `enable_timeline` Robot failure

Should not occur when using the orchestrator (Robot is skipped). If Timeline
Metadata was missing and billing UI fails:

1. Re-deploy gold Industries (`enableTimelinePref=true`).
2. Continue billing from `deploy_billing_id_settings` onward (never re-run
   Robot `enable_timeline` on SDOs):
   - `deploy_billing_id_settings`
   - `deploy_billing_template_settings`
   - `deploy_post_billing_ui`
   - `assign_permission_sets` (`RLM_BillingUI`)
   - `apply_context_billing_order` (**no** `--org` — uses CCI default org)
   - `cci flow run prepare_billing_portal`
3. Resume orchestrator from step 14 (`prepare_collections`).

#### Local-only CCI tasks

Never pass `--org` to:

- `revert_payments_site_after_deploy`
- `apply_context_billing_order` (pass nothing; relies on `cci org default`)

(The orchestrator already omits `--org` for these.)

## Success criteria

- Orchestrator completes (with documented recoveries if needed)
- QuantumBit apps/metadata deployed; product dataset present only if user said Yes
- SDO Lightning theme **not** replaced by QuantumBit branding
- Robot `enable_timeline` was **not** invoked (skipped)
- Summarize duration (per-step table from timings file), org alias, profile,
  product-set Yes/No, branding strip, recoveries

#### PCM search index language error (`PCM_RUNTIME_SNAPSHOT_DEPLOY_014`)

If `rebuild_search_index` warns with HTTP 400
`Specify a valid supported language and a valid default language` and continues:

1. Do **not** abort prepare — upstream already warns and continues by default.
2. In Setup, open **Product Catalog Management** / **Build Catalog Index** (or Product
   Discovery index settings) and set **Supported Languages** and **Default Language**
   (typically `en_US`), then rebuild from the UI component.
3. Document in the completion summary that Step 7 / index rebuild may need a manual
   language fix before a successful Connect API rebuild.

## Validation (timed Full Step 5)

Baseline (SDOTest5, product set Yes, monolithic + timeline fail/resume): **~81 min**.

After this skill change, a fresh Full-profile timed run should show:

1. No mid-flow abort at `enable_timeline`
2. Payments create does not burn 300s×N when a Live webhook Network already exists
3. Wall-clock under that ~81 min baseline; completion summary includes the
   orchestrator per-step timing table

## After this file

Return to SKILL.md: ask about optional **RLM Generic Demo Products**, then
**always** run Step 7 last (decision tables + PCM search index rebuild).
