# Quantumbit SDO Agent

Cursor agent (project skill) that sets up **Agentforce Revenue Management**,
**Revenue Cloud**, and **Salesforce Billing** in a Salesforce org, **always**
deploys [QuantumBit rlm-base-dev](https://github.com/bgaldino/rlm-base-dev)
(with an optional product set), optionally runs **RLM Generic Demo Products**,
then always refreshes decision tables / the PCM search index.

This is **not** an in-org Agentforce agent. It runs in Cursor and drives the org via
CLI / MCP.

## Invoke

In Cursor chat, ask for something like:

- “Set up Revenue Cloud / Agentforce Revenue Management on my SDO”
- “Run the revenue-cloud-sdo-setup skill”
- “Configure ARM and Billing, then deploy QuantumBit”

The skill **must** ask for the target org first and prompt authorization before any
setup mutations.

## What it does

1. Asks for the target org and authorizes it (QX / `sf`)
2. Assigns **admin-for-everyone** Revenue Cloud / Billing / related permissions
3. Deploys EFM2 gold org settings + Quotes related list on Opportunity layouts
4. Follows Salesforce Help [Set Up Agentforce for Revenue Management](https://help.salesforce.com/s/articleView?id=ind.rev_agent_setup.htm&type=5)
5. **Always** deploys QuantumBit (`prepare_rlm_org` SDO profile); asks whether to
   include the QuantumBit **product set** (`qb` / `constraints_data`)
6. Asks whether to run [RLM Generic Demo Products](.cursor/skills/rlm-generic-demo-products/SKILL.md);
   on Yes, always syncs that skill from
   [upstream](https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill)
   (commit/push if the local copy changed) before running
7. **Always** refreshes decision tables and rebuilds the PCM search index

## Skill locations

```
.cursor/skills/revenue-cloud-sdo-setup/
  SKILL.md
  references/
  scripts/

.cursor/skills/rlm-generic-demo-products/
  SKILL.md
  scripts/
```

## Notes

- `vendor/rlm-base-dev/` is gitignored; the skill clones it during Step 5.
- Upstream generic-products source (synced on every Step 6 Yes):
  https://github.com/aaronlong78/8-9-26-CBS-SEs-demo-product-builder-skill
- Irreversible org toggles always require explicit confirmation.
