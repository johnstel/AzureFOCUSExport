# SPDX-License-Identifier: AGPL-3.0-only

"""Configuration loading and validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AuthConfig:
    method: str = "default"
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    def __post_init__(self):
        # Allow env var overrides for secrets
        self.tenant_id = self.tenant_id or os.environ.get("AZURE_TENANT_ID")
        self.client_id = self.client_id or os.environ.get("AZURE_CLIENT_ID")
        self.client_secret = self.client_secret or os.environ.get("AZURE_CLIENT_SECRET")


@dataclass
class ScopeConfig:
    type: str = "subscription"
    subscription_id: Optional[str] = None
    billing_account_id: Optional[str] = None

    @property
    def scope_uri(self) -> str:
        """Build the Azure Resource Manager scope URI."""
        if self.type == "subscription":
            if not self.subscription_id:
                raise ValueError("subscription_id is required for subscription scope")
            return f"/subscriptions/{self.subscription_id}"
        elif self.type == "billing_account":
            if not self.billing_account_id:
                raise ValueError("billing_account_id is required for billing_account scope")
            return f"/providers/Microsoft.Billing/billingAccounts/{self.billing_account_id}"
        else:
            raise ValueError(f"Unknown scope type: {self.type}")


@dataclass
class StorageConfig:
    subscription_id: str = ""
    resource_group: str = ""
    account_name: str = ""
    container: str = "cost-exports"
    root_folder: str = "focus"

    @property
    def resource_id(self) -> str:
        """Build the storage account resource ID."""
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{self.account_name}"
        )


@dataclass
class ExportConfig:
    history_months: int = 36
    export_name_prefix: str = "focus-export"
    granularity: str = "Daily"
    partition_data: bool = True
    format: str = "Parquet"
    compression: str = "snappy"
    overwrite: bool = True
    request_timeout_seconds: int = 90
    monitor_poll_interval_seconds: int = 45
    monitor_max_wait_seconds: int = 10800
    throttle_delay_seconds: int = 8


@dataclass
class AppConfig:
    auth: AuthConfig = field(default_factory=AuthConfig)
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    export: ExportConfig = field(default_factory=ExportConfig)


def load_config(config_path: str) -> AppConfig:
    """Load configuration from a YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError("Configuration file is empty")

    auth_data = raw.get("auth", {})
    scope_data = raw.get("scope", {})
    storage_data = raw.get("storage", {})
    export_data = raw.get("export", {})

    config = AppConfig(
        auth=AuthConfig(**auth_data),
        scope=ScopeConfig(**scope_data),
        storage=StorageConfig(**storage_data),
        export=ExportConfig(**export_data),
    )

    _validate_config(config)
    return config


def _validate_config(config: AppConfig) -> None:
    """Validate the configuration."""
    # Validate auth
    if config.auth.method == "service_principal":
        if not config.auth.tenant_id:
            raise ValueError("tenant_id is required for service_principal auth")
        if not config.auth.client_id:
            raise ValueError("client_id is required for service_principal auth")
        if not config.auth.client_secret:
            raise ValueError("client_secret is required for service_principal auth (set via config or AZURE_CLIENT_SECRET env var)")

    # Validate scope
    if config.scope.type == "subscription" and not config.scope.subscription_id:
        raise ValueError("subscription_id is required for subscription scope")
    if config.scope.type == "billing_account" and not config.scope.billing_account_id:
        raise ValueError("billing_account_id is required for billing_account scope")

    # Validate storage
    if not config.storage.subscription_id:
        raise ValueError("storage.subscription_id is required")
    if not config.storage.resource_group:
        raise ValueError("storage.resource_group is required")
    if not config.storage.account_name:
        raise ValueError("storage.account_name is required")

    # Validate export settings
    if config.export.format not in ("Parquet", "Csv"):
        raise ValueError(f"Invalid format: {config.export.format}. Must be 'Parquet' or 'Csv'")
    if config.export.compression not in ("snappy", "gzip", "None"):
        raise ValueError(f"Invalid compression: {config.export.compression}. Must be 'snappy', 'gzip', or 'None'")
    if config.export.history_months < 1 or config.export.history_months > 48:
        raise ValueError(f"history_months must be between 1 and 48, got {config.export.history_months}")
    if config.export.request_timeout_seconds < 30 or config.export.request_timeout_seconds > 300:
        raise ValueError("request_timeout_seconds must be between 30 and 300")
    if config.export.monitor_poll_interval_seconds < 10 or config.export.monitor_poll_interval_seconds > 300:
        raise ValueError("monitor_poll_interval_seconds must be between 10 and 300")
    if config.export.monitor_max_wait_seconds < 600 or config.export.monitor_max_wait_seconds > 43200:
        raise ValueError("monitor_max_wait_seconds must be between 600 and 43200")
    if config.export.throttle_delay_seconds < 1 or config.export.throttle_delay_seconds > 60:
        raise ValueError("throttle_delay_seconds must be between 1 and 60")
