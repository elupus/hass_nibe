"""Nibe uplink configuration."""
from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow

from . import NibeData
from .const import CONF_SYSTEMS, DATA_NIBE_ENTRIES, DOMAIN


class NibeConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Config flow for nibe uplink."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the Options Flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow."""

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
