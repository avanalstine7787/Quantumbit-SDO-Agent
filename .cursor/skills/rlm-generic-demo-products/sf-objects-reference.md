# Salesforce RLM Object & Field Reference

Field format: `API Name | Type | Notes`

Companion to [`SKILL.md`](SKILL.md) (`salesforce-rlm-generic-demo-products`). Prefer the skill for workflow; use this file for field-level gotchas.

> Fields marked ⚠️ are common failure points validated in prior live runs.

---

## Runtime lookup names (never hardcode IDs)

Resolve by `Name` at runtime against the target org. Stop if missing.

| Object | Name |
|---|---|
| `TaxPolicy` | `Default Tax Policy` |
| `BillingPolicy` | `Billing Policy - Advance` |
| `BillingPolicy` | `Billing Policy - Arrears` |
| `ProductSellingModel` | Selected selling model name(s) from Phase 3 |
| `Pricebook2` | Standard price book (`IsStandard=true`) |
| `ProductRelationshipType` | Bundle component relationship (see below) |
| `ProrationPolicy` | `Default Proration Policy` |
| `UnitOfMeasureClass` | `Case` |
| `UnitOfMeasure` | `Each` |
| `UnitOfMeasure` | `USD` |
| `UsageResourceBillingPolicy` | `Monthly Total` |
| `UsageOveragePolicy` | `Default Usage Overage Policy` |
| `RatingFrequencyPolicy` | `Monthly Rating Frequency` |
| `RateCard` | `Base Rate Card` |
| `LightningExperienceTheme` | Developer Name `QuantumBitSLDSv2` (Setup → Themes and Branding; always the existing active theme) |

---

## ProductCatalog
| API Name | Type | Value / Notes |
|---|---|---|
| `Name` | Text(255) | Company name + " Catalog" (e.g., "Acme Catalog") |

> ⚠️ `IsActive` does **not** exist on `ProductCatalog` — omit it.

---

## ProductCategory
| API Name | Type | Value / Notes |
|---|---|---|
| `Name` | Text(255) | Always `"Offerings"` |
| `CatalogId` | Lookup(ProductCatalog) | ID of the catalog created above |

> ⚠️ `IsActive` does **not** exist on `ProductCategory` — omit it.

---

## ProductCategoryProduct
Junction object assigning a product to a category.

| API Name | Type | Value / Notes |
|---|---|---|
| `ProductId` | Lookup(Product2) | ID of the product |
| `ProductCategoryId` | Lookup(ProductCategory) | ID of the "Offerings" category |

---

## Product2
| API Name | Type | Value / Notes |
|---|---|---|
| `Name` | Text(255) | Full product name |
| `ProductCode` | Text(255) | Concise unique code from research phase |
| `Description` | Text Area(4000) | Concise description — prefer Python REST API for long text, not `--values` |
| `IsActive` | Checkbox | Always `true` |
| `IsAssetizable` | Checkbox | Always `true` |
| `CurrencyIsoCode` | Picklist | Always `USD` |
| `DisplayUrl` | URL(1000) | `/resource/<sanitizedResourceName>` when an image was uploaded |
| `Type` | Picklist | `Bundle` — bundle parent products only; omit for all others |
| `ConfigureDuringSale` | Picklist | `Allowed` — bundle parent products only; omit for all others |
| `TaxPolicyId` | Lookup(TaxPolicy) | Always set — ID of "Default Tax Policy" |
| `BillingPolicyId` | Lookup(BillingPolicy) | Set only when selling model is **not** `One-Time` (Advance or Arrears policy from Phase 3) |
| `UsageModelType` | Picklist | Always `Anchor` for usage-priced products (Phase 3); omit for all other products |

> ⚠️ Do NOT use `sf data create record --body <file>` — the `--body` flag does not exist in SF CLI versions prior to 2.130. Use the **Python REST API approach** when needed for product creation.
>
> ⚠️ Do **not** run milestone billing setup scripts in this skill. Org billing policies (`Billing Policy - Advance` / `Arrears`) are looked up at runtime.

**Static resource name sanitization rule**: Replace spaces and hyphens with underscores; strip all other special characters. Salesforce static resource names must be alphanumeric + underscores only.

---

