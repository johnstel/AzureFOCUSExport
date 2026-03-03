# Fabric Integration Guide

This guide explains how to connect your exported FOCUS cost data to Microsoft Fabric for reporting and analysis.

## Notebook Variants

This project provides two notebook options:

- **Source-based**: [notebooks/focus_source_pipeline.ipynb](../notebooks/focus_source_pipeline.ipynb)
    - Imports from `src/azure_focus_export`
    - Better when you maintain code centrally in the Python package
- **Standalone**: [notebooks/focus_single_pipeline.ipynb](../notebooks/focus_single_pipeline.ipynb)
    - Fully self-contained
    - Better for quick Fabric experiments or isolated execution

For interactive notebook runs, you can use **user-context authentication** (`az login` / browser prompt) and avoid app secrets.

## Overview

The recommended integration pattern uses **OneLake ADLS Gen2 shortcuts**:

```
ADLS Gen2 Storage Account          OneLake (Fabric)
┌────────────────────────┐         ┌────────────────────────┐
│ cost-exports/          │         │ MyLakehouse/           │
│   focus/               │◀───────▶│   Tables/              │
│     focus-export-*/    │ shortcut│     focus_costs/        │
│       *.parquet        │         │       (reads in-place)  │
└────────────────────────┘         └────────────────────────┘
```

**Benefits of shortcuts over copying:**
- No data duplication — Fabric reads directly from your storage account
- No pipeline to maintain for data movement
- Near-instant data availability after export completes
- Reduced Fabric compute costs (no copy activity)

## Step 1: Create a Lakehouse

1. Open the **Microsoft Fabric portal** (app.fabric.microsoft.com)
2. Navigate to your Workspace
3. Click **+ New → Lakehouse**
4. Name it (e.g., `CostManagement`)
5. Click **Create**

## Step 2: Create an ADLS Gen2 Cloud Connection

1. In Fabric, go to **Settings (⚙) → Manage connections and gateways**
2. Click **+ New connection**
3. Select **Cloud → Azure Data Lake Storage Gen2**
4. Fill in:
   - **Server**: `https://<storage-account-name>.dfs.core.windows.net`
   - **Authentication**: Use Service Principal or Organizational Account
   - **Tenant ID**, **Client ID**, **Client Secret** (same as your export config)
5. Click **Create**

## Step 3: Create the OneLake Shortcut

1. Open your Lakehouse in the Fabric portal
2. In the **Files** section (or **Tables** if your data is in Delta format), right-click and select **New shortcut**
3. Select **Azure Data Lake Storage Gen2**
4. Choose the cloud connection you created in Step 2
5. Set:
   - **URL**: `https://<storage-account-name>.dfs.core.windows.net`
   - **Shortcut Name**: `focus_costs`
   - **Sub Path**: `/<container-name>/<root-folder>` (e.g., `/cost-exports/focus`)
6. Click **Create**

The shortcut now appears in your Lakehouse. All exported Parquet files are immediately accessible.

## Step 4: Query the Data

### Spark SQL (Notebooks)

```python
# Read all FOCUS cost data
df = spark.read.parquet("Files/focus_costs/**/*.parquet")
df.printSchema()
display(df.limit(10))
```

### Monthly Cost Summary

```python
df.createOrReplaceTempView("focus_costs")

summary = spark.sql("""
    SELECT 
        date_format(ChargePeriodStart, 'yyyy-MM') as Month,
        ServiceName,
        ServiceCategory,
        SUM(BilledCost) as TotalBilledCost,
        SUM(EffectiveCost) as TotalEffectiveCost,
        COUNT(*) as LineItems
    FROM focus_costs
    GROUP BY 1, 2, 3
    ORDER BY 1 DESC, 4 DESC
""")
display(summary)
```

### Cost by Resource Group

```python
by_rg = spark.sql("""
    SELECT 
        x_ResourceGroupName,
        SUM(EffectiveCost) as TotalCost,
        COUNT(DISTINCT ResourceId) as ResourceCount
    FROM focus_costs
    WHERE x_ResourceGroupName IS NOT NULL
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 20
""")
display(by_rg)
```

### Commitment Discount Analysis

```python
commitments = spark.sql("""
    SELECT 
        CommitmentDiscountType,
        CommitmentDiscountName,
        SUM(BilledCost) as BilledCost,
        SUM(EffectiveCost) as EffectiveCost,
        SUM(BilledCost) - SUM(EffectiveCost) as Savings
    FROM focus_costs
    WHERE CommitmentDiscountId IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 5 DESC
""")
display(commitments)
```

### SQL Analytics Endpoint

If your shortcut is in the **Tables** section with Delta format, you can also query via the SQL analytics endpoint:

```sql
SELECT TOP 100 *
FROM [CostManagement].[dbo].[focus_costs]
WHERE ChargePeriodStart >= '2025-01-01'
ORDER BY EffectiveCost DESC
```

## Step 5: Build Power BI Reports

### Direct Lake Mode (Recommended)

1. From your Lakehouse, click **New semantic model**
2. Select the `focus_costs` table (or shortcut)
3. Click **Confirm**
4. The semantic model is created in **Direct Lake** mode — Power BI reads directly from OneLake
5. Click **New report** to start building visuals

### Suggested Report Views

- **Cost Trend** — Line chart of `EffectiveCost` by `ChargePeriodStart` (monthly)
- **Cost by Service** — Bar chart of `EffectiveCost` by `ServiceName`
- **Cost by Resource Group** — Treemap of `EffectiveCost` by `x_ResourceGroupName`
- **Commitment Utilization** — Gauge showing reservation/savings plan usage
- **Top Resources** — Table of `ResourceName`, `ResourceType`, `EffectiveCost`

### Key FOCUS Columns for Reports

| Column | Description |
|--------|-------------|
| `BilledCost` | Actual invoiced cost |
| `EffectiveCost` | Amortized cost (spreads upfront payments over term) |
| `ServiceName` | Azure service name |
| `ServiceCategory` | High-level service category |
| `ResourceName` | Individual resource name |
| `x_ResourceGroupName` | Resource group |
| `SubAccountName` | Subscription name |
| `RegionName` | Azure region |
| `PricingCategory` | On-Demand, Commitment, etc. |
| `ChargeCategory` | Usage, Purchase, Tax, etc. |
| `Tags` | Custom resource tags (JSON) |
| `CommitmentDiscountName` | Reservation or savings plan name |

## Step 6: Schedule Ongoing Updates

After running `azure-focus-export schedule`, a monthly export runs automatically. New data appears in the storage account and is immediately visible through the OneLake shortcut — no additional pipeline needed.

To refresh Power BI reports with new data:
- **Direct Lake**: Automatically picks up new data on next query
- **Import mode**: Configure a scheduled refresh in the semantic model settings

## Troubleshooting

### Shortcut doesn't show data
- Verify the storage account, container, and path are correct
- Check that the cloud connection has valid credentials
- Ensure the storage account firewall allows access from Fabric

### Parquet files not recognized as tables
- Place the shortcut in the **Files** section if data isn't in Delta format
- Azure Cost Management exports Parquet (not Delta) — use `spark.read.parquet()` to query

### Authentication errors
- Verify the Service Principal or Managed Identity has **Storage Blob Data Reader** on the storage account
- For Fabric Managed Identity, ensure the workspace identity is assigned the correct roles
