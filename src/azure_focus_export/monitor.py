# SPDX-License-Identifier: AGPL-3.0-only

"""Export status monitoring with polling and progress tracking."""

import logging
import time
from typing import Optional

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .exports_api import ExportsApiClient
from .utils import console

logger = logging.getLogger(__name__)


class ExportMonitor:
    """Monitors export execution status with polling."""

    # Export run statuses
    STATUS_QUEUED = "Queued"
    STATUS_IN_PROGRESS = "InProgress"
    STATUS_COMPLETED = "Completed"
    STATUS_FAILED = "Failed"
    STATUS_TIMED_OUT = "TimedOut"

    TERMINAL_STATUSES = {STATUS_COMPLETED, STATUS_FAILED, STATUS_TIMED_OUT}

    def __init__(
        self,
        api_client: ExportsApiClient,
        poll_interval: int = 45,
        max_wait: int = 10800,
    ):
        self._api = api_client
        self._poll_interval = poll_interval
        self._max_wait = max_wait

    def wait_for_completion(
        self,
        export_name: str,
        show_progress: bool = True,
    ) -> dict:
        """Wait for an export run to complete.

        Args:
            export_name: Name of the export to monitor
            show_progress: Whether to show a progress spinner

        Returns:
            The final run history entry

        Raises:
            TimeoutError: If the export doesn't complete within max_wait
            RuntimeError: If the export fails
        """
        start_time = time.time()

        if show_progress:
            return self._wait_with_progress(export_name, start_time)
        else:
            return self._wait_silent(export_name, start_time)

    def _wait_with_progress(self, export_name: str, start_time: float) -> dict:
        """Wait with a rich progress spinner."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Waiting for {export_name}...", total=None)
            while True:
                run = self._check_latest_run(export_name)
                if run:
                    status = run.get("properties", {}).get("executionStatus", "Unknown")
                    progress.update(task, description=f"{export_name}: {status}")
                    if status in self.TERMINAL_STATUSES:
                        return self._handle_terminal(export_name, run, status)

                elapsed = time.time() - start_time
                if elapsed > self._max_wait:
                    raise TimeoutError(
                        f"Export {export_name} did not complete within {self._max_wait}s"
                    )

                time.sleep(self._poll_interval)

    def _wait_silent(self, export_name: str, start_time: float) -> dict:
        """Wait without progress display."""
        while True:
            run = self._check_latest_run(export_name)
            if run:
                status = run.get("properties", {}).get("executionStatus", "Unknown")
                logger.info(f"{export_name}: {status}")
                if status in self.TERMINAL_STATUSES:
                    return self._handle_terminal(export_name, run, status)

            elapsed = time.time() - start_time
            if elapsed > self._max_wait:
                raise TimeoutError(
                    f"Export {export_name} did not complete within {self._max_wait}s"
                )

            time.sleep(self._poll_interval)

    def _check_latest_run(self, export_name: str) -> Optional[dict]:
        """Get the latest run history entry for an export."""
        try:
            export = self._api.get_export(export_name, expand="runHistory")
            runs = (
                export.get("properties", {})
                .get("runHistory", {})
                .get("value", [])
            )
            if runs:
                # Sort by submittedTime descending and return the latest
                runs.sort(
                    key=lambda r: r.get("properties", {}).get("submittedTime", ""),
                    reverse=True,
                )
                return runs[0]
        except Exception as e:
            logger.warning(f"Error checking status for {export_name}: {e}")
        return None

    def _handle_terminal(self, export_name: str, run: dict, status: str) -> dict:
        """Handle a terminal export status."""
        if status == self.STATUS_COMPLETED:
            logger.info(f"Export {export_name} completed successfully")
            return run
        elif status == self.STATUS_FAILED:
            error = run.get("properties", {}).get("error", {})
            error_msg = error.get("message", "Unknown error")
            raise RuntimeError(f"Export {export_name} failed: {error_msg}")
        elif status == self.STATUS_TIMED_OUT:
            raise TimeoutError(f"Export {export_name} timed out on the server side")
        return run

    def get_run_status(self, export_name: str) -> Optional[str]:
        """Get the current status of the latest run for an export."""
        run = self._check_latest_run(export_name)
        if run:
            return run.get("properties", {}).get("executionStatus", "Unknown")
        return None
