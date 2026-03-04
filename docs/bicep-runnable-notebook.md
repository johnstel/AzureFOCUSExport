# Deploy a Runnable Notebook Environment (Azure Container Instances)

This is the simplest one-step deployment to get an immediately runnable notebook URL.

- Template: `infra/deploy-runnable-notebook-aci.bicep`
- Parameters profile: `infra/deploy-runnable-notebook-aci.bicepparam`
- Private profile: `infra/deploy-runnable-notebook-aci-private.bicepparam`
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

### Public mode (default)

```bash
az deployment group create \
  --resource-group <resource-group> \
  --parameters @infra/deploy-runnable-notebook-aci.bicepparam
```

### Private-only mode (enterprise)

Prerequisite: use a subnet delegated to `Microsoft.ContainerInstance/containerGroups`.

1. Update `infra/deploy-runnable-notebook-aci-private.bicepparam`:
   - set strong `jupyterToken`
   - set `subnetResourceId` to the delegated subnet resource ID

2. Deploy:

```bash
az deployment group create \
  --resource-group <resource-group> \
  --parameters @infra/deploy-runnable-notebook-aci-private.bicepparam
```

## Open and Run

1. From deployment outputs, copy `notebookUrl`.
2. In public mode, open URL directly in browser.
3. In private mode, connect from inside the VNet (or via VPN/ExpressRoute/Bastion + jump host), then browse to container private IP on port `8888`.
4. Enter the `jupyterToken` value from your parameter file.
5. Run the notebook cells in order.

## Important for Azure auth inside notebook

The notebook currently defaults to `AuthConfig(method="user")`.

For this ACI runtime, set it to managed identity in the config cell:

- `auth=AuthConfig(method="managed_identity")`

Then grant required roles to the container managed identity (`managedIdentityPrincipalId` output):

- `Cost Management Contributor` on billing scope
- `Storage Blob Data Contributor` on target storage account

## Security notes

- Public mode exposes Jupyter on port `8888` with token auth.
- Private mode removes public ingress and uses subnet-based private networking.
- Use strong tokens and rotate them for long-lived environments.
