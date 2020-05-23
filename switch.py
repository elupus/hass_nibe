"""Nibe Switch."""
import logging

from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchEntity
from homeassistant.exceptions import PlatformNotReady

from .const import CONF_SWITCHES, DATA_NIBE
from .entity import NibeParameterEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the device based on a config entry."""
    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE].uplink
    systems = hass.data[DATA_NIBE].systems

    entities = []
    for system in systems.values():
        for parameter_id in system.config[CONF_SWITCHES]:
            entities.append(NibeSwitch(uplink, system.system_id, parameter_id, entry))

    async_add_entities(entities, True)


class NibeSwitch(NibeParameterEntity, SwitchEntity):
    """Nibe Switch Entity."""

    def __init__(self, uplink, system_id, parameter_id, entry):
        """Init."""
        super(NibeSwitch, self).__init__(
            uplink, system_id, parameter_id, None, ENTITY_ID_FORMAT
        )

    @property
    def is_on(self):
        """Return if entity is on."""
        data = self._parameters[self._parameter_id]
        if data:
            return data["rawValue"] == "1"
        else:
            return None

    async def async_turn_on(self, **kwargs):
        """Turn entity on."""
        await self._uplink.put_parameter(self._system_id, self._parameter_id, "1")

    async def async_turn_off(self, **kwargs):
        """Turn entity off."""
        await self._uplink.put_parameter(self._system_id, self._parameter_id, "0")
