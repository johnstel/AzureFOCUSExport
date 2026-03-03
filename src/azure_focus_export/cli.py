# SPDX-License-Identifier: AGPL-3.0-only

"""CLI entry point for Azure FOCUS Export."""

import logging
import sys

import click

from .auth import AzureAuthenticator
from .config import load_config
from .exports_api import ExportsApiClient
from .monitor import ExportMonitor
from .scheduler import RecurringScheduler
from .seeder import HistoricalSeeder
from .utils import console, setup_logging

logger = logging.getLogger(__name__)


@click.group()
@click.option("--config", "-c", default="config.yaml", help="Path to configuration YAML file")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose/debug logging")
@click.pass_context
def cli(ctx, config, verbose):
    """Azure FOCUS Export — Export Azure billing data in FOCUS format to ADLS Gen2."""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["verbose"] = verbose


def _load(ctx) -> tuple:
    """Load config, create authenticator and API client."""
    config_path = ctx.obj["config_path"]
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)

    auth = AzureAuthenticator(config.auth)
    api = ExportsApiClient(auth, config)
    return config, auth, api


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without creating exports")
@click.option("--skip-existing/--no-skip-existing", default=True, help="Skip months that already have exports")
@click.option("--batch-size", default=3, help="Number of exports to run concurrently per batch")
@click.pass_context
def seed(ctx, dry_run, skip_existing, batch_size):
    """Seed historical FOCUS data by creating one-time exports for each month.

    Creates one-time FOCUS exports for the last N months (configured in config.yaml)
    in 1-month chunks, executes each, and monitors completion. Parquet files with
    Snappy compression are written to the configured ADLS Gen2 storage account.
    """
    config, auth, api = _load(ctx)
    monitor = ExportMonitor(
        api,
        poll_interval=config.export.monitor_poll_interval_seconds,
        max_wait=config.export.monitor_max_wait_seconds,
    )
    seeder = HistoricalSeeder(api, monitor, config)

    summary = seeder.seed(
        dry_run=dry_run,
        skip_existing=skip_existing,
        batch_size=batch_size,
    )

    if summary.get("failed", 0) > 0:
        sys.exit(1)


@cli.command()
@click.option("--name", default=None, help="Custom name for the recurring export")
@click.option("--dry-run", is_flag=True, help="Show what would be done without creating the export")
@click.pass_context
def schedule(ctx, name, dry_run):
    """Set up a recurring monthly FOCUS export for ongoing data.

    Creates a scheduled monthly export that runs automatically and exports
    the previous month's cost data in FOCUS format.
    """
    config, auth, api = _load(ctx)
    scheduler = RecurringScheduler(api, config)

    scheduler.setup_monthly_export(export_name=name, dry_run=dry_run)


@cli.command()
@click.pass_context
def status(ctx):
    """Show the status of all FOCUS exports for the configured scope."""
    config, auth, api = _load(ctx)

    console.print(f"\n[bold]Export Status[/bold]")
    console.print(f"  Scope: {config.scope.scope_uri}\n")

    try:
        exports = api.list_exports()
    except Exception as e:
        console.print(f"[red]Error listing exports: {e}[/red]")
        sys.exit(1)

    if not exports:
        console.print("  No exports found.")
        return

    prefix = config.export.export_name_prefix
    focus_exports = [e for e in exports if e.get("name", "").startswith(prefix)]

    if not focus_exports:
        console.print(f"  No exports found with prefix '{prefix}'.")
        console.print(f"  Total exports in scope: {len(exports)}")
        return

    for export in focus_exports:
        name = export.get("name", "Unknown")
        props = export.get("properties", {})
        export_type = props.get("definition", {}).get("type", "Unknown")
        timeframe = props.get("definition", {}).get("timeframe", "Unknown")
        fmt = props.get("format", "Unknown")
        schedule_info = props.get("schedule", {})
        schedule_status = schedule_info.get("status", "Unknown")
        next_run = props.get("nextRunTimeEstimate", "N/A")

        # Get latest run status
        runs = props.get("runHistory", {}).get("value", [])
        if runs:
            runs.sort(key=lambda r: r.get("properties", {}).get("submittedTime", ""), reverse=True)
            latest = runs[0].get("properties", {})
            run_status = latest.get("executionStatus", "Unknown")
            submitted = latest.get("submittedTime", "Unknown")
        else:
            run_status = "Never run"
            submitted = "N/A"

        status_color = {
            "Completed": "green",
            "InProgress": "yellow",
            "Queued": "blue",
            "Failed": "red",
        }.get(run_status, "white")

        console.print(f"  [bold]{name}[/bold]")
        console.print(f"    Type: {export_type} | Format: {fmt} | Timeframe: {timeframe}")
        console.print(f"    Schedule: {schedule_status} | Next run: {next_run}")
        console.print(f"    Latest run: [{status_color}]{run_status}[/{status_color}] (submitted: {submitted})")
        console.print()


@cli.command()
@click.option("--keep-monthly", is_flag=True, default=True, help="Keep the recurring monthly export")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def cleanup(ctx, keep_monthly, confirm):
    """Delete completed one-time seed exports.

    Removes the one-time historical exports created by the 'seed' command,
    keeping the recurring monthly export. The exported data in storage is not affected.
    """
    config, auth, api = _load(ctx)

    prefix = config.export.export_name_prefix
    monthly_name = f"{prefix}-monthly"

    try:
        exports = api.list_exports()
    except Exception as e:
        console.print(f"[red]Error listing exports: {e}[/red]")
        sys.exit(1)

    to_delete = []
    for export in exports:
        name = export.get("name", "")
        if name.startswith(prefix) and name != monthly_name:
            to_delete.append(name)

    if not to_delete:
        console.print("No one-time seed exports found to clean up.")
        return

    console.print(f"\n[bold]Exports to delete ({len(to_delete)}):[/bold]")
    for name in to_delete:
        console.print(f"  - {name}")

    if keep_monthly:
        console.print(f"\n  [dim]Keeping: {monthly_name}[/dim]")

    if not confirm:
        if not click.confirm("\nProceed with deletion?"):
            console.print("Cancelled.")
            return

    deleted = 0
    for name in to_delete:
        try:
            api.delete_export(name)
            logger.info(f"Deleted: {name}")
            deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete {name}: {e}")

    console.print(f"\n[green]Deleted {deleted}/{len(to_delete)} exports.[/green]")
    console.print("[dim]Note: Exported data in storage is not affected.[/dim]")


if __name__ == "__main__":
    cli()
