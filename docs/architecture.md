# Architecture

This document describes the design decisions and technical architecture of Azure FOCUS Export.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Environment                             │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐                          │
│  │   CLI App    │    │ Fabric Notebook  │                          │
│  │  (local/CI)  │    │  (Spark env)     │                          │
│  └──────┬───────┘    └────────┬─────────┘                          │
│         │                     │                                     │
│         ▼                     ▼                                     │
│  ┌──────────────────────────────────────┐                          │
│  │      azure_focus_export package      │                          │
│  │                                      │                          │
│  │  ┌────────┐  ┌─────────┐  ┌───────┐ │                          │
│  │  │  Auth  │  │ Config  │  │ Utils │ │                          │
│  │  └───┬────┘  └────┬────┘  └───────┘ │                          │
│  │      │            │                  │                          │
│  │  ┌───▼────────────▼──┐               │                          │
│  │  │   Exports API     │               │                          │
│  │  │   Client          │               │                          │
│  │  └───┬───────────────┘               │                          │
│  │      │                               │                          │
│  │  ┌───▼────┐ ┌─────────┐ ┌─────────┐ │                          │
│  │  │ Seeder │ │ Monitor │ │Schedule │ │                          │
│  │  └────────┘ └─────────┘ └─────────┘ │                          │
│  └──────────────────┬───────────────────┘                          │
└─────────────────────┼───────────────────────────────────────────────┘
                      │ HTTPS (REST API)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Azure Cloud                                      │
│                                                                     │
│  ┌──────────────────────────┐      ┌────────────────────────────┐  │
│  │  Azure Cost Management   │      │  ADLS Gen2 Storage Account │  │
│  │                          │      │                            │  │
│  │  Exports API             │─────▶│  cost-exports/             │  │
│  │  - Create Export         │      │    focus/                  │  │
│  │  - Execute Export        │      │      focus-export-2024-01/ │  │
│  │  - Get Status            │      │        manifest.json       │  │
│  │  - Schedule Recurring    │      │        part0.parquet       │  │
│  │                          │      │        part1.parquet       │  │
│  └──────────────────────────┘      │      focus-export-2024-02/ │  │
│                                    │        ...                 │  │
│                                    └─────────────┬──────────────┘  │
└──────────────────────────────────────────────────┼──────────────────┘
                                                   │ ADLS Gen2 Shortcut
                                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Microsoft Fabric                                  │
│                                                                     │
│  ┌────────────────┐  ┌───────────────┐  ┌────────────────────────┐ │
│  │   OneLake      │  │   Lakehouse   │  │  Power BI Reports     │ │
│  │                │  │               │  │                        │ │
│  │  Shortcut ─────│──│─▶ Tables/     │──│─▶ Cost Trend          │ │
│  │  (reads from   │  │    focus_costs│  │   Cost by Service     │ │
│  │   ADLS Gen2)   │  │               │  │   Resource Analysis   │ │
│  └────────────────┘  └───────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Historical Seeding (one-time)

```
For each of the last 36 months:
  1. Create export:  PUT /scope/providers/Microsoft.CostManagement/exports/{name}
     - type: FocusCost
     - timeframe: Custom (1st to last day of month)
     - format: Parquet, compression: snappy
     - schedule: Inactive (one-time)
  2. Execute export: POST /scope/providers/Microsoft.CostManagement/exports/{name}/run
  3. Poll status:    GET  /scope/providers/Microsoft.CostManagement/exports/{name}?$expand=runHistory
  4. Repeat for next month
```

### 2. Ongoing Monthly Export (recurring)

```
  1. Create scheduled export:
     - type: FocusCost
     - timeframe: TheLastMonth
     - recurrence: Monthly
     - schedule: Active
  2. Azure Cost Management runs it automatically each month
  3. New Parquet files appear in storage → visible via OneLake shortcut
```

## API Details

### Base URL
```
https://management.azure.com/{scope}/providers/Microsoft.CostManagement/exports
```

### API Version
`2025-03-01` (latest as of March 2026)

### Scope URIs

| Scope Type | URI Pattern |
|-----------|-------------|
| Subscription | `/subscriptions/{subscriptionId}` |
| Billing Account (EA) | `/providers/Microsoft.Billing/billingAccounts/{billingAccountId}` |
| Billing Account (MCA) | `/providers/Microsoft.Billing/billingAccounts/{billingAccountId}` |
| Resource Group | `/subscriptions/{subId}/resourceGroups/{rgName}` |
| Management Group | `/providers/Microsoft.Management/managementGroups/{mgId}` |

### Export Types

| Type | Description |
|------|-------------|
| `FocusCost` | **FOCUS format** — combines actual + amortized costs (recommended) |
| `ActualCost` | Actual (billed) costs only |
| `AmortizedCost` | Amortized costs only |
| `Usage` | Legacy format (deprecated) |