## ProductSellingModelOption
| API Name | Type | Value / Notes |
|---|---|---|
| `Product2Id` | Lookup(Product2) | ID of the product |
| `ProductSellingModelId` | Master-Detail(ProductSellingModel) | Runtime-selected selling model for this product |
| `ProrationPolicyId` | Lookup(ProrationPolicy) | Always set — ID of "Default Proration Policy" from Phase 4 |
| `IsDefault` | Checkbox | **Required — always set `true`** so the selling model option resolves for pricing |

> ⚠️ Field is `Product2Id`, **not** `ProductId`.

---

## PricebookEntry
| API Name | Type | Value / Notes |
|---|---|---|
| `Product2Id` | Lookup(Product2) | ID of the product |
| `Pricebook2Id` | Lookup(Pricebook2) | ID of the Standard Price Book (`IsStandard=true`) |
| `UnitPrice` | Currency | Proposed price from research / confirmed proposal |
| `IsActive` | Checkbox | Always `true` |
| `ProductSellingModelId` | Lookup(ProductSellingModel) | Same selling model Id used for the product |
| `CurrencyIsoCode` | Picklist | Always `USD` |

---

## ProductRelationshipType
Pre-fetch the correct relationship type ID before creating bundle components:

```soql
SELECT Id, Name FROM ProductRelationshipType
WHERE Name = 'Bundle to Bundle Component Relationship'
```

Store as `$BUNDLE_REL_TYPE_ID`. This ID is required on every `ProductRelatedComponent` record.

---

## ProductComponentGroup
Intermediate layer between a bundle parent and its add-on children.

| API Name | Type | Value / Notes |
|---|---|---|
| `Name` | Text(255) | `"Optional Add-ons"` |
| `ParentProductId` | Lookup(Product2) | ID of the bundle parent product |
| `MinBundleComponents` | Number | `0` (add-ons are optional) |
| `MaxBundleComponents` | Number | Total number of available add-on children |
| `Sequence` | Number | `1` |

> ⚠️ Fields are `MinBundleComponents` / `MaxBundleComponents`, **not** `MinQty` / `MaxQty`.

---

## ProductRelatedComponent
Links each add-on child product to the component group.

| API Name | Type | Value / Notes |
|---|---|---|
| `ProductComponentGroupId` | Lookup(ProductComponentGroup) | ID of the component group |
| `ParentProductId` | Lookup(Product2) | ID of the bundle parent product — **required** |
| `ChildProductId` | Lookup(Product2) | ID of the add-on child product |
| `ProductRelationshipTypeId` | Lookup(ProductRelationshipType) | ID of "Bundle to Bundle Component Relationship" — **required** |
| `IsDefaultComponent` | Checkbox | `false` — add-ons are optional, not pre-selected |
| `DoesBundlePriceIncludeChild` | Checkbox | `false` — child priced separately; must be set explicitly (defaults to `true` if omitted) |
| `Quantity` | Number | `1` |
| `Sequence` | Number | Sequential integer per child (1, 2, 3…) |

> ⚠️ Field is `ProductComponentGroupId`, **not** `ParentProductComponentGroupId`.
> ⚠️ Field is `IsDefaultComponent`, **not** `IsDefault`.
> ⚠️ Both `IsDefaultComponent` and `DoesBundlePriceIncludeChild` must **always** be set to `False`. `DoesBundlePriceIncludeChild` defaults to `True` when omitted, so set it explicitly.
> ⚠️ `ParentProductId` is **required** — include the bundle parent's product ID.
> ⚠️ `ProductRelationshipTypeId` is **required** — pre-fetch in Phase 4.
> ⚠️ `ParentProductRole` and `ChildProductRole` are **read-only** (auto-set by the system) — do not attempt to set them; you will get an `INVALID_FIELD_FOR_INSERT_UPDATE` error.

---

## UsageResource
| API Name | Type | Value / Notes |
|---|---|---|
| `Name` | Text | Product-relevant meter name (e.g. `Per Visit`, `Per Replacement`) |
| `Code` | Text | Unique code (e.g. `UR-<ProductCode>`) |
| `Category` | Picklist | Always `Usage` |
| `Status` | Picklist | Insert as `Draft`; activate in Phase 6 Step 3 **before** ProductUsageResource |
| `UnitOfMeasureClassId` | Lookup(UnitOfMeasureClass) | `Case` |
| `DefaultUnitOfMeasureId` | Lookup(UnitOfMeasure) | `Each` |
| `UsageDefinitionProductId` | Lookup(Product2) | Product this resource meters |
| `UsageResourceBillingPolicyId` | Lookup(UsageResourceBillingPolicy) | `Monthly Total` |

