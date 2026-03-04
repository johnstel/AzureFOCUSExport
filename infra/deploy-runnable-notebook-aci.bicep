targetScope = 'resourceGroup'

@description('Azure region for deployed resources.')
param location string = resourceGroup().location

@description('Container group name for the runnable notebook host.')
param containerGroupName string = 'focus-notebook-runner'

@description('Network mode for notebook access.')
@allowed([
  'public'
  'private'
])
param networkMode string = 'public'

@description('DNS label prefix used to build the public notebook URL (must be globally unique in region).')
param dnsNameLabel string = toLower('focusnb-${uniqueString(resourceGroup().id)}')

@description('Resource ID of delegated subnet for private mode (required when networkMode=private).')
param subnetResourceId string = ''

@description('Notebook source URL (raw .ipynb file).')
param notebookSourceUrl string = 'https://raw.githubusercontent.com/johnstel/AzureFOCUSExport/main/notebooks/focus_single_pipeline.ipynb'

@description('Notebook file name in the Jupyter workspace.')
param notebookFileName string = 'focus_single_pipeline.ipynb'

@description('Jupyter auth token shown to the user for first login.')
@secure()
param jupyterToken string

@description('CPU cores for the notebook container.')
@minValue(1)
@maxValue(4)
param cpuCores int = 2

@description('Memory in GB for the notebook container.')
@minValue(2)
@maxValue(16)
param memoryGb int = 4

var startupCommand = 'set -e; mkdir -p /home/jovyan/work; curl -L "$NOTEBOOK_URL" -o "/home/jovyan/work/$NOTEBOOK_FILE"; start-notebook.sh --NotebookApp.token="$JUPYTER_TOKEN" --NotebookApp.password="" --NotebookApp.allow_origin="*" --NotebookApp.ip=0.0.0.0 --NotebookApp.port=8888'

resource notebookRunnerPublic 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = if (networkMode == 'public') {
  name: containerGroupName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    osType: 'Linux'
    restartPolicy: 'Always'
    containers: [
      {
        name: 'jupyter'
        properties: {
          image: 'jupyter/minimal-notebook:python-3.11'
          resources: {
            requests: {
              cpu: cpuCores
              memoryInGB: memoryGb
            }
          }
          environmentVariables: [
            {
              name: 'NOTEBOOK_URL'
              value: notebookSourceUrl
            }
            {
              name: 'NOTEBOOK_FILE'
              value: notebookFileName
            }
            {
              name: 'JUPYTER_TOKEN'
              secureValue: jupyterToken
            }
          ]
          command: [
            'bash'
            '-lc'
            startupCommand
          ]
          ports: [
            {
              port: 8888
              protocol: 'TCP'
            }
          ]
        }
      }
    ]
    ipAddress: {
      type: 'Public'
      dnsNameLabel: dnsNameLabel
      ports: [
        {
          protocol: 'TCP'
          port: 8888
        }
      ]
    }
  }
}

resource notebookRunnerPrivate 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = if (networkMode == 'private') {
  name: containerGroupName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    osType: 'Linux'
    restartPolicy: 'Always'
    containers: [
      {
        name: 'jupyter'
        properties: {
          image: 'jupyter/minimal-notebook:python-3.11'
          resources: {
            requests: {
              cpu: cpuCores
              memoryInGB: memoryGb
            }
          }
          environmentVariables: [
            {
              name: 'NOTEBOOK_URL'
              value: notebookSourceUrl
            }
            {
              name: 'NOTEBOOK_FILE'
              value: notebookFileName
            }
            {
              name: 'JUPYTER_TOKEN'
              secureValue: jupyterToken
            }
          ]
          command: [
            'bash'
            '-lc'
            startupCommand
          ]
          ports: [
            {
              port: 8888
              protocol: 'TCP'
            }
          ]
        }
      }
    ]
    subnetIds: [
      {
        id: subnetResourceId
      }
    ]
  }
}

output deploymentMode string = networkMode
output notebookUrl string = networkMode == 'public' ? 'http://${notebookRunnerPublic.properties.ipAddress.fqdn}:8888/lab/tree/${notebookFileName}' : 'Private mode: access Jupyter over private network using the container group private IP on port 8888.'
output notebookTokenHint string = 'Use the deployment input value for jupyterToken to sign in.'
output managedIdentityPrincipalId string = networkMode == 'public' ? notebookRunnerPublic.identity.principalId : notebookRunnerPrivate.identity.principalId
