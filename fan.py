"""FAN for nibe."""

import asyncio
import logging
from typing import Dict, List, Optional, Union

from homeassistant.components.fan import (
    ENTITY_ID_FORMAT,
    SUPPORT_PRESET_MODE,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.exceptions import PlatformNotReady
from nibeuplink import Uplink, VentilationSystem, get_active_ventilations

from . import NibeSystem
from .const import DATA_NIBE
from .const import DOMAIN as DOMAIN_NIBE
from .entity import NibeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)
SPEED_AUTO = "auto"
SPEED_BOOST = "boost"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the climate device based on a config entry."""
    if DATA_NIBE not in hass.data:
        raise PlatformNotReady

    uplink = hass.data[DATA_NIBE].uplink  # type: Uplink
    systems = hass.data[DATA_NIBE].systems  # type: List[NibeSystem]

    entities = []

    async def add_active(system: NibeSystem):
        ventilations = await get_active_ventilations(uplink, system.system_id)
        for ventilation in ventilations.values():
            entities.append(NibeFan(uplink, system.system_id, ventilation))

    await asyncio.gather(*[add_active(system) for system in systems.values()])

    async_add_entities(entities, True)


class NibeFan(NibeEntity, FanEntity):
    """Nibe Sensor."""

    def __init__(self, uplink: Uplink, system_id: int, ventilation: VentilationSystem):
        """Init."""
        super().__init__(uplink, system_id)

        self._ventilation = ventilation
        self.entity_id = ENTITY_ID_FORMAT.format(
            "{}_{}_{}".format(DOMAIN_NIBE, system_id, str(ventilation.name).lower())
        )

        self.get_parameters(
            [
                ventilation.fan_speed,
                ventilation.ventilation_boost,
                ventilation.extract_air,
                ventilation.exhaust_speed_normal,
                ventilation.exhaust_air,
                ventilation.exhaust_speed_1,
                ventilation.exhaust_speed_2,
                ventilation.exhaust_speed_3,
                ventilation.exhaust_speed_4,
            ]
        )

    @property
    def name(self):
        """Return name of entity."""
        return self._ventilation.name

    @property
    def is_on(self):
        """Return true if the entity is on."""
        fan_speed = self.get_value(self._ventilation.fan_speed)
        if fan_speed:
            return True
        return False

    @property
    def percentage(self) -> Optional[int]:
        return self.get_float(self._ventilation.fan_speed)

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        boost = self.get_raw(self._ventilation.ventilation_boost)
        if boost:
            return SPEED_BOOST
        else:
            return SPEED_AUTO

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return [SPEED_AUTO, SPEED_BOOST]

    @property
    def state_attributes(self) -> dict:
        """Return optional state attributes.

        Overide base class state_attibutes to support device specific.
        """
        data = super().state_attributes
        data.update(self.device_state_attributes)
        return data

    @property
    def device_state_attributes(self) -> Dict[str, Optional[str]]:
        """Return extra state."""
        data = {}
        data["extract_air"] = self.get_value(self._ventilation.extract_air)
        data["exhaust_air"] = self.get_value(self._ventilation.exhaust_air)
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
        """Set the preset mode of the fan"""
        if preset_mode == SPEED_BOOST:
            value = 1
        else:
            value = 0

        await self._uplink.put_parameter(
            self._system_id,
            self._ventilation.ventilation_boost,
            value,
        )

    async def async_set_percentage(self, percentage: int) -> None:
        raise NotImplementedError("Can't set exact speed")

    @property
    def unique_id(self) -> str:
        """Return a unique identifier for a this parameter."""
        return "{}_{}".format(self._system_id, self._ventilation.fan_speed)

    @property
    def supported_features(self) -> Optional[int]:
        """Return supported features."""
        return SUPPORT_PRESET_MODE | SUPPORT_SET_SPEED
