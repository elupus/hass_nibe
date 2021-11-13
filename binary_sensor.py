"""Binary sensors for nibe uplink."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import ENTITY_ID_FORMAT, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from nibeuplink.typing import ParameterId

from . import NibeData, NibeSystem
from .const import CONF_BINARY_SENSORS, DATA_NIBE_ENTRIES
from .entity import NibeParameterEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]

    entities = []
    for system in data.systems.values():
        for parameter_id in system.config[CONF_BINARY_SENSORS]:
            entities.append(NibeBinarySensor(system, parameter_id))

    async_add_entities(entities, True)


class NibeBinarySensor(NibeParameterEntity, BinarySensorEntity):
    """Binary sensor."""

    def __init__(self, system: NibeSystem, parameter_id: ParameterId):
        """Init."""
        super().__init__(system, parameter_id, None, ENTITY_ID_FORMAT)

    @property
    def is_on(self):
        """Return if sensor is on."""
        data = self.get_parameter[self._parameter_id]
        if data:
            return data["rawValue"] == "1"
        else:
            return None
