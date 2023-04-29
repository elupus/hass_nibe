"""FAN for nibe."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.fan import ENTITY_ID_FORMAT, FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from nibeuplink import VentilationSystem, get_active_ventilations

from . import NibeData, NibeSystem
from .const import DATA_NIBE_ENTRIES
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)
PRESET_VALUES = {
    "Normal": 0,
    "Speed 1": 1,
    "Speed 2": 2,
    "Speed 3": 3,
    "Speed 4": 4
}
PRESET_NAMES = list(PRESET_VALUES.keys())


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the climate device based on a config entry."""
    data: NibeData = hass.data[DATA_NIBE_ENTRIES][entry.entry_id]
    uplink = data.uplink
    systems = data.systems

    entities = []

    async def add_active(system: NibeSystem):
        ventilations = await get_active_ventilations(uplink, system.system_id)
        for ventilation in ventilations.values():
            entities.append(NibeFan(system, ventilation))

    await asyncio.gather(*[add_active(system) for system in systems.values()])

    async_add_entities(entities, True)


class NibeFan(NibeEntity, FanEntity):
    """Nibe Sensor."""

    def __init__(self, system: NibeSystem, ventilation: VentilationSystem):
        """Init."""
        parameters = {
            ventilation.fan_speed,
            ventilation.ventilation_boost,
            ventilation.extract_air,
            ventilation.exhaust_speed_normal,
            ventilation.exhaust_air,
            ventilation.exhaust_speed_1,
            ventilation.exhaust_speed_2,
            ventilation.exhaust_speed_3,
            ventilation.exhaust_speed_4,
        }
        super().__init__(system, parameters)

        self._ventilation = ventilation
        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}_{}".format(
                DOMAIN_NIBE, system.system_id, str(ventilation.name).lower()
            )
        )
        self._attr_name = ventilation.name
        self._attr_unique_id = f"{system.system_id}_{ventilation.fan_speed}"

    @property
    def is_on(self):
        """Return true if the entity is on."""
        fan_speed = self.get_value(self._ventilation.fan_speed)
        if fan_speed:
            return True
        return False

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return PRESET_NAMES[self.get_raw(self._ventilation.ventilation_boost)]

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return PRESET_NAMES

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return extra state."""
        data = {}
        data["extract_air"] = self.get_value(self._ventilation.extract_air)
        data["exhaust_air"] = self.get_value(self._ventilation.exhaust_air)
        data["fan_speed"] = self.get_raw(self._ventilation.fan_speed)
        data["ventilation_boost"] = self.get_value(self._ventilation.ventilation_boost)
        data["ventilation_boost_raw"] = self.get_raw(
            self._ventilation.ventilation_boost
        )
        return data

    # pylint: disable=arguments-differ
    async def async_turn_on(self, preset: str = None, **kwargs) -> None:
        """Turn on the fan."""
        if preset:
            await self.async_set_preset_mode(preset)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        assert self._ventilation.ventilation_boost, "Ventilation boost not supported"
        await self._uplink.put_parameter(
            self._system_id,
            self._ventilation.ventilation_boost,
            PRESET_VALUES[preset_mode],
        )

    @property
    def unique_id(self) -> str:
        """Return a unique identifier for a this parameter."""
        return f"{self._system_id}_{self._ventilation.fan_speed}"

    @property
    def supported_features(self) -> int | None:
        """Return supported features."""
        return FanEntityFeature.PRESET_MODE
