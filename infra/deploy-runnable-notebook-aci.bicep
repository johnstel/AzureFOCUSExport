targetScope = 'resourceGroup'

@description('Azure region for deployed resources.')
param location string = resourceGroup().location

@description('Container group name for the runnable notebook host.')
param containerGroupName string = 'focus-notebook-runner'

@description('DNS label prefix used to build the public notebook URL (must be globally unique in region).')
param dnsNameLabel string = toLower('focusnb-${uniqueString(resourceGroup().id)}')

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

resource notebookRunner 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
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
            'set -e; mkdir -p /home/jovyan/work; curl -L "$NOTEBOOK_URL" -o "/home/jovyan/work/$NOTEBOOK_FILE"; start-notebook.sh --NotebookApp.token="$JUPYTER_TOKEN" --NotebookApp.password="" --NotebookApp.allow_origin="*" --NotebookApp.ip=0.0.0.0 --NotebookApp.port=8888'
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

output notebookUrl string = 'http://${notebookRunner.properties.ipAddress.fqdn}:8888/lab/tree/${notebookFileName}'
output notebookTokenHint string = 'Use the deployment input value for jupyterToken to sign in.'
output managedIdentityPrincipalId string = notebookRunner.identity.principalId
