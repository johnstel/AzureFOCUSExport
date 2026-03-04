using './deploy-runnable-notebook-aci.bicep'

// Set a strong token before deployment.
param jupyterToken = 'ChangeThisToken-Immediately'
param networkMode = 'public'
