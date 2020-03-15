"""FAN for nibe."""

import asyncio
import logging
from typing import List, Dict, Optional

from homeassistant.components.fan import ENTITY_ID_FORMAT, SUPPORT_SET_SPEED, FanEntity
from homeassistant.exceptions import PlatformNotReady

from nibeuplink import get_active_ventilations, VentilationSystem, Uplink

from . import NibeSystem
from .const import DATA_NIBE, DOMAIN as DOMAIN_NIBE
from .entity import NibeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)
SPEED_AUTO = "auto"
SPEED_BOOST = "boost"

NIBE_BOOST_TO_SPEED = {0: SPEED_AUTO, 1: SPEED_BOOST}
HA_SPEED_TO_NIBE = {v: k for k, v in NIBE_BOOST_TO_SPEED.items()}


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

    await asyncio.gather(
        *[add_active(system) for system in systems.values()]
    )

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
        return self.get_value(self._ventilation.fan_speed) is not None

    @property
    def state(self) -> str:
        """Return current fan state."""
        return self.get_value(self._ventilation.fan_speed)

    @property
    def speed(self) -> str:
        """Return the current speed."""
        boost = self.get_raw(self._ventilation.ventilation_boost)
        return NIBE_BOOST_TO_SPEED.get(boost, str(boost))

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        return list(NIBE_BOOST_TO_SPEED.values())

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
        data["fan_speed"] = self.get_value(self._ventilation.fan_speed)
        data["fan_speed_raw"] = self.get_raw(self._ventilation.fan_speed)
        data["extract_air"] = self.get_value(self._ventilation.extract_air)
        data["exhaust_air"] = self.get_value(self._ventilation.exhaust_air)
        data["ventilation_boost"] = self.get_value(self._ventilation.ventilation_boost)
        data["ventilation_boost_raw"] = self.get_raw(
            self._ventilation.ventilation_boost
        )
        return data

    # pylint: disable=arguments-differ
    async def async_turn_on(self, speed: str = None, **kwargs) -> None:
        """Turn on the fan."""
        await self.async_set_speed(speed or SPEED_AUTO)

    async def async_set_speed(self, speed: str) -> None:
        """Set the speed of the fan."""
        if speed in HA_SPEED_TO_NIBE and self._ventilation.ventilation_boost:
            await self._uplink.put_parameter(
                self._system_id,
                self._ventilation.ventilation_boost,
                HA_SPEED_TO_NIBE[speed],
            )
        else:
            _LOGGER.error("Unsupported speed %s", speed)
            raise NotImplementedError()

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_SET_SPEED

    @property
    def unique_id(self) -> str:
        """Return a unique identifier for a this parameter."""
        return "{}_{}".format(self._system_id, self._ventilation.fan_speed)
