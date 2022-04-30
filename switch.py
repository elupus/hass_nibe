"""Nibe Switch."""
from __future__ import annotations

import logging

from homeassistant.components.switch import (
    ENTITY_ID_FORMAT,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from . import NibeData, NibeSystem
from .const import CONF_SWITCHES, DATA_NIBE_ENTRIES
from .entity import NibeParameterEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


PARAMETER_SWITCHES = [
    SwitchEntityDescription(
        key="48043", name="Vacation Mode", entity_category=EntityCategory.CONFIG
    )
]
PARAMETER_SWITCHES_IDS = {int(x.key) for x in PARAMETER_SWITCHES}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]

    entities = []
    for system in data.systems.values():
        for entity_description in PARAMETER_SWITCHES:
            entities.append(
                NibeSwitch(system, int(entity_description.key), entity_description)
            )

        parameters = set(system.config[CONF_SWITCHES]) - PARAMETER_SWITCHES_IDS
        for parameter_id in parameters:
            entities.append(NibeSwitch(system, parameter_id))

    async_add_entities(entities, True)


class NibeSwitch(NibeParameterEntity, SwitchEntity):
    """Nibe Switch Entity."""

    def __init__(
        self,
        system: NibeSystem,
        parameter_id,
        entity_description: SwitchEntityDescription | None = None,
    ):
        """Init."""
        super().__init__(system, parameter_id, ENTITY_ID_FORMAT)
        if entity_description:
            self.entity_description = entity_description

    @property
    def is_on(self):
        """Return if entity is on."""
        if (data := self.get_raw(self._parameter_id)) is not None:
            return data == "1"
        else:
            return None

    async def async_turn_on(self, **kwargs):
        """Turn entity on."""
        await self._uplink.put_parameter(self._system_id, self._parameter_id, "1")

    async def async_turn_off(self, **kwargs):
        """Turn entity off."""
        await self._uplink.put_parameter(self._system_id, self._parameter_id, "0")
