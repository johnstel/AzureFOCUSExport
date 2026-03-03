# SPDX-License-Identifier: AGPL-3.0-only

"""Azure Cost Management Exports REST API client."""

import logging
from typing import Any, Dict, List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from .auth import AzureAuthenticator
from .config import AppConfig

logger = logging.getLogger(__name__)

API_VERSION = "2025-03-01"
BASE_URL = "https://management.azure.com"
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _is_retryable_exception(exception: Exception) -> bool:
    """Return True when a request exception should be retried."""
    if isinstance(exception, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exception, ExportsApiError):
        return exception.status_code in RETRYABLE_STATUS_CODES
    return False


class ExportsApiError(Exception):
    """Raised when the Exports API returns an error."""

    def __init__(self, status_code: int, message: str, details: Optional[dict] = None):
        self.status_code = status_code
        self.details = details
        super().__init__(f"Exports API error ({status_code}): {message}")


class ExportsApiClient:
    """Client for the Azure Cost Management Exports REST API."""

    def __init__(self, authenticator: AzureAuthenticator, config: AppConfig):
        self._auth = authenticator
        self._config = config
        self._session = requests.Session()
        self._request_timeout_seconds = max(30, getattr(config.export, "request_timeout_seconds", 90))

    def _url(self, scope: str, export_name: Optional[str] = None) -> str:
        """Build the API URL for the given scope and optional export name."""
        base = f"{BASE_URL}{scope}/providers/Microsoft.CostManagement/exports"
        if export_name:
            base = f"{base}/{export_name}"
        return f"{base}?api-version={API_VERSION}"

    def _handle_response(self, response: requests.Response) -> dict:
        """Handle API response, raising on errors."""
        if response.status_code in (200, 201):
            return response.json() if response.content else {}

        try:
            error_body = response.json()
            error_msg = error_body.get("error", {}).get("message", response.text)
        except Exception:
            error_msg = response.text

        raise ExportsApiError(response.status_code, error_msg)

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=5, max=180),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
    def create_export(
        self,
        export_name: str,
        export_type: str,
        time_period_from: str,
        time_period_to: str,
        timeframe: str = "Custom",
        schedule_status: str = "Inactive",
        schedule_recurrence: Optional[str] = None,
        recurrence_period_from: Optional[str] = None,
        recurrence_period_to: Optional[str] = None,
    ) -> dict:
        """Create or update a cost management export.

        Args:
            export_name: Name of the export resource
            export_type: Type of export (FocusCost, ActualCost, AmortizedCost)
            time_period_from: Start date for Custom timeframe (ISO 8601)
            time_period_to: End date for Custom timeframe (ISO 8601)
            timeframe: Timeframe type (Custom, MonthToDate, TheLastMonth, etc.)
            schedule_status: Schedule status (Active, Inactive)
            schedule_recurrence: Recurrence (Daily, Weekly, Monthly, None)
            recurrence_period_from: Recurrence start date
            recurrence_period_to: Recurrence end date
        """
        scope = self._config.scope.scope_uri
        url = self._url(scope, export_name)

        overwrite_behavior = (
            "OverwritePreviousReport" if self._config.export.overwrite else "CreateNewReport"
        )

        body: Dict[str, Any] = {
            "identity": {"type": "SystemAssigned"},
            "location": "centralus",
            "properties": {
                "format": self._config.export.format,
                "compressionMode": self._config.export.compression,
                "dataOverwriteBehavior": overwrite_behavior,
                "partitionData": self._config.export.partition_data,
                "definition": {
                    "type": export_type,
                    "dataSet": {
                        "configuration": {"dataVersion": "2023-05-01"},
                        "granularity": self._config.export.granularity,
                    },
                },
                "deliveryInfo": {
                    "destination": {
                        "type": "AzureBlob",
                        "container": self._config.storage.container,
                        "rootFolderPath": self._config.storage.root_folder,
                        "resourceId": self._config.storage.resource_id,
                    }
                },
                "exportDescription": f"FOCUS cost export: {export_name}",
            },
        }

        # Set timeframe and time period
        definition = body["properties"]["definition"]
        if timeframe == "Custom":
            definition["timeframe"] = "Custom"
            definition["timePeriod"] = {
                "from": time_period_from,
                "to": time_period_to,
            }
        else:
            definition["timeframe"] = timeframe

        # Set schedule
        schedule: Dict[str, Any] = {"status": schedule_status}
        if schedule_recurrence:
            schedule["recurrence"] = schedule_recurrence
        if recurrence_period_from and recurrence_period_to:
            schedule["recurrencePeriod"] = {
                "from": recurrence_period_from,
                "to": recurrence_period_to,
            }
        body["properties"]["schedule"] = schedule

        logger.debug(f"Creating export: PUT {url}")
        headers = self._auth.get_headers()
        response = self._session.put(
            url,
            json=body,
            headers=headers,
            timeout=self._request_timeout_seconds,
        )
        return self._handle_response(response)

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=5, max=180),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
    def execute_export(self, export_name: str) -> None:
        """Trigger an export to run immediately."""
        scope = self._config.scope.scope_uri
        url = f"{BASE_URL}{scope}/providers/Microsoft.CostManagement/exports/{export_name}/run?api-version={API_VERSION}"

        logger.debug(f"Executing export: POST {url}")
        headers = self._auth.get_headers()
        response = self._session.post(
            url,
            headers=headers,
            timeout=self._request_timeout_seconds,
        )

        if response.status_code not in (200, 202):
            self._handle_response(response)

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=5, max=180),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
    def get_export(self, export_name: str, expand: str = "runHistory") -> dict:
        """Get export details including run history."""
        scope = self._config.scope.scope_uri
        url = self._url(scope, export_name)
        if expand:
            url += f"&$expand={expand}"

        logger.debug(f"Getting export: GET {url}")
        headers = self._auth.get_headers()
        response = self._session.get(
            url,
            headers=headers,
            timeout=self._request_timeout_seconds,
        )
        return self._handle_response(response)

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=5, max=180),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
    def list_exports(self) -> List[dict]:
        """List all exports for the configured scope."""
        scope = self._config.scope.scope_uri
        url = self._url(scope)

        logger.debug(f"Listing exports: GET {url}")
        headers = self._auth.get_headers()
        response = self._session.get(
            url,
            headers=headers,
            timeout=self._request_timeout_seconds,
        )
        result = self._handle_response(response)
        return result.get("value", [])

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=5, max=180),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
    def delete_export(self, export_name: str) -> None:
        """Delete an export."""
        scope = self._config.scope.scope_uri
        url = self._url(scope, export_name)

        logger.debug(f"Deleting export: DELETE {url}")
        headers = self._auth.get_headers()
        response = self._session.delete(
            url,
            headers=headers,
            timeout=self._request_timeout_seconds,
        )

        if response.status_code not in (200, 204):
            self._handle_response(response)
