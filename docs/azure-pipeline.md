# Azure Import Pipeline (GitHub Actions)

This project includes a GitHub Actions workflow to run FOCUS import/export operations directly against your Azure environment:

- Workflow file: `.github/workflows/azure-import.yml`
- Trigger: **Run workflow** (manual)
- Supported operations: `dry-run`, `seed`, `schedule`, `status`

## 1) Configure GitHub OIDC Authentication

Create a Microsoft Entra App Registration (or use an existing one), configure **federated credentials** for GitHub Actions, then set these repository secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

The workflow uses `azure/login@v2` with OIDC (no client secret required).

## 2) Add Pipeline Config Secret

Create your `config.yaml` for this project and base64-encode it.

Example (PowerShell):

```powershell
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Get-Content .\config.yaml -Raw)))
```

Save the output as repository secret:

- `AZURE_FOCUS_CONFIG_YAML_B64`

## 3) Run the Pipeline

1. Open **Actions** in GitHub.
2. Select **Azure FOCUS Import**.
3. Click **Run workflow**.
4. Choose operation:
   - `dry-run` (recommended first)
   - `seed` (historical import)
   - `schedule` (monthly recurring export)
   - `status` (current export status)

## Notes

- Start with `dry-run` to validate scope/config/auth.
- For large tenants, tune retry/timeout settings in config:
  - `request_timeout_seconds`
  - `monitor_poll_interval_seconds`
  - `monitor_max_wait_seconds`
  - `throttle_delay_seconds`
- Ensure role assignments exist before running (`Cost Management Contributor`, `Storage Blob Data Contributor`).
