"""Services for nibe uplink."""
import logging
import json

import voluptuous as vol

from homeassistant.helpers.event import async_call_later
import homeassistant.helpers.config_validation as cv
from homeassistant.const import ATTR_NAME, ATTR_TEMPERATURE

from .const import (
    ATTR_TARGET_TEMPERATURE,
    ATTR_VALVE_POSITION,
    DATA_NIBE,
    DOMAIN,
    SERVICE_SET_PARAMETER,
    SERVICE_SET_SMARTHOME_MODE,
    SERVICE_SET_THERMOSTAT,
    SERVICE_GET_PARAMETER,
)

_LOGGER = logging.getLogger(__name__)


def async_track_delta_time(hass, delta, callable):
    """
    Run callable cyclicly.

    Similar to async_track_time_interval, but where we
    instead guarantee delta between calls
    """
    remove = None
    skipped = False

    def skip():
        nonlocal skipped
        skipped = True

    async def fun(now):
        nonlocal remove
        remove = skip

        try:
            await callable()
        finally:
            if not skipped:
                remove = async_call_later(hass, delta, fun)

    def remover():
        remove()

    remove = async_call_later(hass, delta, fun)
    return remover


async def async_register_services(hass):
    """Register public services."""
    from nibeuplink import SMARTHOME_MODES, SetThermostatModel

    async def set_smarthome_mode(call):
        """Set smarthome mode."""
        uplink = hass.data[DATA_NIBE].uplink
        await uplink.put_smarthome_mode(call.data["system"], call.data["mode"])

    async def set_parameter(call):
        uplink = hass.data[DATA_NIBE].uplink
        await uplink.put_parameter(
            call.data["system"], call.data["parameter"], call.data["value"]
        )

    async def get_parameter(call):
        uplink = hass.data[DATA_NIBE].uplink
        data = await uplink.get_parameter(call.data["system"], call.data["parameter"])

        hass.components.persistent_notification.async_create(
            json.dumps(data, indent=1), "Nibe get parameter result"
        )

    async def set_thermostat(call):
        uplink = hass.data[DATA_NIBE].uplink

        def scaled(value, multi=10):
            if value is None:
                return None
            else:
                return round(value * multi)

        data = SetThermostatModel(
            externalId=call.data["id"],
            name=call.data[ATTR_NAME],
            actualTemp=scaled(call.data[ATTR_TEMPERATURE]),
            targetTemp=scaled(call.data[ATTR_TARGET_TEMPERATURE]),
            valvePosition=call.data[ATTR_VALVE_POSITION],
            climateSystems=call.data["systems"],
        )

        _LOGGER.debug("Publish thermostat {}".format(data))
        await uplink.post_smarthome_thermostats(call.data["system"], data)

    SERVICE_SET_SMARTHOME_MODE_SCHEMA = vol.Schema(
        {
            vol.Required("system"): cv.positive_int,
            vol.Required("mode"): vol.In(SMARTHOME_MODES.values()),
        }
    )

    SERVICE_SET_PARAMETER_SCHEMA = vol.Schema(
        {
            vol.Required("system"): cv.positive_int,
            vol.Required("parameter"): cv.string,
            vol.Required("value"): cv.string,
        }
    )

    SERVICE_GET_PARAMETER_SCHEMA = vol.Schema(
        {vol.Required("system"): cv.positive_int, vol.Required("parameter"): cv.string}
    )

    SERVICE_SET_THERMOSTAT_SCHEMA = vol.Schema(
        {
            vol.Required("system"): cv.positive_int,
            vol.Required("id"): cv.positive_int,
            vol.Required(ATTR_NAME): cv.string,
            vol.Required("systems"): cv.ensure_list,
            vol.Optional(ATTR_TEMPERATURE, default=None): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(ATTR_TARGET_TEMPERATURE, default=None): vol.Any(
                None, vol.Coerce(float)
            ),
            vol.Optional(ATTR_VALVE_POSITION, default=None): vol.Any(
                None, vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
            ),
        }
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SMARTHOME_MODE,
        set_smarthome_mode,
        SERVICE_SET_SMARTHOME_MODE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_PARAMETER, set_parameter, SERVICE_SET_PARAMETER_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, SERVICE_GET_PARAMETER, get_parameter, SERVICE_GET_PARAMETER_SCHEMA
    )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_THERMOSTAT, set_thermostat, SERVICE_SET_THERMOSTAT_SCHEMA
    )
