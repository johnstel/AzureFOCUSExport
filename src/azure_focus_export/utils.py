# SPDX-License-Identifier: AGPL-3.0-only

"""Utility functions for date ranges, logging, and helpers."""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def generate_monthly_ranges(months: int) -> List[Tuple[str, str]]:
    """Generate a list of (start_date, end_date) tuples for each month going back N months.

    Returns ISO 8601 date strings like "2024-01-01T00:00:00Z" and "2024-01-31T00:00:00Z".
    Each range covers one calendar month (1st to last day).
    """
    ranges = []
    now = datetime.utcnow()

    for i in range(months):
        # Go back i+1 months from current month
        target = now.replace(day=1) - timedelta(days=1)  # last day of previous month
        for _ in range(i):
            target = target.replace(day=1) - timedelta(days=1)

        year = target.year
        month = target.month

        # First day of the month
        start = datetime(year, month, 1)
        # Last day of the month
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)

        start_str = start.strftime("%Y-%m-%dT00:00:00Z")
        end_str = end.strftime("%Y-%m-%dT00:00:00Z")

        ranges.append((start_str, end_str))

    # Return in chronological order (oldest first)
    ranges.reverse()
    return ranges


def month_label(date_str: str) -> str:
    """Extract a YYYY-MM label from an ISO date string."""
    return date_str[:7]


def export_name_for_month(prefix: str, date_str: str) -> str:
    """Generate an export resource name for a given month.

    Example: focus-export-2024-01
    """
    label = month_label(date_str)
    return f"{prefix}-{label}"
