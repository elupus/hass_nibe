"""application_credentials platform the NEW_NAME integration."""

from typing import Any

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

AUTHORIZATION_SERVER = AuthorizationServer(
    "https://api.nibeuplink.com/oauth/authorize",
    "https://api.nibeuplink.com/oauth/token",
)


class NibeAuthImplementation(AuthImplementation):
    """Nibe implementation of LocalOAuth2Implementation.

    We need this class because we have to add client_secret and scope to the authorization request.
    """

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": "READSYSTEM WRITESYSTEM",
        }


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    """Return auth implementation."""
    return NibeAuthImplementation(hass, auth_domain, credential, AUTHORIZATION_SERVER)


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholders for the credentials dialog."""
    return {"redirect_url": "https://my.home-assistant.io/redirect/oauth"}