---

## ProductUsageResource
| API Name | Type | Value / Notes |
|---|---|---|
| `ProductId` | Lookup(Product2) | Target product |
| `UsageResourceId` | Lookup(UsageResource) | UsageResource from Step 1 |
| `Status` | Picklist | Insert as `Draft`; activate in Phase 6 Step 3 **after** UsageResource |
| `EffectiveStartDate` | Date | November 1 of the previous calendar year (e.g. run in 2026 → `2025-11-01`) |

---

## ProductUsageResourcePolicy
| API Name | Type | Value / Notes |
|---|---|---|
| `ProductUsageResourceId` | Master-Detail(ProductUsageResource) | New PUR Id |
| `ProductSellingModelId` | Lookup(ProductSellingModel) | Same selling model as the product |
| `UsageAggregationPolicyId` | Lookup(UsageResourceBillingPolicy) | `Monthly Total` (API field points at UsageResourceBillingPolicy) |
| `UsageOveragePolicyId` | Lookup(UsageOveragePolicy) | `Default Usage Overage Policy` |
| `RatingFrequencyPolicyId` | Lookup(RatingFrequencyPolicy) | `Monthly Rating Frequency` |

---

## RateCardEntry
| API Name | Type | Value / Notes |
|---|---|---|
| `UsageResourceId` | Lookup(UsageResource) | UsageResource from Step 1 |
| `ProductId` | Lookup(Product2) | Target product |
| `Status` | Picklist | Insert as `Draft`, then set `Active` |
| `RateCardId` | Master-Detail(RateCard) | `Base Rate Card` |
| `DefaultUnitOfMeasureId` | Lookup(UnitOfMeasure) | `Each` |
| `ProductSellingModelId` | Lookup(ProductSellingModel) | Same selling model as the product |
| `RateUnitOfMeasureId` | Lookup(UnitOfMeasure) | `USD` |
| `Rate` | Number(12, 6) | Proposed price from research / confirmed proposal |
| `RateNegotiation` | Picklist | Always `Negotiable` |
| `EffectiveFrom` | Date/Time | November 1 of the previous calendar year |

**Activation order (usage):** create Draft UsageResource → PUR → PURP → activate UsageResource → activate PUR → create Draft RateCardEntry → activate RateCardEntry.

---

## StaticResource (image upload via REST API)

> ⚠️ Do **not** use `sf project deploy start --metadata` for static resource upload — it requires an SFDX project scaffold and does not reliably package binary files ("Required field is missing: content"). Use the REST API approach below (no scaffold needed).

> ⚠️ Do **not** use `curl` with a command-line `-d` argument containing the base64 body — large images produce base64 strings that exceed shell argument length limits (`argument list too long`). Use Python's `urllib` instead.

The `scripts/upload-static-resource.sh` helper does this: it fetches org credentials from `sf org display --target-org <orgUsername> --json` (third argument, or `SF_TARGET_ORG`), base64-encodes the image, and POSTs to `<instanceUrl>/services/data/v<apiVersion>/sobjects/StaticResource` with body `{Name, Body, ContentType, CacheControl}`. It is idempotent (skips resources that already exist). Pass the **`./assets/` copy** of the image (also keep the absolute path returned by `GenerateImage`).

```bash
bash scripts/upload-static-resource.sh "<absoluteImagePath>" "<sanitizedResourceName>" "<orgUsername>"
```

---

## LightningExperienceTheme / BrandingSetProperty (org Brand Image)

From the setup menu, under Themes and Branding, there will always be an existing active record: **QuantumBitSLDSv2** (Developer Name). The existing Brand Image will need to be replaced with the logo from the researched company.

The logo image from the researched company will need to be **600x120 px**, JPG/PNG/GIF, and smaller than 5 MB. Do **not** stretch; the helper contain+pads onto a 600×120 canvas.

