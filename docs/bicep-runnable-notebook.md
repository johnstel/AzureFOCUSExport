# Deploy a Runnable Notebook Environment (Azure Container Instances)

This is the simplest one-step deployment to get an immediately runnable notebook URL.

- Template: `infra/deploy-runnable-notebook-aci.bicep`
- Parameters profile: `infra/deploy-runnable-notebook-aci.bicepparam`
- Runtime: Jupyter Lab in Azure Container Instances (ACI)
- Notebook preloaded: `notebooks/focus_single_pipeline.ipynb`

## Prerequisites

```bash
az login
az account set --subscription <subscription-id>
az group create --name <resource-group> --location <region>
```

## Deploy

Before deploy, update `infra/deploy-runnable-notebook-aci.bicepparam` with a strong `jupyterToken`.

```bash
az deployment group create \
  --resource-group <resource-group> \
  --parameters @infra/deploy-runnable-notebook-aci.bicepparam
```

## Open and Run

1. From deployment outputs, copy `notebookUrl`.
2. Open in browser.
3. Enter the `jupyterToken` value from your parameter file.
4. Run the notebook cells in order.

## Important for Azure auth inside notebook

The notebook currently defaults to `AuthConfig(method="user")`.

For this ACI runtime, set it to managed identity in the config cell:

- `auth=AuthConfig(method="managed_identity")`

Then grant required roles to the container managed identity (`managedIdentityPrincipalId` output):

- `Cost Management Contributor` on billing scope
- `Storage Blob Data Contributor` on target storage account

## Security notes

- This deployment exposes Jupyter publicly on port 8888.
- Use a strong token and prefer a temporary resource group for testing.
- Restrict or remove public exposure when moving to production.
