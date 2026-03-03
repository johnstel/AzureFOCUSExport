# SPDX-License-Identifier: AGPL-3.0-only

"""Historical data seeder — creates and executes one-time FOCUS exports for each month."""

import logging
import time
from typing import List, Optional

from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from .config import AppConfig
from .exports_api import ExportsApiClient, ExportsApiError
from .monitor import ExportMonitor
from .utils import console, export_name_for_month, generate_monthly_ranges, month_label

logger = logging.getLogger(__name__)

# Delay between creating/executing exports to avoid API throttling
DEFAULT_THROTTLE_DELAY = 8


class HistoricalSeeder:
    """Seeds historical cost data by creating one-time FOCUS exports for each month."""

    def __init__(
        self,
        api_client: ExportsApiClient,
        monitor: ExportMonitor,
        config: AppConfig,
    ):
        self._api = api_client
        self._monitor = monitor
        self._config = config

    def seed(
        self,
        dry_run: bool = False,
        skip_existing: bool = True,
        batch_size: int = 3,
    ) -> dict:
        """Seed historical data by exporting each month individually.

        Args:
            dry_run: If True, only show what would be done without creating exports
            skip_existing: If True, skip months that already have exports
            batch_size: Number of exports to execute concurrently before waiting

        Returns:
            Summary dict with counts of created, skipped, failed exports
        """
        months = self._config.export.history_months
        prefix = self._config.export.export_name_prefix
        ranges = generate_monthly_ranges(months)

        console.print(f"\n[bold]Seeding {months} months of historical FOCUS data[/bold]")
        console.print(f"  Scope: {self._config.scope.scope_uri}")
        console.print(f"  Storage: {self._config.storage.account_name}/{self._config.storage.container}/{self._config.storage.root_folder}")
        console.print(f"  Format: {self._config.export.format} ({self._config.export.compression})")
        console.print(f"  Date range: {month_label(ranges[0][0])} to {month_label(ranges[-1][0])}\n")

        if dry_run:
            return self._dry_run(ranges, prefix)

        # Get existing exports for skip detection
        existing_exports = set()
        if skip_existing:
            existing_exports = self._get_existing_export_names()

        summary = {"created": 0, "skipped": 0, "failed": 0, "completed": 0}

        # Process in batches
        batches = [ranges[i:i + batch_size] for i in range(0, len(ranges), batch_size)]

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            overall = progress.add_task("Overall progress", total=len(ranges))

            for batch in batches:
                batch_exports = []

                # Create and execute exports in this batch
                for start_date, end_date in batch:
                    name = export_name_for_month(prefix, start_date)
                    label = month_label(start_date)

                    if name in existing_exports:
                        logger.info(f"Skipping {label} — export already exists")
                        summary["skipped"] += 1
                        progress.advance(overall)
                        continue

                    try:
                        self._create_and_execute(name, start_date, end_date)
                        batch_exports.append(name)
                        summary["created"] += 1
                    except ExportsApiError as e:
                        logger.error(f"Failed to create export for {label}: {e}")
                        summary["failed"] += 1
                        progress.advance(overall)
                        continue

                    throttle_delay = getattr(
                        self._config.export,
                        "throttle_delay_seconds",
                        DEFAULT_THROTTLE_DELAY,
                    )
                    time.sleep(throttle_delay)

                # Wait for batch to complete
                for name in batch_exports:
                    try:
                        self._monitor.wait_for_completion(name, show_progress=False)
                        summary["completed"] += 1
                    except (TimeoutError, RuntimeError) as e:
                        logger.error(f"Export {name} did not complete: {e}")
                        summary["failed"] += 1
                    progress.advance(overall)

        self._print_summary(summary)
        return summary

    def _create_and_execute(self, export_name: str, start_date: str, end_date: str) -> None:
        """Create a one-time export and execute it."""
        logger.info(f"Creating export: {export_name} ({start_date} to {end_date})")

        self._api.create_export(
            export_name=export_name,
            export_type="FocusCost",
            time_period_from=start_date,
            time_period_to=end_date,
            timeframe="Custom",
            schedule_status="Inactive",
        )

        logger.info(f"Executing export: {export_name}")
        self._api.execute_export(export_name)

    def _get_existing_export_names(self) -> set:
        """Get names of existing exports for the scope."""
        try:
            exports = self._api.list_exports()
            names = {e.get("name", "") for e in exports}
            if names:
                logger.info(f"Found {len(names)} existing exports")
            return names
        except ExportsApiError:
            logger.warning("Could not list existing exports — will create all")
            return set()

    def _dry_run(self, ranges: list, prefix: str) -> dict:
        """Show what would be created without actually doing it."""
        console.print("[yellow]DRY RUN — no exports will be created[/yellow]\n")
        for start_date, end_date in ranges:
            name = export_name_for_month(prefix, start_date)
            console.print(f"  Would create: {name} ({start_date} → {end_date})")

        summary = {"created": 0, "skipped": 0, "failed": 0, "completed": 0, "dry_run": True}
        console.print(f"\n  Total: {len(ranges)} exports would be created")
        return summary

    def _print_summary(self, summary: dict) -> None:
        """Print a summary of the seeding operation."""
        console.print("\n[bold]Seeding Summary[/bold]")
        console.print(f"  Created & executed: {summary['created']}")
        console.print(f"  Completed: {summary['completed']}")
        console.print(f"  Skipped (existing): {summary['skipped']}")
        console.print(f"  Failed: {summary['failed']}")

        if summary["failed"] > 0:
            console.print("\n[red]Some exports failed. Re-run with --skip-existing to retry only failed months.[/red]")
        else:
            console.print("\n[green]All historical data seeded successfully![/green]")