| Object | API / field | Notes |
|---|---|---|
| `LightningExperienceTheme` | `DeveloperName` | Lookup key: `QuantumBitSLDSv2`. Query via **Tooling API**. Never hardcode the theme Id. |
| `LightningExperienceTheme` | `DefaultBrandingSetId` | Id of the theme’s `BrandingSet`. Stop if missing. |
| `BrandingSetProperty` | `PropertyName` | Case-sensitive. Brand Image is `BRAND_IMAGE`. |
| `BrandingSetProperty` | `PropertyValue` | `/file-asset/<ContentAsset.DeveloperName>?v=<VersionNumber>` |
| `ContentVersion` | `IsAssetEnabled` | Set `true` on **first** insert so Salesforce creates a `ContentAsset`. Omit on later versions. |
| `ContentAsset` | `DeveloperName` | Alphanumeric + underscores, start with a letter, ≤40 chars (e.g. `AcmeCorp_BrandLogo`). |

Query theme + property (Tooling API):

```soql
SELECT Id, DeveloperName, DefaultBrandingSetId
FROM LightningExperienceTheme
WHERE DeveloperName = 'QuantumBitSLDSv2'
```

```soql
SELECT Id, PropertyName, PropertyValue
FROM BrandingSetProperty
WHERE BrandingSetId = '<DefaultBrandingSetId>'
AND PropertyName = 'BRAND_IMAGE'
```

> ⚠️ `BRAND_IMAGE` must refer to an **asset file** (`ContentAsset`) that already exists in the org — not a Static Resource and not a regular Salesforce File URL.
>
> ⚠️ Do **not** use `sf project deploy start --metadata` for the brand image — same scaffold/binary issues as StaticResource. Use `scripts/update-theme-brand-image.sh`.
>
> ⚠️ Do **not** change other theme properties (colors, banner, etc.). Replace only `BRAND_IMAGE`.
>
> ⚠️ Tooling API is required for `LightningExperienceTheme` and `BrandingSetProperty` (`sf data query --use-tooling-api`, or REST `/tooling/query` and `/tooling/sobjects/BrandingSetProperty`).

The helper resizes, uploads (idempotent: new `ContentVersion` if the asset already exists), and PATCHes `BRAND_IMAGE`:

```bash
bash scripts/update-theme-brand-image.sh "<absoluteLogoPath>" "<sanitizedAssetName>" "<orgUsername>"
```

---

## Documentation References

- [RLM Developer Guide](https://developer.salesforce.com/docs/atlas.en-us.revenue_lifecycle_management_dev_guide.meta/revenue_lifecycle_management_dev_guide/) — primary object reference for all RLM-specific objects
- [Usage Management Standard Objects](https://developer.salesforce.com/docs/atlas.en-us.revenue_lifecycle_management_dev_guide.meta/revenue_lifecycle_management_dev_guide/usage_management_std_objects_parent.htm) — UsageResource, PUR, policies, RateCardEntry
- [Product Catalog Data Model Gallery](https://developer.salesforce.com/docs/platform/data-models/guide/product-catalog-mgmt.html) — full data model including `ProductComponentGroup`, `ProductRelatedComponent`, `ProductRelationshipType`
- [Salesforce Pricing Data Model](https://developer.salesforce.com/docs/platform/data-models/guide/salesforce-pricing.html) — `ProductSellingModel`, `ProductSellingModelOption`, `PricebookEntry` relationships
- [Trailhead: Create a Product Bundle](https://trailhead.salesforce.com/content/learn/modules/product-catalog-management-with-revenue-cloud/create-a-product-bundle) — step-by-step configurable bundle setup with component groups
- [Trailhead: Get Started with Product Catalog Management](https://trailhead.salesforce.com/content/learn/modules/product-catalog-management-with-revenue-cloud/get-started-with-product-catalog-management) — catalog/category foundational context
- [Salesforce Help: Product Catalog Products](https://help.salesforce.com/s/articleView?id=ind.product_catalog_products.htm&type=5) — product types including bundle parent
- [SF CLI Command Reference](https://developer.salesforce.com/docs/atlas.en-us.sfdx_cli_reference.meta/sfdx_cli_reference/cli_reference_top.htm) — `sf data create record`, `sf data query` syntax
- [PricebookEntry Object Reference](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_pricebookentry.htm) — field-level reference
- [BrandingSet (Metadata API)](https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_brandingset.htm) — `BRAND_IMAGE` 600x120 asset-file requirement
- [LightningExperienceTheme (Metadata API)](https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_lightningexperiencetheme.htm) — theme to BrandingSet relationship
- [ContentAsset Object Reference](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_contentasset.htm) — asset files referenced by `/file-asset/`
