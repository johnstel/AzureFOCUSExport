# Setup Guide

This guide walks you through the prerequisites and configuration needed to run Azure FOCUS Export.

## Prerequisites

### 1. Azure Subscription

You need an Azure subscription with one of the following billing account types:
- **Enterprise Agreement (EA)**
- **Microsoft Customer Agreement (MCA)**

### 2. Python 3.9+

Install Python 3.9 or later. Verify with:

```bash
python --version
```

### 3. Choose an Authentication Mode

You can run this project with any of these auth modes:

| Mode | Best for | Requires App Registration? |
|------|----------|----------------------------|
| User context (`az login` / browser) | Interactive local or notebook runs | No |
| Managed Identity | Azure-hosted compute (Fabric, Functions, Containers, VMs) | No |
| Service Principal | CI/CD and explicit app identity | Yes |
| DefaultAzureCredential | Mixed environments | Depends on credential source |

#### User Context (No app authentication required)

1. Sign in:

```bash
az login
```

2. (Optional) Select subscription:

```bash
az account set --subscription <subscription-id>
```

3. Use notebook `AuthConfig(method="user")` in the standalone notebook.

### 4. Azure App Registration (only for Service Principal auth)

If running locally or in CI/CD, create an App Registration:

1. Go to **Azure Portal → Microsoft Entra ID → App registrations → New registration**
2. Name: `azure-focus-export` (or your choice)
3. Click **Register**
4. Note the **Application (client) ID** and **Directory (tenant) ID**
5. Go to **Certificates & secrets → New client secret**
6. Note the **Secret value** (you won't see it again)

### 5. RBAC Permissions

The Service Principal (or Managed Identity) needs:

#### On the billing scope (subscription or billing account):

| Role | Purpose |
|------|---------|
| **Cost Management Reader** | Read cost data and create exports |
| **Cost Management Contributor** | Create, modify, and delete exports |

To assign at subscription level:

```bash
az role assignment create \
  --assignee <client-id> \
  --role "Cost Management Contributor" \
  --scope /subscriptions/<subscription-id>
```

To assign at billing account level (EA):

```bash
az role assignment create \
  --assignee <client-id> \
  --role "Cost Management Contributor" \
  --scope /providers/Microsoft.Billing/billingAccounts/<billing-account-id>
```

#### On the storage account:

| Role | Purpose |
|------|---------|
| **Storage Blob Data Contributor** | Write export data to blob storage |
| **Owner** *(only if using storage firewall)* | Assign managed identity roles |

```bash
az role assignment create \
  --assignee <client-id> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>
```

### 6. ADLS Gen2 Storage Account

Create an ADLS Gen2-enabled storage account if you don't have one:

```bash
az storage account create \
  --name <storage-account-name> \
  --resource-group <resource-group> \
  --location <region> \
  --sku Standard_LRS \
  --kind StorageV2 \
  --hns true
```

Create the export container:

```bash
az storage container create \
  --account-name <storage-account-name> \
  --name cost-exports \
  --auth-mode login
```

#### Storage Firewall (Optional)

If your storage account has a firewall enabled:

1. Enable **"Allow trusted Azure services"** on the storage account
2. Ensure the **Permitted scope for copy operations** is set to **From any storage account**
3. The app needs **Owner** role on the storage account to set up the system-assigned managed identity

### 7. Managed Identity (for Azure-hosted environments)

If running in Azure (Fabric, Azure Functions, Azure Container Instances):

1. The compute resource gets a system-assigned managed identity automatically
2. Assign the same RBAC roles listed above to the managed identity
3. Set `auth.method: "managed_identity"` in config.yaml

## Configuration

### config.yaml

Copy `config.example.yaml` to `config.yaml` and fill in your values:

```yaml
auth:
  method: "service_principal"
  tenant_id: "<tenant-id>"
  client_id: "<client-id>"
  client_secret: "<client-secret>"

scope:
  type: "subscription"
  subscription_id: "<subscription-id>"

storage:
  subscription_id: "<storage-subscription-id>"
  resource_group: "<resource-group>"
  account_name: "<storage-account-name>"
  container: "cost-exports"
  root_folder: "focus"

export:
  history_months: 36
  export_name_prefix: "focus-export"
  format: "Parquet"
  compression: "snappy"
  request_timeout_seconds: 90
  monitor_poll_interval_seconds: 45
  monitor_max_wait_seconds: 10800
  throttle_delay_seconds: 8
```

### Environment Variables

You can override secrets with environment variables instead of putting them in config.yaml:

| Variable | Overrides |
|----------|-----------|
| `AZURE_TENANT_ID` | `auth.tenant_id` |
| `AZURE_CLIENT_ID` | `auth.client_id` |
| `AZURE_CLIENT_SECRET` | `auth.client_secret` |

## Notebook Setup Notes

- Source-based notebook: [notebooks/focus_source_pipeline.ipynb](../notebooks/focus_source_pipeline.ipynb)
  - Ensure source package path is available to the notebook runtime.
- Standalone notebook: [notebooks/focus_single_pipeline.ipynb](../notebooks/focus_single_pipeline.ipynb)
  - No source import required; all logic is inline.

## Verification

Test your configuration:

```bash
# Dry run — validates config and authentication without creating anything
azure-focus-export seed --dry-run --config config.yaml
```

If authentication succeeds, you'll see a preview of the 36 monthly exports that would be created.

## Retry and Timeout Behavior

The Exports API client includes built-in retries to reduce transient failures from quota/throttling and service instability.

- Retries include HTTP/network transient cases such as `429`, `408`, and `5xx` responses.
- Backoff uses exponential delay with multiple attempts before failing.
- Export monitoring waits up to `monitor_max_wait_seconds` per run before local timeout.

If you still see throttling pressure, increase `throttle_delay_seconds` and/or reduce seed `batch_size`.
