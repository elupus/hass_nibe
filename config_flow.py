"""Nibe uplink configuration."""
from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp.web import HTTPBadRequest, Request, Response
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import callback
from nibeuplink import Uplink, UplinkSession

from . import NibeData
from .const import (
    AUTH_CALLBACK_NAME,
    AUTH_CALLBACK_URL,
    CONF_ACCESS_DATA,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_REDIRECT_URI,
    CONF_SYSTEMS,
    CONF_UPLINK_APPLICATION_URL,
    CONF_WRITEACCESS,
    DATA_NIBE_CONFIG,
    DATA_NIBE_ENTRIES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_view = None


class NibeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Conflig flow for nibe uplink."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Init."""
        self.access_data = None
        self.user_data = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the Options Flow."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input:
            scope = None
            if user_input[CONF_WRITEACCESS]:
                scope = ["READSYSTEM", "WRITESYSTEM"]
            else:
                scope = ["READSYSTEM"]

            session = UplinkSession(
                client_id=user_input[CONF_CLIENT_ID],
                client_secret=user_input[CONF_CLIENT_SECRET],
                redirect_uri=user_input[CONF_REDIRECT_URI],
                scope=scope,
            )
            await session.open()

            self.uplink = Uplink(session, throttle=0.0)
            self.session = session
            self.user_data = user_input
            return await self.async_step_auth()

        url = "{}{}".format(
            self.hass.helpers.network.get_url(prefer_external=True), AUTH_CALLBACK_URL
        )

        if DATA_NIBE_CONFIG in self.hass.data:
            config = self.hass.data[DATA_NIBE_CONFIG]
        else:
            config = {}

        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "application": CONF_UPLINK_APPLICATION_URL,
                "suffix": AUTH_CALLBACK_URL,
            },
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REDIRECT_URI, default=config.get(CONF_REDIRECT_URI, url)
                    ): str,
                    vol.Required(
                        CONF_CLIENT_ID, default=config.get(CONF_CLIENT_ID, None)
                    ): str,
                    vol.Required(
                        CONF_CLIENT_SECRET, default=config.get(CONF_CLIENT_SECRET, None)
                    ): str,
                    vol.Required(
                        CONF_WRITEACCESS, default=config.get(CONF_WRITEACCESS, False)
                    ): bool,
                }
            ),
        )

    async def async_step_auth(self, user_input=None):
        """Handle authentication step."""
        _LOGGER.debug("Async step auth %s", user_input)

        errors = {}
        if user_input is not None:
            try:
                await self.session.get_access_token(user_input["code"])
            except Exception:
                _LOGGER.exception("Error on converting code")
                errors["base"] = "code"
            else:
                self.user_data[CONF_ACCESS_DATA] = self.session.access_data
                return self.async_external_step_done(next_step_id="confirm")

        global _view
        if not _view:
            _view = NibeAuthView()
            self.hass.http.register_view(_view)

        url = self.session.get_authorize_url()
        _view.register_flow(self.session.state, self.flow_id)

        return self.async_external_step(step_id="auth", url=url)

    async def async_step_confirm(self, user_input=None):
        """Configure selected systems."""
        if user_input is not None:
            return self.async_create_entry(title="", data=self.user_data)

        self._set_confirm_only()
        return self.async_show_form(step_id="confirm")


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for a Konnected Panel."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            user_input[CONF_SYSTEMS] = [int(x) for x in user_input[CONF_SYSTEMS]]
            return self.async_create_entry(title="", data=user_input)

        data: NibeData = self.hass.data[DATA_NIBE_ENTRIES][self._entry.entry_id]
        systems = await data.uplink.get_systems()

        systems_dict = {
            str(system["systemId"]): f"{system['name']} : {system['systemId']}"
            for system in systems
        }

        if system_conf := self._entry.options.get(CONF_SYSTEMS):
            system_sel = [str(system_id) for system_id in system_conf]
        else:
            system_sel = list(systems_dict.keys())

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SYSTEMS, default=system_sel): cv.multi_select(
                        systems_dict
                    )
                }
            ),
        )


class NibeAuthView(HomeAssistantView):
    """Handle nibe  authentication callbacks."""

    url = AUTH_CALLBACK_URL
    name = AUTH_CALLBACK_NAME

    requires_auth = False

    def __init__(self) -> None:
        """Initialize instance of the view."""
        super().__init__()
        self._flows: dict[str, str] = {}

    def register_flow(self, state, flow_id):
        """Register a flow in the view."""
        self._flows[state] = flow_id
        _LOGGER.debug("Register state %s for flow_id %s", state, flow_id)

    async def get(self, request: Request) -> Response:
        """Handle oauth token request."""
        hass = request.app["hass"]

        def check_get(param):
            if param not in request.query:
                _LOGGER.error("State missing in request.")
                raise HTTPBadRequest(text="Parameter {} not found".format(param))
            return request.query[param]

        state = check_get("state")
        code = check_get("code")

        if state not in self._flows:
            _LOGGER.error("State unexpected %s", state)
            raise HTTPBadRequest(text="State can not be translated into flow")

        flow_id = self._flows[state]
        _LOGGER.debug("Received auth request for flow %s", flow_id)

        try:
            await hass.config_entries.flow.async_configure(flow_id, {"code": code})

            return Response(
                headers={"content-type": "text/html"},
                text="<script>window.close()</script>",
            )
        except data_entry_flow.UnknownFlow:
            raise HTTPBadRequest(text="Unkown flow")
