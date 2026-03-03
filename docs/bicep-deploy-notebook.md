# Deploy Standalone Notebook with Bicep

This guide deploys the standalone notebook artifact (`focus_single_pipeline.ipynb`) to your Azure environment using one Bicep file.

- Bicep file: `infra/deploy-single-notebook.bicep`
- Parameters profile: `infra/deploy-single-notebook.bicepparam`
- Result: storage account + private blob container + uploaded notebook blob

## Prerequisites

- Azure CLI logged in:

```bash
az login
```

- Target subscription selected:

```bash
az account set --subscription <subscription-id>
```

- Existing resource group (or create one):

```bash
az group create --name <resource-group> --location <region>
```

## Deploy

Recommended (uses ready-to-run defaults):

```bash
az deployment group create \
  --resource-group <resource-group> \
  --parameters @infra/deploy-single-notebook.bicepparam
```

Explicit template call (for custom overrides):

```bash
az deployment group create \
  --resource-group <resource-group> \
  --template-file infra/deploy-single-notebook.bicep \
  --parameters storageAccountName=<globally-unique-name>
```

Optional parameters:

- `containerName` (default: `notebooks`)
- `notebookBlobName` (default: `focus_single_pipeline.ipynb`)
- `notebookSourceUrl` (defaults to this repo notebook URL)
- `deployIdentityName`
- `scriptTimeoutMinutes`

## Outputs

Deployment returns:

- `storageAccountResourceId`
- `notebookBlobUrl`
- `notebookSource`

Use `notebookBlobUrl` to download/import the notebook into your target notebook environment.

## Notes

- The deployment uses a user-assigned managed identity with `Storage Blob Data Contributor` on the new storage account.
- The upload runs through an Azure deployment script and stores the notebook privately (`publicAccess: None`).