### Export Request Body (FocusCost + Parquet/Snappy)

```json
{
  "identity": { "type": "SystemAssigned" },
  "location": "centralus",
  "properties": {
    "format": "Parquet",
    "compressionMode": "snappy",
    "dataOverwriteBehavior": "OverwritePreviousReport",
    "partitionData": true,
    "definition": {
      "type": "FocusCost",
      "dataSet": {
        "configuration": { "dataVersion": "2023-05-01" },
        "granularity": "Daily"
      },
      "timeframe": "Custom",
      "timePeriod": {
        "from": "2024-01-01T00:00:00Z",
        "to": "2024-01-31T00:00:00Z"
      }
    },
    "deliveryInfo": {
      "destination": {
        "type": "AzureBlob",
        "container": "cost-exports",
        "rootFolderPath": "focus",
        "resourceId": "/subscriptions/.../storageAccounts/..."
      }
    },
    "schedule": { "status": "Inactive" }
  }
}
```

## FOCUS Schema Overview

The FOCUS 1.2 specification defines 53 standard columns plus Azure-specific extensions (prefixed with `x_`). Key columns:

### Cost Columns
| Column | Description |
|--------|-------------|
| `BilledCost` | Actual invoiced amount |
| `EffectiveCost` | Amortized cost after applying all discounts |
| `ContractedCost` | Cost at negotiated rates |
| `ListCost` | Cost at list/retail prices |

### Dimension Columns
| Column | Description |
|--------|-------------|
| `ServiceName` | Azure service (e.g., "Virtual Machines") |
| `ServiceCategory` | Category (e.g., "Compute", "Storage") |
| `ResourceId` / `ResourceName` | Individual resource |
| `RegionName` | Azure region |
| `SubAccountId` / `SubAccountName` | Subscription |
| `Tags` | Resource tags (JSON) |

### Pricing Columns
| Column | Description |
|--------|-------------|
| `PricingCategory` | On-Demand, Commitment, Dynamic |
| `PricingQuantity` / `PricingUnit` | Usage quantity and unit |
| `ListUnitPrice` / `ContractedUnitPrice` | Price per unit |

### Commitment Discount Columns
| Column | Description |
|--------|-------------|
| `CommitmentDiscountId` | Reservation or savings plan ID |
| `CommitmentDiscountName` | Human-readable name |
| `CommitmentDiscountType` | Type of commitment |
| `CommitmentDiscountCategory` | Usage-based or spend-based |

## Design Decisions

### Why FOCUS instead of ActualCost + AmortizedCost?

The `FocusCost` export type produces a **single dataset** that includes both `BilledCost` (actual) and `EffectiveCost` (amortized) columns. This eliminates the need to:
- Create and manage two separate exports
- Join or union two datasets in your analytics layer
- Handle schema differences between actual and amortized formats

### Why Parquet + Snappy?

- **Parquet**: Columnar format ideal for analytical queries — Fabric/Spark read only the columns needed
- **Snappy**: Fast compression/decompression with good ratios — optimal for Spark workloads
- **Native support**: Azure Cost Management exports directly in this format — no conversion needed

### Why OneLake Shortcuts instead of data copy?

- **No duplication**: Data exists in one place (ADLS Gen2); Fabric reads it in-place
- **No pipeline**: No Copy Activity or data movement to maintain
- **Instant availability**: New export files are immediately visible via the shortcut
- **Cost efficient**: No Fabric compute used for data movement

### Why 1-month chunks for seeding?

Per Microsoft's recommendation:
- Large date ranges can cause export timeouts
- Monthly chunks ensure reliable export completion
- File sizes remain manageable for partitioning
- Failed months can be retried individually

### How we handle throttling and timeouts

The Exports API client is tuned for transient Azure control-plane limits:

- Retries include network failures and transient HTTP responses (`408`, `429`, `500`, `502`, `503`, `504`)
- Backoff uses exponential delay across multiple attempts before surfacing a failure
- Request timeout is configurable (`request_timeout_seconds`)
- Monitoring poll cadence and max wait are configurable (`monitor_poll_interval_seconds`, `monitor_max_wait_seconds`)
- Seeding adds an inter-request delay (`throttle_delay_seconds`) to reduce burst pressure

For quota-heavy subscriptions, increase `throttle_delay_seconds` and reduce seed `batch_size` before increasing concurrency.

### Why REST API instead of the Python SDK?

The `azure-mgmt-costmanagement` Python SDK may not support the latest API version (2025-03-01) or all parameters (like `FocusCost` type, `compressionMode`, etc.). Using direct REST calls gives us:
- Access to the latest API features immediately
- Full control over the request body
- No dependency on SDK release cycles

We still use `azure-identity` for token acquisition, which is well-maintained.
