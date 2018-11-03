"""Nibe Uplink OAuth View."""

import logging

from aiohttp.web import Request, Response
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import (
    HTTP_OK,
    HTTP_BAD_REQUEST
)

_LOGGER = logging.getLogger(__name__)

CONFIG_NAME = "Nibe Uplink authorization required"
CONFIG_SUBMIT_CAPTION = 'Manually set url'
CONFIG_DESCRIPTION = """
Please authorize Home Assistant to access nibe
uplink by following the authorization link.

Automatic configuration will only work if your
configured redirect url is set to a url that will
match the access url of Home Assistant. If for example
you access Home Assisstant on http://localhost:8123
you should set your callback url, both on Nibe Uplink
and in Home Assistant configuration, to
http://localhost:8123/api/nibe/auth.

If automatic configuration of home assistant fails,
you can enter the url to the webpage you get redirected
to in the below prompt.
"""
CONFIG_LINK_NAME = "Authorize"


class NibeAuthView(HomeAssistantView):
    """Handle nibe  authentication callbacks."""

    url = '/api/nibe/auth'
    name = 'api:nibe:auth'

    requires_auth = False

    def __init__(self, hass, uplink, config, setup) -> None:
        """Initialize instance of the view."""
        super().__init__()
        self.hass = hass
        self.uplink = uplink
        self.config = config
        self.request_id = None
        self.setup = setup
        self.configurator = hass.components.configurator

    def async_request_config(self):
        auth_uri = self.uplink.get_authorize_url()

        async def callback(self, data):
            await self.configure(data['url'])

        self.request_id = self.configurator.async_request_config(
            CONFIG_NAME,
            callback=callback,
            description=CONFIG_DESCRIPTION,
            link_name=CONFIG_LINK_NAME,
            link_url=auth_uri,
            fields=[{'id': 'url', 'name': 'Full url', 'type': ''}],
            submit_caption=CONFIG_SUBMIT_CAPTION
        )

    async def configure(self, url):

        if not self.request_id:
            raise Exception('No Nibe configuration in progress!')

        try:
            code = self.uplink.get_code_from_url(url)

            await self.uplink.get_access_token(code)

            self.configurator.async_request_done(self.request_id)
            self.hass.async_add_job(
                self.setup(self.hass, self.config, self.uplink)
            )

        except BaseException:
            self.configurator.async_notify_errors(
                self.request_id,
                """An error occured during nibe authorization.
                   See logfile for more information."""
            )
            raise

    async def get(self, request: Request) -> Response:
        """Handle oauth token request."""

        try:
            await self.configure(str(request.url))
        except BaseException:
            msg = "An error occured during nibe authorization."
            _LOGGER.exception(msg)
            return self.json_message(msg, status_code=HTTP_BAD_REQUEST)
        else:
            msg = """Nibe has been authorized!
                     you can close this window, and restart Home Assistant."""
            _LOGGER.info(msg)
            return self.json_message(msg, status_code=HTTP_OK)
