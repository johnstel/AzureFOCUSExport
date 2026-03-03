# Azure FOCUS Export

Export Azure billing data in the **FOCUS format** (FinOps Open Cost & Usage Specification) to ADLS Gen2 as **Parquet files with Snappy compression**, ready for reporting in **Microsoft Fabric**.

## What is FOCUS?

[FOCUS](https://focus.finops.org/) is an open specification that standardizes cloud cost and usage data across providers. The Azure `FocusCost` export type **combines actual and amortized costs** into a single dataset with 100+ standardized columns, reducing data processing times and storage costs.

## Features

- 🔄 **Seed 3 years of historical data** — one-time exports in 1-month chunks
- 📅 **Recurring monthly exports** — scheduled exports for ongoing data
- 📦 **Parquet + Snappy** — optimal format for Fabric/Spark analytics
- 🔗 **OneLake integration** — use ADLS Gen2 shortcuts (no data copy needed)
- 🔐 **Flexible auth** — User context (Azure CLI / browser), Service Principal, Managed Identity, or DefaultAzureCredential
- 📊 **Multi-scope** — supports subscription and billing account (EA & MCA)
- 🔁 **Resume support** — safely re-run if interrupted
- 📓 **Two notebook variants** — source-based and fully standalone

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your Azure details
```

See [docs/setup-guide.md](docs/setup-guide.md) for detailed setup instructions.

### 3. Preview (Dry Run)

```bash
# See what would be created without making any API calls
azure-focus-export seed --dry-run --config config.yaml
```

### 4. Seed Historical Data

```bash
# Create and execute exports for the last 36 months
azure-focus-export seed --config config.yaml
```

### 5. Set Up Monthly Recurring Export

```bash
# Create a scheduled monthly export for ongoing data
azure-focus-export schedule --config config.yaml
```

### 6. Check Status

```bash
azure-focus-export status --config config.yaml
```

### 7. Clean Up Seed Exports

```bash
# Delete one-time exports (keeps recurring monthly export, data is not affected)
azure-focus-export cleanup --config config.yaml
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `seed` | Seed historical FOCUS data (36 months in 1-month chunks) |
| `schedule` | Set up recurring monthly FOCUS export |
| `status` | Show status of all FOCUS exports |
| `cleanup` | Delete completed one-time seed exports |

### Global Options

| Option | Description |
|--------|-------------|
| `--config, -c` | Path to config YAML file (default: `config.yaml`) |
| `--verbose, -v` | Enable debug logging |

### Seed Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview without creating exports |
| `--skip-existing / --no-skip-existing` | Skip months with existing exports (default: on) |
| `--batch-size` | Concurrent exports per batch (default: 3) |

## Architecture

```
┌──────────────────┐     ┌──────────────────────┐     ┌────────────────┐     ┌──────────────┐
│  CLI / Fabric    │────▶│ Azure Cost Management│────▶│ ADLS Gen2      │◀───▶│ OneLake      │
│  Notebook        │     │ Exports API          │     │ Storage Acct   │     │ (Shortcut)   │
└──────────────────┘     └──────────────────────┘     └────────────────┘     └──────┬───────┘
                                                                                    │
                                                                              ┌─────▼───────┐
                                                                              │ Fabric      │
                                                                              │ Lakehouse / │
                                                                              │ Reports     │
                                                                              └─────────────┘
```

1. **Python app** calls the Azure Cost Management Exports API
2. **API exports** FOCUS data as Parquet/Snappy to your ADLS Gen2 storage account
3. **OneLake shortcut** points to the storage account — Fabric reads data in-place
4. **Fabric reports** query the data via DirectLake, Spark SQL, or the SQL endpoint

## Notebook Options

Use the notebook that matches how you want to operate:

- **Source-based notebook**: [notebooks/focus_source_pipeline.ipynb](notebooks/focus_source_pipeline.ipynb)
  - Imports logic from `src/azure_focus_export`
  - Best when you want notebook orchestration with maintainable module code
- **Standalone notebook**: [notebooks/focus_single_pipeline.ipynb](notebooks/focus_single_pipeline.ipynb)
  - Contains all logic inline
  - Best for copy/paste portability and quick execution in isolated notebook environments

For Microsoft Fabric, either notebook works. If you choose the source-based notebook, upload the `src/azure_focus_export` package path to your Lakehouse Files and verify the notebook import path.

For detailed Fabric integration instructions, see [docs/fabric-integration.md](docs/fabric-integration.md).

## Documentation

- [Setup Guide](docs/setup-guide.md) — Prerequisites, app registration, RBAC permissions
- [Fabric Integration](docs/fabric-integration.md) — OneLake shortcuts, Lakehouse configuration
- [Architecture](docs/architecture.md) — Design decisions, API details, FOCUS schema
- [Azure Pipeline](docs/azure-pipeline.md) — GitHub Actions workflow to run imports in Azure
- [Bicep Notebook Deployment](docs/bicep-deploy-notebook.md) — Deploy the standalone notebook artifact to Azure (includes ready-to-run `.bicepparam` profile)

## License

AGPL-3.0-only (GNU Affero General Public License v3.0)
