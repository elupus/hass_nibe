"""Nibe uplink configuration."""
import copy
import logging
from abc import abstractmethod
from typing import Any, AsyncIterator, Dict

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp.web import HTTPBadRequest, Request, Response
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import callback  # noqa
from nibeuplink import Uplink, UplinkSession

from .const import (
    AUTH_CALLBACK_NAME,
    AUTH_CALLBACK_URL,
    CONF_ACCESS_DATA,
    CONF_CATEGORIES,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_REDIRECT_URI,
    CONF_SYSTEMS,
    CONF_UNITS,
    CONF_UPLINK_APPLICATION_URL,
    CONF_WRITEACCESS,
    DATA_NIBE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_view = None


@config_entries.HANDLERS.register(DOMAIN)
class NibeConfigFlow(config_entries.ConfigFlow):
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

        if DATA_NIBE in self.hass.data:
            config = self.hass.data[DATA_NIBE].config
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
                return self.async_external_step_done(next_step_id="systems")

        global _view
        if not _view:
            _view = NibeAuthView()
            self.hass.http.register_view(_view)

        url = self.session.get_authorize_url()
        _view.register_flow(self.session.state, self.flow_id)

        return self.async_external_step(step_id="auth", url=url)

    async def async_step_systems(self, user_input=None):
        """Configure selected systems."""
        if user_input is not None:
            self.user_data[CONF_SYSTEMS] = {key: {} for key in user_input[CONF_SYSTEMS]}

            return self.async_create_entry(title="", data=self.user_data)

        systems = await self.uplink.get_systems()
        systems_dict = {
            str(x["systemId"]): f"{x['name']} ({x['productName']})" for x in systems
        }
        systems_sel = list(systems_dict.keys())

        return self.async_show_form(
            step_id="systems",
            description_placeholders={},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SYSTEMS, default=systems_sel): cv.multi_select(
                        systems_dict
                    )
                }
            ),
        )


class FunctionFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for a Konnected Panel."""

    _step_iter: AsyncIterator[Dict[str, Any]]

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self._step_iter = self.run()

    @abstractmethod
    async def run(self):
        """Run the options flow."""
        pass

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        try:
            if user_input is not None:
                result = await self._step_iter.asend(user_input)
            else:
                result = await self._step_iter.__anext__()
        except StopAsyncIteration:
            return self.async_abort("abort")

        if "step_id" in result:
            name = f"async_step_{result['step_id']}"
            if not hasattr(self, name):
                setattr(self, name, self.async_step_init)

        return result


class OptionsFlowHandler(FunctionFlowHandler):
    """Handle a option flow for a Konnected Panel."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self._entry = config_entry
        self._config = copy.deepcopy(dict(config_entry.data))
        super().__init__(config_entry)

    async def run(self):
        """Run the options flow."""
        uplink: Uplink = self.hass.data[DATA_NIBE].uplink

        systems = await uplink.get_systems()
        systems_config = self._config[CONF_SYSTEMS]

        for system in systems:
            system_config = systems_config.setdefault(str(system["systemId"]), {})

            units = await uplink.get_units(system["systemId"])
            units_configs = system_config.setdefault(CONF_UNITS, {})
            for unit in units:
                units_configs.setdefault(str(unit["systemUnitId"]), {})

            categories_schema = cv.multi_select(
                {str(unit["systemUnitId"]): unit["name"] for unit in units}
            )
            categories_selected = {
                unit_id
                for unit_id, unit_config in units_configs.items()
                if unit_config.get(CONF_CATEGORIES, False)
            }

            data = yield self.async_show_form(
                step_id="system",
                description_placeholders=system,
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CATEGORIES,
                            default=categories_selected,
                        ): categories_schema
                    }
                ),
            )

            for unit_id, units_config in units_configs.items():
                units_config[CONF_CATEGORIES] = unit_id in data[CONF_CATEGORIES]

        self.hass.config_entries.async_update_entry(self._entry, data=self._config)
        yield self.async_create_entry(title="", data={})


class NibeAuthView(HomeAssistantView):
    """Handle nibe  authentication callbacks."""

    url = AUTH_CALLBACK_URL
    name = AUTH_CALLBACK_NAME

    requires_auth = False

    def __init__(self) -> None:
        """Initialize instance of the view."""
        super().__init__()
        self._flows = {}  # type: Dict[str, str]

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
