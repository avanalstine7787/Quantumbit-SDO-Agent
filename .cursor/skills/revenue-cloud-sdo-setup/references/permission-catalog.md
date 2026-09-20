# Permission Catalog (Admin-for-Everyone)

Assign **PSLs first**, then **permission sets**. Discover what exists in the target
org; skip missing names. Assign the full admin/design catalog to every eligible
active user (see `scripts/assign_revenue_access.py`).

Sources:

- https://help.salesforce.com/s/articleView?id=ind.admin_permission_sets.htm&type=5
- https://help.salesforce.com/s/articleView?id=ind.revenue_cloud_permission_sets_table.htm&type=5
- Common Revenue Cloud PSL / PS labels used in field setups

## Permission set licenses (MasterLabel / common names)

Match by `MasterLabel` or `DeveloperName` with case-insensitive contains when exact
match is missing.

| Priority | Label / pattern |
|----------|-----------------|
| Core | Revenue Cloud User |
| PCM | Product Catalog Management Administrator |
| PCM | Product Catalog Management Viewer |
| Pricing | Salesforce Pricing Design Time |
| Pricing | Salesforce Pricing Run Time |
| Billing | Billing |
| Discovery | Product Discovery User |
| Config | Product Configuration User |
| BRE | Business Rules Engine Designer |
| BRE | Business Rules Engine Runtime |
| Pipelines | Data Pipelines Base User |
| DPE | Data Processing Engine Psl |
| Omni | OmniStudio |
| DocGen | DocGen Designer |
| DocGen | Document Builder User |
| Rating | Rate Management Design Time |
| Rating | Rate Management Run Time |
| Usage | Usage Management Design Time |
| Usage | Usage Management Run Time |
| Wallet | Wallet Management User |
| Decimal | Decimal Quantity DesignTime User |
| Decimal | Decimal Quantity Runtime User |
| CLM | Contract LifeCycle Management User |
| CLM | Clause Management User |
| CLM | Microsoft Word 365 |
| DRO | Fulfillment User PSL |
| DRO | Obligation Management User |
| Agentforce | Any Einstein / Agentforce / Gen AI related PSL present in org |

## Permission sets (API Name → Label)

Assign all that exist. Admin/design entries are required for admin-for-everyone;
viewer/runtime entries are included when present (not as a ceiling).

### Product catalog and discovery

| API Name | Label |
|----------|-------|
| ProductCatalogManagementAdministrator | Product Catalog Management Designer |
| ProductCatalogManagementViewer | Product Catalog Management Viewer |
| ProductDiscoveryAdmin | Product Discovery Admin |
| ProductDiscoveryUser | Product Discovery User |

### Pricing and rules

| API Name | Label |
|----------|-------|
| CorePricingAdmin | Salesforce Pricing Admin |
| CorePricingDesignTimeUser | Salesforce Pricing Design Time User |
| CorePricingManager | Salesforce Pricing Manager |
| CorePricingRunTimeUser | Salesforce Pricing Run Time User |
| BREDesigner | Rule Engine Designer |
| BRERuntime | Rule Engine Runtime |

### Billing and tax

| API Name | Label |
|----------|-------|
| RevenueLifecycleManagementBillingAdmin | Billing Admin |
| RevenueLifecycleManagementBillingOperations | Billing Operations User |
| RevenueLifecycleManagementBillingTaxAdmin | Tax Admin |
| RevenueLifecycleManagementTaxConfiguration | Tax Configuration |
| RevenueLifecycleManagementBillingCreateInvoiceFromBillingScheduleApi | Generate Invoices From Billing Schedule API |
| RevenueLifecycleManagementBillingVoidPostedInvoiceApi | Void a Posted Invoice API |
| RevenueLifecycleManagementCreateBillingScheduleFromBillingTransactionApi | Create Billing Schedules From Billing Transactions API |
| RevLifecycleManagementCalculateTaxesApi | CalculateTaxes API |

### Quotes, orders, assets, APIs

| API Name | Label |
|----------|-------|
| RevLifecycleManagementCreateOrderFromQuote | Create Orders from Quotes |
| RevLifecycleManagementCoreCPQAssetization | Assetize Order |
| RevLifecycleManagementQuotePricesTaxes | Price and Tax Calculation for Quoting |
| RevLifecycleManagementCalculatePricesApi | CalculatePrices API |
| RevLifecycleManagementPlaceOrderApi | PlaceOrder API |
| RevLifecycleManagementCreateContractApi | CreateContract API |
| RevLifecycleManagementInitiateAmendmentApi | InitiateAmendment API |
| RevLifecycleManagementInitiateCancellationApi | InitiateCancellation API |
| RevLifecycleManagementInitiateRenewalApi | InitiateRenewal API |
| RevLifecycleManagementProductAndPriceConfigurationApi | ProductAndPriceConfiguration API |
| RevLifecycleManagementProductImportApi | ProductImport API |
| OrderSubmitUser | Order Submit User |

### Usage, rating, wallets, decimal qty

| API Name | Label |
|----------|-------|
| RevLifecycleManagementUsageDesignUser | Usage: Design User |
| UsageManagementDesigner | Usage Management Design Time |
| UsageManagementRunTimeUser | Usage Management Run Time |
| RatingAdmin | Rate Management: Admin |
| RatingDesignTimeUser | Rate Management: Design Time User |
| RatingManager | Rate Management: Manager |
| RatingRunTimeUser | Rate Management: Run Time User |
| WalletManagementUser | Wallet Management User |
| DecimalQuantityDesigntime | DecimalQuantityDesigntime |
| DecimalQuantityRuntime | DecimalQuantityRuntime |

### Document generation, OmniStudio, data pipelines

| API Name | Label |
|----------|-------|
| DocGenDesigner | DocGen Designer |
| DocGenUser | DocGen User |
| DocumentBuilderUser | Document Builder User |
| OmniStudioAdmin | OmniStudio Admin |
| AnalyticsStoreUser | Data Pipelines Base User |
| DataProcessingEngineUser | Use Data Processing Engine |

### CLM

| API Name | Label |
|----------|-------|
| CLMAdminUser | CLM Admin User |
| CLMRuntimeUser | CLM Runtime User |
| ClauseDesigner | Clause Designer User |
| ClauseUser | Clause User |

### DRO / fulfillment

| API Name | Label |
|----------|-------|
| DfoAdminUser | DRO Admin User |
| DFODesignerUser | Fulfillment Designer |
| DFOManagerOperatorUser | Fulfillment Manager/Operator |
| DROOrderSubmitInitiateUser | DRO Order Submit Initiate User |
| ObligationAssignee | Obligation Assignee |
| ObligationManager | Obligation Manager |
| ObligationUser | Obligation User |

### Agentforce / Einstein (discover by pattern)

Also assign any permission set whose Name or Label matches (case-insensitive):

- `Agentforce`
- `Einstein`
- `GenAI`
- `PromptTemplate`
- `Manage AI Agents` (user permission may live on a perm set)

## Users to include / exclude

**Include:** `User` where `IsActive = true` and `UserType = 'Standard'` (and other
interactive user types that can hold PSLs if present).

**Exclude:**

- Automated Process / Platform Integration User patterns
- Chatter Free / Chatter Guest when they cannot hold the licenses
- Users that fail assignment with LICENSE_LIMIT_EXCEEDED (record and continue)

## Seat exhaustion

When a PSL has `UsedLicenses >= TotalLicenses`, skip further assignments for that
PSL and report which users did not receive it. Do not abort the whole run.
