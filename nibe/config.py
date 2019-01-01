import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from urllib.parse import urlsplit, parse_qs
from .const import *

from aiohttp.web import Request, Response
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import (
    HTTP_OK,
    HTTP_BAD_REQUEST
)
from homeassistant.data_entry_flow import UnknownFlow, RESULT_TYPE_ABORT

_LOGGER = logging.getLogger(__name__)
_view = None

@callback
def configured_hosts(hass):
    """Return a set of the configured hosts."""
    return set()


@config_entries.HANDLERS.register(DOMAIN)
class NibeConfigFlow(config_entries.ConfigFlow):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        self.access_data = None
        self.user_data = None

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""

        if user_input:
            from nibeuplink import Uplink

            scope = None
            if user_input[CONF_WRITEACCESS]:
                scope = ['READSYSTEM', 'WRITESYSTEM']
            else:
                scope = ['READSYSTEM']

            uplink = Uplink(
                client_id=user_input[CONF_CLIENT_ID],
                client_secret=user_input[CONF_CLIENT_SECRET],
                redirect_uri=user_input[CONF_REDIRECT_URI],
                scope=scope
            )
            self.uplink = uplink
            self.user_data = user_input
            return await self.async_step_auth()

        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required(CONF_REDIRECT_URI,
                             default=CONF_REDIRECT_URI_DEFAULT): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Required(CONF_WRITEACCESS,
                             default=False): bool,
            })
        )

    async def async_step_auth(self, user_input=None):
        errors = {}
        if user_input:
            try:
                await self.uplink.get_access_token(user_input['code'])
            except Exception as e:
                _LOGGER.exception('Error on converting code')
                errors['base'] = 'code'
            else:
                self.user_data[CONF_ACCESS_DATA] = self.uplink.access_data
                return self.async_create_entry(
                    title="Nibe Uplink",
                    data= self.user_data
                )
        global _view
        if not _view:
            _view = NibeAuthView(self.hass)
            self.hass.http.register_view(_view)

        url = self.uplink.get_authorize_url()
        _view.register_flow(self.uplink.state, self.flow_id)

        return self.async_show_form(
            step_id='auth',
            description_placeholders={
                'url': url
            },
            data_schema=vol.Schema({
                vol.Required(CONF_CODE): str
            }),
            errors=errors
        )

class NibeAuthView(HomeAssistantView):
    """Handle nibe  authentication callbacks."""

    url = '/api/nibe/auth'
    name = 'api:nibe:auth'

    requires_auth = False

    def __init__(self, hass) -> None:
        """Initialize instance of the view."""
        super().__init__()
        self.hass = hass
        self._flows = {}

    def register_flow(self, state, flow_id):
        self._flows[state] = flow_id
        _LOGGER.debug('Register state %s for flow_id %s', state, flow_id)

    async def get(self, request: Request) -> Response:
        """Handle oauth token request."""
        if 'state' not in request.query:
            _LOGGER.error("state missing in request")
            return self.json_message("state missing in url",
                                     status_code=HTTP_BAD_REQUEST)
        state = request.query['state']

        if 'code' not in request.query:
            _LOGGER.error("state missing in request")
            return self.json_message("code missing in url",
                                     status_code=HTTP_BAD_REQUEST)
        code = request.query['code']

        _LOGGER.debug('Received auth request for state %s', state)

        if state not in self._flows:
            _LOGGER.error("state unexpected %s", state)
            return self.json_message("state unexpected",
                                     status_code=HTTP_BAD_REQUEST)

        flow_id = self._flows[state]

        try:
            result = await self.hass.config_entries.flow.async_configure(
                flow_id,
                {'code': code}
            )
        except UnknownFlow:
            return self.json_message("flow not found",
                                     status_code=HTTP_BAD_REQUEST)

        if result['type'] == RESULT_TYPE_ABORT:
            return self.json_message("authorization failed",
                                     status_code=HTTP_BAD_REQUEST)
        else:
            return self.json_message("authorization succeeded",
                                     status_code=HTTP_OK)
