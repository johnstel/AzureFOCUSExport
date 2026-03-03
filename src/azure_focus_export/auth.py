# SPDX-License-Identifier: AGPL-3.0-only

"""Azure authentication module supporting Service Principal, Managed Identity, and Default credentials."""

import logging
from typing import Optional

from azure.identity import ClientSecretCredential, DefaultAzureCredential, ManagedIdentityCredential

from .config import AuthConfig

logger = logging.getLogger(__name__)

AZURE_MANAGEMENT_SCOPE = "https://management.azure.com/.default"


class AzureAuthenticator:
    """Handles Azure AD authentication and token acquisition."""

    def __init__(self, auth_config: AuthConfig):
        self._config = auth_config
        self._credential = self._create_credential()

    def _create_credential(self):
        """Create the appropriate Azure credential based on configuration."""
        method = self._config.method

        if method == "service_principal":
            logger.info("Using Service Principal authentication")
            return ClientSecretCredential(
                tenant_id=self._config.tenant_id,
                client_id=self._config.client_id,
                client_secret=self._config.client_secret,
            )
        elif method == "managed_identity":
            logger.info("Using Managed Identity authentication")
            kwargs = {}
            if self._config.client_id:
                kwargs["client_id"] = self._config.client_id
            return ManagedIdentityCredential(**kwargs)
        elif method == "default":
            logger.info("Using DefaultAzureCredential authentication")
            return DefaultAzureCredential()
        else:
            raise ValueError(f"Unknown auth method: {method}")

    def get_token(self) -> str:
        """Acquire a bearer token for Azure Management API."""
        token = self._credential.get_token(AZURE_MANAGEMENT_SCOPE)
        return token.token

    def get_headers(self) -> dict:
        """Get HTTP headers with authorization for API calls."""
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
