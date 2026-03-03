targetScope = 'resourceGroup'

@description('Azure region for deployed resources.')
param location string = resourceGroup().location

@description('Storage account name for notebook artifact storage (3-24 lowercase letters/numbers).')
param storageAccountName string = toLower('focusnb${uniqueString(subscription().id, resourceGroup().id)}')

@description('Blob container name to store notebook artifacts.')
param containerName string = 'notebooks'

@description('Notebook blob file name in the target container.')
param notebookBlobName string = 'focus_single_pipeline.ipynb'

@description('Public URL for the standalone notebook source file.')
param notebookSourceUrl string = 'https://raw.githubusercontent.com/johnstel/AzureFOCUSExport/main/notebooks/focus_single_pipeline.ipynb'

@description('User-assigned managed identity name used by deployment script for blob upload.')
param deployIdentityName string = 'focus-notebook-deploy-uami'

@description('Deployment script runtime in minutes before timeout.')
param scriptTimeoutMinutes int = 20

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  name: 'default'
  parent: storage
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: containerName
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: deployIdentityName
  location: location
}

resource blobDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, deployIdentity.id, 'Storage Blob Data Contributor')
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource uploadNotebookScript 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: 'upload-single-notebook'
  location: location
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${deployIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.61.0'
    retentionInterval: 'P1D'
    timeout: 'PT${scriptTimeoutMinutes}M'
    cleanupPreference: 'OnSuccess'
    environmentVariables: [
      {
        name: 'NOTEBOOK_URL'
        value: notebookSourceUrl
      }
      {
        name: 'NOTEBOOK_NAME'
        value: notebookBlobName
      }
      {
        name: 'STORAGE_ACCOUNT_NAME'
        value: storage.name
      }
      {
        name: 'CONTAINER_NAME'
        value: container.name
      }
    ]
    scriptContent: '''
      set -euo pipefail

      curl -L "$NOTEBOOK_URL" -o "$NOTEBOOK_NAME"

      az storage blob upload \
        --auth-mode login \
        --account-name "$STORAGE_ACCOUNT_NAME" \
        --container-name "$CONTAINER_NAME" \
        --name "$NOTEBOOK_NAME" \
        --file "$NOTEBOOK_NAME" \
        --overwrite true

      echo "Uploaded notebook to https://$STORAGE_ACCOUNT_NAME.blob.core.windows.net/$CONTAINER_NAME/$NOTEBOOK_NAME"
    '''
  }
  dependsOn: [
    container
    blobDataContributorRole
  ]
}

output storageAccountResourceId string = storage.id
output notebookBlobUrl string = 'https://${storage.name}.blob.core.windows.net/${container.name}/${notebookBlobName}'
output notebookSource string = notebookSourceUrl