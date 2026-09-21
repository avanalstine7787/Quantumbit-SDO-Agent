# Billing Guided Setup → Metadata Mapping

Source profile: **EFM2** gold Billing settings (portable toggles/names only).
Help: [Billing Guided Setup](https://help.salesforce.com/s/articleView?id=ind.billing_guided_setup.htm&type=5)

Deploy via `org-settings-gold/Billing.settings-meta.xml` (no hardcoded Salesforce IDs).

| Guided Setup assistant | Automated via metadata |
|------------------------|------------------------|
| Billing Prerequisites (enable Billing) | `enableBillingSetup=true` + Phase A perm assignment |
| Invoice / Document Generation | `enableInvoicePdfGeneration`, `enableInvoiceEmailDelivery` |
| Accounting / journals / FX | `enableTransactionJournalCreation`, `enableForeignExchangeTrxnJrnlCreation`, `enableTrxnAmountsStorageInCorpCurrency` |
| Payment configurations (feature flags) | `enablePaymentSchedulesAndItemsCreation`, `enablePaymentApplicationToPostedInvoices`, `enableTransactionsApplicationToInvoices`, `enableAutomaticRefunds`, `enableFailedPaymentsRetry`, `enableEnhancedPaymentData` |
| Credit memo / dispute / dunning / milestones | `enableCrMemoApplicationToPostedInvoices`, `enableConvertedCrMemoCrMemoLnAppln`, `enableNegInvoiceLnConversionToCrMemoLn`, `enableBillingDisputeManagement`, `enableDunningOrchestration`, `enableMilestoneBillingForAmend` |

## Deferred until billing data / features exist

Deploy only after QuantumBit `prepare_billing` (or equivalent) succeeds; skip on
Metadata errors rather than copying EFM2 IDs:

- `billingContextDefinition=RLM_BillingContext`, `billingContextSourceMapping=OrderEntitiesMapping`
- DPE definition names (`defaultAPClosureDPEDefnName`, FX/LEAP DPE names)
- `enableInvoiceSequenceService`, `enableCreditMemoSequenceService` (rejected on some orgs until sequence setup)
- `ruleBasedCrAndPymtAppln`
- Default legal entity, billing/tax treatments, invoice templates, email template, GL accounts

Resolve IDs via SOQL on the **target** org (same pattern as
`vendor/rlm-base-dev/unpackaged/post_billing_id_settings`).

## RevenueManagement note

EFM2 has `enableContextReuse=true`. Gold XML omits it by default because some
orgs reject the field on Metadata deploy; enable via Setup if Help requires it
and deploy fails.

## Timeline (Industries)

Gold includes [Industries.settings-meta.xml](Industries.settings-meta.xml) with
`enableTimelinePref=true` (same Metadata path TSO builds use). Deploy this in
Phase A and again immediately before QuantumBit prepare so Billing UI flexipages
that reference Timeline can deploy. The SDO orchestrator
(`run_prepare_rlm_org_sdo.py`) **skips** Robot `enable_timeline` after Metadata
is on — do not wait for a Robot flake. Fallback recovery (if Metadata was
missing) is in [quantumbit-deploy.md](../quantumbit-deploy.md).
