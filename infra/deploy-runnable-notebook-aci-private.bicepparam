using './deploy-runnable-notebook-aci.bicep'

// Private-only profile for enterprise deployments.
// Replace placeholders before deployment.
param jupyterToken = 'ChangeThisToken-Immediately'
param networkMode = 'private'
param subnetResourceId = '/subscriptions/<subscription-id>/resourceGroups/<network-rg>/providers/Microsoft.Network/virtualNetworks/<vnet-name>/subnets/<delegated-subnet-name>'
